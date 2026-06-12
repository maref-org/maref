"""
GovernanceStateMachine 关键路径测试

覆盖审计问题 P16 扩展：force_stabilize、force_halt、回调触发、快照/恢复。
"""

from __future__ import annotations

import pytest

from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState


class TestForceStabilize:
    def test_force_stabilize_from_observe(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")
        result = sm.force_stabilize("test")
        assert result is True
        assert sm.current_state == GovernanceState.STABILIZE

    def test_force_stabilize_from_act(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")
        sm.transition(GovernanceState.ANALYZE, "analyze")
        sm.transition(GovernanceState.EVALUATE, "evaluate")
        sm.transition(GovernanceState.DECIDE, "decide")
        sm.transition(GovernanceState.ACT, "act")
        result = sm.force_stabilize("test")
        assert result is True
        assert sm.current_state == GovernanceState.STABILIZE

    def test_force_stabilize_from_halt_fails(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")
        sm.transition(GovernanceState.VERIFY, "verify")
        sm.transition(GovernanceState.HALT, "halt")
        result = sm.force_stabilize("test")
        assert result is False
        assert sm.current_state == GovernanceState.HALT

    def test_force_stabilize_from_init(self) -> None:
        sm = GovernanceStateMachine()
        result = sm.force_stabilize("test")
        assert result is True
        assert sm.current_state == GovernanceState.STABILIZE


class TestForceHalt:
    def test_force_halt_from_observe(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")
        result = sm.force_halt("test")
        assert result is True
        assert sm.current_state == GovernanceState.HALT

    def test_force_halt_from_analyze(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")
        sm.transition(GovernanceState.ANALYZE, "analyze")
        result = sm.force_halt("test")
        assert result is True
        assert sm.current_state == GovernanceState.HALT

    def test_force_halt_from_init(self) -> None:
        sm = GovernanceStateMachine()
        result = sm.force_halt("test")
        assert result is True
        assert sm.current_state == GovernanceState.HALT

    def test_force_halt_bfs_path(self) -> None:
        """HALT is not directly reachable from all states; BFS should find path."""
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")
        sm.transition(GovernanceState.ANALYZE, "analyze")
        sm.transition(GovernanceState.EVALUATE, "evaluate")
        result = sm.force_halt("test")
        assert result is True
        assert sm.current_state == GovernanceState.HALT


class TestCallbacks:
    def test_callback_triggered(self) -> None:
        sm = GovernanceStateMachine()
        called = []

        def callback(transition):
            called.append(transition)

        sm.add_callback(callback)
        sm.transition(GovernanceState.OBSERVE, "test")
        assert len(called) == 1
        assert called[0].to_state == GovernanceState.OBSERVE

    def test_callback_removed(self) -> None:
        sm = GovernanceStateMachine()
        called = []

        def callback(transition):
            called.append(transition)

        sm.add_callback(callback)
        sm.remove_callback(callback)
        sm.transition(GovernanceState.OBSERVE, "test")
        assert len(called) == 0

    def test_multiple_callbacks(self) -> None:
        sm = GovernanceStateMachine()
        calls1 = []
        calls2 = []

        def cb1(t):
            calls1.append(t)

        def cb2(t):
            calls2.append(t)

        sm.add_callback(cb1)
        sm.add_callback(cb2)
        sm.transition(GovernanceState.OBSERVE, "test")
        assert len(calls1) == 1
        assert len(calls2) == 1


class TestSnapshot:
    def test_snapshot_basic(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")
        snapshot = sm.snapshot()
        assert snapshot.current_state == GovernanceState.OBSERVE
        assert snapshot.current_entropy == 1
        assert snapshot.transition_count == 1

    def test_snapshot_terminal(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")
        sm.transition(GovernanceState.VERIFY, "verify")
        sm.transition(GovernanceState.HALT, "halt")
        snapshot = sm.snapshot()
        assert snapshot.is_terminal is True

    def test_snapshot_valid_next_states(self) -> None:
        sm = GovernanceStateMachine()
        snapshot = sm.snapshot()
        assert GovernanceState.OBSERVE in snapshot.valid_next_states
        assert GovernanceState.HALT not in snapshot.valid_next_states


class TestEdgeCases:
    def test_get_history(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "first")
        sm.transition(GovernanceState.ANALYZE, "second")
        history = sm.get_history()
        assert len(history) == 2
        assert history[0].reason == "first"
        assert history[1].reason == "second"

    def test_get_history_empty(self) -> None:
        sm = GovernanceStateMachine()
        assert sm.get_history() == []

    def test_force_halt_from_already_halt(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")
        sm.transition(GovernanceState.VERIFY, "verify")
        sm.transition(GovernanceState.HALT, "halt")
        result = sm.force_halt("another_halt")
        assert result is False
        assert sm.current_state == GovernanceState.HALT

    def test_force_halt_via_report_intermediate(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")
        sm.transition(GovernanceState.ANALYZE, "analyze")
        sm.transition(GovernanceState.EVALUATE, "evaluate")
        sm.transition(GovernanceState.DECIDE, "decide")
        sm.transition(GovernanceState.ACT, "act")
        sm.transition(GovernanceState.VERIFY, "verify")
        # From STABILIZE: REPORT is valid, then HALT via REPORT
        sm.transition(GovernanceState.STABILIZE, "stabilize")
        result = sm.force_halt("halt_after_stabilize")
        assert result is True
        assert sm.current_state == GovernanceState.HALT

    def test_get_valid_next_states(self) -> None:
        sm = GovernanceStateMachine()
        states = sm.get_valid_next_states()
        assert isinstance(states, list)
        assert GovernanceState.OBSERVE in states

    def test_get_valid_next_states_after_transition(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")
        states = sm.get_valid_next_states()
        assert GovernanceState.ANALYZE in states
        assert isinstance(states, list)
