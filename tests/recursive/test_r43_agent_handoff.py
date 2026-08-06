from __future__ import annotations

from maref.recursive.agent_handoff import (
    AgentHandoffProtocol,
    HandoffReason,
    HandoffRequest,
    HandoffResult,
    HandoffStatus,
)
from maref.recursive.safety_gate_v2 import SafetyGateV2


class TestHandoffRequest:
    def test_create_request(self) -> None:
        req = HandoffRequest(
            from_agent="agent_a",
            to_agent="agent_b",
            task_context={"task": "test"},
            reason=HandoffReason.SUBTASK_COMPLETE,
            transfer_state={"progress": 0.5},
        )
        assert req.from_agent == "agent_a"
        assert req.to_agent == "agent_b"
        assert req.reason == HandoffReason.SUBTASK_COMPLETE
        assert req.transfer_state == {"progress": 0.5}
        assert len(req.request_id) > 0

    def test_request_to_dict(self) -> None:
        req = HandoffRequest(
            from_agent="agent_a",
            to_agent="agent_b",
            reason=HandoffReason.CAPABILITY_MISMATCH,
        )
        d = req.to_dict()
        assert d["from_agent"] == "agent_a"
        assert d["to_agent"] == "agent_b"
        assert d["reason"] == "capability_mismatch"
        assert "request_id" in d

    def test_request_priority(self) -> None:
        req = HandoffRequest(
            from_agent="a",
            to_agent="b",
            priority=5,
        )
        assert req.priority == 5


class TestHandoffResult:
    def test_accepted_result(self) -> None:
        result = HandoffResult(
            accepted=True,
            from_agent="agent_a",
            to_agent="agent_b",
            handoff_id="hoff_001",
            status=HandoffStatus.ACCEPTED,
        )
        assert result.accepted is True
        assert result.status == HandoffStatus.ACCEPTED

    def test_rejected_result(self) -> None:
        result = HandoffResult(
            accepted=False,
            from_agent="a",
            to_agent="b",
            handoff_id="hoff_002",
            status=HandoffStatus.REJECTED,
            refusal_reason="trust too low",
        )
        assert result.accepted is False
        assert result.refusal_reason == "trust too low"

    def test_result_to_dict(self) -> None:
        result = HandoffResult(
            accepted=True,
            from_agent="a",
            to_agent="b",
            handoff_id="hoff_003",
            status=HandoffStatus.ACCEPTED,
            request_id="req_001",
        )
        d = result.to_dict()
        assert d["handoff_id"] == "hoff_003"
        assert d["status"] == "accepted"


class TestAgentHandoffProtocolBasic:
    def test_init(self) -> None:
        protocol = AgentHandoffProtocol()
        assert protocol.get_active_handoffs() == []

    def test_set_and_get_trust(self) -> None:
        protocol = AgentHandoffProtocol()
        protocol.set_trust("agent_a", "agent_b", 0.8)
        assert protocol.get_trust("agent_a", "agent_b") == 0.8

    def test_get_trust_default_zero(self) -> None:
        protocol = AgentHandoffProtocol()
        assert protocol.get_trust("unknown_a", "unknown_b") == 0.0


class TestAgentHandoffProtocolRequest:
    def test_request_handoff_success(self) -> None:
        protocol = AgentHandoffProtocol()
        protocol.set_trust("agent_a", "agent_b", 0.8)
        req = HandoffRequest(
            from_agent="agent_a",
            to_agent="agent_b",
            reason=HandoffReason.SUBTASK_COMPLETE,
        )
        result = protocol.request_handoff(req)
        assert result.accepted is True
        assert result.status == HandoffStatus.ACCEPTED
        assert result.from_agent == "agent_a"
        assert result.to_agent == "agent_b"

    def test_request_handoff_trust_below_threshold(self) -> None:
        protocol = AgentHandoffProtocol()
        protocol.set_trust("agent_a", "agent_b", 0.1)
        req = HandoffRequest(from_agent="agent_a", to_agent="agent_b")
        result = protocol.request_handoff(req)
        assert result.accepted is False
        assert result.status == HandoffStatus.NACK
        assert "Trust" in result.refusal_reason

    def test_request_handoff_no_trust_set(self) -> None:
        protocol = AgentHandoffProtocol()
        req = HandoffRequest(from_agent="agent_a", to_agent="agent_b")
        result = protocol.request_handoff(req)
        assert result.accepted is False

    def test_request_escalation_requires_higher_trust(self) -> None:
        protocol = AgentHandoffProtocol()
        protocol.set_trust("agent_a", "agent_b", 0.4)
        req = HandoffRequest(
            from_agent="agent_a",
            to_agent="agent_b",
            reason=HandoffReason.ESCALATION,
        )
        result = protocol.request_handoff(req)
        assert result.accepted is False
        assert "Escalation" in result.refusal_reason

    def test_request_escalation_success_with_high_trust(self) -> None:
        protocol = AgentHandoffProtocol()
        protocol.set_trust("agent_a", "agent_b", 0.6)
        req = HandoffRequest(
            from_agent="agent_a",
            to_agent="agent_b",
            reason=HandoffReason.ESCALATION,
        )
        result = protocol.request_handoff(req)
        assert result.accepted is True

    def test_max_concurrent_handoffs_enforced(self) -> None:
        protocol = AgentHandoffProtocol()
        for i in range(AgentHandoffProtocol.MAX_CONCURRENT_HANDOFFS_PER_AGENT):
            protocol.set_trust("agent_a", f"agent_{i}", 0.8)
        for i in range(AgentHandoffProtocol.MAX_CONCURRENT_HANDOFFS_PER_AGENT):
            req = HandoffRequest(from_agent="agent_a", to_agent=f"agent_{i}")
            result = protocol.request_handoff(req)
            assert result.accepted is True
        protocol.set_trust("agent_a", "agent_overflow", 0.8)
        req = HandoffRequest(from_agent="agent_a", to_agent="agent_overflow")
        result = protocol.request_handoff(req)
        assert result.accepted is False
        assert "Max concurrent" in result.refusal_reason


