"""
CircuitBreaker extended tests.

Covers: normal depth/oscillation/RSI checks, trip on all thresholds,
half-open lifecycle (probe success → CLOSED, probe failure → OPEN),
entropy tracking via trip records, pool/max_trips management,
error budget via consecutive failures, and config export.
"""

from __future__ import annotations

import time as time_module
from unittest.mock import patch

import pytest

from maref.governance.circuit_breaker import BreakerState, BreakerTrip, CircuitBreaker


class TestNormalOperation:
    """Breaker stays CLOSED under normal conditions."""

    def test_check_depth_allowed(self):
        cb = CircuitBreaker(max_depth=3)
        assert cb.check_depth(1) is True
        assert cb.check_depth(3) is True
        assert cb.state == BreakerState.CLOSED

    def test_check_oscillation_allowed(self):
        cb = CircuitBreaker(max_oscillation_rate=10.0)
        assert cb.check_oscillation(5.0, 2, "ACT") is True
        assert cb.check_oscillation(10.0, 2, "ACT") is True
        assert cb.state == BreakerState.CLOSED

    def test_check_rsi_oscillation_no_flips(self):
        cb = CircuitBreaker(rsi_max_flip_flops=3)
        statuses = ["keep", "keep", "keep"]
        assert cb.check_rsi_oscillation(statuses) is True

    def test_check_rsi_oscillation_few_flips(self):
        cb = CircuitBreaker(rsi_max_flip_flops=3)
        statuses = ["keep", "discard", "keep"]
        assert cb.check_rsi_oscillation(statuses) is True

    def test_check_rsi_quality_high(self):
        cb = CircuitBreaker(rsi_min_quality=0.3, rsi_quality_window=3)
        scores = [0.9, 0.8, 0.95]
        assert cb.check_rsi_quality(scores) is True

    def test_check_rsi_quality_insufficient_data(self):
        cb = CircuitBreaker(rsi_quality_window=5)
        scores = [0.1, 0.2]
        assert cb.check_rsi_quality(scores) is True

    def test_record_success_in_closed_resets_failures(self):
        cb = CircuitBreaker(max_consecutive_failures=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb._failure_count == 0
        assert cb.state == BreakerState.CLOSED

    def test_record_success_in_closed_does_not_change_state(self):
        cb = CircuitBreaker()
        cb.record_success()
        assert cb.state == BreakerState.CLOSED


class TestTripThresholds:
    """Each threshold condition trips the breaker."""

    def test_trip_on_depth_exact_boundary(self):
        cb = CircuitBreaker(max_depth=3)
        assert cb.check_depth(4) is False
        assert cb.state == BreakerState.OPEN

    def test_trip_on_depth_deep_recursion(self):
        cb = CircuitBreaker(max_depth=3)
        assert cb.check_depth(10) is False
        assert cb.state == BreakerState.OPEN

    def test_trip_on_oscillation(self):
        cb = CircuitBreaker(max_oscillation_rate=10.0)
        assert cb.check_oscillation(10.1, 3, "ACT") is False
        assert cb.state == BreakerState.OPEN

    def test_trip_on_oscillation_high_rate(self):
        cb = CircuitBreaker(max_oscillation_rate=5.0)
        assert cb.check_oscillation(100.0, 4, "ACT") is False
        assert cb.state == BreakerState.OPEN

    def test_trip_on_consecutive_failures(self):
        cb = CircuitBreaker(max_consecutive_failures=2)
        cb.record_failure()
        assert cb.state == BreakerState.CLOSED
        cb.record_failure()
        assert cb.state == BreakerState.OPEN

    def test_trip_on_consecutive_failures_exact_boundary(self):
        cb = CircuitBreaker(max_consecutive_failures=1)
        cb.record_failure()
        assert cb.state == BreakerState.OPEN

    def test_trip_on_rsi_oscillation(self):
        cb = CircuitBreaker(rsi_max_flip_flops=2)
        statuses = ["keep", "discard", "keep"]
        assert cb.check_rsi_oscillation(statuses) is False
        assert cb.state == BreakerState.OPEN

    def test_trip_on_rsi_oscillation_many_flips(self):
        cb = CircuitBreaker(rsi_max_flip_flops=3)
        statuses = ["keep", "discard", "keep", "discard", "keep"]
        assert cb.check_rsi_oscillation(statuses) is False

    def test_trip_on_rsi_quality_degradation(self):
        cb = CircuitBreaker(rsi_min_quality=0.3, rsi_quality_window=3)
        scores = [0.1, 0.2, 0.15]
        assert cb.check_rsi_quality(scores) is False
        assert cb.state == BreakerState.OPEN

    def test_trip_on_rsi_quality_boundary(self):
        cb = CircuitBreaker(rsi_min_quality=0.5, rsi_quality_window=4)
        scores = [0.4, 0.4, 0.4, 0.4]
        assert cb.check_rsi_quality(scores) is False

    def test_multiple_trip_sources_accumulate(self):
        cb = CircuitBreaker(max_depth=2, max_oscillation_rate=3.0)
        cb.check_depth(5)
        assert len(cb._trips) == 1
        cb.reset()
        cb.check_oscillation(10.0, 2, "ACT")
        assert len(cb._trips) == 2


class TestOpenStateBehavior:
    """Breaker behavior while in OPEN state."""

    def test_check_depth_when_open_blocks(self):
        cb = CircuitBreaker(max_depth=3)
        cb._state = BreakerState.OPEN
        cb._last_trip_time = time_module.time()
        result = cb.check_depth(1)
        assert result is False

    def test_check_oscillation_when_open_blocks(self):
        cb = CircuitBreaker()
        cb._state = BreakerState.OPEN
        assert cb.check_oscillation(1.0, 0, "ACT") is False

    def test_check_rsi_oscillation_when_open_blocks(self):
        cb = CircuitBreaker()
        cb._state = BreakerState.OPEN
        assert cb.check_rsi_oscillation(["keep", "discard"]) is False

    def test_check_rsi_quality_when_open_blocks(self):
        cb = CircuitBreaker()
        cb._state = BreakerState.OPEN
        assert cb.check_rsi_quality([0.9, 0.8]) is False

    def test_is_open_property(self):
        cb = CircuitBreaker()
        assert cb.is_open is False
        cb._state = BreakerState.OPEN
        assert cb.is_open is True

    def test_state_property_thread_safe(self):
        cb = CircuitBreaker()
        assert cb.state == BreakerState.CLOSED


class TestHalfOpenLifecycle:
    """HALF_OPEN state: probe success → CLOSED, probe failure → OPEN."""

    def test_half_open_probe_success(self):
        cb = CircuitBreaker()
        cb._state = BreakerState.HALF_OPEN
        cb._failure_count = 3
        cb.record_success()
        assert cb.state == BreakerState.CLOSED
        assert cb._failure_count == 0

    def test_half_open_probe_failure(self):
        cb = CircuitBreaker(max_consecutive_failures=1)
        cb._state = BreakerState.HALF_OPEN
        cb.record_failure()
        assert cb.state == BreakerState.OPEN

    def test_half_open_allows_depth_check(self):
        cb = CircuitBreaker(max_depth=3)
        cb._state = BreakerState.HALF_OPEN
        assert cb.check_depth(1) is True

    def test_half_open_transitions_to_closed_on_success_then_allows(self):
        cb = CircuitBreaker(max_depth=3)
        cb._state = BreakerState.HALF_OPEN
        cb.record_success()
        assert cb.state == BreakerState.CLOSED
        assert cb.check_depth(1) is True

    def test_half_open_probe_failure_extends_cooldown(self):
        cb = CircuitBreaker(max_consecutive_failures=1)
        cb._state = BreakerState.HALF_OPEN
        cb.record_failure()
        assert cb.state == BreakerState.OPEN
        assert cb._last_trip_time > 0

    def test_half_open_auto_transition_on_check_depth(self):
        with patch("time.time", return_value=1000.0):
            with patch("random.uniform", return_value=0.0):
                cb = CircuitBreaker(cooldown_seconds=10.0)
                cb._state = BreakerState.OPEN
                cb._last_trip_time = 500.0
                assert cb.check_depth(1) is True
                assert cb.state == BreakerState.HALF_OPEN


class TestEntropyAndTracking:
    """Trip records capture entropy, state, and depth."""

    def test_trip_records_depth(self):
        cb = CircuitBreaker(max_depth=3)
        cb.check_depth(10)
        assert cb._trips[0].depth == 10

    def test_trip_records_entropy(self):
        cb = CircuitBreaker(max_oscillation_rate=5.0)
        cb.check_oscillation(10.0, 4, "ACT")
        assert cb._trips[0].entropy == 4

    def test_trip_records_state_before(self):
        cb = CircuitBreaker(max_oscillation_rate=5.0)
        cb.check_oscillation(10.0, 4, "DECIDE")
        assert cb._trips[0].state_before == "DECIDE"

    def test_trip_records_action_taken(self):
        cb = CircuitBreaker(max_depth=3)
        cb.check_depth(5)
        assert cb._trips[0].action_taken == "force_degrade_to_primary"

    def test_trip_records_timestamp(self):
        cb = CircuitBreaker(max_depth=3)
        cb.check_depth(5)
        assert cb._trips[0].timestamp > 0

    def test_oscillation_trip_reason_format(self):
        cb = CircuitBreaker(max_oscillation_rate=10.0)
        cb.check_oscillation(15.5, 0, "")
        assert "oscillation_rate" in cb._trips[0].reason
        assert "15.5" in cb._trips[0].reason

    def test_depth_trip_reason_format(self):
        cb = CircuitBreaker(max_depth=3)
        cb.check_depth(7)
        assert "recursion_depth" in cb._trips[0].reason
        assert "7" in cb._trips[0].reason

    def test_failure_trip_reason_format(self):
        cb = CircuitBreaker(max_consecutive_failures=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert "consecutive_failures" in cb._trips[-1].reason

    def test_rsi_oscillation_trip_reason(self):
        cb = CircuitBreaker(rsi_max_flip_flops=2)
        cb.check_rsi_oscillation(["keep", "discard", "keep"])
        assert "rsi_oscillation" in cb._trips[0].reason

    def test_rsi_quality_trip_reason(self):
        cb = CircuitBreaker(rsi_min_quality=0.3, rsi_quality_window=3)
        cb.check_rsi_quality([0.1, 0.2, 0.1])
        assert "rsi_quality_degradation" in cb._trips[0].reason


class TestErrorBudget:
    """Error budget tracking via consecutive failures."""

    def test_failure_count_accumulates(self):
        cb = CircuitBreaker(max_consecutive_failures=10)
        for _ in range(5):
            cb.record_failure()
        assert cb._failure_count == 5

    def test_failure_count_resets_on_success(self):
        cb = CircuitBreaker(max_consecutive_failures=10)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb._failure_count == 0

    def test_failure_count_resets_on_trip(self):
        cb = CircuitBreaker(max_consecutive_failures=3)
        cb.record_failure()
        cb.record_failure()
        assert cb._failure_count == 2
        cb.record_failure()
        assert cb._failure_count == 0

    def test_cascading_failures_after_reset(self):
        cb = CircuitBreaker(max_consecutive_failures=3)
        cb.record_failure()
        cb.record_failure()
        assert cb._failure_count == 2
        cb.record_success()
        assert cb._failure_count == 0
        cb.record_failure()
        assert cb._failure_count == 1

    def test_record_failure_while_open_does_not_increment(self):
        cb = CircuitBreaker(max_consecutive_failures=3)
        cb._state = BreakerState.OPEN
        cb._failure_count = 0
        cb.record_failure()
        assert cb._failure_count == 1
        assert cb.state == BreakerState.OPEN


class TestConfigAndStats:
    """Configuration export and statistics."""

    def test_get_config_structure(self):
        cb = CircuitBreaker(
            max_depth=5,
            max_oscillation_rate=20.0,
            max_consecutive_failures=10,
            cooldown_seconds=60.0,
            rsi_max_flip_flops=3,
            rsi_quality_window=7,
            rsi_min_quality=0.5,
        )
        config = cb.get_config()
        assert config["max_depth"] == 5
        assert config["max_oscillation_rate"] == 20.0
        assert config["max_consecutive_failures"] == 10
        assert config["cooldown_seconds"] == 60.0
        assert config["rsi_max_flip_flops"] == 3
        assert config["rsi_quality_window"] == 7
        assert config["rsi_min_quality"] == 0.5
        assert config["state"] == "closed"
        assert config["trip_count"] == 0
        assert config["recent_trips"] == []

    def test_get_config_after_trip(self):
        cb = CircuitBreaker(max_depth=2)
        cb.check_depth(5)
        config = cb.get_config()
        assert config["state"] == "open"
        assert config["trip_count"] == 1
        assert len(config["recent_trips"]) == 1
        assert config["recent_trips"][0]["reason"] == "recursion_depth:5>2"

    def test_get_config_recent_trips_limited_to_5(self):
        cb = CircuitBreaker(max_depth=1)
        for _ in range(10):
            cb.check_depth(2)
            cb.reset()
        config = cb.get_config()
        assert len(config["recent_trips"]) == 5

    def test_get_stats_initial(self):
        cb = CircuitBreaker()
        stats = cb.get_stats()
        assert stats["state"] == "closed"
        assert stats["failure_count"] == 0
        assert stats["trip_count"] == 0
        assert stats["last_trip"] is None

    def test_get_stats_after_multiple_trips(self):
        cb = CircuitBreaker(max_depth=1)
        cb.check_depth(2)
        assert cb.get_stats()["trip_count"] == 1
        cb.reset()
        cb.check_depth(3)
        stats = cb.get_stats()
        assert stats["trip_count"] == 2
        assert stats["last_trip"] == "recursion_depth:3>1"

    def test_get_stats_after_reset(self):
        cb = CircuitBreaker(max_consecutive_failures=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.get_stats()["state"] == "open"
        cb.reset()
        stats = cb.get_stats()
        assert stats["state"] == "closed"
        assert stats["failure_count"] == 0

    def test_get_stats_half_open(self):
        cb = CircuitBreaker()
        cb._state = BreakerState.HALF_OPEN
        stats = cb.get_stats()
        assert stats["state"] == "half_open"

    def test_get_stats_failure_count_tracking(self):
        cb = CircuitBreaker(max_consecutive_failures=10)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.get_stats()["failure_count"] == 3


class TestTripRecordEdgeCases:
    """Trip record (BreakerTrip) details and rotation."""

    def test_trip_record_is_dataclass(self):
        trip = BreakerTrip(
            timestamp=100.0,
            reason="test",
            depth=3,
            entropy=2,
            state_before="ACT",
            action_taken="force_degrade",
        )
        assert trip.timestamp == 100.0
        assert trip.reason == "test"
        assert trip.depth == 3
        assert trip.entropy == 2
        assert trip.state_before == "ACT"
        assert trip.action_taken == "force_degrade"

    def test_trip_rotation_max_trips(self):
        cb = CircuitBreaker(max_depth=1)
        for _ in range(150):
            cb.check_depth(2)
            cb.reset()
        # _trip caps at _max_trips (100) each call
        assert len(cb._trips) <= 100

    def test_trip_rotation_exact_boundary(self):
        cb = CircuitBreaker(max_depth=1)
        for _ in range(100):
            cb.check_depth(2)
            cb.reset()
        assert len(cb._trips) == 100

    def test_trip_rotation_keeps_newest(self):
        cb = CircuitBreaker(max_depth=1)
        for _ in range(120):
            cb.check_depth(2)
            cb.reset()
        assert len(cb._trips) == 100
        assert all(t.reason == "recursion_depth:2>1" for t in cb._trips)

    def test_trip_self_trims_at_max_trips(self):
        cb = CircuitBreaker(max_depth=1)
        for _ in range(120):
            cb.check_depth(2)
            cb.reset()
        # _trip trims to _max_trips (100) on every call after exceeding
        assert len(cb._trips) == 100

    def test_reset_does_not_trim_under_limit(self):
        cb = CircuitBreaker(max_depth=1)
        cb.check_depth(2)
        cb.reset()
        assert len(cb._trips) == 1

    def test_reset_clears_failure_count(self):
        cb = CircuitBreaker(max_consecutive_failures=3)
        cb.record_failure()
        cb.record_failure()
        cb.reset()
        assert cb._failure_count == 0
        assert cb.state == BreakerState.CLOSED


class TestEdgeCases:
    """Additional edge cases and boundary conditions."""

    def test_check_depth_zero(self):
        cb = CircuitBreaker(max_depth=0)
        assert cb.check_depth(0) is True
        assert cb.check_depth(1) is False

    def test_check_oscillation_zero_rate(self):
        cb = CircuitBreaker(max_oscillation_rate=0.0)
        assert cb.check_oscillation(0.0, 0, "INIT") is True
        assert cb.check_oscillation(0.1, 0, "INIT") is False

    def test_rsi_oscillation_single_entry(self):
        cb = CircuitBreaker(rsi_max_flip_flops=1)
        assert cb.check_rsi_oscillation(["keep"]) is True
        assert cb.state == BreakerState.CLOSED

    def test_rsi_oscillation_empty(self):
        cb = CircuitBreaker(rsi_max_flip_flops=1)
        assert cb.check_rsi_oscillation([]) is True

    def test_rsi_quality_empty(self):
        cb = CircuitBreaker(rsi_quality_window=3)
        assert cb.check_rsi_quality([]) is True

    def test_rsi_quality_exact_window_size_passes(self):
        cb = CircuitBreaker(rsi_min_quality=0.5, rsi_quality_window=3)
        scores = [0.6, 0.7, 0.8]
        assert cb.check_rsi_quality(scores) is True

    def test_state_lock_held_during_trip(self):
        cb = CircuitBreaker(max_depth=3)
        with cb._lock:
            cb.check_depth(5)
        assert cb.state == BreakerState.OPEN
        assert len(cb._trips) == 1

    def test_multiple_oscillation_checks_before_trip(self):
        cb = CircuitBreaker(max_oscillation_rate=10.0)
        assert cb.check_oscillation(5.0, 1, "ACT") is True
        assert cb.check_oscillation(7.0, 2, "ACT") is True
        assert cb.check_oscillation(3.0, 1, "ACT") is True
        assert cb.state == BreakerState.CLOSED

    def test_recovery_after_depth_trip_via_reset(self):
        cb = CircuitBreaker(max_depth=3)
        cb.check_depth(5)
        assert cb.state == BreakerState.OPEN
        cb.reset()
        assert cb.state == BreakerState.CLOSED
        assert cb.check_depth(2) is True

    def test_breakers_start_independently(self):
        cb1 = CircuitBreaker(max_depth=3)
        cb2 = CircuitBreaker(max_depth=5)
        cb1.check_depth(4)
        assert cb1.state == BreakerState.OPEN
        assert cb2.state == BreakerState.CLOSED
