"""Federated Cascade Circuit Breaker.

Multi-agent cascade fault isolation: when an upstream agent fails, every
agent that depends on it is notified and degraded, while unrelated agents
remain unaffected. The failing agent itself is isolated (rejects traffic);
once it recovers (probe success after cooldown), degraded dependents
automatically return to nominal.

Design (deliberately distinct from the single-agent
:class:`~maref.governance.circuit_breaker.CircuitBreaker`):

- Single-agent breaker: per-process state (recursion depth, oscillation,
  consecutive failures). No cross-agent signalling.
- Cascade breaker: a per-agent status overlay over a **dependency graph**.
  Agent states are :class:`CascadeStatus`:

  - ``NOMINAL``: healthy; all upstream dependencies healthy.
  - ``DEGRADED``: itself healthy, but an upstream dependency is isolated.
    Traffic is still allowed, but callers may select a fallback path.
  - ``ISOLATED``: this agent's own failure threshold was reached. Traffic
    is rejected until the cooldown elapses.
  - ``RECOVERING``: cooldown elapsed; a single probe call is permitted.
    Probe success → ``NOMINAL`` (dependents un-degrade); probe failure →
    ``ISOLATED`` again with an extended cooldown.

Propagation follows the declared dependency edges in reverse
(``upstream → dependents``). ``propagate_secondary`` extends the
notification transitively (dependents of dependents). Recovery is exact:
an agent is un-degraded only when every upstream it was degraded for has
recovered.

Reference: task_plan Phase 2.4 — 级联断路器（多 Agent 级联故障隔离）。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

# Maximum length of the in-memory trip ledger.
_MAX_TRIPS = 200


class CascadeStatus(str, Enum):
    """Per-agent cascade isolation status."""

    NOMINAL = "nominal"
    DEGRADED = "degraded"
    ISOLATED = "isolated"
    RECOVERING = "recovering"


@dataclass
class CascadeTrip:
    """Record of an isolation event and its cascade footprint."""

    timestamp: float
    agent_id: str
    reason: str
    affected: tuple[str, ...]
    action_taken: str


class FederationCascadeBreaker:
    """Multi-agent cascade fault isolation over a dependency graph.

    Usage::

        breaker = FederationCascadeBreaker(cooldown_seconds=30.0)
        breaker.declare_dependency(dependent="agent-a", upstream="agent-b")
        breaker.declare_dependency(dependent="agent-b", upstream="agent-c")

        # Agent C fails repeatedly → isolated; B degrades; A is untouched.
        breaker.record_failure("agent-c", reason="timeout")
        breaker.record_failure("agent-c")
        breaker.record_failure("agent-c")
        assert breaker.status("agent-c") == CascadeStatus.ISOLATED
        assert breaker.status("agent-b") == CascadeStatus.DEGRADED
        assert breaker.status("agent-a") == CascadeStatus.NOMINAL

        # After the cooldown, a probe succeeds and the cascade unwinds.
        assert breaker.can_proceed("agent-c")   # RECOVERING probe
        breaker.record_success("agent-c")
        assert breaker.status("agent-b") == CascadeStatus.NOMINAL
    """

    def __init__(
        self,
        cooldown_seconds: float = 30.0,
        max_failures: int = 3,
        propagate_secondary: bool = False,
        audit_logger: Any | None = None,
    ) -> None:
        """Initialize the cascade breaker.

        Args:
            cooldown_seconds: Time an isolated agent must wait before a
                half-open probe is permitted.
            max_failures: Consecutive failures required to isolate an agent.
            propagate_secondary: Whether degradation propagates transitively
                (dependents of dependents). Defaults to False, so a single
                point of failure only degrades its direct dependents.
            audit_logger: Optional :class:`~maref.governance.audit.AuditLogger`
                to record isolation events with HMAC signing.
        """
        self._cooldown = cooldown_seconds
        self._max_failures = max(1, max_failures)
        self._propagate_secondary = propagate_secondary
        self._audit_logger = audit_logger
        self._lock = threading.RLock()
        # agent_id -> list of upstream agents it depends on.
        self._dependencies: dict[str, list[str]] = {}
        # upstream agent_id -> list of agents that depend on it.
        self._dependents: dict[str, list[str]] = {}
        self._states: dict[str, CascadeStatus] = {}
        self._failure_counts: dict[str, int] = {}
        self._last_trip_time: dict[str, float] = {}
        # agent_id -> set of isolated upstreams currently degrading it.
        self._degraded_upstreams: dict[str, set[str]] = {}
        self._trips: list[CascadeTrip] = []

    # ── Graph management ────────────────────────────────────────────────

    def register_agent(self, agent_id: str) -> None:
        """Register an agent as a known node (idempotent)."""
        with self._lock:
            self._states.setdefault(agent_id, CascadeStatus.NOMINAL)
            self._dependencies.setdefault(agent_id, [])
            self._failure_counts.setdefault(agent_id, 0)

    def declare_dependency(self, dependent: str, upstream: str) -> None:
        """Declare that ``dependent`` depends on ``upstream``.

        If ``upstream`` is isolated, ``dependent`` is degraded (and,
        transitively, its own dependents when ``propagate_secondary``).
        """
        with self._lock:
            self.register_agent(dependent)
            self.register_agent(upstream)
            if upstream not in self._dependencies[dependent]:
                self._dependencies[dependent].append(upstream)
            dependents = self._dependents.setdefault(upstream, [])
            if dependent not in dependents:
                dependents.append(dependent)

    # ── Failure / success signalling ────────────────────────────────────

    def record_failure(self, agent_id: str, reason: str = "") -> tuple[str, ...]:
        """Record a failure for an agent.

        Once the consecutive-failure threshold is reached the agent is
        isolated and the isolation propagates to its dependents.

        Returns:
            The tuple of agents affected by this call (isolated or degraded),
            empty if the threshold was not reached.
        """
        with self._lock:
            self.register_agent(agent_id)
            state = self._states[agent_id]
            if state in (CascadeStatus.ISOLATED, CascadeStatus.RECOVERING):
                # Probe failed or still isolated: extend the cooldown.
                self._last_trip_time[agent_id] = time.time()
                self._states[agent_id] = CascadeStatus.ISOLATED
                return (agent_id,)
            self._failure_counts[agent_id] += 1
            if self._failure_counts[agent_id] < self._max_failures:
                return ()
            return self._isolate(
                agent_id,
                reason or f"consecutive_failures:{self._failure_counts[agent_id]}",
            )

    def record_success(self, agent_id: str) -> None:
        """Record a success.

        For a ``RECOVERING`` agent this completes the probe: the agent
        returns to ``NOMINAL`` and every dependent degraded because of it
        is un-degraded (exact recovery).
        """
        with self._lock:
            self.register_agent(agent_id)
            self._failure_counts[agent_id] = 0
            if self._states[agent_id] == CascadeStatus.RECOVERING:
                self._states[agent_id] = CascadeStatus.NOMINAL
                self._release_dependents(agent_id)

    def can_proceed(self, agent_id: str) -> bool:
        """Check whether an agent may execute.

        ``ISOLATED`` agents reject traffic until the cooldown elapses; a
        single probe is then permitted (``RECOVERING``). ``DEGRADED`` and
        ``NOMINAL`` agents always proceed.
        """
        with self._lock:
            self.register_agent(agent_id)
            if self._states[agent_id] == CascadeStatus.ISOLATED:
                if self._should_try_recover(agent_id):
                    self._states[agent_id] = CascadeStatus.RECOVERING
                    return True
                return False
            return True

    # ── Status / observability ──────────────────────────────────────────

    def status(self, agent_id: str) -> CascadeStatus:
        """Return the current status of an agent."""
        with self._lock:
            self.register_agent(agent_id)
            return self._states[agent_id]

    def get_status_map(self) -> dict[str, str]:
        """Return a sorted ``{agent_id: status}`` snapshot."""
        with self._lock:
            return {aid: s.value for aid, s in sorted(self._states.items())}

    def degraded_agents(self) -> list[str]:
        """Return agents currently in the ``DEGRADED`` state."""
        with self._lock:
            return [
                aid for aid, s in self._states.items()
                if s == CascadeStatus.DEGRADED
            ]

    def isolated_agents(self) -> list[str]:
        """Return agents currently in the ``ISOLATED`` state."""
        with self._lock:
            return [
                aid for aid, s in self._states.items()
                if s == CascadeStatus.ISOLATED
            ]

    def summary(self) -> dict[str, Any]:
        """Return a summary of the cascade breaker state."""
        with self._lock:
            counts: dict[str, int] = {s.value: 0 for s in CascadeStatus}
            for state in self._states.values():
                counts[state.value] += 1
            return {
                "total_agents": len(self._states),
                "status_counts": counts,
                "dependency_edges": sum(
                    len(u) for u in self._dependencies.values()
                ),
                "propagate_secondary": self._propagate_secondary,
                "cooldown_seconds": self._cooldown,
                "max_failures": self._max_failures,
                "trip_count": len(self._trips),
                "recent_trips": [
                    {
                        "timestamp": t.timestamp,
                        "agent_id": t.agent_id,
                        "reason": t.reason,
                        "affected": list(t.affected),
                    }
                    for t in self._trips[-5:]
                ],
            }

    def reset(self) -> None:
        """Reset every agent to ``NOMINAL`` and clear the trip ledger."""
        with self._lock:
            for agent_id in self._states:
                self._states[agent_id] = CascadeStatus.NOMINAL
            self._failure_counts.clear()
            self._last_trip_time.clear()
            self._degraded_upstreams.clear()
            self._trips.clear()

    # ── Internals ───────────────────────────────────────────────────────

    def _isolate(self, agent_id: str, reason: str) -> tuple[str, ...]:
        """Isolate an agent and degrade its dependents. Returns affected."""
        self._states[agent_id] = CascadeStatus.ISOLATED
        self._failure_counts[agent_id] = 0
        self._last_trip_time[agent_id] = time.time()

        affected = [agent_id]
        affected.extend(self._propagate(agent_id, visited={agent_id}))

        self._trips.append(
            CascadeTrip(
                timestamp=time.time(),
                agent_id=agent_id,
                reason=reason,
                affected=tuple(affected),
                action_taken="isolate_and_degrade_dependents",
            )
        )
        if len(self._trips) > _MAX_TRIPS:
            self._trips = self._trips[-_MAX_TRIPS:]

        self._audit(
            event_type="federation_cascade_isolated",
            actor="FederationCascadeBreaker",
            action="isolate",
            details=f"Isolated agent {agent_id}: {reason}; "
                    f"affected {len(affected) - 1} dependents",
            metadata={
                "agent_id": agent_id,
                "reason": reason,
                "affected": list(affected),
            },
        )
        return tuple(affected)

    def _propagate(self, upstream: str, visited: set[str]) -> list[str]:
        """Degrade direct (and optionally transitive) dependents of ``upstream``."""
        degraded: list[str] = []
        queue = [upstream]
        while queue:
            current = queue.pop(0)
            for dependent in self._dependents.get(current, []):
                if dependent in visited:
                    continue
                visited.add(dependent)
                self._degraded_upstreams.setdefault(dependent, set()).add(upstream)
                if self._states[dependent] != CascadeStatus.ISOLATED:
                    self._states[dependent] = CascadeStatus.DEGRADED
                degraded.append(dependent)
                if self._propagate_secondary:
                    queue.append(dependent)
        return degraded

    def _release_dependents(self, upstream: str) -> None:
        """Un-degrade dependents once ``upstream`` has recovered."""
        for dependent in self._dependents.get(upstream, []):
            reasons = self._degraded_upstreams.get(dependent)
            if reasons is None:
                continue
            reasons.discard(upstream)
            if not reasons and self._states[dependent] == CascadeStatus.DEGRADED:
                self._states[dependent] = CascadeStatus.NOMINAL

    def _should_try_recover(self, agent_id: str) -> bool:
        import random

        jitter = random.uniform(0, self._cooldown * 0.2)
        return (time.time() - self._last_trip_time.get(agent_id, 0.0)) > (
            self._cooldown + jitter
        )

    def _audit(
        self,
        event_type: str,
        actor: str,
        action: str,
        details: str,
        metadata: dict[str, Any],
    ) -> None:
        if self._audit_logger is None:
            return
        try:
            self._audit_logger.log(
                event_type=event_type,
                actor=actor,
                action=action,
                details=details,
                metadata=metadata,
            )
        except Exception:
            # Audit logging must never break the cascade isolation path.
            return


__all__ = [
    "CascadeStatus",
    "CascadeTrip",
    "FederationCascadeBreaker",
]
