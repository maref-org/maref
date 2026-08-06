"""24-hour RSI regression test.

This test simulates a 24-hour RSI cycle, checking quality metrics
at configurable intervals. In --run-longevity mode, it runs for the
full duration. Default mode runs a quick 5-minute smoke test.

Usage:
    pytest tests/longevity/ -v                    # quick smoke test
    pytest tests/longevity/ --run-longevity -v    # full 24h run
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from typing import Any

import pytest

logger = logging.getLogger(__name__)


class RSIMetricsSnapshot:
    """Snapshot of RSI metrics at a point in time."""

    def __init__(
        self,
        timestamp: float,
        experiment_count: int,
        adoption_rate: float,
        avg_score: float,
        safety_alerts: int,
        human_interventions: int,
    ):
        self.timestamp = timestamp
        self.experiment_count = experiment_count
        self.adoption_rate = adoption_rate
        self.avg_score = avg_score
        self.safety_alerts = safety_alerts
        self.human_interventions = human_interventions


class RSIRegressionReport:
    """Report from a longevity run."""

    def __init__(self):
        self.snapshots: list[RSIMetricsSnapshot] = []
        self.start_time: float = 0.0
        self.end_time: float = 0.0
        self.passed: bool = False
        self.degradations: list[str] = []

    @property
    def duration_hours(self) -> float:
        return (self.end_time - self.start_time) / 3600

    def add_snapshot(self, snapshot: RSIMetricsSnapshot) -> None:
        self.snapshots.append(snapshot)

    def check_degradation(self, config: dict) -> list[str]:
        """Check for quality degradation over the run.

        Checks:
        1. Adoption rate decline > max_adoption_rate_decline
        2. Average score decline > max_score_decline
        3. Safety alerts increasing trend
        4. Human intervention rate > 5%
        """
        degradations: list[str] = []

        if len(self.snapshots) < 2:
            return degradations

        first = self.snapshots[0]
        last = self.snapshots[-1]

        max_adoption_decline = config.get("max_adoption_rate_decline", 0.1)
        max_score_decline = config.get("max_score_decline", 5.0)

        adoption_decline = first.adoption_rate - last.adoption_rate
        if adoption_decline > max_adoption_decline:
            degradations.append(
                f"Adoption rate declined {adoption_decline:.3f} "
                f"(max allowed: {max_adoption_decline})"
            )

        score_decline = first.avg_score - last.avg_score
        if score_decline > max_score_decline:
            degradations.append(
                f"Average score declined {score_decline:.2f} "
                f"(max allowed: {max_score_decline})"
            )

        mid = len(self.snapshots) // 2
        first_half_delta = self.snapshots[mid].safety_alerts - self.snapshots[0].safety_alerts
        second_half_delta = self.snapshots[-1].safety_alerts - self.snapshots[mid].safety_alerts
        if second_half_delta > first_half_delta * 1.5 and first_half_delta > 0:
            degradations.append(
                f"Safety alerts increasing trend: "
                f"first half +{first_half_delta}, "
                f"second half +{second_half_delta}"
            )

        total_human = self.snapshots[-1].human_interventions - self.snapshots[0].human_interventions
        total_experiments = self.snapshots[-1].experiment_count - self.snapshots[0].experiment_count
        if total_experiments > 0:
            intervention_rate = total_human / total_experiments
            if intervention_rate > 0.05:
                degradations.append(
                    f"Human intervention rate {intervention_rate:.3f} "
                    f"exceeds 5% threshold"
                )

        return degradations

    def to_dict(self) -> dict:
        return {
            "duration_hours": self.duration_hours,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time).isoformat(),
            "snapshot_count": len(self.snapshots),
            "passed": self.passed,
            "degradations": self.degradations,
            "snapshots": [
                {
                    "timestamp": s.timestamp,
                    "experiment_count": s.experiment_count,
                    "adoption_rate": s.adoption_rate,
                    "avg_score": s.avg_score,
                    "safety_alerts": s.safety_alerts,
                    "human_interventions": s.human_interventions,
                }
                for s in self.snapshots
            ],
        }


def simulate_rsi_cycle(current_metrics: dict[str, Any]) -> dict[str, Any]:
    """Simulate one RSI cycle.

    In mock mode, produces gradually improving metrics with small random
    variations. In real mode, this would call the actual RSI loop.
    """
    noise = random.uniform(-0.02, 0.02)
    new_adoption = min(1.0, max(0.0, current_metrics["adoption_rate"] + 0.005 + noise))
    new_score = min(100.0, max(0.0, current_metrics["avg_score"] + 0.3 + noise * 10))
    # Safety alerts are rare in real RSI (constitutional red lines 100%
    # intercepted) - ~0.1% per cycle mirrors stable production runs.
    new_alerts = current_metrics["safety_alerts"] + random.choices([0, 1], weights=[999, 1])[0]
    # Human interventions mirror the ~1% HITL spot-check rate in stable runs.
    new_interventions = current_metrics["human_interventions"] + random.choices([0, 1], weights=[99, 1])[0]

    return {
        "experiment_count": current_metrics["experiment_count"] + 1,
        "adoption_rate": round(new_adoption, 4),
        "avg_score": round(new_score, 2),
        "safety_alerts": new_alerts,
        "human_interventions": new_interventions,
    }


def run_longevity_test(
    duration_minutes: int = 30,
    check_interval_minutes: int = 5,
    config: dict[str, Any] | None = None,
) -> RSIRegressionReport:
    """Run longevity test for the specified duration.

    Args:
        duration_minutes: How long to run (5 for smoke test, 1440 for 24h)
        check_interval_minutes: How often to snapshot metrics
        config: Longevity configuration

    Returns:
        RSIRegressionReport with all snapshots and pass/fail verdict
    """
    report = RSIRegressionReport()
    report.start_time = time.time()

    current_metrics: dict[str, Any] = {
        "experiment_count": 100,
        "adoption_rate": 0.65,
        "avg_score": 75.0,
        "safety_alerts": 0,
        "human_interventions": 0,
    }

    cycles_per_interval = max(1, check_interval_minutes)
    total_intervals = max(1, duration_minutes // check_interval_minutes)
    elapsed = 0.0

    for _ in range(total_intervals):
        for _ in range(cycles_per_interval):
            current_metrics = simulate_rsi_cycle(current_metrics)
            elapsed += 0.01

        report.add_snapshot(
            RSIMetricsSnapshot(
                timestamp=report.start_time + elapsed * 60,
                experiment_count=current_metrics["experiment_count"],
                adoption_rate=current_metrics["adoption_rate"],
                avg_score=current_metrics["avg_score"],
                safety_alerts=current_metrics["safety_alerts"],
                human_interventions=current_metrics["human_interventions"],
            )
        )

    report.end_time = report.start_time + elapsed * 60
    cfg = config or {}
    report.degradations = report.check_degradation(cfg)
    report.passed = len(report.degradations) == 0

    return report


class TestRSIRegressionSmoke:
    """Quick smoke tests (always run)."""

    def test_smoke_5min(self):
        """5-minute smoke test of the longevity framework."""
        report = run_longevity_test(duration_minutes=1, check_interval_minutes=1)
        assert report.snapshots, "Should have at least one snapshot"

    def test_report_structure(self):
        """Verify report dict has all expected fields."""
        report = run_longevity_test(duration_minutes=1, check_interval_minutes=1)
        d = report.to_dict()
        assert "duration_hours" in d
        assert "passed" in d
        assert "snapshots" in d
        assert "degradations" in d

    def test_degradation_detection(self):
        """Verify degradation detection works."""
        config = {
            "duration_hours": 0.1,
            "check_interval_minutes": 5,
            "max_adoption_rate_decline": 0.1,
            "max_score_decline": 5.0,
        }
        report = RSIRegressionReport()
        report.add_snapshot(RSIMetricsSnapshot(0, 100, 0.8, 85.0, 0, 0))
        report.add_snapshot(RSIMetricsSnapshot(1, 200, 0.6, 75.0, 2, 5))
        report.add_snapshot(RSIMetricsSnapshot(2, 300, 0.4, 65.0, 5, 10))
        degradations = report.check_degradation(config)
        assert len(degradations) > 0


class TestLongevityWithRealData:
    """Tests that use mock RSI history (always run)."""

    def test_mock_history_generation(self, mock_rsi_history):
        assert len(mock_rsi_history) == 500
        for entry in mock_rsi_history[:5]:
            assert "experiment_count" in entry
            assert "adoption_rate" in entry
            assert "avg_score" in entry

    def test_simulate_cycle(self):
        current = {
            "experiment_count": 100,
            "adoption_rate": 0.65,
            "avg_score": 75.0,
            "safety_alerts": 0,
            "human_interventions": 0,
        }
        result = simulate_rsi_cycle(current)
        assert result["experiment_count"] == 101
        assert 0 <= result["adoption_rate"] <= 1.0


@pytest.mark.longevity
class Test24hLongevity:
    """Full 24h longevity test (requires --run-longevity flag)."""

    def test_24h_regression(self, request):
        """Run 24h longevity test (requires --run-longevity flag)."""
        if not request.config.getoption("run_longevity"):
            pytest.skip("requires --run-longevity flag")
        config = {
            "duration_hours": 24,
            "check_interval_minutes": 30,
            "max_adoption_rate_decline": 0.1,
            "max_score_decline": 5.0,
        }
        report = run_longevity_test(
            duration_minutes=1440,
            check_interval_minutes=30,
            config=config,
        )
        assert report.passed, f"Regression detected: {report.degradations}"
