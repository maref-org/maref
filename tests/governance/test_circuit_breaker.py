"""
CircuitBreaker 独立测试

覆盖审计问题 P16：断路器状态转换、深度检查、振荡检查、连续失败检查。
"""

from __future__ import annotations

import time

import pytest

from maref.governance.circuit_breaker import BreakerState, BreakerTrip, CircuitBreaker


class TestCircuitBreakerStateTransitions:
    def test_initial_state_closed(self) -> None:
        cb = CircuitBreaker()
        assert cb.state == BreakerState.CLOSED
        assert cb.is_open is False

    def test_trip_on_depth(self) -> None:
        cb = CircuitBreaker(max_depth=3)
        assert cb.check_depth(4) is False
        assert cb.state == BreakerState.OPEN
        assert cb.is_open is True

    def test_trip_on_oscillation(self) -> None:
        cb = CircuitBreaker(max_oscillation_rate=10.0)
        assert cb.check_oscillation(15.0, 0, "ACT") is False
        assert cb.state == BreakerState.OPEN

    def test_trip_on_consecutive_failures(self) -> None:
        cb = CircuitBreaker(max_consecutive_failures=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == BreakerState.CLOSED
        cb.record_failure()
        assert cb.state == BreakerState.OPEN

    def test_half_open_recovery(self) -> None:
        cb = CircuitBreaker(max_consecutive_failures=3, cooldown_seconds=0.1)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == BreakerState.OPEN
        time.sleep(0.15)
        assert cb.check_depth(1) is True
        assert cb.state == BreakerState.HALF_OPEN

    def test_half_open_to_closed_on_success(self) -> None:
        cb = CircuitBreaker()
        cb._state = BreakerState.HALF_OPEN
        cb.record_success()
        assert cb.state == BreakerState.CLOSED

    def test_half_open_to_open_on_failure(self) -> None:
        cb = CircuitBreaker(max_consecutive_failures=1, cooldown_seconds=0.1)
        cb._state = BreakerState.HALF_OPEN
        cb.record_failure()
        assert cb.state == BreakerState.OPEN

    def test_reset(self) -> None:
        cb = CircuitBreaker(max_consecutive_failures=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == BreakerState.OPEN
        cb.reset()
        assert cb.state == BreakerState.CLOSED
        assert cb.is_open is False


class TestCircuitBreakerStats:
    def test_get_stats_initial(self) -> None:
        cb = CircuitBreaker()
        stats = cb.get_stats()
        assert stats["state"] == "closed"
        assert stats["failure_count"] == 0
        assert stats["trip_count"] == 0
        assert stats["last_trip"] is None

    def test_get_stats_after_trip(self) -> None:
        cb = CircuitBreaker(max_depth=1)
        cb.check_depth(2)
        stats = cb.get_stats()
        assert stats["state"] == "open"
        assert stats["trip_count"] == 1
        assert stats["last_trip"] == "recursion_depth:2>1"

    def test_trip_records_details(self) -> None:
        cb = CircuitBreaker(max_depth=2)
        cb.check_depth(5)
        assert len(cb._trips) == 1
        trip = cb._trips[0]
        assert isinstance(trip, BreakerTrip)
        assert trip.depth == 5
        assert "recursion_depth" in trip.reason

    def test_trip_rotation(self) -> None:
        cb = CircuitBreaker(max_depth=1)
        for _ in range(110):
            cb.check_depth(2)
            cb.reset()
        assert len(cb._trips) <= 100  # Should be capped at _max_trips


class TestCircuitBreakerJitter:
    def test_half_open_jitter(self) -> None:
        cb = CircuitBreaker(cooldown_seconds=1.0)
        cb._trip("test", 0, 0, "")
        # Immediately after trip, should not allow half-open
        assert cb.check_depth(1) is False
        time.sleep(1.5)
        # After cooldown + jitter, should allow half-open
        assert cb.check_depth(1) is True
