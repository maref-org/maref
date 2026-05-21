from __future__ import annotations

from unittest.mock import MagicMock

from maref.governance.state_machine import (
    GovernanceState,
    GovernanceStateMachine,
)


class TestStateMachineEdgeCases:
    def test_remove_callback_existing(self) -> None:
        sm = GovernanceStateMachine()
        cb = MagicMock()
        sm.add_callback(cb)
        sm.remove_callback(cb)
        assert cb not in sm._callbacks

    def test_remove_callback_not_present(self) -> None:
        sm = GovernanceStateMachine()
        cb = MagicMock()
        sm.remove_callback(cb)
        assert cb not in sm._callbacks

    def test_force_halt_direct(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "t1")
        sm.transition(GovernanceState.ANALYZE, "t2")
        sm.transition(GovernanceState.EVALUATE, "t3")
        sm.transition(GovernanceState.DECIDE, "t4")
        sm.transition(GovernanceState.ACT, "t5")
        sm.transition(GovernanceState.VERIFY, "t6")
        sm.transition(GovernanceState.STABILIZE, "t7")
        sm.transition(GovernanceState.REPORT, "t8")
        assert sm.force_halt("emergency") is True
        assert sm.current_state == GovernanceState.HALT

    def test_force_halt_via_report(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "t1")
        sm.transition(GovernanceState.ANALYZE, "t2")
        sm.transition(GovernanceState.EVALUATE, "t3")
        sm.transition(GovernanceState.DECIDE, "t4")
        sm.transition(GovernanceState.ACT, "t5")
        sm.transition(GovernanceState.VERIFY, "t6")
        sm.transition(GovernanceState.STABILIZE, "t7")
        assert sm.force_halt("emergency_via_report") is True
        assert sm.current_state == GovernanceState.HALT

    def test_bfs_to_no_path(self) -> None:
        sm = GovernanceStateMachine()
        sm._state = GovernanceState.HALT
        result = sm._bfs_to(GovernanceState.OBSERVE, "no_path")
        assert result is False

    def test_notify_callbacks_exception_silent(self) -> None:
        sm = GovernanceStateMachine()
        cb = MagicMock(side_effect=RuntimeError("boom"))
        sm.add_callback(cb)
        sm._state = GovernanceState.OBSERVE
        result = sm.transition(GovernanceState.ANALYZE, "test")
        assert result is True

    def test_repr(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "t1")
        r = repr(sm)
        assert "GovernanceStateMachine" in r
        assert "OBSERVE" in r


class TestSnapshotRestore:
    def test_snapshot_roundtrip(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "t1")
        sm.transition(GovernanceState.ANALYZE, "t2")
        snap = sm.snapshot()
        restored = GovernanceStateMachine.restore(snap)
        assert restored.current_state == GovernanceState.ANALYZE
        assert restored._transition_count == 2


class TestEntropyTrend:
    def test_empty_entropy_trend(self) -> None:
        sm = GovernanceStateMachine()
        trend = sm.get_entropy_trend()
        assert trend["mean"] == 0.0
        assert trend["max"] == 0.0
        assert trend["current"] == 0.0

    def test_entropy_trend_with_data(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "t1")
        sm.transition(GovernanceState.ANALYZE, "t2")
        trend = sm.get_entropy_trend()
        assert trend["current"] >= 0
        assert isinstance(trend["max"], float)


class TestCanTransition:
    def test_cannot_transition_from_halt(self) -> None:
        sm = GovernanceStateMachine()
        sm.force_halt("emergency")
        assert sm.can_transition(GovernanceState.OBSERVE) is False

    def test_can_transition_to_valid(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "t1")
        assert sm.can_transition(GovernanceState.ANALYZE) is True

    def test_cannot_transition_to_invalid(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "t1")
        assert sm.can_transition(GovernanceState.HALT) is False

    def test_transition_to_invalid_returns_false(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "t1")
        result = sm.transition(GovernanceState.REPORT, "invalid")
        assert result is False
