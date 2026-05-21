"""
MAREF Circuit Breaker

Protects the recursive governance system from runaway depth,
oscillation storms, and policy cascades. When tripped, the
breaker forces degradation to the primary overlay and logs
the incident to the audit trail.

States: CLOSED → OPEN → HALF_OPEN → CLOSED
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any


class BreakerState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class BreakerTrip:
    """Record of a circuit breaker trip event."""

    timestamp: float
    reason: str
    depth: int
    entropy: int
    state_before: str
    action_taken: str


class CircuitBreaker:
    """
    Circuit breaker for recursive governance safety.

    Trips on:
    - Recursion depth > max_depth (default 3)
    - Oscillation rate > max_oscillation (default 10/min)
    - Consecutive failures > max_failures (default 5)

    Recovery:
    - HALF_OPEN: allow 1 probe call to test
    - If probe succeeds → CLOSED (reset)
    - If probe fails → OPEN (extend cooldown)
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
        self._state = BreakerState.CLOSED
        self._failure_count = 0
        self._last_trip_time = 0.0
        self._trips: list[BreakerTrip] = []

    @property
    def state(self) -> BreakerState:
        return self._state

    @property
    def is_open(self) -> bool:
        return self._state == BreakerState.OPEN

    def check_depth(self, depth: int) -> bool:
        """Check recursion depth. Returns True if allowed."""
        if self._state == BreakerState.OPEN:
            if self._should_try_half_open():
                self._state = BreakerState.HALF_OPEN
                return True
            return False

        if depth > self._max_depth:
            self._trip(f"recursion_depth:{depth}>{self._max_depth}", depth, 0, "")
            return False

        return True

    def check_oscillation(self, rate: float, current_entropy: int, current_state: str) -> bool:
        if self.is_open:
            return False

        if rate > self._max_oscillation:
            self._trip(f"oscillation_rate:{rate:.1f}>{self._max_oscillation}", 0, current_entropy, current_state)
            return False

        return True

    def record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= self._max_failures:
            self._trip(f"consecutive_failures:{self._failure_count}", 0, 0, "")
            self._failure_count = 0

    def record_success(self) -> None:
        if self._state == BreakerState.HALF_OPEN:
            self._state = BreakerState.CLOSED
            self._failure_count = 0
        else:
            self._failure_count = 0

    def _trip(self, reason: str, depth: int, entropy: int, state_before: str) -> None:
        self._state = BreakerState.OPEN
        self._last_trip_time = time.time()
        self._trips.append(
            BreakerTrip(
                timestamp=self._last_trip_time,
                reason=reason,
                depth=depth,
                entropy=entropy,
                state_before=state_before,
                action_taken="force_degrade_to_primary",
            )
        )

    def _should_try_half_open(self) -> bool:
        import random
        jitter = random.uniform(0, self._cooldown * 0.2)
        return (time.time() - self._last_trip_time) > (self._cooldown + jitter)

    def reset(self) -> None:
        self._state = BreakerState.CLOSED
        self._failure_count = 0
        if len(self._trips) > 100:
            self._trips = self._trips[-50:]

    def get_stats(self) -> dict[str, Any]:
        return {
            "state": self._state.value,
            "failure_count": self._failure_count,
            "trip_count": len(self._trips),
            "last_trip": self._trips[-1].reason if self._trips else None,
        }