class TestAgentHandoffProtocolComplete:
    def test_complete_handoff(self) -> None:
        protocol = AgentHandoffProtocol()
        protocol.set_trust("agent_a", "agent_b", 0.8)
        req = HandoffRequest(from_agent="agent_a", to_agent="agent_b")
        result = protocol.request_handoff(req)
        completed = protocol.complete_handoff(result.handoff_id)
        assert completed is not None
        assert completed.status == HandoffStatus.COMPLETED

    def test_complete_unknown_handoff_returns_none(self) -> None:
        protocol = AgentHandoffProtocol()
        completed = protocol.complete_handoff("nonexistent")
        assert completed is None

    def test_complete_releases_concurrency_slot(self) -> None:
        protocol = AgentHandoffProtocol()
        protocol.set_trust("agent_a", "agent_b", 0.8)
        protocol.MAX_CONCURRENT_HANDOFFS_PER_AGENT = 1
        req = HandoffRequest(from_agent="agent_a", to_agent="agent_b")
        result = protocol.request_handoff(req)
        assert result.accepted is True
        protocol.complete_handoff(result.handoff_id)
        req2 = HandoffRequest(from_agent="agent_a", to_agent="agent_b")
        result2 = protocol.request_handoff(req2)
        assert result2.accepted is True

    def test_complete_with_output(self) -> None:
        protocol = AgentHandoffProtocol()
        protocol.set_trust("agent_a", "agent_b", 0.8)
        req = HandoffRequest(from_agent="agent_a", to_agent="agent_b")
        result = protocol.request_handoff(req)
        completed = protocol.complete_handoff(result.handoff_id, {"result": "done"})
        assert completed is not None
        assert completed.status == HandoffStatus.COMPLETED


class TestAgentHandoffProtocolRollback:
    def test_rollback_handoff(self) -> None:
        protocol = AgentHandoffProtocol()
        protocol.set_trust("agent_a", "agent_b", 0.8)
        req = HandoffRequest(from_agent="agent_a", to_agent="agent_b")
        result = protocol.request_handoff(req)
        assert result.accepted is True
        rolled = protocol.rollback_handoff(result.handoff_id)
        assert rolled is not None
        assert rolled.status == HandoffStatus.ROLLED_BACK
        assert rolled.accepted is True

    def test_rollback_unknown_handoff_returns_none(self) -> None:
        protocol = AgentHandoffProtocol()
        rolled = protocol.rollback_handoff("nonexistent")
        assert rolled is None

    def test_rollback_releases_concurrency_slot(self) -> None:
        protocol = AgentHandoffProtocol()
        protocol.set_trust("agent_a", "agent_b", 0.8)
        protocol.MAX_CONCURRENT_HANDOFFS_PER_AGENT = 1
        req = HandoffRequest(from_agent="agent_a", to_agent="agent_b")
        result = protocol.request_handoff(req)
        protocol.rollback_handoff(result.handoff_id)
        req2 = HandoffRequest(from_agent="agent_a", to_agent="agent_b")
        result2 = protocol.request_handoff(req2)
        assert result2.accepted is True


