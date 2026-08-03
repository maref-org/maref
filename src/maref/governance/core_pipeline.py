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
        policy_rules: list[tuple[int, Callable[[GovernanceRequest], tuple[Verdict, str, HITLTier | None]]]] | None = None,
        boundary: Any | None = None,
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

    @staticmethod
    def _default_policy_rules() -> list[tuple[int, Callable[[GovernanceRequest], tuple[Verdict, str, HITLTier | None]]]]:
        """Default policy rules, highest priority first."""

        from maref.integration.hitl import HITLTier as _HITLTier

        def p0_dangerous_actions(req: GovernanceRequest) -> tuple[Verdict, str, HITLTier | None]:
            dangerous = {"file.delete", "shell.exec", "system.shutdown", "registry.modify"}
            if req.action in dangerous:
                if req.trust_score < 70:
                    return Verdict.ASK_USER, "Dangerous action requires approval", _HITLTier.P0_RESPONSE
                return Verdict.ALLOW, "Dangerous action allowed for trusted agent", None
            return Verdict.ALLOW, "", None

        def p0_git_push(req: GovernanceRequest) -> tuple[Verdict, str, HITLTier | None]:
            if req.action == "git.push":
                return Verdict.ASK_USER, "git.push requires human approval", _HITLTier.P0_RESPONSE
            return Verdict.ALLOW, "", None

        def p1_git_commit(req: GovernanceRequest) -> tuple[Verdict, str, HITLTier | None]:
            if req.action == "git.commit":
                if req.trust_score < 80:
                    return Verdict.ASK_USER, "git.commit requires approval for untrusted agents", _HITLTier.P1_ESCALATE
                return Verdict.ALLOW, "git.commit allowed for trusted agent", None
            return Verdict.ALLOW, "", None

        def p1_recursion_depth(req: GovernanceRequest) -> tuple[Verdict, str, HITLTier | None]:
            if req.recursion_depth > 2:
                return Verdict.ASK_USER, f"High recursion depth ({req.recursion_depth})", _HITLTier.P1_ESCALATE
            return Verdict.ALLOW, "", None

        def p2_low_trust(req: GovernanceRequest) -> tuple[Verdict, str, HITLTier | None]:
            if req.trust_score < 30:
                return Verdict.DENY, f"Trust score too low ({req.trust_score:.0f})", _HITLTier.P2_LOG
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
                self._trust_callback(req.tenant_id, req.agent_id, min(100.0, req.trust_score + 0.5), "pipeline:allow")
            elif verdict == Verdict.DENY:
                self._trust_callback(req.tenant_id, req.agent_id, max(0.0, req.trust_score - 1.0), "pipeline:deny")

        # 8. Circuit breaker record
        if self._cb_record_callback:
            self._cb_record_callback(req.tenant_id, req.agent_id, req.action, verdict == Verdict.ALLOW)

        result.latency_ms = int((time.time() - start) * 1000)
        return result

    @property
    def hitl(self) -> HITLRouter:
        return self._hitl

    @property
    def permission(self) -> PermissionMatrix:
        return self._permission
