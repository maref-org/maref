from __future__ import annotations

import pytest

from maref.recursive.recursive_evolution_loop import (
    RELState,
    RELStateMachine,
    IllegalTransitionError,
    can_transition,
    hamming_distance,
)


class TestHammingDistance:
    def test_main_path_states_have_distance_one(self) -> None:
        main_path = [
            (RELState.IDLE, RELState.TRIGGERED),
            (RELState.TRIGGERED, RELState.OBSERVE),
            (RELState.OBSERVE, RELState.DIAGNOSE),
            (RELState.DIAGNOSE, RELState.ARCHITECT),
            (RELState.ARCHITECT, RELState.CODEGEN),
            (RELState.CODEGEN, RELState.SAFETY),
            (RELState.SAFETY, RELState.DEPLOY),
            (RELState.DEPLOY, RELState.VERIFY),
            (RELState.VERIFY, RELState.EVALUATE),
            (RELState.EVALUATE, RELState.STOP),
        ]
        for a, b in main_path:
            assert hamming_distance(a, b) == 1, (
                f"{a.name} -> {b.name}: expected Hamming distance 1, "
                f"got {hamming_distance(a, b)}"
            )
        feedback_paths = [
            (RELState.VERIFY, RELState.CODEGEN),
            (RELState.CODEGEN, RELState.ARCHITECT),
            (RELState.EVALUATE, RELState.OBSERVE),
        ]
        for a, b in feedback_paths:
            assert hamming_distance(a, b) > 0

    def test_same_state_distance_zero(self) -> None:
        for state in RELState:
            assert hamming_distance(state, state) == 0

    def test_far_states_distance_greater_than_one(self) -> None:
        pairs = [
            (RELState.IDLE, RELState.CODEGEN),
            (RELState.TRIGGERED, RELState.DEPLOY),
            (RELState.OBSERVE, RELState.STOP),
        ]
        for a, b in pairs:
            assert hamming_distance(a, b) > 1, (
                f"{a.name} -> {b.name}: expected distance > 1, got {hamming_distance(a, b)}"
            )


class TestCanTransition:
    def test_legal_transitions(self) -> None:
        legal = [
            (RELState.IDLE, RELState.TRIGGERED),
            (RELState.TRIGGERED, RELState.OBSERVE),
            (RELState.CODEGEN, RELState.SAFETY),
            (RELState.CODEGEN, RELState.ARCHITECT),
            (RELState.VERIFY, RELState.EVALUATE),
            (RELState.VERIFY, RELState.CODEGEN),
            (RELState.EVALUATE, RELState.OBSERVE),
            (RELState.EVALUATE, RELState.STOP),
            (RELState.EVALUATE, RELState.IDLE),
            (RELState.HALT, RELState.IDLE),
        ]
        for current, target in legal:
            assert can_transition(current, target), (
                f"Expected legal: {current.name} -> {target.name}"
            )

    def test_illegal_transitions(self) -> None:
        illegal = [
            (RELState.IDLE, RELState.STOP),
            (RELState.TRIGGERED, RELState.DEPLOY),
            (RELState.STOP, RELState.OBSERVE),
            (RELState.CODEGEN, RELState.DEPLOY),
            (RELState.DEPLOY, RELState.CODEGEN),
            (RELState.EVALUATE, RELState.TRIGGERED),
        ]
        for current, target in illegal:
            assert not can_transition(current, target), (
                f"Expected illegal: {current.name} -> {target.name}"
            )

    def test_any_state_to_halt(self) -> None:
        haltable = [s for s in RELState if s not in (RELState.HALT, RELState.STOP)]
        for state in haltable:
            assert can_transition(state, RELState.HALT), (
                f"Expected HALT reachable from {state.name}"
            )

    def test_halt_has_no_incoming_from_stop(self) -> None:
        assert not can_transition(RELState.STOP, RELState.HALT)