class TestAgentHandoffProtocolQuery:
    def test_get_active_handoffs(self) -> None:
        protocol = AgentHandoffProtocol()
        protocol.set_trust("agent_a", "agent_b", 0.8)
        req = HandoffRequest(from_agent="agent_a", to_agent="agent_b")
        protocol.request_handoff(req)
        active = protocol.get_active_handoffs()
        assert len(active) == 1

    def test_get_active_excludes_completed(self) -> None:
        protocol = AgentHandoffProtocol()
        protocol.set_trust("agent_a", "agent_b", 0.8)
        req = HandoffRequest(from_agent="agent_a", to_agent="agent_b")
        result = protocol.request_handoff(req)
        protocol.complete_handoff(result.handoff_id)
        active = protocol.get_active_handoffs()
        assert len(active) == 0

    def test_get_handoff_by_id(self) -> None:
        protocol = AgentHandoffProtocol()
        protocol.set_trust("agent_a", "agent_b", 0.8)
        req = HandoffRequest(from_agent="agent_a", to_agent="agent_b")
        result = protocol.request_handoff(req)
        retrieved = protocol.get_handoff(result.handoff_id)
        assert retrieved is not None
        assert retrieved.handoff_id == result.handoff_id

    def test_get_history(self) -> None:
        protocol = AgentHandoffProtocol()
        protocol.set_trust("agent_a", "agent_b", 0.8)
        req = HandoffRequest(from_agent="agent_a", to_agent="agent_b")
        protocol.request_handoff(req)
        history = protocol.get_history()
        assert len(history) == 1

    def test_agent_handoff_count(self) -> None:
        protocol = AgentHandoffProtocol()
        protocol.set_trust("agent_a", "agent_b", 0.8)
        req = HandoffRequest(from_agent="agent_a", to_agent="agent_b")
        protocol.request_handoff(req)
        assert protocol.agent_handoff_count("agent_a") == 1


class TestAgentHandoffProtocolStats:
    def test_stats_empty(self) -> None:
        protocol = AgentHandoffProtocol()
        st = protocol.stats()
        assert st["total_handoffs"] == 0
        assert st["accepted"] == 0

    def test_stats_with_handoffs(self) -> None:
        protocol = AgentHandoffProtocol()
        protocol.set_trust("agent_a", "agent_b", 0.8)
        protocol.set_trust("agent_a", "agent_c", 0.8)
        req1 = HandoffRequest(from_agent="agent_a", to_agent="agent_b")
        r1 = protocol.request_handoff(req1)
        protocol.complete_handoff(r1.handoff_id)
        req2 = HandoffRequest(from_agent="agent_a", to_agent="agent_c")
        r2 = protocol.request_handoff(req2)
        protocol.rollback_handoff(r2.handoff_id)
        st = protocol.stats()
        assert st["total_handoffs"] == 2
        assert st["accepted"] == 2
        assert st["completed"] == 1
        assert st["rolled_back"] == 1


class TestAgentHandoffProtocolSafetyGate:
    def test_safety_gate_block_on_core_component(self) -> None:
        sg = SafetyGateV2()
        protocol = AgentHandoffProtocol(safety_gate=sg)
        protocol.set_trust("agent_a", "circuit_breaker", 0.8)
        req = HandoffRequest(from_agent="agent_a", to_agent="circuit_breaker")
        result = protocol.request_handoff(req)
        assert result.accepted is False
        assert "Safety gate" in result.refusal_reason

    def test_safety_gate_allows_normal_handoff(self) -> None:
        sg = SafetyGateV2()
        protocol = AgentHandoffProtocol(safety_gate=sg)
        protocol.set_trust("agent_a", "agent_normal", 0.8)
        req = HandoffRequest(from_agent="agent_a", to_agent="agent_normal")
        result = protocol.request_handoff(req)
        assert result.accepted is True


class TestAgentHandoffProtocolAudit:
    def test_audit_records_on_request(self) -> None:
        protocol = AgentHandoffProtocol()
        protocol.set_trust("agent_a", "agent_b", 0.8)
        req = HandoffRequest(from_agent="agent_a", to_agent="agent_b")
        protocol.request_handoff(req)
        assert protocol._audit_store.count() > 0

    def test_audit_records_on_complete(self) -> None:
        protocol = AgentHandoffProtocol()
        protocol.set_trust("agent_a", "agent_b", 0.8)
        req = HandoffRequest(from_agent="agent_a", to_agent="agent_b")
        result = protocol.request_handoff(req)
        count_before = protocol._audit_store.count()
        protocol.complete_handoff(result.handoff_id)
        assert protocol._audit_store.count() > count_before

    def test_audit_records_on_rollback(self) -> None:
        protocol = AgentHandoffProtocol()
        protocol.set_trust("agent_a", "agent_b", 0.8)
        req = HandoffRequest(from_agent="agent_a", to_agent="agent_b")
        result = protocol.request_handoff(req)
        count_before = protocol._audit_store.count()
        protocol.rollback_handoff(result.handoff_id)
        assert protocol._audit_store.count() > count_before

    def test_clear_resets_all_state(self) -> None:
        protocol = AgentHandoffProtocol()
        protocol.set_trust("agent_a", "agent_b", 0.8)
        req = HandoffRequest(from_agent="agent_a", to_agent="agent_b")
        protocol.request_handoff(req)
        protocol.clear()
        assert protocol.get_active_handoffs() == []
        assert protocol.get_history() == []
        assert protocol.agent_handoff_count("agent_a") == 0


class TestHandoffReasons:
    def test_all_reasons_defined(self) -> None:
        reasons = list(HandoffReason)
        assert HandoffReason.SUBTASK_COMPLETE in reasons
        assert HandoffReason.CAPABILITY_MISMATCH in reasons
        assert HandoffReason.ESCALATION in reasons
        assert HandoffReason.LOAD_BALANCE in reasons
        assert HandoffReason.PREEMPTION in reasons
