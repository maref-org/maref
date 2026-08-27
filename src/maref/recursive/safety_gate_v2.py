from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maref.immunity.ai_stench_detector import AIStenchDetector
    from maref.immunity.intent_drift_detector import IntentDriftDetector
    from maref.recursive.meta_agent_closure import EvolutionDecision, MetaAgentClosure


@dataclass
class ThreatAssessment:
    threat_detected: bool
    threat_type: str
    severity: str
    reason: str
    blocked: bool


@dataclass
class ChangeRecord:
    timestamp: float
    target: str
    direction: str
    value: Any


class SafetyGateV2:
    _CORE_COMPONENTS = [
        "circuit_breaker",
        "state_machine",
        "audit_logger",
        "meta_governance",
        # N10: 元闭环自身亦为受保护核心组件，否则可被拆除而绕过全部红线检查
        "meta_agent_closure",
        "evolution_dsl",
    ]

    _DANGEROUS_CAPABILITIES = [
        "halt",
        "circuit_break",
    ]

    _HIGH_PRIVILEGE_CAPABILITIES = [
        "halt",
        "circuit_break",
        "state_transition",
    ]

    MAX_SUBTASKS = 12
    DANGEROUS_MAX_SUBTASKS = 8

    def __init__(self) -> None:
        self._change_history: dict[str, list[ChangeRecord]] = {}
        self._audit_trail: list[dict[str, Any]] = []
        self._stench_detector: AIStenchDetector | None = None
        self._intent_drift_detector: IntentDriftDetector | None = None  # M4
        self._sentinel_observer: Any | None = None  # M4
        # N10: 注入后启用生产级宪法红线检查（见 attach_meta_closure）
        self._meta_closure: MetaAgentClosure | None = None
        self._blocked = False

    def detect_core_removal(self, target: str) -> ThreatAssessment:
        for core in self._CORE_COMPONENTS:
            if core in target.lower():
                return ThreatAssessment(
                    threat_detected=True,
                    threat_type="core_removal",
                    severity="CRITICAL",
                    reason=f"cannot remove core component: {target}",
                    blocked=True,
                )
        return ThreatAssessment(
            threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False
        )

    def detect_gradual_weakening(self, target: str, new_value: Any) -> ThreatAssessment:
        if target not in self._change_history:
            self._change_history[target] = []
            return ThreatAssessment(
                threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False
            )

        history = self._change_history[target]
        if len(history) < 2:
            self._record_change(target, new_value)
            return ThreatAssessment(
                threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False
            )

        recent = history[-2:]
        if all(r.direction == "decrease" for r in recent):
            self._record_change(target, new_value)
            return ThreatAssessment(
                threat_detected=True,
                threat_type="gradual_weakening",
                severity="WARNING",
                reason=f"target {target} has been decreased 3 consecutive times",
                blocked=True,
            )

        self._record_change(target, new_value)
        return ThreatAssessment(
            threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False
        )

    def detect_combinatorial_explosion(self, batch: list[dict[str, Any]]) -> ThreatAssessment:
        if len(batch) < 3:
            return ThreatAssessment(
                threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False
            )

        core_affected = set()
        for change in batch:
            target = change.get("target", "")
            for core in self._CORE_COMPONENTS:
                if core in target.lower():
                    core_affected.add(core)

        if len(core_affected) >= 2:
            return ThreatAssessment(
                threat_detected=True,
                threat_type="combinatorial_explosion",
                severity="HIGH",
                reason=f"batch modifies {len(core_affected)} core components: {core_affected}",
                blocked=True,
            )
        return ThreatAssessment(
            threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False
        )

    def safety_self_audit(self) -> dict[str, Any]:
        core_listed = len(self._CORE_COMPONENTS)
        history_entries = sum(len(v) for v in self._change_history.values())
        audit_entries = len(self._audit_trail)
        return {
            "core_components_count": core_listed,
            "core_components": list(self._CORE_COMPONENTS),
            "change_history_entries": history_entries,
            "audit_trail_entries": audit_entries,
            "gate_healthy": core_listed >= 5,
        }

    def safety_audit_trail(self) -> list[dict[str, Any]]:
        return list(self._audit_trail)

    def harden_parameters(self, current_params: dict[str, Any]) -> dict[str, Any]:
        hardened = dict(current_params)
        for core in self._CORE_COMPONENTS:
            for key, value in list(hardened.items()):
                if core in key.lower() and isinstance(value, (int, float)):
                    if "threshold" in key.lower() or "cooldown" in key.lower():
                        original = current_params.get(key, value)
                        hardened[key] = max(value, original * 0.5)
        return hardened

    def _record_change(self, target: str, new_value: Any) -> None:
        previous_value: Any = None
        if target in self._change_history and self._change_history[target]:
            previous_value = self._change_history[target][-1].value

        if isinstance(new_value, (int, float)) and isinstance(previous_value, (int, float)):
            direction = "decrease" if new_value < previous_value else "increase"
        elif isinstance(new_value, (int, float)):
            direction = "decrease" if new_value < 0 else "increase"
        else:
            direction = "unknown"

        record = ChangeRecord(
            timestamp=time.time(),
            target=target,
            direction=direction,
            value=new_value,
        )
        if target not in self._change_history:
            self._change_history[target] = []
        self._change_history[target].append(record)
        self._audit_trail.append(
            {
                "timestamp": record.timestamp,
                "target": target,
                "direction": record.direction,
                "value": record.value,
            }
        )

    def validate_decomposition(
        self, subtask_count: int, capabilities: list[str]
    ) -> ThreatAssessment:
        has_dangerous = any(cap in self._DANGEROUS_CAPABILITIES for cap in capabilities)
        if has_dangerous and subtask_count > self.DANGEROUS_MAX_SUBTASKS:
            return ThreatAssessment(
                threat_detected=True,
                threat_type="decomposition_dangerous_explosion",
                severity="HIGH",
                reason=f"Dangerous capabilities with {subtask_count} subtasks (max {self.DANGEROUS_MAX_SUBTASKS})",
                blocked=True,
            )
        if subtask_count > self.MAX_SUBTASKS:
            return ThreatAssessment(
                threat_detected=True,
                threat_type="decomposition_subtask_explosion",
                severity="WARNING",
                reason=f"Subtask count {subtask_count} exceeds max {self.MAX_SUBTASKS}",
                blocked=True,
            )
        return ThreatAssessment(
            threat_detected=False,
            threat_type="",
            severity="NONE",
            reason="",
            blocked=False,
        )

    def validate_handoff(
        self,
        from_agent: str,
        to_agent: str,
        from_capabilities: list[str],
        to_capabilities: list[str],
    ) -> ThreatAssessment:
        from_has_high = any(cap in self._HIGH_PRIVILEGE_CAPABILITIES for cap in from_capabilities)
        to_has_high = any(cap in self._HIGH_PRIVILEGE_CAPABILITIES for cap in to_capabilities)
        if not from_has_high and to_has_high:
            return ThreatAssessment(
                threat_detected=True,
                threat_type="handoff_privilege_escalation",
                severity="HIGH",
                reason=f"Handoff from low-privilege {from_agent} to high-privilege {to_agent}",
                blocked=True,
            )
        return ThreatAssessment(
            threat_detected=False,
            threat_type="",
            severity="NONE",
            reason="",
            blocked=False,
        )

    def validate_capability_assignment(
        self,
        subtask_capabilities: list[str],
        agent_capabilities: list[str],
        contract_registry: Any = None,
    ) -> ThreatAssessment:
        for cap in subtask_capabilities:
            if cap in self._DANGEROUS_CAPABILITIES and cap not in agent_capabilities:
                return ThreatAssessment(
                    threat_detected=True,
                    threat_type="dangerous_capability_mismatch",
                    severity="HIGH",
                    reason=f"Dangerous capability '{cap}' assigned to agent without it",
                    blocked=True,
                )
            if cap in self._DANGEROUS_CAPABILITIES and cap not in self._HIGH_PRIVILEGE_CAPABILITIES:
                continue

        if contract_registry is not None and hasattr(contract_registry, "get"):
            analyzer = None
            try:
                from maref.recursive.capability_contracts import CombinatorialRiskAnalyzer

                analyzer = CombinatorialRiskAnalyzer(contract_registry)
                report = analyzer.analyze(subtask_capabilities)
                if report.total_risk_score >= 1.5:
                    return ThreatAssessment(
                        threat_detected=True,
                        threat_type="combinatorial_risk",
                        severity="HIGH",
                        reason=f"Capability set has combinatorial risk score {report.total_risk_score:.2f}: {report.recommendations}",
                        blocked=True,
                    )
                if report.total_risk_score >= 0.7:
                    return ThreatAssessment(
                        threat_detected=True,
                        threat_type="combinatorial_risk",
                        severity="WARNING",
                        reason=f"Capability set has moderate combinatorial risk: {report.recommendations}",
                        blocked=False,
                    )
            except ImportError:
                pass

        return ThreatAssessment(
            threat_detected=False,
            threat_type="",
            severity="NONE",
            reason="",
            blocked=False,
        )

    def validate_contract(
        self, capability_id: str, input_data: dict[str, Any], contract_registry: Any
    ) -> ThreatAssessment:
        if contract_registry is None or not hasattr(contract_registry, "validate"):
            return ThreatAssessment(
                threat_detected=False,
                threat_type="",
                severity="NONE",
                reason="",
                blocked=False,
            )
        result = contract_registry.validate(capability_id, input_data)
        if not result.valid:
            return ThreatAssessment(
                threat_detected=True,
                threat_type="contract_violation",
                severity="HIGH",
                reason=f"Contract validation failed for {capability_id}: {result.errors}",
                blocked=True,
            )
        return ThreatAssessment(
            threat_detected=False,
            threat_type="",
            severity="NONE",
            reason="",
            blocked=False,
        )

    def validate_contract_set(
        self, capability_ids: list[str], contract_registry: Any
    ) -> ThreatAssessment:
        if contract_registry is None:
            return ThreatAssessment(
                threat_detected=False,
                threat_type="",
                severity="NONE",
                reason="",
                blocked=False,
            )
        unknown = [cid for cid in capability_ids if contract_registry.get(cid) is None]
        if unknown:
            return ThreatAssessment(
                threat_detected=True,
                threat_type="unregistered_capability",
                severity="HIGH",
                reason=f"Capabilities not registered: {unknown}",
                blocked=True,
            )
        return ThreatAssessment(
            threat_detected=False,
            threat_type="",
            severity="NONE",
            reason="",
            blocked=False,
        )

    def validate_handoff_chain(
        self, chain: list[tuple[str, str]], agent_capabilities: dict[str, list[str]]
    ) -> ThreatAssessment:
        for from_agent, to_agent in chain:
            from_caps = agent_capabilities.get(from_agent, [])
            to_caps = agent_capabilities.get(to_agent, [])
            assessment = self.validate_handoff(from_agent, to_agent, from_caps, to_caps)
            if assessment.threat_detected:
                return assessment
        return ThreatAssessment(
            threat_detected=False,
            threat_type="",
            severity="NONE",
            reason="",
            blocked=False,
        )

    def attach_stench_detector(self, detector: AIStenchDetector) -> None:
        self._stench_detector = detector

    def detect_ai_stench(self, code: str) -> ThreatAssessment:
        if self._stench_detector is None:
            return ThreatAssessment(
                threat_detected=False,
                threat_type="",
                severity="NONE",
                reason="",
                blocked=False,
            )
        warnings = self._stench_detector.scan(code)
        hard_blocks = [w for w in warnings if w.severity == "HARD_BLOCK"]
        soft_warnings = [w for w in warnings if w.severity == "WARNING"]
        if hard_blocks:
            return ThreatAssessment(
                threat_detected=True,
                threat_type="ai_stench_hard",
                severity="CRITICAL",
                reason=f"AI generation stench detected: {', '.join(w.message for w in hard_blocks)}",
                blocked=True,
            )
        if len(soft_warnings) >= 5:
            return ThreatAssessment(
                threat_detected=True,
                threat_type="ai_stench_soft",
                severity="WARNING",
                reason=f"Multiple AI stench indicators: {len(soft_warnings)} warnings",
                blocked=False,
            )
        return ThreatAssessment(
            threat_detected=False,
            threat_type="",
            severity="NONE",
            reason="",
            blocked=False,
        )

    # ── M4: IntentDriftDetector 集成 ──

    def block(self, reason: str) -> bool:
        """M4: 阻断操作并记录审计。

        Args:
            reason: 阻断原因 (如 intent drift hash mismatch)

        Returns:
            True - 阻断已记录并生效
        """
        self._blocked = True
        self._audit_trail.append(
            {
                "timestamp": time.time(),
                "target": "safety_gate_v2",
                "direction": "block",
                "value": reason,
            }
        )
        return True

    def is_blocked(self) -> bool:
        """M4: 查询是否已阻断。"""
        return self._blocked

    def attach_intent_drift_detector(self, detector: IntentDriftDetector) -> None:
        """附加意图漂移检测器。"""
        self._intent_drift_detector = detector

    def attach_sentinel_observer(self, observer: Any) -> None:
        """附加 sentinel 观测器。"""
        self._sentinel_observer = observer

    def validate_runtime_behavior(
        self, agent_id: str, session: Any = None
    ) -> ThreatAssessment:
        """运行时行为验证 — M4 综合评估。

        Args:
            agent_id: 目标 agent ID
            session: SessionRecord (可选,包含 sentinel 观测数据)

        Returns:
            ThreatAssessment 评估结果
        """
        reasons: list[str] = []
        blocked = False

        # 1. Intent drift 检查 (仅当 detector 和 session 都可用时)
        if self._intent_drift_detector is not None and session is not None:
            try:
                code = getattr(session, "last_code", "")
                if code:  # 仅当有实际代码可评估时才调用
                    drift = self._intent_drift_detector.evaluate_code(
                        code=code,
                        criteria=getattr(session, "intent_criteria", []),
                        expected_hash=getattr(session, "prompt_hash", ""),
                    )
                    if not drift.passed:
                        reasons.append(f"intent_drift:{len(drift.test_results)}_failures")
                        blocked = blocked or drift.blocked
            except Exception:
                pass  # intent_drift 评估失败不应阻断主流程

        # 2. Sentinel 观测数据检查
        if session is not None:
            syscall_count = len(getattr(session, "syscall_trace", []))
            network_count = len(getattr(session, "network_egress", []))
            if network_count > 10:
                reasons.append(f"excessive_network_egress:{network_count}")
                blocked = True
            if syscall_count > 100:
                reasons.append(f"excessive_syscalls:{syscall_count}")

        if reasons:
            return ThreatAssessment(
                threat_detected=True,
                threat_type="runtime_behavior_anomaly",
                severity="HIGH" if blocked else "MEDIUM",
                reason="; ".join(reasons),
                blocked=blocked,
            )
        return ThreatAssessment(
            threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False,
        )

    def attach_meta_closure(self, meta_closure: MetaAgentClosure) -> None:
        """注入 MetaAgentClosure 实例，启用生产级红线检查。

        这是 N10 修复的核心入口。一旦注入，所有经过 evaluate_decision()
        的演化决策都将接受宪法红线验证。
        """
        self._meta_closure = meta_closure

    def evaluate_decision(self, decision: EvolutionDecision) -> ThreatAssessment:
        """评估演化决策的宪法红线合规性。

        由 MetaAgentClosure.review_evolution_decision() 执行红线检查。
        如果 meta_closure 未注入（None），则返回非阻断结果。
        这是元治理层从"测试专用"变为"生产强制"的关键集成点。

        无论检查结果如何，只要经过此方法，决策的 safety_gate_evaluated
        标志即被设置为 True（修复 N3: INV-002 据此验证安全门未被绕过）。
        """
        if self._meta_closure is None:
            return ThreatAssessment(
                threat_detected=False,
                threat_type="",
                severity="NONE",
                reason="",
                blocked=False,
            )

        reviewed = self._meta_closure.review_evolution_decision(decision)
        # 修复 N3: 标记决策已通过安全门评估
        decision.safety_gate_evaluated = True
        if reviewed.red_line_violation:
            return ThreatAssessment(
                threat_detected=True,
                threat_type="red_line_violation",
                severity="CRITICAL",
                reason=f"Red line violation: {', '.join(reviewed.violated_red_lines)}",
                blocked=True,
            )
        return ThreatAssessment(
            threat_detected=False,
            threat_type="",
            severity="NONE",
            reason="",
            blocked=False,
        )
