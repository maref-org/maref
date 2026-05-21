"""Tests for C33: Life State Machine."""

from __future__ import annotations

import pytest

from maref.life_state.state_machine import (
    LifeState,
    LifeStateMachine,
    LifeStateTransition,
    TransitionError,
)


class TestLifeState:
    def test_all_states_defined(self):
        assert LifeState.BIRTH.value == "birth"
        assert LifeState.ACTIVE.value == "active"
        assert LifeState.DEGRADED.value == "degraded"
        assert LifeState.RECOVERING.value == "recovering"
        assert LifeState.TERMINATED.value == "terminated"

    def test_state_count(self):
        assert len(list(LifeState)) == 5


class TestLifeStateMachine:
    def test_default_initial_state(self):
        sm = LifeStateMachine()
        assert sm.current == LifeState.BIRTH
        assert not sm.is_terminal
        assert sm.transition_count == 0

    def test_birth_to_active(self):
        sm = LifeStateMachine()
        t = sm.transition_to(LifeState.ACTIVE, reason="init")
        assert sm.current == LifeState.ACTIVE
        assert t.from_state == LifeState.BIRTH
        assert t.to_state == LifeState.ACTIVE
        assert t.reason == "init"
        assert sm.transition_count == 1

    def test_active_to_degraded(self):
        sm = LifeStateMachine()
        sm.transition_to(LifeState.ACTIVE)
        sm.transition_to(LifeState.DEGRADED, reason="high_latency")
        assert sm.current == LifeState.DEGRADED

    def test_degraded_to_recovering(self):
        sm = LifeStateMachine()
        sm.transition_to(LifeState.ACTIVE)
        sm.transition_to(LifeState.DEGRADED)
        sm.transition_to(LifeState.RECOVERING, reason="healing_started")
        assert sm.current == LifeState.RECOVERING

    def test_recovering_to_active(self):
        sm = LifeStateMachine()
        sm.transition_to(LifeState.ACTIVE)
        sm.transition_to(LifeState.DEGRADED)
        sm.transition_to(LifeState.RECOVERING)
        sm.transition_to(LifeState.ACTIVE, reason="healed")
        assert sm.current == LifeState.ACTIVE

    def test_any_to_terminated(self):
        sm = LifeStateMachine()
        sm.transition_to(LifeState.ACTIVE)
        sm.transition_to(LifeState.TERMINATED, reason="shutdown")
        assert sm.current == LifeState.TERMINATED
        assert sm.is_terminal

    def test_terminated_no_transitions(self):
        sm = LifeStateMachine()
        sm.transition_to(LifeState.TERMINATED)
        assert not sm.can_transition(LifeState.ACTIVE)
        with pytest.raises(TransitionError):
            sm.transition_to(LifeState.ACTIVE)

    def test_invalid_transition_raises(self):
        sm = LifeStateMachine()
        with pytest.raises(TransitionError):
            sm.transition_to(LifeState.DEGRADED)

    def test_can_transition_check(self):
        sm = LifeStateMachine()
        assert sm.can_transition(LifeState.ACTIVE)
        assert sm.can_transition(LifeState.TERMINATED)
        assert not sm.can_transition(LifeState.DEGRADED)

    def test_history_tracking(self):
        sm = LifeStateMachine()
        sm.transition_to(LifeState.ACTIVE, reason="r1")
        sm.transition_to(LifeState.DEGRADED, reason="r2")
        history = sm.get_history()
        assert len(history) == 2
        assert history[0].reason == "r1"
        assert history[1].reason == "r2"

    def test_subscribe_and_notify(self):
        sm = LifeStateMachine()
        transitions: list[LifeStateTransition] = []
        sm.subscribe(lambda t: transitions.append(t))
        sm.transition_to(LifeState.ACTIVE)
        assert len(transitions) == 1
        assert transitions[0].to_state == LifeState.ACTIVE

    def test_unsubscribe(self):
        sm = LifeStateMachine()
        transitions: list[LifeStateTransition] = []
        handler = lambda t: transitions.append(t)
        sm.subscribe(handler)
        sm.unsubscribe(handler)
        sm.transition_to(LifeState.ACTIVE)
        assert len(transitions) == 0

    def test_entry_callback(self):
        sm = LifeStateMachine()
        called: list[str] = []
        sm.on_entry(LifeState.ACTIVE, lambda: called.append("entered_active"))
        sm.transition_to(LifeState.ACTIVE)
        assert called == ["entered_active"]

    def test_exit_callback(self):
        sm = LifeStateMachine()
        called: list[str] = []
        sm.on_exit(LifeState.BIRTH, lambda: called.append("exited_birth"))
        sm.transition_to(LifeState.ACTIVE)
        assert called == ["exited_birth"]

    def test_callback_exception_isolated(self):
        sm = LifeStateMachine()
        sm.on_entry(LifeState.ACTIVE, lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        sm.transition_to(LifeState.ACTIVE)
        assert sm.current == LifeState.ACTIVE

    def test_to_dict(self):
        sm = LifeStateMachine()
        sm.transition_to(LifeState.ACTIVE)
        d = sm.to_dict()
        assert d["current"] == "active"
        assert d["is_terminal"] is False
        assert d["transition_count"] == 1
        assert len(d["history"]) == 1

    def test_full_lifecycle(self):
        sm = LifeStateMachine()
        sm.transition_to(LifeState.ACTIVE)
        sm.transition_to(LifeState.DEGRADED)
        sm.transition_to(LifeState.RECOVERING)
        sm.transition_to(LifeState.ACTIVE)
        sm.transition_to(LifeState.TERMINATED)
        assert sm.is_terminal
        assert sm.transition_count == 5
