"""GaaS CircuitBreaker Pool — tenant-isolated circuit breaker instances.

Transforms the single-tenant CircuitBreaker into a multi-tenant service
where each (tenant, agent, action) tuple gets its own CB state.
"""

from __future__ import annotations

import time
from typing import Any

from maref.gaas.models import CircuitBreakerState as CBState
from maref.governance.circuit_breaker import BreakerState, CircuitBreaker


class CircuitBreakerPool:
    """Pool of circuit breakers keyed by (tenant_id, agent_id, action).

    Provides isolation between tenants and fine-grained per-action protection.
    """

    def __init__(
        self,
        max_depth: int = 3,
        max_oscillation_rate: float = 10.0,
        max_consecutive_failures: int = 5,
        cooldown_seconds: float = 30.0,
    ) -> None:
        self._max_depth = max_depth
        self._max_oscillation = max_oscillation_rate
        self._max_failures = max_consecutive_failures
        self._cooldown = cooldown_seconds
        self._pool: dict[str, CircuitBreaker] = {}
        self._stats: dict[str, dict[str, Any]] = {}

    def _key(self, tenant_id: str, agent_id: str, action: str) -> str:
        return f"{tenant_id}:{agent_id}:{action}"

    def _get_or_create(self, key: str) -> CircuitBreaker:
        if key not in self._pool:
            self._pool[key] = CircuitBreaker(
                max_depth=self._max_depth,
                max_oscillation_rate=self._max_oscillation,
                max_consecutive_failures=self._max_failures,
                cooldown_seconds=self._cooldown,
            )
            self._stats[key] = {
                "call_count": 0,
                "error_count": 0,
                "total_latency": 0.0,
                "last_access": time.time(),
            }
        return self._pool[key]

    def check(
        self,
        tenant_id: str,
        agent_id: str,
        action: str,
        depth: int = 0,
    ) -> tuple[bool, CBState]:
        """Check if action is allowed. Returns (allowed, cb_state)."""
        key = self._key(tenant_id, agent_id, action)
        cb = self._get_or_create(key)
        allowed = cb.check_depth(depth)
        state = self._map_state(cb.state)
        self._stats[key]["call_count"] += 1
        self._stats[key]["last_access"] = time.time()
        return allowed, state

    def record_failure(
        self,
        tenant_id: str,
        agent_id: str,
        action: str,
        reason: str = "",
    ) -> CBState:
        """Record a failure for the CB."""
        key = self._key(tenant_id, agent_id, action)
        cb = self._get_or_create(key)
        cb.record_failure()
        self._stats[key]["error_count"] += 1
        return self._map_state(cb.state)

    def record_success(
        self,
        tenant_id: str,
        agent_id: str,
        action: str,
    ) -> CBState:
        """Record a success for the CB."""
        key = self._key(tenant_id, agent_id, action)
        cb = self._get_or_create(key)
        cb.record_success()
        return self._map_state(cb.state)

    def get_status(
        self,
        tenant_id: str,
        agent_id: str,
        action: str,
    ) -> dict[str, Any]:
        """Get CB status for an action."""
        key = self._key(tenant_id, agent_id, action)
        cb = self._get_or_create(key)
        stats = self._stats.get(key, {})
        return {
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "action": action,
            "state": self._map_state(cb.state).value,
            "failure_count": getattr(cb, "_failure_count", 0),
            "last_trip_time": getattr(cb, "_last_trip_time", None),
            "call_count": stats.get("call_count", 0),
            "error_count": stats.get("error_count", 0),
        }

    def _map_state(self, state: BreakerState) -> CBState:
        mapping = {
            BreakerState.CLOSED: CBState.CLOSED,
            BreakerState.OPEN: CBState.OPEN,
            BreakerState.HALF_OPEN: CBState.HALF_OPEN,
        }
        return mapping.get(state, CBState.CLOSED)

    @property
    def breaker_count(self) -> int:
        """Number of active circuit breaker instances."""
        return len(self._pool)

    def cleanup_idle(self, idle_seconds: float = 3600.0) -> int:
        """Remove CBs idle longer than threshold. Returns removed count."""
        now = time.time()
        to_remove = [
            key
            for key, stats in self._stats.items()
            if now - stats.get("last_access", 0) >= idle_seconds
        ]
        for key in to_remove:
            self._pool.pop(key, None)
            self._stats.pop(key, None)
        return len(to_remove)
