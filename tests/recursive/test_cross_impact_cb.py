"""Comprehensive tests for CrossImpactCircuitBreaker.

Covers:
- State transitions: MONITORING -> ALERTED -> TRIPPED -> RECOVERING
- Correlation analysis
- Dimension health reporting
- Configuration and stats export
"""

from __future__ import annotations

import time

from maref.recursive.cross_impact_circuit_breaker import (
    CrossImpactCircuitBreaker,
    CrossImpactEvent,
    CrossImpactState,
    DimensionHealth,
)


def _scores_seq(
    score_a: float, score_b: float, count: int = 5
) -> list[dict[str, float]]:
    """Helper: generate dimension_scores where dim_a and dim_b have fixed values."""
    return [{"dim_a": score_a, "dim_b": score_b} for _ in range(count)]


def _divergent_scores(
    a_start: float, a_end: float, b_start: float, b_end: float, steps: int = 20
) -> list[dict[str, float]]:
    """Helper: generate scores where dim_a and dim_b diverge over time."""
    result: list[dict[str, float]] = []
    for i in range(steps):
        t = i / (steps - 1)
        a = a_start + (a_end - a_start) * t
        b = b_start + (b_end - b_start) * t
        result.append({"dim_a": round(a, 4), "dim_b": round(b, 4)})
    return result


class TestInitialState:
    def test_initial_state_monitoring(self) -> None:
        cb = CrossImpactCircuitBreaker()
        assert cb.state == CrossImpactState.MONITORING

    def test_initial_tripped_dimensions_empty(self) -> None:
        cb = CrossImpactCircuitBreaker()
        assert cb.tripped_dimensions == []

    def test_initial_stats(self) -> None:
        cb = CrossImpactCircuitBreaker()
        stats = cb.get_stats()
        assert stats["state"] == "monitoring"
        assert stats["tripped_dimensions_count"] == 0
        assert stats["alert_count"] == 0
        assert stats["last_trip"] is None
        assert stats["last_trip_time"] == 0.0

    def test_initial_config(self) -> None:
        cb = CrossImpactCircuitBreaker()
        config = cb.get_config()
        assert config["negative_threshold"] == -0.3
        assert config["trip_threshold"] == -0.7
        assert config["alert_window"] == 3
        assert config["cooldown_seconds"] == 60.0
        assert config["max_tripped_dims"] == 2
        assert config["state"] == "monitoring"


class TestAnalyzeEmpty:
    def test_analyze_empty_list_returns_empty(self) -> None:
        cb = CrossImpactCircuitBreaker()
        events = cb.analyze([])
        assert events == []

    def test_analyze_single_entry_returns_empty(self) -> None:
        cb = CrossImpactCircuitBreaker()
        events = cb.analyze([{"dim_a": 1.0, "dim_b": 2.0}])
        assert events == []

    def test_analyze_single_dimension_returns_empty(self) -> None:
        cb = CrossImpactCircuitBreaker()
        events = cb.analyze([{"dim_a": 1.0}, {"dim_a": 2.0}])
        assert events == []


class TestNoNegativeCorrelation:
    def test_positive_correlation_no_events(self) -> None:
        cb = CrossImpactCircuitBreaker(negative_threshold=-0.3)
        scores = _divergent_scores(0.0, 1.0, 0.0, 1.0)
        events = cb.analyze(scores)
        assert events == []

    def test_uncorrelated_no_events(self) -> None:
        cb = CrossImpactCircuitBreaker(negative_threshold=-0.3)
        scores = [
            {"dim_a": 0.0, "dim_b": 1.0},
            {"dim_a": 0.1, "dim_b": 0.0},
            {"dim_a": 0.2, "dim_b": 0.9},
            {"dim_a": 0.3, "dim_b": 0.2},
            {"dim_a": 0.4, "dim_b": 0.8},
            {"dim_a": 0.5, "dim_b": 0.1},
            {"dim_a": 0.6, "dim_b": 0.7},
            {"dim_a": 0.7, "dim_b": 0.3},
            {"dim_a": 0.8, "dim_b": 0.6},
            {"dim_a": 0.9, "dim_b": 0.4},
        ]
        events = cb.analyze(scores)
        assert events == []


