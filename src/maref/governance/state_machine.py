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

import fcntl
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from threading import RLock
from typing import Any

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

logger = logging.getLogger(__name__)


def _default_audit_log_path() -> Path:
    """Return default audit log path."""
    base = Path(os.environ.get("MAREF_AUDIT_PATH", ".governance"))
    candidate = base / "governance_audit.jsonl"
    if candidate.parent.exists():
        return candidate
    return Path.cwd() / "governance_audit.jsonl"


def _actor_audit_log_path(actor: str) -> Path:
    """Return shard audit log path for a specific actor."""
    base = Path(os.environ.get("MAREF_AUDIT_PATH", ".governance"))
    safe_actor = actor.replace("-", "_").replace("/", "_")
    shard = base / f"governance_audit_{safe_actor}.jsonl"
    return shard


def _append_record_locked(fh, record: dict[str, Any]) -> None:
    """Append a JSON record to an open file handle with POSIX advisory lock."""
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    try:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        fh.flush()
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _last_chain_hash(log_path: Path) -> str:
    """Read the last non-empty record's chain_hash without scanning the full file.

    Seeks to the file tail (last 64KB, audit lines are small) and walks
    backwards to the first complete JSON line — O(1) instead of O(n).
    """
    try:
        with open(log_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            if size == 0:
                return ""
            chunk_size = min(size, 65536)
            fh.seek(size - chunk_size)
            tail = fh.read(chunk_size).decode("utf-8", errors="replace")
        for line in reversed(tail.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                prev = json.loads(line)
                return prev.get("chain_hash", prev.get("id", ""))
            except json.JSONDecodeError:
                # Only a line truncated at the seek boundary can fail to parse
                continue
    except OSError:
        pass
    return ""


def _write_state_transition(event: StateTransition, actor: str = "state_machine") -> None:
    """Append a state_transition record to the audit log (best-effort).

    Writes to both the global log and a per-actor shard for isolation.
    Uses POSIX advisory locks to prevent inter-process corruption.

    v0.50 W1-S1 (A9): fail-closed — when ``MAREF_HMAC_SECRET_KEY`` is not set,
    refuse to write an unsigned chain instead of silently degrading to a bare
    SHA-256 hash (tamperable). Aligns with ``AuditLogger`` (audit.py:220).
    """
    _hmac_key = os.environ.get("MAREF_HMAC_SECRET_KEY", "").encode("utf-8")
    if not _hmac_key:
        raise ValueError(
            "MAREF_HMAC_SECRET_KEY is not set — refusing to write unauthenticated "
            "governance audit chain (fail-closed). Set MAREF_HMAC_SECRET_KEY or "
            "route through AuditLogger with an Ed25519 keypair."
        )
    log_path = _default_audit_log_path()
    shard_path = _actor_audit_log_path(actor)
    try:
        previous_hash = _last_chain_hash(log_path) if log_path.exists() else ""

        payload = json.dumps(
            {
                "id": f"audit_{uuid.uuid4().hex[:8]}",
                "timestamp": time.time(),
                "event_type": "state_transition",
                "actor": actor,
                "action": f"{event.from_state.name}_to_{event.to_state.name}",
                "details": event.reason or f"Gray code transition {event.from_state.name} → {event.to_state.name}",
                "metadata": {
                    "from_state": event.from_state.name,
                    "from_state_id": event.from_state.value,
                    "to_state": event.to_state.name,
                    "to_state_id": event.to_state.value,
                    "entropy_before": _ENTROPY_LEVELS.get(event.from_state, 0),
                    "entropy_after": _ENTROPY_LEVELS.get(event.to_state, 0),
                    "previous_hash": previous_hash,
                },
                "previous_hash": previous_hash,
            },
            ensure_ascii=False,
            default=str,
        )
        # HMAC-SHA256 signing matching AuditLogger security level
        chain_hash = hmac.new(_hmac_key, payload.encode(), hashlib.sha256).hexdigest()

        record = json.loads(payload)
        record["chain_hash"] = chain_hash

        # Global log (backward compatible)
        with open(log_path, "a") as f:
            _append_record_locked(f, record)

        # Per-actor shard (isolation)
        shard_path.parent.mkdir(parents=True, exist_ok=True)
        with open(shard_path, "a") as f:
            _append_record_locked(f, record)
    except Exception:
        logger.exception("Audit write failed, falling back to stdout")
        import sys
        _append_record_locked(sys.stdout, record)

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
        self._lock: RLock = RLock()
        self._force_authorizer: Callable[[str, str], bool] | None = None
        self._enforce_force_authorization: bool = False

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

        v0.50 W1-S1 (A9): the audit chain is written before the state change
        is committed, so a fail-closed (missing HMAC key) audit write aborts
        the transition without mutating the state machine.
        """
        with self._lock:
            if not self.can_transition(target):
                return False

            event = StateTransition(
                from_state=self._state,
                to_state=target,
                reason=reason,
            )

            _write_state_transition(event)

            self._state = target
            self._history.append(event)
            self._entropy_history.append(self.current_entropy)
            self._transition_count += 1

            self._notify_callbacks(event)
            return True

    # --- Force Operations ---

    def configure_force_authorization(
        self,
        enforce: bool,
        authorizer: Callable[[str, str], bool] | None,
    ) -> None:
        """Configure authorization for force operations (v0.50 W1-S2 / A12).

        Args:
            enforce: When True, force operations require an actor approved by
                ``authorizer``; unauthorized calls raise :class:`PermissionError`.
            authorizer: Callable ``(actor, reason) -> bool`` deciding whether the
                actor is allowed to force-transition. Must be provided when
                ``enforce`` is True.

        Raises:
            RuntimeError: If ``enforce`` is True but ``authorizer`` is None.
        """
        if enforce and authorizer is None:
            raise RuntimeError(
                "force_authorization enforce=True requires an authorizer callable"
            )
        self._enforce_force_authorization = enforce
        self._force_authorizer = authorizer

    def _check_force_authorization(self, actor: str, reason: str) -> None:
        """Raise PermissionError when force authorization is enforced and denied."""
        if not self._enforce_force_authorization:
            return
        if self._force_authorizer is None:
            raise RuntimeError("force authorization enforced but authorizer is unset")
        if not self._force_authorizer(actor, reason):
            raise PermissionError(
                f"Force operation denied: actor {actor!r} not authorized to "
                f"force-transition (reason={reason!r})"
            )

    def force_stabilize(self, reason: str = "entropy_threshold", actor: str = "state_machine") -> bool:
        """
        Force transition to STABILIZE via BFS shortest path.

        Can reach STABILIZE from any non-HALT state by walking
        through valid intermediate states.

        v0.50 W1-S2 (A12): when force authorization is enforced, requires an
        actor approved by the configured authorizer.
        """
        self._check_force_authorization(actor, reason)
        with self._lock:
            if self._state == GovernanceState.HALT:
                return False
            if self.can_transition(GovernanceState.STABILIZE):
                return self.transition(GovernanceState.STABILIZE, reason)
            return self._bfs_to(GovernanceState.STABILIZE, reason)

    def force_halt(self, reason: str = "emergency", actor: str = "state_machine") -> bool:
        """Force transition to HALT via BFS shortest path."""
        self._check_force_authorization(actor, reason)
        with self._lock:
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

    def health_check(self) -> dict[str, Any]:
        """Export runtime health state for MAS-TS-001 D4 auditing."""
        return {
            "current_state": self._state.name,
            "current_entropy": float(self.current_entropy),
            "transition_count": self._transition_count,
            "is_terminal": self.is_terminal(),
            "valid_next_states": [s.name for s in self.valid_next_states],
            "entropy_trend": self.get_entropy_trend(),
        }

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
        """Restore a state machine from a previously taken snapshot.

        v0.50 W1-S3 (A8): rebuild the transition history chain from
        ``snapshot.history_entries`` so audit traceability survives a restore.
        """
        sm = cls()
        sm._state = snapshot.current_state
        sm._entropy_history = list(snapshot.entropy_history)
        sm._transition_count = snapshot.transition_count
        sm._history = [
            StateTransition(
                from_state=GovernanceState[entry["from_state"]],
                to_state=GovernanceState[entry["to_state"]],
                reason=entry.get("reason", ""),
            )
            for entry in snapshot.history_entries
        ]
        return sm

    # --- Internal ---

    def _notify_callbacks(self, event: StateTransition) -> None:
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                logger.exception("Callback %s failed, isolating", getattr(cb, '__name__', str(cb)))

    def __repr__(self) -> str:
        return (
            f"GovernanceStateMachine(state={self._state.name}, "
            f"entropy={self.current_entropy}, "
            f"transitions={self._transition_count})"
        )
