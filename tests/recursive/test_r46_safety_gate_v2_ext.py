from __future__ import annotations

from maref.recursive.safety_gate_v2 import SafetyGateV2


class TestSafetyGateV2Orchestration:
    def test_validate_decomposition_safe(self) -> None:
        sg = SafetyGateV2()
        result = sg.validate_decomposition(3, ["observe", "collect"])
        assert result.threat_detected is False
        assert result.blocked is False

    def test_validate_decomposition_too_many_subtasks(self) -> None:
        sg = SafetyGateV2()
        result = sg.validate_decomposition(15, ["observe"])
        assert result.threat_detected is True
        assert result.threat_type == "decomposition_subtask_explosion"
        assert result.blocked is True

    def test_validate_decomposition_dangerous_explosion(self) -> None:
        sg = SafetyGateV2()
        result = sg.validate_decomposition(10, ["halt", "circuit_break", "observe"])
        assert result.threat_detected is True
        assert result.threat_type == "decomposition_dangerous_explosion"
        assert result.blocked is True

    def test_validate_decomposition_dangerous_but_small(self) -> None:
        sg = SafetyGateV2()
        result = sg.validate_decomposition(5, ["halt", "observe"])
        assert result.threat_detected is False

    def test_validate_decomposition_at_limit(self) -> None:
        sg = SafetyGateV2()
        result = sg.validate_decomposition(12, ["observe"])
        assert result.threat_detected is False

    def test_validate_decomposition_dangerous_at_limit(self) -> None:
        sg = SafetyGateV2()
        result = sg.validate_decomposition(8, ["halt", "observe"])
        assert result.threat_detected is False


class TestSafetyGateV2Handoff:
    def test_validate_handoff_same_privilege(self) -> None:
        sg = SafetyGateV2()
        result = sg.validate_handoff(
            "agent_a",
            "agent_b",
            ["observe", "collect"],
            ["observe", "monitor"],
        )
        assert result.threat_detected is False

    def test_validate_handoff_high_to_low_allowed(self) -> None:
        sg = SafetyGateV2()
        result = sg.validate_handoff(
            "governance",
            "sidecar",
            ["halt", "circuit_break", "state_transition"],
            ["observe", "collect"],
        )
        assert result.threat_detected is False

    def test_validate_handoff_low_to_high_blocked(self) -> None:
        sg = SafetyGateV2()
        result = sg.validate_handoff(
            "sidecar",
            "governance",
            ["observe", "collect"],
            ["halt", "circuit_break"],
        )
        assert result.threat_detected is True
        assert result.threat_type == "handoff_privilege_escalation"
        assert result.blocked is True

    def test_validate_handoff_both_high_allowed(self) -> None:
        sg = SafetyGateV2()
        result = sg.validate_handoff(
            "gov_a",
            "gov_b",
            ["halt", "state_transition"],
            ["circuit_break", "state_transition"],
        )
        assert result.threat_detected is False


class TestSafetyGateV2CapabilityAssignment:
    def test_validate_assignment_agent_has_capability(self) -> None:
        sg = SafetyGateV2()
        result = sg.validate_capability_assignment(
            ["observe", "collect"],
            ["observe", "collect", "monitor"],
        )
        assert result.threat_detected is False

    def test_validate_assignment_no_dangerous_caps(self) -> None:
        sg = SafetyGateV2()
        result = sg.validate_capability_assignment(
            ["observe"],
            ["monitor"],
        )
        assert result.threat_detected is False

    def test_validate_assignment_dangerous_mismatch(self) -> None:
        sg = SafetyGateV2()
        result = sg.validate_capability_assignment(
            ["halt"],
            ["observe"],
        )
        assert result.threat_detected is True
        assert result.threat_type == "dangerous_capability_mismatch"
        assert result.blocked is True

    def test_validate_assignment_dangerous_match(self) -> None:
        sg = SafetyGateV2()
        result = sg.validate_capability_assignment(
            ["halt", "circuit_break"],
            ["halt", "circuit_break", "state_transition"],
        )
        assert result.threat_detected is False


class TestSafetyGateV2HandoffChain:
    def test_validate_chain_all_safe(self) -> None:
        sg = SafetyGateV2()
        chain = [
            ("gov_a", "gov_b"),
            ("gov_b", "sidecar"),
        ]
        capabilities = {
            "gov_a": ["halt", "circuit_break"],
            "gov_b": ["state_transition"],
            "sidecar": ["observe"],
        }
        result = sg.validate_handoff_chain(chain, capabilities)
        assert result.threat_detected is False

    def test_validate_chain_with_escalation(self) -> None:
        sg = SafetyGateV2()
        chain = [
            ("gov_a", "sidecar"),
            ("sidecar", "gov_b"),
        ]
        capabilities = {
            "gov_a": ["halt"],
            "sidecar": ["observe"],
            "gov_b": ["circuit_break"],
        }
        result = sg.validate_handoff_chain(chain, capabilities)
        assert result.threat_detected is True
        assert result.threat_type == "handoff_privilege_escalation"

    def test_validate_chain_empty(self) -> None:
        sg = SafetyGateV2()
        result = sg.validate_handoff_chain([], {})
        assert result.threat_detected is False


class TestSafetyGateV2BackwardCompatibility:
    def test_core_removal_still_works(self) -> None:
        sg = SafetyGateV2()
        result = sg.detect_core_removal("circuit_breaker")
        assert result.threat_detected is True
        assert result.threat_type == "core_removal"
        assert result.blocked is True

    def test_gradual_weakening_still_works(self) -> None:
        sg = SafetyGateV2()
        sg.detect_gradual_weakening("threshold_a", -1)
        sg.detect_gradual_weakening("threshold_a", -2)
        sg.detect_gradual_weakening("threshold_a", -3)
        result = sg.detect_gradual_weakening("threshold_a", -4)
        assert result.threat_detected is True

    def test_combinatorial_explosion_still_works(self) -> None:
        sg = SafetyGateV2()
        batch = [
            {"target": "circuit_breaker_change"},
            {"target": "state_machine_mod"},
            {"target": "audit_logger_change"},
        ]
        result = sg.detect_combinatorial_explosion(batch)
        assert result.threat_detected is True

    def test_safety_self_audit(self) -> None:
        sg = SafetyGateV2()
        audit = sg.safety_self_audit()
        assert audit["gate_healthy"] is True
        assert audit["core_components_count"] == 6
