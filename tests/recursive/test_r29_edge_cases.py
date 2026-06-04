from __future__ import annotations

from maref.recursive.joint_state_machine import JointStateMachine
from maref.recursive.safety_gate import SafetyGateV2
from maref.recursive.unified_audit import UnifiedAuditRecord, UnifiedAuditStore


class TestUnifiedAuditClear:
    def test_clear_resets_all(self) -> None:
        store = UnifiedAuditStore()
        r = UnifiedAuditRecord(
            record_id="r1", timestamp=1.0, layer="meta",
            round=1, event_type="test", source_module="mod",
            target_module="mod2", decision="act", justification="because",
        )
        store.append(r)
        assert store.count() == 1
        store.clear()
        assert store.count() == 0
        assert store.all() == []
        assert store.query_by_round(1) == []
        assert store.stats_by_event_type() == {}
        assert store.stats_by_module() == {}
        assert store.stats_by_round() == {}

    def test_query_decision_chain_circular(self) -> None:
        store = UnifiedAuditStore()
        r1 = UnifiedAuditRecord(
            record_id="r1", timestamp=1.0, layer="meta",
            round=1, event_type="test", source_module="m1",
            target_module="m2", decision="act", justification="j",
            context_refs=["r2"],
        )
        r2 = UnifiedAuditRecord(
            record_id="r2", timestamp=2.0, layer="inner",
            round=1, event_type="test", source_module="m2",
            target_module="m3", decision="act", justification="j",
            context_refs=["r1"],
        )
        store.append(r1)
        store.append(r2)
        chain = store.query_decision_chain("r1")
        assert len(chain) == 2


class TestJointStateMachine:
    def test_agent_states(self) -> None:
        jsm = JointStateMachine()
        jsm.agents["agent_a"] = "IDLE"
        jsm.agents["agent_b"] = "RUNNING"
        states = jsm.agent_states()
        assert states == {"agent_a": "IDLE", "agent_b": "RUNNING"}

    def test_agent_states_empty(self) -> None:
        jsm = JointStateMachine()
        assert jsm.agent_states() == {}

    def test_agent_count(self) -> None:
        jsm = JointStateMachine()
        jsm.agents["agent_a"] = "IDLE"
        assert jsm.agent_count() == 1


class TestSafetyGateV2EdgeCases:
    def test_detect_gradual_weakening_single_history(self) -> None:
        gate = SafetyGateV2()
        result = gate.detect_gradual_weakening("coverage", 92.0)
        assert result.threat_detected is False

    def test_detect_gradual_weakening_two_changes_first(self) -> None:
        gate = SafetyGateV2()
        gate.detect_gradual_weakening("coverage", 92.0)
        result = gate.detect_gradual_weakening("coverage", 93.0)
        assert result.threat_detected is False

    def test_detect_gradual_weakening_mixed_direction(self) -> None:
        from maref.recursive.safety_gate import ChangeRecord
        gate = SafetyGateV2()
        gate._change_history["target_x"] = [
            ChangeRecord(timestamp=1.0, target="target_x", direction="decrease", value=0.9),
            ChangeRecord(timestamp=2.0, target="target_x", direction="increase", value=0.95),
        ]
        result = gate.detect_gradual_weakening("target_x", 0.97)
        assert result.threat_detected is False

    def test_detect_combinatorial_batch_small(self) -> None:
        gate = SafetyGateV2()
        batch: list[dict[str, object]] = [{"target": "single_change"}]
        result = gate.detect_combinatorial_explosion(batch)
        assert result.threat_detected is False

    def test_harden_parameters_threshold_keys(self) -> None:
        gate = SafetyGateV2()
        params = {
            "some_threshold": 1.0,
            "cooldown_seconds": 30.0,
            "unrelated_param": "string_val",
        }
        hardened = gate.harden_parameters(params)
        assert isinstance(hardened["some_threshold"], float)

    def test_safety_self_audit(self) -> None:
        gate = SafetyGateV2()
        audit = gate.safety_self_audit()
        assert audit["gate_healthy"] is True
        assert audit["core_components_count"] >= 5
        assert "core_components" in audit
