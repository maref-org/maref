"""
GovernanceStateMachine extended tests.

Covers: all valid/invalid transitions, entropy lifecycle, BFS stabilize/halt
from every non-HALT state, snapshot/restore roundtrip, concurrent safety,
HALT absorption, health_check, repr, and callback error isolation.
"""

from __future__ import annotations

import threading
from unittest.mock import patch

from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState

# Gray code single-bit transitions computed from constants.GRAY_CODE.
# Each source→target pair has Hamming distance exactly 1.
# HALT is terminal (no outgoing edges).
_VALID_FROM: dict[GovernanceState, set[GovernanceState]] = {
    GovernanceState.INIT: {GovernanceState.OBSERVE, GovernanceState.EVALUATE, GovernanceState.STABILIZE},
    GovernanceState.OBSERVE: {GovernanceState.INIT, GovernanceState.ANALYZE, GovernanceState.VERIFY},
    GovernanceState.ANALYZE: {GovernanceState.OBSERVE, GovernanceState.EVALUATE, GovernanceState.ACT},
    GovernanceState.EVALUATE: {GovernanceState.INIT, GovernanceState.ANALYZE, GovernanceState.DECIDE},
    GovernanceState.DECIDE: {GovernanceState.EVALUATE, GovernanceState.ACT, GovernanceState.STABILIZE},
    GovernanceState.ACT: {GovernanceState.ANALYZE, GovernanceState.DECIDE, GovernanceState.VERIFY},
    GovernanceState.VERIFY: {GovernanceState.OBSERVE, GovernanceState.ACT, GovernanceState.STABILIZE, GovernanceState.HALT},
    GovernanceState.STABILIZE: {GovernanceState.INIT, GovernanceState.DECIDE, GovernanceState.VERIFY, GovernanceState.REPORT},
    GovernanceState.REPORT: {GovernanceState.STABILIZE, GovernanceState.HALT},
    GovernanceState.HALT: set(),
}

_ALL_STATES = list(GovernanceState)