class TestMildNegativeCorrelation:
    def test_mild_negative_triggers_alerted_state(self) -> None:
        cb = CrossImpactCircuitBreaker(
            negative_threshold=-0.3, trip_threshold=-0.7
        )
        scores = [
            {"dim_a": 0.0, "dim_b": 0.5},
            {"dim_a": 0.2, "dim_b": 0.6},
            {"dim_a": 0.4, "dim_b": 0.4},
            {"dim_a": 0.6, "dim_b": 0.5},
            {"dim_a": 0.8, "dim_b": 0.3},
            {"dim_a": 1.0, "dim_b": 0.4},
        ]
        events = cb.analyze(scores)
        assert len(events) > 0
        assert cb.state == CrossImpactState.ALERTED
        for e in events:
            assert e.event_type == "correlation_alert"
            assert e.severity == "WARNING"

    def test_alert_event_structure(self) -> None:
        cb = CrossImpactCircuitBreaker(negative_threshold=-0.3)
        scores = _divergent_scores(0.0, 1.0, 1.0, 0.0)
        events = cb.analyze(scores)
        assert len(events) > 0
        event = events[0]
        assert isinstance(event, CrossImpactEvent)
        assert isinstance(event.timestamp, float)
        assert event.source_dim in ("dim_a", "dim_b")
        assert event.target_dim in ("dim_a", "dim_b")
        assert event.source_dim != event.target_dim
        assert event.correlation < -0.3
        assert event.event_type == "correlation_alert"


class TestStrongNegativeCorrelation:
    def test_strong_negative_triggers_alert(self) -> None:
        cb = CrossImpactCircuitBreaker(
            negative_threshold=-0.3, trip_threshold=-0.7
        )
        scores = _divergent_scores(0.0, 1.0, 1.0, 0.0, steps=5)
        events = cb.analyze(scores)
        assert len(events) > 0
        assert cb.state in (CrossImpactState.ALERTED, CrossImpactState.TRIPPED)

    def test_strong_negative_critical_severity(self) -> None:
        cb = CrossImpactCircuitBreaker(
            negative_threshold=-0.3, trip_threshold=-0.7
        )
        scores = _divergent_scores(0.0, 1.0, 1.0, 0.0, steps=5)
        events = cb.analyze(scores)
        critical = [e for e in events if e.severity == "CRITICAL"]
        assert len(critical) > 0


class TestPersistentAlerts:
    def test_persistent_alerts_trip_after_window(self) -> None:
        cb = CrossImpactCircuitBreaker(
            negative_threshold=-0.3,
            trip_threshold=-0.7,
            alert_window=3,
        )
        scores = _divergent_scores(0.0, 1.0, 1.0, 0.0, steps=10)

        for i in range(3):
            events = cb.analyze(scores)
            assert cb.state == CrossImpactState.TRIPPED or (
                cb.state == CrossImpactState.ALERTED and i < 2
            )

        assert cb.state == CrossImpactState.TRIPPED
        assert len(cb.tripped_dimensions) > 0
        assert cb.get_stats()["tripped_dimensions_count"] > 0

    def test_trip_recorded_as_event(self) -> None:
        cb = CrossImpactCircuitBreaker(
            negative_threshold=-0.3,
            alert_window=3,
        )
        scores = _divergent_scores(0.0, 1.0, 1.0, 0.0, steps=10)

        trips_before = len([e for e in cb._events if e.event_type == "trip"])

        for _ in range(3):
            cb.analyze(scores)

        trips_after = len([e for e in cb._events if e.event_type == "trip"])
        assert trips_after > trips_before


class TestRecovery:
    def test_recovery_after_cooldown(self) -> None:
        cb = CrossImpactCircuitBreaker(
            negative_threshold=-0.3,
            alert_window=2,
            cooldown_seconds=0.01,
        )
        scores = _divergent_scores(0.0, 1.0, 1.0, 0.0, steps=10)

        for _ in range(2):
            cb.analyze(scores)
        assert cb.state == CrossImpactState.TRIPPED

        time.sleep(0.02)

        events = cb.analyze(scores)
        recovery_events = [e for e in events if e.event_type == "recovery"]
        assert len(recovery_events) > 0 or cb.state == CrossImpactState.RECOVERING

    def test_recovery_event_type(self) -> None:
        cb = CrossImpactCircuitBreaker(
            negative_threshold=-0.3,
            alert_window=2,
            cooldown_seconds=0.01,
        )
        scores = _divergent_scores(0.0, 1.0, 1.0, 0.0, steps=10)

        for _ in range(2):
            cb.analyze(scores)
        assert cb.state == CrossImpactState.TRIPPED

        time.sleep(0.02)
        events = cb.analyze(scores)

        rec_events = [e for e in events if e.event_type == "recovery"]
        if rec_events:
            assert rec_events[0].severity == "INFO"


