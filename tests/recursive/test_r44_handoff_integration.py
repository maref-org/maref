from __future__ import annotations

import time

from maref.recursive.joint_state_machine import JointStateMachine


class TestJointStateMachineHandoff:
    def test_initiate_handoff_sets_states(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("agent_a")
        jsm.register_agent("agent_b")
        result = jsm.initiate_handoff("agent_a", "agent_b")
        assert result is True
        assert jsm.agents["agent_a"] == "HANDOFF_SOURCE"
        assert jsm.agents["agent_b"] == "HANDOFF_TARGET"

    def test_initiate_handoff_unknown_agents(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("agent_a")
        result = jsm.initiate_handoff("agent_a", "unknown")
        assert result is False
        result = jsm.initiate_handoff("unknown", "agent_a")
        assert result is False

    def test_cannot_double_initiate_same_source(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("agent_a")
        jsm.register_agent("agent_b")
        jsm.register_agent("agent_c")
        assert jsm.initiate_handoff("agent_a", "agent_b") is True
        result = jsm.initiate_handoff("agent_a", "agent_c")
        assert result is False

    def test_can_initiate_from_each_source(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("agent_a")
        jsm.register_agent("agent_b")
        jsm.register_agent("agent_c")
        jsm.register_agent("agent_d")
        assert jsm.initiate_handoff("agent_a", "agent_c") is True
        assert jsm.initiate_handoff("agent_b", "agent_d") is True
        assert jsm.agents["agent_a"] == "HANDOFF_SOURCE"
        assert jsm.agents["agent_c"] == "HANDOFF_TARGET"
        assert jsm.agents["agent_b"] == "HANDOFF_SOURCE"
        assert jsm.agents["agent_d"] == "HANDOFF_TARGET"


class TestJointStateMachineCompleteHandoff:
    def test_complete_handoff_transitions(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("agent_a")
        jsm.register_agent("agent_b")
        jsm.initiate_handoff("agent_a", "agent_b")
        result = jsm.complete_handoff("agent_a")
        assert result is True
        assert jsm.agents["agent_a"] == "DONE"
        assert jsm.agents["agent_b"] == "RUNNING"

    def test_complete_no_handoff_returns_false(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("agent_a")
        result = jsm.complete_handoff("agent_a")
        assert result is False

    def test_complete_unknown_agent(self) -> None:
        jsm = JointStateMachine()
        result = jsm.complete_handoff("unknown")
        assert result is False

    def test_cannot_complete_if_not_in_handoff_state(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("agent_a")
        jsm.register_agent("agent_b")
        jsm.agents["agent_a"] = "RUNNING"
        jsm._handoff_pairs["agent_a"] = "agent_b"
        result = jsm.complete_handoff("agent_a")
        assert result is False

    def test_complete_cleans_up_timeouts(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("agent_a")
        jsm.register_agent("agent_b")
        jsm.initiate_handoff("agent_a", "agent_b")
        assert "agent_a" in jsm._handoff_timeouts
        assert "agent_b" in jsm._handoff_timeouts
        jsm.complete_handoff("agent_a")
        assert "agent_a" not in jsm._handoff_timeouts
        assert "agent_b" not in jsm._handoff_timeouts


class TestJointStateMachineRollbackHandoff:
    def test_rollback_handoff(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("agent_a")
        jsm.register_agent("agent_b")
        jsm.initiate_handoff("agent_a", "agent_b")
        result = jsm.rollback_handoff("agent_a")
        assert result is True
        assert jsm.agents["agent_a"] == "RUNNING"
        assert jsm.agents["agent_b"] == "IDLE"

    def test_rollback_no_handoff_returns_false(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("agent_a")
        result = jsm.rollback_handoff("agent_a")
        assert result is False

    def test_rollback_cleans_up(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("agent_a")
        jsm.register_agent("agent_b")
        jsm.initiate_handoff("agent_a", "agent_b")
        jsm.rollback_handoff("agent_a")
        assert jsm._handoff_pairs == {}
        assert jsm._handoff_timeouts == {}


class TestJointStateMachineHandoffTimeout:
    def test_check_timeout_no_timeouts(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("agent_a")
        jsm.register_agent("agent_b")
        timed_out = jsm.check_handoff_timeout()
        assert timed_out == []

    def test_check_timeout_future_deadline(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("agent_a")
        jsm.register_agent("agent_b")
        jsm.initiate_handoff("agent_a", "agent_b", timeout_seconds=300.0)
        timed_out = jsm.check_handoff_timeout()
        assert timed_out == []

    def test_check_timeout_immediate(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("agent_a")
        jsm.register_agent("agent_b")
        jsm.initiate_handoff("agent_a", "agent_b", timeout_seconds=0.0)
        time.sleep(0.01)
        timed_out = jsm.check_handoff_timeout()
        assert len(timed_out) > 0
        assert jsm.agents["agent_a"] == "RUNNING"


class TestJointStateMachineHandoffQuery:
    def test_is_in_handoff(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("agent_a")
        jsm.register_agent("agent_b")
        assert jsm.is_in_handoff("agent_a") is False
        jsm.initiate_handoff("agent_a", "agent_b")
        assert jsm.is_in_handoff("agent_a") is True
        assert jsm.is_in_handoff("agent_b") is True

    def test_handoff_partner(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("agent_a")
        jsm.register_agent("agent_b")
        jsm.initiate_handoff("agent_a", "agent_b")
        assert jsm.handoff_partner("agent_a") == "agent_b"
        assert jsm.handoff_partner("agent_b") == "agent_a"

    def test_handoff_partner_none(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("agent_a")
        assert jsm.handoff_partner("agent_a") is None

    def test_active_handoffs(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("agent_a")
        jsm.register_agent("agent_b")
        jsm.register_agent("agent_c")
        jsm.register_agent("agent_d")
        jsm.initiate_handoff("agent_a", "agent_b")
        jsm.initiate_handoff("agent_c", "agent_d")
        active = jsm.active_handoffs()
        assert len(active) == 2
        assert active["agent_a"] == "agent_b"
        assert active["agent_c"] == "agent_d"


class TestJointStateMachineBackwardCompatibility:
    def test_register_agents(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("a")
        jsm.register_agent("b")
        assert jsm.agent_count() == 2

    def test_advance_and_barrier(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("a")
        jsm.register_agent("b")
        jsm.advance("a", "RUNNING")
        assert jsm.all_at_barrier("RUNNING") is False
        jsm.advance("b", "RUNNING")
        assert jsm.all_at_barrier("RUNNING") is True

    def test_any_at_state(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("a")
        jsm.register_agent("b")
        jsm.advance("a", "ERROR")
        assert jsm.any_at_state("ERROR") is True
        assert jsm.any_at_state("RUNNING") is False

    def test_advance_all_to(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("a")
        jsm.register_agent("b")
        jsm.advance_all_to("DONE")
        assert jsm.all_at_barrier("DONE") is True

    def test_arbitrate_logs_conflict(self) -> None:
        jsm = JointStateMachine()
        resolution = jsm.arbitrate("agent_x", "agent_y", "resource contention")
        assert "resolved" in resolution.lower()
        assert len(jsm.conflict_log) == 1

    def test_reset_clears_handoffs_too(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("a")
        jsm.register_agent("b")
        jsm.initiate_handoff("a", "b")
        jsm.arbitrate("a", "b", "issue")
        jsm.reset()
        assert jsm.agent_count() == 0
        assert len(jsm.conflict_log) == 0
        assert jsm.active_handoffs() == {}

    def test_all_at_barrier_empty(self) -> None:
        jsm = JointStateMachine()
        assert jsm.all_at_barrier("RUNNING") is False

    def test_agent_states(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("a")
        jsm.register_agent("b")
        states = jsm.agent_states()
        assert states == {"a": "IDLE", "b": "IDLE"}
