"""Life State Machine — per-entity state transitions.

C33: Each life state has its own state machine:
    BIRTH → ACTIVE → DEGRADED → RECOVERING → TERMINATED
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class LifeState(str, Enum):
    """Canonical life state values."""

    BIRTH = "birth"
    ACTIVE = "active"
    DEGRADED = "degraded"
    RECOVERING = "recovering"
    TERMINATED = "terminated"


class TransitionError(Exception):
    pass


@dataclass
class LifeStateTransition:
    from_state: LifeState
    to_state: LifeState
    reason: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_state.value,
            "to": self.to_state.value,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


# Valid transitions: source -> set of allowed destinations
_VALID_TRANSITIONS: dict[LifeState, set[LifeState]] = {
    LifeState.BIRTH: {LifeState.ACTIVE, LifeState.TERMINATED},
    LifeState.ACTIVE: {LifeState.DEGRADED, LifeState.TERMINATED},
    LifeState.DEGRADED: {LifeState.RECOVERING, LifeState.TERMINATED},
    LifeState.RECOVERING: {LifeState.ACTIVE, LifeState.DEGRADED, LifeState.TERMINATED},
    LifeState.TERMINATED: set(),
}


class LifeStateMachine:
    """State machine for a single life state entity.

    Usage:
        sm = LifeStateMachine()
        sm.transition_to(LifeState.ACTIVE, reason="initialization_complete")
        assert sm.current == LifeState.ACTIVE
    """

    def __init__(self, initial: LifeState = LifeState.BIRTH) -> None:
        self._current = initial
        self._history: list[LifeStateTransition] = []
        self._subscribers: list[Callable[[LifeStateTransition], None]] = []
        self._entry_callbacks: dict[LifeState, list[Callable[[], None]]] = {
            s: [] for s in LifeState
        }
        self._exit_callbacks: dict[LifeState, list[Callable[[], None]]] = {
            s: [] for s in LifeState
        }

    @property
    def current(self) -> LifeState:
        return self._current

    @property
    def is_terminal(self) -> bool:
        return self._current == LifeState.TERMINATED

    @property
    def transition_count(self) -> int:
        return len(self._history)

    def can_transition(self, target: LifeState) -> bool:
        return target in _VALID_TRANSITIONS.get(self._current, set())

    def transition_to(self, target: LifeState, reason: str = "") -> LifeStateTransition:
        if not self.can_transition(target):
            raise TransitionError(
                f"Cannot transition from {self._current.value} to {target.value}"
            )
        self._run_exit_callbacks(self._current)
        transition = LifeStateTransition(
            from_state=self._current,
            to_state=target,
            reason=reason,
        )
        self._current = target
        self._history.append(transition)
        self._run_entry_callbacks(target)
        self._notify(transition)
        return transition

    def get_history(self) -> list[LifeStateTransition]:
        return list(self._history)

    def on_entry(self, state: LifeState, callback: Callable[[], None]) -> None:
        self._entry_callbacks.setdefault(state, []).append(callback)

    def on_exit(self, state: LifeState, callback: Callable[[], None]) -> None:
        self._exit_callbacks.setdefault(state, []).append(callback)

    def _run_entry_callbacks(self, state: LifeState) -> None:
        for cb in self._entry_callbacks.get(state, []):
            try:
                cb()
            except Exception:
                pass

    def _run_exit_callbacks(self, state: LifeState) -> None:
        for cb in self._exit_callbacks.get(state, []):
            try:
                cb()
            except Exception:
                pass

    def subscribe(self, callback: Callable[[LifeStateTransition], None]) -> None:
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[LifeStateTransition], None]) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def _notify(self, transition: LifeStateTransition) -> None:
        for cb in list(self._subscribers):
            try:
                cb(transition)
            except Exception:
                pass

    def to_dict(self) -> dict[str, Any]:
        return {
            "current": self._current.value,
            "is_terminal": self.is_terminal,
            "transition_count": self.transition_count,
            "history": [t.to_dict() for t in self._history],
        }