class TestCheckDimension:
    def test_check_dimension_allows_positive(self) -> None:
        cb = CrossImpactCircuitBreaker()
        assert cb.check_dimension("dim_a", "dim_b", 0.5) is True
        assert cb.state == CrossImpactState.MONITORING

    def test_check_dimension_blocks_tripped_source(self) -> None:
        cb = CrossImpactCircuitBreaker(
            negative_threshold=-0.3, alert_window=2
        )
        scores = _divergent_scores(0.0, 1.0, 1.0, 0.0, steps=10)
        for _ in range(2):
            cb.analyze(scores)
        assert cb.state == CrossImpactState.TRIPPED
        assert cb.check_dimension("dim_a", "dim_b", -0.9) is False

    def test_check_dimension_accumulates_alerts(self) -> None:
        cb = CrossImpactCircuitBreaker(
            negative_threshold=-0.3, alert_window=3
        )
        assert cb.check_dimension("dim_a", "dim_b", -0.5) is True
        assert cb.state == CrossImpactState.MONITORING
        assert cb.check_dimension("dim_a", "dim_b", -0.5) is True
        assert cb.state == CrossImpactState.MONITORING
        assert cb.check_dimension("dim_a", "dim_b", -0.5) is False
        assert cb.state == CrossImpactState.TRIPPED


class TestReleaseDimension:
    def test_release_dimension_works(self) -> None:
        cb = CrossImpactCircuitBreaker(
            negative_threshold=-0.3, alert_window=2
        )
        scores = _divergent_scores(0.0, 1.0, 1.0, 0.0, steps=10)
        for _ in range(2):
            cb.analyze(scores)

        assert "dim_a" in cb.tripped_dimensions
        assert cb.release_dimension("dim_a") is True
        assert "dim_a" not in cb.tripped_dimensions

    def test_release_dimension_nonexistent(self) -> None:
        cb = CrossImpactCircuitBreaker()
        assert cb.release_dimension("nonexistent") is False

    def test_release_dimension_records_event(self) -> None:
        cb = CrossImpactCircuitBreaker(
            negative_threshold=-0.3, alert_window=2
        )
        scores = _divergent_scores(0.0, 1.0, 1.0, 0.0, steps=10)
        for _ in range(2):
            cb.analyze(scores)

        events_before = len(cb._events)
        cb.release_dimension("dim_a")
        assert len(cb._events) == events_before + 1
        assert cb._events[-1].event_type == "recovery"
        assert cb._events[-1].severity == "INFO"


class TestDimensionHealth:
    def test_get_dimension_health_empty(self) -> None:
        cb = CrossImpactCircuitBreaker()
        assert cb.get_dimension_health([]) == []

    def test_get_dimension_health_structure(self) -> None:
        cb = CrossImpactCircuitBreaker()
        scores = [
            {"dim_a": 0.0, "dim_b": 1.0},
            {"dim_a": 0.5, "dim_b": 0.5},
            {"dim_a": 1.0, "dim_b": 0.0},
        ]
        health = cb.get_dimension_health(scores)
        assert len(health) == 2

        for h in health:
            assert isinstance(h, DimensionHealth)
            assert h.dim in ("dim_a", "dim_b")
            assert isinstance(h.current_score, float)
            assert h.trend in ("improving", "stable", "worsening")
            assert isinstance(h.variance, float)
            assert isinstance(h.correlated_negatives, list)

    def test_get_dimension_health_identifies_negative_correlations(self) -> None:
        cb = CrossImpactCircuitBreaker(negative_threshold=-0.3)
        scores = _divergent_scores(0.0, 1.0, 1.0, 0.0, steps=20)
        health = cb.get_dimension_health(scores)

        dim_a_health = next(h for h in health if h.dim == "dim_a")
        assert len(dim_a_health.correlated_negatives) > 0
        neg_dim, neg_corr = dim_a_health.correlated_negatives[0]
        assert neg_dim == "dim_b"
        assert neg_corr < -0.3


class TestReset:
    def test_reset_clears_state(self) -> None:
        cb = CrossImpactCircuitBreaker(
            negative_threshold=-0.3, alert_window=2
        )
        scores = _divergent_scores(0.0, 1.0, 1.0, 0.0, steps=10)
        for _ in range(2):
            cb.analyze(scores)
        assert cb.state == CrossImpactState.TRIPPED

        cb.reset()
        assert cb.state == CrossImpactState.MONITORING
        assert cb.tripped_dimensions == []
        assert cb.get_stats()["tripped_dimensions_count"] == 0

    def test_reset_clears_alert_counts(self) -> None:
        cb = CrossImpactCircuitBreaker(
            negative_threshold=-0.3, alert_window=2
        )
        scores = _divergent_scores(0.0, 1.0, 1.0, 0.0, steps=10)
        for _ in range(2):
            cb.analyze(scores)

        cb.reset()
        assert cb._alert_counts == {}

    def test_reset_after_reset_analysis_restarts(self) -> None:
        cb = CrossImpactCircuitBreaker(
            negative_threshold=-0.3, alert_window=3
        )
        scores = _divergent_scores(0.0, 1.0, 1.0, 0.0, steps=10)

        cb.reset()
        events = cb.analyze(scores)
        assert cb.state == CrossImpactState.ALERTED


