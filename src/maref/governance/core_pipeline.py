"""Unified Governance Pipeline — shared core for GaaS REST and MCP protocol paths.

Replaces the previous dual-pipeline architecture where GovernanceRouter (GaaS)
and MCPGovernance (MCP) each had independent implementations. Now both delegate
to this single GovernancePipeline, ensuring consistent policy enforcement
regardless of entry point.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from maref.recursive.permission_matrix import PermissionMatrix

if TYPE_CHECKING:
    from maref.integration.hitl import HITLRouter, HITLTier


class Verdict(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    ASK_USER = "ASK_USER"
    DEFER = "DEFER"


def _infer_category(action: str) -> Any:
    """从动作标识推断 ActionCategory (供链级追踪; 保守映射到 OTHER)。"""
    try:
        from maref.governance.intent.chain_tracker import ActionCategory

        a = action.lower()
        if any(k in a for k in ("create", "register", "attach")):
            return ActionCategory.CREATE
        if any(k in a for k in ("read", "query", "list", "fetch", "search")):
            return ActionCategory.READ
        if any(k in a for k in ("edit", "update", "modify", "inject", "history")):
            return ActionCategory.UPDATE
        if any(k in a for k in ("delete", "drop", "remove", "clear", "trace")):
            return ActionCategory.DELETE
        if any(k in a for k in ("send", "message", "email", "comment", "thank")):
            return ActionCategory.COMMUNICATE
        if any(k in a for k in ("submit", "pull_request", "push", "commit", "release", "deploy")):
            return ActionCategory.EXTERNAL
        if any(k in a for k in ("credential", "password", "token", "secret")):
            return ActionCategory.CREDENTIAL
        if any(
            k in a
            for k in (
                "identity",
                "account",
                "role",
                "rotate",
                "switch",
                "reuse",
                "review",
                "approve",
                "endorse",
            )
        ):
            return ActionCategory.IDENTITY
        if any(k in a for k in ("network", "proxy", "tor", "connect", "egress")):
            return ActionCategory.NETWORK
        if any(k in a for k in ("exec", "run", "shell", "bash", "code")):
            return ActionCategory.EXECUTE
        return ActionCategory.OTHER
    except Exception:
        from maref.governance.intent.chain_tracker import ActionCategory

        return ActionCategory.OTHER


def _risk_level_of(verdict: Verdict) -> Any:
    """将单步裁决映射为链级单步风险。"""
    try:
        from maref.governance.intent.chain_tracker import ChainRiskLevel

        if verdict == Verdict.DENY:
            return ChainRiskLevel.HIGH
        if verdict == Verdict.ASK_USER:
            return ChainRiskLevel.MEDIUM
        return ChainRiskLevel.LOW
    except Exception:
        return "LOW"


@dataclass
class GovernanceRequest:
    """Universal governance request — used by GaaS, MCP, and future peers."""

    action: str
    agent_id: str
    tenant_id: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    recursion_depth: int = 0
    trust_score: float = 50.0
    role: str = "坎"
    session_id: str = ""
    source_ip: str = ""
    delegations: list[str] = field(default_factory=list)


@dataclass
class GovernanceResult:
    """Universal governance result — verdict with full audit metadata."""

    verdict: Verdict
    reason: str = ""
    hitl_tier: HITLTier | None = None
    hitl_event_id: str = ""
    matched_rule: str = ""
    risk_score: float = 0.0
    latency_ms: int = 0


class GovernancePipeline:
    """Unified governance pipeline — single code path for ALL governance decisions.

    8-step pipeline:
      1. Circuit breaker depth check (recursion / delegation depth)
      2. Permission matrix check (role-based tool access)
      3. Circuit breaker failure monitor
      4. Policy rule evaluation (action × trust × context)
      5. HITL routing (if verdict is ASK_USER)
      6. Audit logging
      7. Trust score update
      8. Circuit breaker success/failure record

    Both GovernanceRouter (GaaS) and MCPGovernance (MCP) delegate to this class.
    """

    def __init__(
        self,
        hitl: HITLRouter | None = None,
        permission: PermissionMatrix | None = None,
        audit_callback: Callable[[GovernanceRequest, GovernanceResult], None] | None = None,
        trust_callback: Callable[[str, str, float, str], None] | None = None,
        cb_check_callback: Callable[[str, str, str, int], bool] | None = None,
        cb_record_callback: Callable[[str, str, str, bool], None] | None = None,
        policy_rules: list[
            tuple[int, Callable[[GovernanceRequest], tuple[Verdict, str, HITLTier | None]]]
        ]
        | None = None,
        boundary: Any | None = None,
        # v0.52.1 G2: 可选动作链意图推理挂接 (C7)。注入后 govern 会在动作
        # 记录后追加链级评估; 未注入则行为完全不变 (向后兼容)。
        intent_tracker: Any | None = None,
        intent_gate: Any | None = None,
        # v0.53 S7: 可选预算熔断器 / 破坏性操作门。注入后 govern 在
        # TrustBoundary 之后追加预算超限 DENY 与破坏性操作 HITL 升级;
        # 未注入则行为完全不变 (向后兼容)。
        budget_breaker: Any | None = None,
        destructive_gate: Any | None = None,
    ):
        from maref.integration.hitl import HITLRouter as _HITLRouter

        self._hitl = hitl or _HITLRouter()
        self._permission = permission or PermissionMatrix()
        self._audit_callback = audit_callback
        self._trust_callback = trust_callback
        self._cb_check_callback = cb_check_callback
        self._cb_record_callback = cb_record_callback
        self._policy_rules = policy_rules or self._default_policy_rules()
        # TrustBoundaryManager (v0.47 S9): mandatory pre-action boundary gate.
        # Injected via duck typing so core_pipeline does not hard-depend on
        # maref.governance.trust_boundary.
        self._boundary = boundary
        self._intent_tracker = intent_tracker
        self._intent_gate = intent_gate
        self._budget_breaker = budget_breaker
        self._destructive_gate = destructive_gate

    @staticmethod
    def _default_policy_rules() -> list[
        tuple[int, Callable[[GovernanceRequest], tuple[Verdict, str, HITLTier | None]]]
    ]:
        """Default policy rules, highest priority first."""

        from maref.integration.hitl import HITLTier as _HITLTier

        def p0_dangerous_actions(req: GovernanceRequest) -> tuple[Verdict, str, HITLTier | None]:
            dangerous = {"file.delete", "shell.exec", "system.shutdown", "registry.modify"}
            if req.action in dangerous:
                if req.trust_score < 70:
                    return (
                        Verdict.ASK_USER,
                        "Dangerous action requires approval",
                        _HITLTier.P0_RESPONSE,
                    )
                return Verdict.ALLOW, "Dangerous action allowed for trusted agent", None
            return Verdict.ALLOW, "", None

        def p0_git_push(req: GovernanceRequest) -> tuple[Verdict, str, HITLTier | None]:
            if req.action == "git.push":
                return Verdict.ASK_USER, "git.push requires human approval", _HITLTier.P0_RESPONSE
            return Verdict.ALLOW, "", None

        def p1_git_commit(req: GovernanceRequest) -> tuple[Verdict, str, HITLTier | None]:
            if req.action == "git.commit":
                if req.trust_score < 80:
                    return (
                        Verdict.ASK_USER,
                        "git.commit requires approval for untrusted agents",
                        _HITLTier.P1_ESCALATE,
                    )
                return Verdict.ALLOW, "git.commit allowed for trusted agent", None
            return Verdict.ALLOW, "", None

        def p1_recursion_depth(req: GovernanceRequest) -> tuple[Verdict, str, HITLTier | None]:
            if req.recursion_depth > 2:
                return (
                    Verdict.ASK_USER,
                    f"High recursion depth ({req.recursion_depth})",
                    _HITLTier.P1_ESCALATE,
                )
            return Verdict.ALLOW, "", None

        def p2_low_trust(req: GovernanceRequest) -> tuple[Verdict, str, HITLTier | None]:
            if req.trust_score < 30:
                return (
                    Verdict.DENY,
                    f"Trust score too low ({req.trust_score:.0f})",
                    _HITLTier.P2_LOG,
                )
            return Verdict.ALLOW, "", None

        def p3_default_allow(req: GovernanceRequest) -> tuple[Verdict, str, HITLTier | None]:
            return Verdict.ALLOW, "Default allow", None

        return [
            (100, p0_dangerous_actions),
            (90, p0_git_push),
            (80, p1_git_commit),
            (70, p1_recursion_depth),
            (60, p2_low_trust),
            (0, p3_default_allow),
        ]

    def govern(self, req: GovernanceRequest) -> GovernanceResult:
        """Execute the unified 8-step governance pipeline."""
        start = time.time()

        # 0. TrustBoundaryManager gate (v0.47 S9): mandatory pre-action
        # boundary check before any other rule.  Out-of-bounds → DENY
        # (E1006 semantics surfaced as Verdict.DENY / trust_boundary).
        if self._boundary is not None:
            try:
                boundary_decision = self._boundary.check_no_raise(
                    action=req.action,
                    agent_id=req.agent_id,
                    metadata=req.parameters,
                )
            except Exception:
                boundary_decision = None
            if boundary_decision is not None and not boundary_decision.allowed:
                result = GovernanceResult(
                    verdict=Verdict.DENY,
                    reason=f"TrustBoundary 阻断越界动作: {boundary_decision.reason}",
                    matched_rule="trust_boundary",
                )
                result.latency_ms = int((time.time() - start) * 1000)
                if self._audit_callback:
                    self._audit_callback(req, result)
                if self._cb_record_callback:
                    self._cb_record_callback(req.tenant_id, req.agent_id, req.action, False)
                return result

            # P0-2: IRREVERSIBLE 动作即使授权放行，仍升级真实 HITL（人工确认）。
            # 替换"仅返回 action_required=HITL 字符串"的空转——此处真正发起审批事件。
            if (
                boundary_decision is not None
                and boundary_decision.allowed
                and getattr(boundary_decision, "consensus_required", False)
            ):
                from maref.integration.hitl import HITLTier as _HITLTier

                hitl_event = self._hitl.request(
                    tenant_id=req.tenant_id or "default",
                    agent_id=req.agent_id,
                    action=req.action,
                    description=f"IRREVERSIBLE 动作需人工确认: {req.action}",
                    parameters=req.parameters,
                    tier=_HITLTier.P0_RESPONSE,
                )
                result = GovernanceResult(
                    verdict=Verdict.ASK_USER,
                    reason=f"IRREVERSIBLE 动作 {req.action} 升级人工审批",
                    hitl_tier=_HITLTier.P0_RESPONSE,
                    hitl_event_id=hitl_event.event_id,
                    matched_rule="irreversible_hitl",
                )
                result.latency_ms = int((time.time() - start) * 1000)
                if self._audit_callback:
                    self._audit_callback(req, result)
                if self._trust_callback:
                    self._trust_callback(
                        req.tenant_id,
                        req.agent_id,
                        max(0.0, req.trust_score - 0.5),
                        "pipeline:irreversible_hitl",
                    )
                return result

        # 0.5. v0.53 S7: 预算熔断器 — agent 预算超限直接 DENY。
        # I2: 直接调用 check_agent_budget（其内部处理 OPEN→HALF_OPEN 探针与
        # CLOSED 检查），避免 `is_open is False` 短路使恢复逻辑成为死代码。
        # I3: 熔断器异常时 fail-closed（无法确认预算安全 → 拒绝并审计）。
        if self._budget_breaker is not None:
            try:
                budget_ok = self._budget_breaker.check_agent_budget(
                    req.agent_id,
                    self._budget_breaker.get_agent_spend(req.agent_id),
                )
            except Exception:
                budget_ok = False
            if not budget_ok:
                result = GovernanceResult(
                    verdict=Verdict.DENY,
                    reason=f"Budget breaker open for agent '{req.agent_id}'",
                    matched_rule="budget_breaker",
                )
                result.latency_ms = int((time.time() - start) * 1000)
                if self._audit_callback:
                    self._audit_callback(req, result)
                if self._cb_record_callback:
                    self._cb_record_callback(req.tenant_id, req.agent_id, req.action, False)
                return result

        # 0.6. v0.53 S7: 破坏性操作门 — 命中破坏性模式时升级 HITL。
        if self._destructive_gate is not None and self._destructive_gate.enabled:
            try:
                gate_decision = self._destructive_gate.evaluate(
                    operation=req.action,
                    tool_name=req.action.split(".")[0],
                    args=req.parameters,
                    agent_id=req.agent_id,
                )
            except Exception:
                # I3: 门自身异常时 fail-closed — 无法确认操作安全性则拒绝。
                gate_decision = None
                gate_error = True
            else:
                gate_error = False
            if gate_error:
                result = GovernanceResult(
                    verdict=Verdict.DENY,
                    reason="Destructive gate evaluation error (fail-closed)",
                    matched_rule="destructive_gate_error",
                )
                result.latency_ms = int((time.time() - start) * 1000)
                if self._audit_callback:
                    self._audit_callback(req, result)
                if self._cb_record_callback:
                    self._cb_record_callback(req.tenant_id, req.agent_id, req.action, False)
                return result
            if gate_decision is not None:
                from maref.governance.destructive_gate import GateVerdict

                if gate_decision.verdict == GateVerdict.BLOCK:
                    result = GovernanceResult(
                        verdict=Verdict.DENY,
                        reason=f"Destructive gate BLOCK: {gate_decision.reason}",
                        matched_rule="destructive_gate",
                    )
                    result.latency_ms = int((time.time() - start) * 1000)
                    if self._audit_callback:
                        self._audit_callback(req, result)
                    if self._cb_record_callback:
                        self._cb_record_callback(req.tenant_id, req.agent_id, req.action, False)
                    return result
                if gate_decision.verdict == GateVerdict.HITL_REQUIRED:
                    from maref.integration.hitl import HITLTier as _HITLTier

                    hitl_event = self._hitl.request(
                        tenant_id=req.tenant_id or "default",
                        agent_id=req.agent_id,
                        action=req.action,
                        description=f"破坏性操作需人工确认: {gate_decision.reason}",
                        parameters=req.parameters,
                        tier=_HITLTier.P0_RESPONSE,
                    )
                    result = GovernanceResult(
                        verdict=Verdict.ASK_USER,
                        reason=f"破坏性操作升级人工审批: {gate_decision.reason}",
                        hitl_tier=_HITLTier.P0_RESPONSE,
                        hitl_event_id=hitl_event.event_id,
                        matched_rule="destructive_gate_hitl",
                    )
                    result.latency_ms = int((time.time() - start) * 1000)
                    if self._audit_callback:
                        self._audit_callback(req, result)
                    if self._cb_record_callback:
                        self._cb_record_callback(req.tenant_id, req.agent_id, req.action, False)
                    return result

        # 1. Circuit breaker depth check
        if self._cb_check_callback:
            allowed = self._cb_check_callback(
                req.tenant_id, req.agent_id, req.action, req.recursion_depth
            )
            if not allowed:
                result = GovernanceResult(
                    verdict=Verdict.DENY,
                    reason="Circuit breaker open",
                    matched_rule="circuit_breaker_depth",
                )
                result.latency_ms = int((time.time() - start) * 1000)
                if self._cb_record_callback:
                    self._cb_record_callback(req.tenant_id, req.agent_id, req.action, False)
                return result

        # 2. Permission matrix check (role-based)
        if req.role:
            pm_ok = self._permission.check(req.role, req.action)
            if not pm_ok:
                result = GovernanceResult(
                    verdict=Verdict.DENY,
                    reason=f"Permission denied for role '{req.role}' on '{req.action}'",
                    matched_rule="permission_matrix",
                )
                result.latency_ms = int((time.time() - start) * 1000)
                return result

        # 3-4. Policy rule evaluation (sorted by priority, highest first)
        verdict: Verdict | None = None
        reason = ""
        hitl_tier: HITLTier | None = None
        matched_rule = ""

        for priority, rule_fn in sorted(self._policy_rules, key=lambda x: x[0], reverse=True):
            v, r, h = rule_fn(req)
            if v == Verdict.DENY or v == Verdict.ASK_USER:
                matched_rule = f"rule_p{priority}"
                verdict, reason, hitl_tier = v, r, h
                break
            if v == Verdict.ALLOW and not reason:
                verdict, reason = v, r

        if verdict is None:
            verdict = Verdict.DENY
            reason = "No matching policy"

        # 5. HITL routing
        hitl_event_id = ""
        if verdict == Verdict.ASK_USER and hitl_tier:
            event = self._hitl.request(
                tenant_id=req.tenant_id or "default",
                agent_id=req.agent_id,
                action=req.action,
                description=reason,
                parameters=req.parameters,
                tier=hitl_tier,
            )
            hitl_event_id = event.event_id

        # 5.5 v0.52.1 G2-C7: 链级意图评估。
        # 在审计/信任副作用 (step 6-8) 之前执行, 使链级 HALT/ESCALATE 覆盖的
        # 裁决能被审计/信任正确反映 (G2-3 修复); escalate 在此发起真实 HITL
        # 审批事件 (G2-2 修复)。
        if self._intent_tracker is not None and self._intent_gate is not None:
            try:
                from maref.governance.intent.chain_tracker import (
                    ActionRecord,
                )

                tracker = self._intent_tracker
                cat = _infer_category(req.action)
                tracker.record(
                    ActionRecord(
                        action=req.action,
                        agent_id=req.agent_id,
                        category=cat,
                        risk_level=_risk_level_of(verdict),
                        subject=str(req.parameters.get("subject", "")),
                        outcome="denied" if verdict == Verdict.DENY else "success",
                        metadata={"tenant_id": req.tenant_id, **req.parameters},
                    )
                )
                chain_verdict = self._intent_gate.evaluate_agent(tracker, req.agent_id)
                if chain_verdict.decision.value == "halt":
                    verdict, reason = Verdict.DENY, f"链级意图熔断: {chain_verdict.reason}"
                    matched_rule = "intent_chain_halt"
                elif chain_verdict.decision.value == "escalate":
                    verdict, reason = Verdict.ASK_USER, f"链级意图升级: {chain_verdict.reason}"
                    matched_rule = "intent_chain_escalate"
                    if hitl_tier is None:
                        from maref.integration.hitl import HITLTier as _HITLTier

                        hitl_tier = _HITLTier.P1_ESCALATE
            except Exception as _intent_exc:  # noqa: BLE001
                # 链级评估失败不阻断主流程 (fail-open 保活, 但已记录审计)
                import logging as _logging

                _logging.getLogger(__name__).debug("intent chain eval failed: %s", _intent_exc)
                pass

            # 链级覆盖后重新发起 HITL 审批 (escalate 场景; G2-2 修复)
            if verdict == Verdict.ASK_USER and hitl_tier:
                event = self._hitl.request(
                    tenant_id=req.tenant_id or "default",
                    agent_id=req.agent_id,
                    action=req.action,
                    description=reason,
                    parameters=req.parameters,
                    tier=hitl_tier,
                )
                hitl_event_id = event.event_id

        result = GovernanceResult(
            verdict=verdict,
            reason=reason,
            hitl_tier=hitl_tier if verdict == Verdict.ASK_USER else None,
            hitl_event_id=hitl_event_id,
            matched_rule=matched_rule,
        )

        # 6. Audit callback
        if self._audit_callback:
            self._audit_callback(req, result)

        # 7. Trust score update
        if self._trust_callback:
            if verdict == Verdict.ALLOW:
                self._trust_callback(
                    req.tenant_id, req.agent_id, min(100.0, req.trust_score + 0.5), "pipeline:allow"
                )
            elif verdict == Verdict.DENY:
                self._trust_callback(
                    req.tenant_id, req.agent_id, max(0.0, req.trust_score - 1.0), "pipeline:deny"
                )

        # 8. Circuit breaker record
        if self._cb_record_callback:
            self._cb_record_callback(
                req.tenant_id, req.agent_id, req.action, verdict == Verdict.ALLOW
            )

        result.latency_ms = int((time.time() - start) * 1000)
        return result

    @property
    def hitl(self) -> HITLRouter:
        return self._hitl

    @property
    def permission(self) -> PermissionMatrix:
        return self._permission
