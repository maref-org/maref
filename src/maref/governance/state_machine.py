"""
MAREF Governance State Machine

10-state Gray code state machine with entropy-based governance,
single-bit transitions, and pickle-safe snapshot/restore.

Key properties:
- Each transition changes exactly ONE bit — prevents race conditions
- HALT state is terminal and absorbing (no outgoing edges)
- Entropy profile: INIT(0) → ACT(4) → HALT(0) forming a mountain curve
- force_stabilize() uses BFS to find shortest path to STABILIZE
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable

from maref.governance.constants import (
    ENTROPY_LEVELS as _ENTROPY_LEVELS_INT,
)
from maref.governance.constants import (
    compute_valid_transitions as _compute_valid_transitions,
)
from maref.governance.types import (
    GovernanceState,
    StateMachineSnapshot,
    StateTransition,
)

_ENTROPY_LEVELS: dict[GovernanceState, int] = {
    GovernanceState(s): e for s, e in _ENTROPY_LEVELS_INT.items()
}


_VALID_TRANSITIONS: dict[GovernanceState, list[GovernanceState]] = {
    GovernanceState(s): [GovernanceState(t) for t in targets]
    for s, targets in _compute_valid_transitions().items()
}


class GovernanceStateMachine:
    """
    MAREF governance state machine.

    Manages agent lifecycle through 10 Gray code states with
    entropy-based governance decisions. Supports callback
    registration for external observers and pickle-safe
    snapshot/restore for persistence.

    Usage:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start monitoring")
        snapshot = sm.snapshot()
        # ... later ...
        sm2 = GovernanceStateMachine.restore(snapshot)
    """

    def __init__(self) -> None:
        self._state: GovernanceState = GovernanceState.INIT
        self._history: list[StateTransition] = []
        self._callbacks: list[Callable[[StateTransition], None]] = []
        self._entropy_history: list[int] = []
        self._transition_count: int = 0

    # --- Properties ---

    @property
    def current_state(self) -> GovernanceState:
        """Current governance state."""
        return self._state

    @property
    def current_entropy(self) -> int:
        """Current entropy level (0-4)."""
        return _ENTROPY_LEVELS[self._state]

    @property
    def transition_count(self) -> int:
        """Total number of successful transitions."""
        return self._transition_count

    @property
    def valid_next_states(self) -> list[GovernanceState]:
        """List of valid next states from current state."""
        return list(_VALID_TRANSITIONS[self._state])

    # --- Callbacks ---

    def add_callback(self, callback: Callable[[StateTransition], None]) -> None:
        """Register a callback invoked on each successful transition."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[StateTransition], None]) -> None:
        """Remove a previously registered callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    # --- Transition ---

    def can_transition(self, target: GovernanceState) -> bool:
        """Check if transition to target is valid from current state."""
        if self._state == GovernanceState.HALT:
            return False
        return target in _VALID_TRANSITIONS[self._state]

    def transition(self, target: GovernanceState, reason: str = "") -> bool:
        """
        Attempt to transition to target state.

        Returns True if the transition was accepted.
        """
        if not self.can_transition(target):
            return False

        event = StateTransition(
            from_state=self._state,
            to_state=target,
            reason=reason,
        )

        self._state = target
        self._history.append(event)
        self._entropy_history.append(self.current_entropy)
        self._transition_count += 1

        self._notify_callbacks(event)
        return True

    # --- Force Operations ---

    def force_stabilize(self, reason: str = "entropy_threshold") -> bool:
        """
        Force transition to STABILIZE via BFS shortest path.

        Can reach STABILIZE from any non-HALT state by walking
        through valid intermediate states.
        """
        if self._state == GovernanceState.HALT:
            return False
        if self.can_transition(GovernanceState.STABILIZE):
            return self.transition(GovernanceState.STABILIZE, reason)
        return self._bfs_to(GovernanceState.STABILIZE, reason)

    def force_halt(self, reason: str = "emergency") -> bool:
        """Force transition to HALT via BFS shortest path."""
        if self._state == GovernanceState.HALT:
            return False
        if self.can_transition(GovernanceState.HALT):
            return self.transition(GovernanceState.HALT, reason)
        if self.can_transition(GovernanceState.REPORT):
            self.transition(GovernanceState.REPORT, "pre_halt")
            if self.can_transition(GovernanceState.HALT):
                return self.transition(GovernanceState.HALT, reason)
        return self._bfs_to(GovernanceState.HALT, reason)

    def _bfs_to(self, target: GovernanceState, reason: str) -> bool:
        """Find and execute shortest path to target via BFS."""
        visited: set[GovernanceState] = {self._state}
        queue: list[tuple[GovernanceState, list[GovernanceState]]] = [(self._state, [])]
        while queue:
            current, path = queue.pop(0)
            for neighbor in _VALID_TRANSITIONS[current]:
                if neighbor in visited:
                    continue
                if neighbor == target:
                    for intermediate in path:
                        self.transition(intermediate, reason)
                    return self.transition(target, reason)
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
        return False

    # --- History & Statistics ---

    def get_history(self) -> list[StateTransition]:
        """Return a copy of the full transition history."""
        return list(self._history)

    def get_entropy_trend(self) -> dict[str, float]:
        """Return entropy statistics (mean, max, current)."""
        if not self._entropy_history:
            return {"mean": 0.0, "max": 0.0, "current": 0.0}
        return {
            "mean": sum(self._entropy_history) / len(self._entropy_history),
            "max": float(max(self._entropy_history)),
            "current": float(self.current_entropy),
        }

    def is_terminal(self) -> bool:
        """True if the state machine has reached a terminal state."""
        return self._state == GovernanceState.HALT

    def get_valid_next_states(self) -> list[GovernanceState]:
        """List of valid next states from current state (deprecated, use valid_next_states)."""
        return self.valid_next_states

    # --- Snapshot / Restore ---

    def snapshot(self) -> StateMachineSnapshot:
        """Create a pickle-safe snapshot of the current state machine."""
        return StateMachineSnapshot(
            current_state=self._state,
            current_entropy=self.current_entropy,
            entropy_history=list(self._entropy_history),
            history_length=len(self._history),
            transition_count=self._transition_count,
            valid_next_states=list(self.valid_next_states),
            is_terminal=self.is_terminal(),
            history_entries=[
                {"from_state": t.from_state.name, "to_state": t.to_state.name, "reason": t.reason}
                for t in self._history[-200:]
            ],
        )

    @classmethod
    def restore(cls, snapshot: StateMachineSnapshot) -> GovernanceStateMachine:
        """Restore a state machine from a previously taken snapshot."""
        sm = cls()
        sm._state = snapshot.current_state
        sm._entropy_history = list(snapshot.entropy_history)
        sm._transition_count = snapshot.transition_count
        sm._history = []
        return sm

    # --- Internal ---

    def _notify_callbacks(self, event: StateTransition) -> None:
        for cb in self._callbacks:
            with contextlib.suppress(Exception):
                cb(event)

    def __repr__(self) -> str:
        return (
            f"GovernanceStateMachine(state={self._state.name}, "
            f"entropy={self.current_entropy}, "
            f"transitions={self._transition_count})"
        )
