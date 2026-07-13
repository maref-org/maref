"""Tests for joint_state_machine.py — state transitions, handoffs, edge cases."""
from __future__ import annotations

import time

import pytest

from maref.recursive.joint_state_machine import JointStateMachine


class TestJointStateMachine:
    @pytest.mark.parametrize("states,barrier,expected", [
        ({}, "DONE", False),
        ({"a": "DONE"}, "DONE", True),
        ({"a": "DONE", "b": "DONE"}, "DONE", True),
        ({"a": "DONE", "b": "RUNNING"}, "DONE", False),
        ({"a": "IDLE", "b": "IDLE"}, "IDLE", True),
    ])
    def test_all_at_barrier(self, states, barrier, expected):
        jsm = JointStateMachine()
        jsm.agents.update(states)
        assert jsm.all_at_barrier(barrier) == expected

    @pytest.mark.parametrize("states,state,expected", [
        ({}, "DONE", False),
        ({"a": "DONE"}, "DONE", True),
        ({"a": "DONE", "b": "RUNNING"}, "DONE", True),
        ({"a": "IDLE", "b": "RUNNING"}, "DONE", False),
    ])
    def test_any_at_state(self, states, state, expected):
        jsm = JointStateMachine()
        jsm.agents.update(states)
        assert jsm.any_at_state(state) == expected

    def test_register_agent_defaults_to_idle(self):
        jsm = JointStateMachine()
        jsm.register_agent("agent-a")
        assert jsm.agents["agent-a"] == "IDLE"

    def test_register_agent_preserves_existing(self):
        jsm = JointStateMachine()
        jsm.agents["agent-a"] = "RUNNING"
        jsm.register_agent("agent-a")
        assert jsm.agents["agent-a"] == "RUNNING"

    def test_advance(self):
        jsm = JointStateMachine()
        jsm.register_agent("agent-a")
        jsm.advance("agent-a", "RUNNING")
        assert jsm.agents["agent-a"] == "RUNNING"

    def test_advance_all_to(self):
        jsm = JointStateMachine()
        jsm.register_agent("a")
        jsm.register_agent("b")
        jsm.advance_all_to("DONE")
        assert jsm.agents == {"a": "DONE", "b": "DONE"}

    def test_arbitrate(self):
        jsm = JointStateMachine()
        resolution = jsm.arbitrate("a", "b", "resource conflict")
        assert "resource conflict" in resolution
        assert len(jsm.conflict_log) == 1
        assert jsm.conflict_log[0]["issue"] == "resource conflict"

    def test_agent_count(self):
        jsm = JointStateMachine()
        assert jsm.agent_count() == 0
        jsm.register_agent("a")
        assert jsm.agent_count() == 1

    def test_agent_states(self):
        jsm = JointStateMachine()
        jsm.register_agent("a")
        assert jsm.agent_states() == {"a": "IDLE"}

    def test_reset(self):
        jsm = JointStateMachine()
        jsm.register_agent("a")
        jsm.advance("a", "RUNNING")
        jsm.arbitrate("a", "b", "issue")
        jsm.reset()
        assert jsm.agent_count() == 0
        assert len(jsm.conflict_log) == 0

    def test_initiate_handoff(self):
        jsm = JointStateMachine()
        jsm.register_agent("src")
        jsm.register_agent("tgt")
        result = jsm.initiate_handoff("src", "tgt")
        assert result is True
        assert jsm.agents["src"] == "HANDOFF_SOURCE"
        assert jsm.agents["tgt"] == "HANDOFF_TARGET"

    def test_initiate_handoff_missing_agent(self):
        jsm = JointStateMachine()
        jsm.register_agent("src")
        result = jsm.initiate_handoff("src", "missing")
        assert result is False

    def test_initiate_handoff_already_in_handoff(self):
        jsm = JointStateMachine()
        jsm.register_agent("src")
        jsm.register_agent("tgt")
        jsm.register_agent("tgt2")
        jsm.initiate_handoff("src", "tgt")
        result = jsm.initiate_handoff("src", "tgt2")
        assert result is False

    def test_complete_handoff(self):
        jsm = JointStateMachine()
        jsm.register_agent("src")
        jsm.register_agent("tgt")
        jsm.initiate_handoff("src", "tgt")
        result = jsm.complete_handoff("src")
        assert result is True
        assert jsm.agents["src"] == "DONE"
        assert jsm.agents["tgt"] == "RUNNING"

    def test_complete_handoff_invalid_state(self):
        jsm = JointStateMachine()
        result = jsm.complete_handoff("nonexistent")
        assert result is False

    def test_rollback_handoff(self):
        jsm = JointStateMachine()
        jsm.register_agent("src")
        jsm.register_agent("tgt")
        jsm.initiate_handoff("src", "tgt")
        result = jsm.rollback_handoff("src")
        assert result is True
        assert jsm.agents["src"] == "RUNNING"
        assert jsm.agents["tgt"] == "IDLE"

    def test_rollback_handoff_nonexistent(self):
        jsm = JointStateMachine()
        result = jsm.rollback_handoff("nonexistent")
        assert result is False

    def test_check_handoff_timeout(self):
        jsm = JointStateMachine()
        jsm.register_agent("src")
        jsm.register_agent("tgt")
        jsm.initiate_handoff("src", "tgt", timeout_seconds=-1)
        timed_out = jsm.check_handoff_timeout()
        assert len(timed_out) > 0

    def test_is_in_handoff(self):
        jsm = JointStateMachine()
        jsm.register_agent("src")
        jsm.register_agent("tgt")
        assert jsm.is_in_handoff("src") is False
        jsm.initiate_handoff("src", "tgt")
        assert jsm.is_in_handoff("src") is True
        assert jsm.is_in_handoff("tgt") is True

    def test_is_in_handoff_nonexistent(self):
        jsm = JointStateMachine()
        assert jsm.is_in_handoff("nonexistent") is False

    def test_handoff_partner(self):
        jsm = JointStateMachine()
        jsm.register_agent("src")
        jsm.register_agent("tgt")
        jsm.initiate_handoff("src", "tgt")
        assert jsm.handoff_partner("src") == "tgt"
        assert jsm.handoff_partner("tgt") == "src"

    def test_handoff_partner_none(self):
        jsm = JointStateMachine()
        assert jsm.handoff_partner("nonexistent") is None

    def test_active_handoffs(self):
        jsm = JointStateMachine()
        jsm.register_agent("src")
        jsm.register_agent("tgt")
        assert jsm.active_handoffs() == {}
        jsm.initiate_handoff("src", "tgt")
        assert "src" in jsm.active_handoffs()
