"""
MAREF Circuit Breaker

Protects the recursive governance system from runaway depth,
oscillation storms, and policy cascades. When tripped, the
breaker forces degradation to the primary overlay and logs
the incident to the audit trail.

States: CLOSED → OPEN → HALF_OPEN → CLOSED
"""

from __future__ import annotations

import threading
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
    - Consecutive failures > max_failures (default 3)

    Recovery:
    - HALF_OPEN: allow 1 probe call to test
    - If probe succeeds -> CLOSED (reset)
    - If probe fails -> OPEN (extend cooldown)
    """

    def __init__(
        self,
        max_depth: int = 3,
        max_oscillation_rate: float = 10.0,
        max_consecutive_failures: int = 3,
        cooldown_seconds: float = 30.0,
        rsi_max_flip_flops: int = 7,
        rsi_quality_window: int = 5,
        rsi_min_quality: float = 0.3,
    ) -> None:
        self._max_depth = max_depth
        self._max_oscillation = max_oscillation_rate
        self._max_failures = max_consecutive_failures
        self._cooldown = cooldown_seconds
        self._rsi_max_flip_flops = rsi_max_flip_flops
        self._rsi_quality_window = rsi_quality_window
        self._rsi_min_quality = rsi_min_quality
        self._lock = threading.RLock()
        self._state = BreakerState.CLOSED
        self._failure_count = 0
        self._last_trip_time = 0.0
        self._trips: list[BreakerTrip] = []
        self._max_trips = 100

    @property
    def state(self) -> BreakerState:
        with self._lock:
            return self._state

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._state == BreakerState.OPEN

    def check_depth(self, depth: int) -> bool:
        """Check recursion depth. Returns True if allowed."""
        with self._lock:
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
        with self._lock:
            if self._state == BreakerState.OPEN:
                return False

            if rate > self._max_oscillation:
                self._trip(
                    f"oscillation_rate:{rate:.1f}>{self._max_oscillation}",
                    0,
                    current_entropy,
                    current_state,
                )
                return False

            return True

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            if self._failure_count >= self._max_failures:
                self._trip(f"consecutive_failures:{self._failure_count}", 0, 0, "")
                self._failure_count = 0

    def record_success(self) -> None:
        with self._lock:
            if self._state == BreakerState.HALF_OPEN:
                self._state = BreakerState.CLOSED
                self._failure_count = 0
            else:
                self._failure_count = 0

    def force_open(self, reason: str) -> None:
        """Externally trip the breaker (S2 行为审计闭环降级入口).

        异常行为（如 critical 行为异常）可主动触发降级，记录到 trip
        历史并拒绝后续流量，直到冷却后 HALF_OPEN 探测。已 OPEN 时幂等。
        """
        with self._lock:
            if self._state == BreakerState.OPEN:
                return
            self._trip(reason, 0, 0, self._state.value)

    def check_rsi_oscillation(self, statuses: list[str]) -> bool:
        """RSI-specific: detect keep/discard oscillation.
        Trips if flip-flops >= threshold in the full provided window.
        Returns True if allowed, False if tripped."""
        with self._lock:
            if self._state == BreakerState.OPEN:
                return False
            if len(statuses) < 2:
                return True
            flips = sum(1 for i in range(1, len(statuses)) if statuses[i] != statuses[i - 1])
            if flips >= self._rsi_max_flip_flops:
                self._trip(
                    f"rsi_oscillation:{flips}>={self._rsi_max_flip_flops}",
                    0, 0, "",
                )
                return False
            return True

    def check_rsi_quality(self, scores: list[float]) -> bool:
        """RSI-specific: detect sustained quality degradation.
        Trips if avg of last N scores drops below min_quality.
        Returns True if allowed, False if tripped."""
        with self._lock:
            if self._state == BreakerState.OPEN:
                return False
            if len(scores) < self._rsi_quality_window:
                return True
            recent = scores[-self._rsi_quality_window:]
            avg = sum(recent) / len(recent)
            if avg < self._rsi_min_quality:
                self._trip(
                    f"rsi_quality_degradation:avg={avg:.2f}<{self._rsi_min_quality}",
                    0, 0, "",
                )
                return False
            return True

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
        # Trim old trips to prevent unbounded memory growth
        if len(self._trips) > self._max_trips:
            self._trips = self._trips[-self._max_trips :]

    def _should_try_half_open(self) -> bool:
        import random

        jitter = random.uniform(0, self._cooldown * 0.2)
        return (time.time() - self._last_trip_time) > (self._cooldown + jitter)

    def reset(self) -> None:
        with self._lock:
            self._state = BreakerState.CLOSED
            self._failure_count = 0
            if len(self._trips) > 100:
                self._trips = self._trips[-50:]

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self._state.value,
                "failure_count": self._failure_count,
                "trip_count": len(self._trips),
                "last_trip": self._trips[-1].reason if self._trips else None,
            }

    def get_config(self) -> dict[str, Any]:
        """Export all configuration thresholds for MAS-TS-001 D4 auditing."""
        with self._lock:
            return {
                "max_depth": self._max_depth,
                "max_oscillation_rate": self._max_oscillation,
                "max_consecutive_failures": self._max_failures,
                "cooldown_seconds": self._cooldown,
                "rsi_max_flip_flops": self._rsi_max_flip_flops,
                "rsi_quality_window": self._rsi_quality_window,
                "rsi_min_quality": self._rsi_min_quality,
                "state": self._state.value,
                "trip_count": len(self._trips),
                "recent_trips": [
                    {"timestamp": t.timestamp, "reason": t.reason, "depth": t.depth, "entropy": t.entropy}
                    for t in self._trips[-5:]
                ],
            }