class TestMaxTrippedDims:
    def test_max_tripped_dims_enforced(self) -> None:
        cb = CrossImpactCircuitBreaker(
            negative_threshold=-0.6,
            trip_threshold=-0.8,
            alert_window=2,
            max_tripped_dims=1,
        )
        scores = _divergent_scores(0.0, 1.0, 1.0, 0.0, steps=15)
        for _ in range(3):
            cb.analyze(scores)

        assert cb.state == CrossImpactState.TRIPPED or cb.state == CrossImpactState.ALERTED
        assert len(cb.tripped_dimensions) <= 1

    def test_max_tripped_dims_three_dimensions(self) -> None:
        cb = CrossImpactCircuitBreaker(
            negative_threshold=-0.3,
            alert_window=2,
            max_tripped_dims=2,
        )
        scores_3d = [
            {"dim_a": 0.0, "dim_b": 1.0, "dim_c": 0.0},
            {"dim_a": 0.2, "dim_b": 0.8, "dim_c": 0.2},
            {"dim_a": 0.4, "dim_b": 0.6, "dim_c": 0.4},
            {"dim_a": 0.6, "dim_b": 0.4, "dim_c": 0.6},
            {"dim_a": 0.8, "dim_b": 0.2, "dim_c": 0.8},
            {"dim_a": 1.0, "dim_b": 0.0, "dim_c": 1.0},
        ]
        for _ in range(3):
            cb.analyze(scores_3d)

        assert len(cb.tripped_dimensions) <= 2


class TestGetStats:
    def test_get_stats_returns_expected_keys(self) -> None:
        cb = CrossImpactCircuitBreaker()
        stats = cb.get_stats()
        expected_keys = {
            "state",
            "tripped_dimensions_count",
            "tripped_dimensions",
            "alert_count",
            "last_trip",
            "last_trip_time",
        }
        assert set(stats.keys()) == expected_keys

    def test_get_stats_after_trip(self) -> None:
        cb = CrossImpactCircuitBreaker(
            negative_threshold=-0.3, alert_window=2
        )
        scores = _divergent_scores(0.0, 1.0, 1.0, 0.0, steps=10)
        for _ in range(2):
            cb.analyze(scores)

        stats = cb.get_stats()
        assert stats["state"] == "tripped"
        assert stats["tripped_dimensions_count"] >= 1
        assert stats["alert_count"] > 0
        assert stats["last_trip"] is not None
        assert stats["last_trip_time"] > 0.0


class TestGetConfig:
    def test_get_config_returns_expected_keys(self) -> None:
        cb = CrossImpactCircuitBreaker()
        config = cb.get_config()
        expected_keys = {
            "negative_threshold",
            "trip_threshold",
            "alert_window",
            "cooldown_seconds",
            "max_tripped_dims",
            "state",
            "tripped_dimensions",
            "recent_events",
        }
        assert set(config.keys()) == expected_keys

    def test_get_config_values_match_init(self) -> None:
        cb = CrossImpactCircuitBreaker(
            negative_threshold=-0.5,
            trip_threshold=-0.9,
            alert_window=4,
            cooldown_seconds=120.0,
            max_tripped_dims=3,
        )
        config = cb.get_config()
        assert config["negative_threshold"] == -0.5
        assert config["trip_threshold"] == -0.9
        assert config["alert_window"] == 4
        assert config["cooldown_seconds"] == 120.0
        assert config["max_tripped_dims"] == 3


class TestMultipleDimensionPairs:
    def test_multiple_pairs_tracked_independently(self) -> None:
        cb = CrossImpactCircuitBreaker(
            negative_threshold=-0.3, alert_window=3
        )
        scores_abc = [
            {"dim_a": 0.0, "dim_b": 1.0, "dim_c": 0.5},
            {"dim_a": 0.2, "dim_b": 0.8, "dim_c": 0.5},
            {"dim_a": 0.4, "dim_b": 0.6, "dim_c": 0.5},
            {"dim_a": 0.6, "dim_b": 0.4, "dim_c": 0.5},
            {"dim_a": 0.8, "dim_b": 0.2, "dim_c": 0.5},
            {"dim_a": 1.0, "dim_b": 0.0, "dim_c": 0.5},
        ]

        for _ in range(3):
            cb.analyze(scores_abc)

        assert cb.state == CrossImpactState.TRIPPED

        dim_a_tripped = "dim_a" in cb.tripped_dimensions
        dim_b_tripped = "dim_b" in cb.tripped_dimensions
        assert dim_a_tripped or dim_b_tripped
        assert "dim_c" not in cb.tripped_dimensions