class TestStateTransitions:
    def test_all_valid_transitions_succeed(self):
        for from_state, targets in _VALID_FROM.items():
            for to_state in targets:
                sm = GovernanceStateMachine()
                sm._state = from_state
                with patch("maref.governance.state_machine._write_state_transition"):
                    result = sm.transition(to_state, "test")
                assert result is True, (
                    f"Expected valid transition {from_state.name} → {to_state.name}"
                )
                assert sm.current_state == to_state

    def test_all_invalid_transitions_fail(self):
        for from_state in _ALL_STATES:
            valid_set = _VALID_FROM[from_state]
            invalid = [s for s in _ALL_STATES if s != from_state and s not in valid_set]
            for to_state in invalid:
                sm = GovernanceStateMachine()
                sm._state = from_state
                with patch("maref.governance.state_machine._write_state_transition"):
                    result = sm.transition(to_state, "test")
                assert result is False, (
                    f"Expected invalid transition {from_state.name} → {to_state.name}"
                )
                assert sm.current_state == from_state

    def test_can_transition_halt_returns_false_for_all(self):
        sm = GovernanceStateMachine()
        sm._state = GovernanceState.HALT
        for target in _ALL_STATES:
            assert sm.can_transition(target) is False

    def test_can_transition_returns_true_for_valid(self):
        for from_state, targets in _VALID_FROM.items():
            if from_state == GovernanceState.HALT:
                continue
            sm = GovernanceStateMachine()
            sm._state = from_state
            for target in targets:
                assert sm.can_transition(target) is True

    def test_transition_count_increments(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            assert sm.transition_count == 0
            sm.transition(GovernanceState.OBSERVE, "start")
            assert sm.transition_count == 1
            sm.transition(GovernanceState.ANALYZE, "analyze")
            assert sm.transition_count == 2

    def test_transition_count_not_incremented_on_failure(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm.transition(GovernanceState.HALT, "try")
            assert sm.transition_count == 0

    def test_history_recorded(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm.transition(GovernanceState.OBSERVE, "reason_1")
            sm.transition(GovernanceState.ANALYZE, "reason_2")
            history = sm.get_history()
        assert len(history) == 2
        assert history[0].from_state == GovernanceState.INIT
        assert history[0].to_state == GovernanceState.OBSERVE
        assert history[0].reason == "reason_1"
        assert history[1].reason == "reason_2"

    def test_valid_next_states_property(self):
        sm = GovernanceStateMachine()
        assert set(sm.valid_next_states) == _VALID_FROM[GovernanceState.INIT]

    def test_get_valid_next_states_deprecated(self):
        sm = GovernanceStateMachine()
        assert sm.get_valid_next_states() == sm.valid_next_states


class TestEntropy:
    def test_entropy_mountain_curve(self):
        known_entropy = {
            GovernanceState.INIT: 0,
            GovernanceState.OBSERVE: 1,
            GovernanceState.ANALYZE: 2,
            GovernanceState.EVALUATE: 2,
            GovernanceState.DECIDE: 3,
            GovernanceState.ACT: 4,
            GovernanceState.VERIFY: 3,
            GovernanceState.STABILIZE: 1,
            GovernanceState.REPORT: 0,
            GovernanceState.HALT: 0,
        }
        for state, expected in known_entropy.items():
            sm = GovernanceStateMachine()
            sm._state = state
            assert sm.current_entropy == expected, f"{state.name}: expected {expected}"

    def test_entropy_history_recorded(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm.transition(GovernanceState.OBSERVE, "step1")
            sm.transition(GovernanceState.ANALYZE, "step2")
            assert sm._entropy_history == [1, 2]

    def test_entropy_trend_empty(self):
        sm = GovernanceStateMachine()
        trend = sm.get_entropy_trend()
        assert trend == {"mean": 0.0, "max": 0.0, "current": 0.0}

    def test_entropy_trend_after_transitions(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm.transition(GovernanceState.OBSERVE, "")
            trend = sm.get_entropy_trend()
        assert trend["mean"] == 1.0
        assert trend["max"] == 1.0
        assert trend["current"] == 1.0

    def test_entropy_trend_after_multiple(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm.transition(GovernanceState.OBSERVE, "")
            sm.transition(GovernanceState.ANALYZE, "")
            trend = sm.get_entropy_trend()
        assert trend["mean"] == (1 + 2) / 2
        assert trend["max"] == 2.0
        assert trend["current"] == 2.0


class TestForceStabilizeBFS:
    def test_force_stabilize_from_init(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            assert sm.force_stabilize("test") is True
            assert sm.current_state == GovernanceState.STABILIZE

    def test_force_stabilize_from_observe(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm._state = GovernanceState.OBSERVE
            assert sm.force_stabilize("test") is True
            assert sm.current_state == GovernanceState.STABILIZE

    def test_force_stabilize_from_evaluate(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm._state = GovernanceState.EVALUATE
            assert sm.force_stabilize("test") is True
            assert sm.current_state == GovernanceState.STABILIZE

    def test_force_stabilize_from_act(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm._state = GovernanceState.ACT
            assert sm.force_stabilize("test") is True
            assert sm.current_state == GovernanceState.STABILIZE

    def test_force_stabilize_from_verify(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm._state = GovernanceState.VERIFY
            assert sm.force_stabilize("test") is True
            assert sm.current_state == GovernanceState.STABILIZE

    def test_force_stabilize_from_report(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm._state = GovernanceState.REPORT
            assert sm.force_stabilize("test") is True
            assert sm.current_state == GovernanceState.STABILIZE

    def test_force_stabilize_from_halt_fails(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm._state = GovernanceState.HALT
            assert sm.force_stabilize("test") is False
            assert sm.current_state == GovernanceState.HALT

    def test_force_stabilize_path_correctness(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm._state = GovernanceState.REPORT
            sm.force_stabilize("test")
            history = sm.get_history()
            assert history[-1].to_state == GovernanceState.STABILIZE


class TestForceHaltBFS:
    def test_force_halt_from_all_non_halt_states(self):
        non_halt = [s for s in _ALL_STATES if s != GovernanceState.HALT]
        for state in non_halt:
            with patch("maref.governance.state_machine._write_state_transition"):
                sm = GovernanceStateMachine()
                sm._state = state
                result = sm.force_halt("emergency")
            assert result is True, f"force_halt from {state.name} failed"
            assert sm.current_state == GovernanceState.HALT

    def test_force_halt_from_halt_fails(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm._state = GovernanceState.HALT
            assert sm.force_halt("emergency") is False
            assert sm.current_state == GovernanceState.HALT

    def test_force_halt_path_ends_at_halt(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm._state = GovernanceState.VERIFY
            sm.force_halt("emergency")
            history = sm.get_history()
            assert history[-1].to_state == GovernanceState.HALT


class TestSnapshotRestore:
    def test_snapshot_basic(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm.transition(GovernanceState.OBSERVE, "step1")
            sm.transition(GovernanceState.ANALYZE, "step2")
            snapshot = sm.snapshot()
        assert snapshot.current_state == GovernanceState.ANALYZE
        assert snapshot.current_entropy == 2
        assert snapshot.transition_count == 2
        assert snapshot.history_length == 2
        assert not snapshot.is_terminal
        assert set(snapshot.valid_next_states) == _VALID_FROM[GovernanceState.ANALYZE]

    def test_snapshot_terminal(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm._state = GovernanceState.HALT
            snapshot = sm.snapshot()
        assert snapshot.is_terminal is True
        assert snapshot.valid_next_states == []

    def test_restore_roundtrip(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm.transition(GovernanceState.OBSERVE, "step1")
            sm.transition(GovernanceState.ANALYZE, "step2")
            sm.transition(GovernanceState.EVALUATE, "step3")
            snapshot = sm.snapshot()
        restored = GovernanceStateMachine.restore(snapshot)
        assert restored.current_state == GovernanceState.EVALUATE
        assert restored.current_entropy == 2
        assert restored.transition_count == 3
        assert restored._entropy_history == [1, 2, 2]
        assert not restored.is_terminal()

    def test_restore_terminal_state(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm._state = GovernanceState.HALT
            snapshot = sm.snapshot()
        restored = GovernanceStateMachine.restore(snapshot)
        assert restored.current_state == GovernanceState.HALT
        assert restored.is_terminal()

    def test_restored_machine_can_transition(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm.transition(GovernanceState.OBSERVE, "step1")
            snapshot = sm.snapshot()
        restored = GovernanceStateMachine.restore(snapshot)
        assert restored.can_transition(GovernanceState.ANALYZE)
        with patch("maref.governance.state_machine._write_state_transition"):
            restored.transition(GovernanceState.ANALYZE, "continue")
        assert restored.current_state == GovernanceState.ANALYZE
        assert restored.transition_count == 2

    def test_snapshot_contains_history_entries(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm.transition(GovernanceState.OBSERVE, "reason_x")
            snapshot = sm.snapshot()
        assert len(snapshot.history_entries) >= 1
        assert snapshot.history_entries[0]["from_state"] == "INIT"
        assert snapshot.history_entries[0]["to_state"] == "OBSERVE"
        assert snapshot.history_entries[0]["reason"] == "reason_x"

    def test_snapshot_history_entries_limited_to_200(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            for _ in range(250):
                sm._history.append(sm._history[-1]) if sm._history else sm._history.append(
                    sm.transition(GovernanceState.OBSERVE, "x") or True
                )
        # Reset and add dummy transitions via direct append
        sm = GovernanceStateMachine()
        from maref.governance.types import StateTransition
        sm._history = [
            StateTransition(from_state=GovernanceState.INIT, to_state=GovernanceState.OBSERVE, reason="fill")
            for _ in range(500)
        ]
        snapshot = sm.snapshot()
        assert len(snapshot.history_entries) <= 200

    def test_snapshot_to_dict(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm._state = GovernanceState.DECIDE
            snapshot = sm.snapshot()
            d = snapshot.to_dict()
        assert d["current_state"] == "DECIDE"
        assert d["current_state_id"] == 4
        assert d["current_entropy"] == 3


class TestHaltAbsorbing:
    def test_halt_is_terminal(self):
        sm = GovernanceStateMachine()
        sm._state = GovernanceState.HALT
        assert sm.is_terminal() is True

    def test_non_halt_not_terminal(self):
        sm = GovernanceStateMachine()
        assert sm.is_terminal() is False

    def test_no_transition_from_halt(self):
        sm = GovernanceStateMachine()
        sm._state = GovernanceState.HALT
        for target in _ALL_STATES:
            assert sm.transition(target) is False

    def test_can_transition_from_halt(self):
        sm = GovernanceStateMachine()
        sm._state = GovernanceState.HALT
        for target in _ALL_STATES:
            assert sm.can_transition(target) is False

    def test_valid_next_states_from_halt(self):
        sm = GovernanceStateMachine()
        sm._state = GovernanceState.HALT
        assert sm.valid_next_states == []


class TestConcurrentSafety:
    def test_concurrent_transitions_are_thread_safe(self):
        results: list[bool] = []
        errors: list[Exception] = []

        def worker(sm: GovernanceStateMachine, target: GovernanceState, results: list, errors: list):
            try:
                with patch("maref.governance.state_machine._write_state_transition"):
                    r = sm.transition(target, "concurrent")
                results.append(r)
            except Exception as e:
                errors.append(e)

        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            threads = []
            for target in [
                GovernanceState.OBSERVE,
                GovernanceState.HALT,
                GovernanceState.ANALYZE,
            ]:
                t = threading.Thread(target=worker, args=(sm, target, results, errors))
                threads.append(t)
                t.start()
            for t in threads:
                t.join()

        assert len(errors) == 0, f"Concurrent errors: {errors}"
        assert sm.transition_count >= 1

    def test_lock_is_rlock(self):
        sm = GovernanceStateMachine()
        assert isinstance(sm._lock, type(threading.RLock()))


class TestCallbacksExtended:
    def test_callback_exception_does_not_block_transition(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()

            def failing_cb(event):
                raise RuntimeError("callback failure")

            def working_cb(event):
                working_cb.called = True
            working_cb.called = False

            sm.add_callback(failing_cb)
            sm.add_callback(working_cb)
            result = sm.transition(GovernanceState.OBSERVE, "test")
        assert result is True
        assert working_cb.called is True

    def test_remove_unregistered_callback_is_safe(self):
        sm = GovernanceStateMachine()

        def cb(event):
            pass

        sm.remove_callback(cb)
        with patch("maref.governance.state_machine._write_state_transition"):
            result = sm.transition(GovernanceState.OBSERVE, "test")
        assert result is True

    def test_multiple_callbacks_all_invoked(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            calls1 = []
            calls2 = []

            def cb1(event):
                calls1.append(event)

            def cb2(event):
                calls2.append(event)

            sm.add_callback(cb1)
            sm.add_callback(cb2)
            sm.transition(GovernanceState.OBSERVE, "test")
        assert len(calls1) == 1
        assert len(calls2) == 1

    def test_remove_callback_stops_invocation(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            calls = []

            def cb(event):
                calls.append(event)

            sm.add_callback(cb)
            sm.remove_callback(cb)
            sm.transition(GovernanceState.OBSERVE, "test")
        assert len(calls) == 0


class TestHealthCheck:
    def test_health_check_structure(self):
        sm = GovernanceStateMachine()
        health = sm.health_check()
        assert "current_state" in health
        assert "current_entropy" in health
        assert "transition_count" in health
        assert "is_terminal" in health
        assert "valid_next_states" in health
        assert "entropy_trend" in health
        assert health["current_state"] == "INIT"
        assert health["current_entropy"] == 0.0
        assert health["transition_count"] == 0
        assert health["is_terminal"] is False
        assert "OBSERVE" in health["valid_next_states"]

    def test_health_check_after_transitions(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm.transition(GovernanceState.OBSERVE, "")
            health = sm.health_check()
        assert health["current_state"] == "OBSERVE"
        assert health["transition_count"] == 1

    def test_health_check_halt(self):
        sm = GovernanceStateMachine()
        sm._state = GovernanceState.HALT
        health = sm.health_check()
        assert health["is_terminal"] is True
        assert health["valid_next_states"] == []

    def test_repr(self):
        sm = GovernanceStateMachine()
        r = repr(sm)
        assert "INIT" in r
        assert "entropy=0" in r
        assert "transitions=0" in r

    def test_repr_after_transition(self):
        with patch("maref.governance.state_machine._write_state_transition"):
            sm = GovernanceStateMachine()
            sm.transition(GovernanceState.OBSERVE, "")
        r = repr(sm)
        assert "OBSERVE" in r
        assert "entropy=1" in r
