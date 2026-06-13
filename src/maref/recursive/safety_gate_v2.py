from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maref.immunity.ai_stench_detector import AIStenchDetector


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
        return ThreatAssessment(threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False)

    def detect_gradual_weakening(self, target: str, new_value: Any) -> ThreatAssessment:
        if target not in self._change_history:
            self._change_history[target] = []
            return ThreatAssessment(threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False)

        history = self._change_history[target]
        if len(history) < 2:
            self._record_change(target, new_value)
            return ThreatAssessment(threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False)

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
        return ThreatAssessment(threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False)

    def detect_combinatorial_explosion(self, batch: list[dict[str, Any]]) -> ThreatAssessment:
        if len(batch) < 3:
            return ThreatAssessment(threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False)

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
        return ThreatAssessment(threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False)

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
        self._audit_trail.append({
            "timestamp": record.timestamp,
            "target": target,
            "direction": record.direction,
            "value": record.value,
        })

    def validate_decomposition(self, subtask_count: int,
                                capabilities: list[str]) -> ThreatAssessment:
        has_dangerous = any(
            cap in self._DANGEROUS_CAPABILITIES for cap in capabilities
        )
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
            threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False,
        )

    def validate_handoff(self, from_agent: str, to_agent: str,
                          from_capabilities: list[str],
                          to_capabilities: list[str]) -> ThreatAssessment:
        from_has_high = any(
            cap in self._HIGH_PRIVILEGE_CAPABILITIES for cap in from_capabilities
        )
        to_has_high = any(
            cap in self._HIGH_PRIVILEGE_CAPABILITIES for cap in to_capabilities
        )
        if not from_has_high and to_has_high:
            return ThreatAssessment(
                threat_detected=True,
                threat_type="handoff_privilege_escalation",
                severity="HIGH",
                reason=f"Handoff from low-privilege {from_agent} to high-privilege {to_agent}",
                blocked=True,
            )
        return ThreatAssessment(
            threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False,
        )

    def validate_capability_assignment(self, subtask_capabilities: list[str],
                                        agent_capabilities: list[str],
                                        contract_registry: Any = None) -> ThreatAssessment:
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
            threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False,
        )

    def validate_contract(self, capability_id: str,
                          input_data: dict[str, Any],
                          contract_registry: Any) -> ThreatAssessment:
        if contract_registry is None or not hasattr(contract_registry, "validate"):
            return ThreatAssessment(
                threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False,
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
            threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False,
        )

    def validate_contract_set(self, capability_ids: list[str],
                              contract_registry: Any) -> ThreatAssessment:
        if contract_registry is None:
            return ThreatAssessment(
                threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False,
            )
        unknown = [cid for cid in capability_ids
                   if contract_registry.get(cid) is None]
        if unknown:
            return ThreatAssessment(
                threat_detected=True,
                threat_type="unregistered_capability",
                severity="HIGH",
                reason=f"Capabilities not registered: {unknown}",
                blocked=True,
            )
        return ThreatAssessment(
            threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False,
        )

    def validate_handoff_chain(self, chain: list[tuple[str, str]],
                                agent_capabilities: dict[str, list[str]]) -> ThreatAssessment:
        for from_agent, to_agent in chain:
            from_caps = agent_capabilities.get(from_agent, [])
            to_caps = agent_capabilities.get(to_agent, [])
            assessment = self.validate_handoff(from_agent, to_agent, from_caps, to_caps)
            if assessment.threat_detected:
                return assessment
        return ThreatAssessment(
            threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False,
        )

    def attach_stench_detector(self, detector: AIStenchDetector) -> None:
        self._stench_detector = detector

    def detect_ai_stench(self, code: str) -> ThreatAssessment:
        if self._stench_detector is None:
            return ThreatAssessment(
                threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False,
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
            threat_detected=False, threat_type="", severity="NONE", reason="", blocked=False,
        )