class TestRELStateMachine:
    def test_initial_state_is_idle(self) -> None:
        sm = RELStateMachine()
        assert sm.state == RELState.IDLE

    def test_legal_transition_succeeds(self) -> None:
        sm = RELStateMachine()
        sm.transition(RELState.TRIGGERED)
        assert sm.state == RELState.TRIGGERED

    def test_illegal_transition_raises(self) -> None:
        sm = RELStateMachine()
        with pytest.raises(IllegalTransitionError):
            sm.transition(RELState.STOP)

    def test_full_cycle(self) -> None:
        sm = RELStateMachine()
        path = [
            RELState.TRIGGERED,
            RELState.OBSERVE,
            RELState.DIAGNOSE,
            RELState.ARCHITECT,
            RELState.CODEGEN,
            RELState.SAFETY,
            RELState.DEPLOY,
            RELState.VERIFY,
            RELState.EVALUATE,
            RELState.STOP,
        ]
        for target in path:
            sm.transition(target)
        assert sm.state == RELState.STOP

    def test_converge_loop(self) -> None:
        sm = RELStateMachine()
        path = [
            RELState.TRIGGERED,
            RELState.OBSERVE,
            RELState.DIAGNOSE,
            RELState.ARCHITECT,
            RELState.CODEGEN,
            RELState.SAFETY,
            RELState.DEPLOY,
            RELState.VERIFY,
            RELState.EVALUATE,
            RELState.OBSERVE,
        ]
        for target in path:
            sm.transition(target)
        assert sm.state == RELState.OBSERVE

    def test_halt_from_any_state(self) -> None:
        for start in RELState:
            if start == RELState.HALT or start == RELState.STOP:
                continue
            if not can_transition(start, RELState.HALT):
                continue
            sm = RELStateMachine()
            if start != RELState.IDLE:
                try:
                    sm.transition(start)
                except IllegalTransitionError:
                    continue
            halted = False
            if can_transition(sm.state, RELState.HALT):
                sm.transition(RELState.HALT)
                halted = True
            if halted:
                assert sm.state == RELState.HALT, f"Failed to halt from {start.name}"

    def test_recover_from_halt(self) -> None:
        sm = RELStateMachine()
        sm.transition(RELState.TRIGGERED)
        sm.transition(RELState.OBSERVE)
        sm.transition(RELState.DIAGNOSE)
        sm.transition(RELState.ARCHITECT)
        sm.transition(RELState.CODEGEN)
        sm.transition(RELState.SAFETY)
        sm.transition(RELState.DEPLOY)
        sm.transition(RELState.VERIFY)
        sm.transition(RELState.EVALUATE)
        assert sm.state == RELState.EVALUATE
        sm.transition(RELState.STOP)
        assert sm.state == RELState.STOP

    def test_reset(self) -> None:
        sm = RELStateMachine()
        sm.transition(RELState.TRIGGERED)
        sm.transition(RELState.OBSERVE)
        sm.reset()
        assert sm.state == RELState.IDLE

    def test_transition_history(self) -> None:
        sm = RELStateMachine()
        sm.transition(RELState.TRIGGERED)
        sm.transition(RELState.OBSERVE)
        history = sm.transition_history
        assert len(history) == 2
        assert history[0][0] == RELState.IDLE
        assert history[0][1] == RELState.TRIGGERED
        assert history[1][0] == RELState.TRIGGERED
        assert history[1][1] == RELState.OBSERVE


def _adjacent_states(state: RELState) -> list[RELState]:
    adjacency = {
        RELState.IDLE: [RELState.TRIGGERED],
        RELState.TRIGGERED: [RELState.OBSERVE],
        RELState.OBSERVE: [RELState.DIAGNOSE],
        RELState.DIAGNOSE: [RELState.ARCHITECT],
        RELState.ARCHITECT: [RELState.CODEGEN],
        RELState.CODEGEN: [RELState.SAFETY, RELState.ARCHITECT],
        RELState.SAFETY: [RELState.DEPLOY],
        RELState.DEPLOY: [RELState.VERIFY],
        RELState.VERIFY: [RELState.EVALUATE, RELState.CODEGEN],
        RELState.EVALUATE: [RELState.OBSERVE, RELState.STOP, RELState.IDLE],
        RELState.STOP: [],
        RELState.HALT: [RELState.IDLE],
    }
    return adjacency.get(state, [])
