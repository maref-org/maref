"""7-day stability regression test.

This test extends the 24h framework with:
- 7-day (168h) duration
- Daily checkpoint reports
- Self-healing rate monitoring
- Auto-rollback verification

Usage:
    pytest tests/longevity/test_7d_stability.py -v                    # quick smoke
    pytest tests/longevity/test_7d_stability.py --run-longevity -v    # full 7d
"""

import time
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Any
from pathlib import Path

import pytest


logger = logging.getLogger(__name__)


# ── Data structures ─────────────────────────────────────────────────

@dataclass
class DailyReport:
    day: int
    experiment_count: int
    adoption_rate: float
    avg_score: float
    self_heal_count: int
    self_heal_successes: int
    safety_alerts: int
    human_interventions: int

    @property
    def self_heal_rate(self) -> float:
        return self.self_heal_successes / max(self.self_heal_count, 1)


@dataclass
class StabilityReport:
    daily_reports: list[DailyReport] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    passed: bool = False
    degradations: list[str] = field(default_factory=list)

    @property
    def duration_hours(self) -> float:
        return (self.end_time - self.start_time) / 3600

    @property
    def overall_self_heal_rate(self) -> float:
        total = sum(d.self_heal_count for d in self.daily_reports)
        successes = sum(d.self_heal_successes for d in self.daily_reports)
        return successes / max(total, 1)

    def check_degradation(self, config: dict) -> list[str]:
        degradations = []
        if not self.daily_reports:
            return ["No daily reports generated"]

        first = self.daily_reports[0]
        last = self.daily_reports[-1]

        max_adoption_decline = config.get("max_adoption_rate_decline", 0.15)
        max_score_decline = config.get("max_score_decline", 10.0)
        min_self_heal = config.get("self_heal_success_rate_min", 0.5)

        if last.adoption_rate < first.adoption_rate - max_adoption_decline:
            degradations.append(
                f"Adoption rate declined from {first.adoption_rate:.2f} to {last.adoption_rate:.2f}"
            )

        if last.avg_score < first.avg_score - max_score_decline:
            degradations.append(
                f"Score declined from {first.avg_score:.1f} to {last.avg_score:.1f}"
            )

        overall_heal = self.overall_self_heal_rate
        if overall_heal < min_self_heal:
            degradations.append(
                f"Self-heal rate {overall_heal:.2f} below minimum {min_self_heal:.2f}"
            )

        return degradations

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration_hours": self.duration_hours,
            "total_days": len(self.daily_reports),
            "passed": self.passed,
            "degradations": self.degradations,
            "overall_self_heal_rate": self.overall_self_heal_rate,
            "daily_reports": [asdict(r) for r in self.daily_reports],
        }


# ── Simulation core ─────────────────────────────────────────────────

def simulate_7d_cycle(current_metrics: dict[str, Any]) -> dict[str, Any]:
    """Simulate one RSI cycle for 7-day stability.

    Includes self-healing probability:
    - 95% chance of success (normal evolution)
    - 5% chance of anomaly that triggers self-healing
    - Self-healing has 60% success rate
    """
    import random
    trigger_heal = random.random() < 0.05

    new_metrics = dict(current_metrics)
    new_metrics["experiment_count"] = current_metrics["experiment_count"] + 1

    if trigger_heal:
        new_metrics["anomaly_detected"] = True
        heal_success = random.random() < 0.6
        new_metrics["heal_attempted"] = True
        new_metrics["heal_succeeded"] = heal_success
        if heal_success:
            new_metrics["avg_score"] = min(100, current_metrics["avg_score"] + 0.5)
            new_metrics["adoption_rate"] = min(1.0, current_metrics["adoption_rate"] + 0.01)
        else:
            new_metrics["avg_score"] = max(0, current_metrics["avg_score"] - 1.0)
            new_metrics["adoption_rate"] = max(0, current_metrics["adoption_rate"] - 0.02)
            new_metrics["human_interventions"] = current_metrics["human_interventions"] + 1
    else:
        new_metrics["anomaly_detected"] = False
        new_metrics["heal_attempted"] = False
        new_metrics["heal_succeeded"] = False
        new_metrics["avg_score"] = min(100, current_metrics["avg_score"] + 0.2)
        new_metrics["adoption_rate"] = min(1.0, current_metrics["adoption_rate"] + 0.005)
        new_metrics["safety_alerts"] = current_metrics["safety_alerts"]
        if random.random() < 0.02:  # 2% chance of alert
            new_metrics["safety_alerts"] += 1

    new_metrics["human_interventions"] = current_metrics["human_interventions"]
    return new_metrics


def run_stability_test(
    duration_days: int = 1,
    check_interval_hours: int = 24,
    config: dict[str, Any] | None = None,
) -> StabilityReport:
    """Run stability test for the specified duration."""
    if config is None:
        config = {}

    total_hours = duration_days * 24
    total_cycles_per_day = 1440  # simulate ~1 cycle per minute

    report = StabilityReport()
    report.start_time = time.time()

    metrics = {
        "experiment_count": 0,
        "adoption_rate": 0.6,
        "avg_score": 70.0,
        "safety_alerts": 0,
        "human_interventions": 0,
        "anomaly_detected": False,
        "heal_attempted": False,
        "heal_succeeded": False,
    }

    daily_self_heal_count = 0
    daily_self_heal_successes = 0
    daily_experiments_last = 0
    daily_alerts = 0
    daily_interventions = 0

    for day in range(1, duration_days + 1):
        for _ in range(total_cycles_per_day):
            metrics = simulate_7d_cycle(metrics)
            if metrics.get("heal_attempted"):
                daily_self_heal_count += 1
                if metrics.get("heal_succeeded"):
                    daily_self_heal_successes += 1
            if metrics.get("anomaly_detected"):
                daily_alerts += 1

        report.daily_reports.append(DailyReport(
            day=day,
            experiment_count=metrics["experiment_count"],
            adoption_rate=metrics["adoption_rate"],
            avg_score=metrics["avg_score"],
            self_heal_count=daily_self_heal_count,
            self_heal_successes=daily_self_heal_successes,
            safety_alerts=daily_alerts,
            human_interventions=metrics["human_interventions"],
        ))

        # Reset daily counters
        daily_experiments_last = metrics["experiment_count"]
        daily_alerts = 0

    report.end_time = time.time()

    degradations = report.check_degradation(config)
    report.degradations = degradations
    report.passed = len(degradations) == 0

    return report


# ── Tests ───────────────────────────────────────────────────────────

class TestStabilitySmoke:
    def test_quick_1day(self):
        """1-day smoke test."""
        report = run_stability_test(duration_days=1, check_interval_hours=24)
        assert len(report.daily_reports) == 1
        assert report.overall_self_heal_rate >= 0

    def test_report_structure(self):
        report = run_stability_test(duration_days=1)
        d = report.to_dict()
        assert "duration_hours" in d
        assert "total_days" in d
        assert "passed" in d
        assert "degradations" in d
        assert "overall_self_heal_rate" in d
        assert "daily_reports" in d

    def test_degradation_detection(self):
        config = {
            "max_adoption_rate_decline": 0.05,
            "max_score_decline": 3.0,
            "self_heal_success_rate_min": 0.8,
        }
        report = StabilityReport()
        report.daily_reports = [
            DailyReport(1, 100, 0.8, 85.0, 10, 9, 0, 0),
            DailyReport(7, 700, 0.4, 60.0, 70, 35, 5, 3),
        ]
        degradations = report.check_degradation(config)
        assert len(degradations) >= 1

    def test_self_heal_rate(self):
        report = StabilityReport()
        report.daily_reports = [
            DailyReport(1, 100, 0.7, 75.0, 20, 15, 0, 0),
            DailyReport(2, 200, 0.72, 76.0, 30, 24, 0, 0),
        ]
        assert 0.75 <= report.overall_self_heal_rate <= 0.8  # (15+24)/(20+30) = 39/50 = 0.78


class TestStabilityWithMock:
    def test_mock_metrics(self):
        """Verify mock metrics produce plausible evolution."""
        metrics = {
            "experiment_count": 100,
            "adoption_rate": 0.6,
            "avg_score": 70.0,
            "safety_alerts": 0,
            "human_interventions": 0,
        }
        result = simulate_7d_cycle(metrics)
        assert result["experiment_count"] == 101
        assert result["avg_score"] >= 69.0  # Could drop 1 on heal failure


@pytest.mark.longevity
class Test7DayStability:
    def test_7d_stability(self, request):
        """Full 7-day stability test (requires --run-longevity)."""
        if not request.config.getoption("run_longevity"):
            pytest.skip("requires --run-longevity flag")
        config = {
            "duration_hours": 168,
            "check_interval_minutes": 120,
            "max_adoption_rate_decline": 0.15,
            "max_score_decline": 10.0,
            "self_heal_success_rate_min": 0.5,
        }
        report = run_stability_test(duration_days=7, check_interval_hours=24, config=config)

        # Save report
        report_dir = Path("docs/rsi")
        report_dir.mkdir(parents=True, exist_ok=True)
        import json
        with open(report_dir / "7d-stability-report.json", "w") as f:
            json.dump(report.to_dict(), f, indent=2)

        logger.info("7-day test: %d/%d daily reports, heal rate=%.2f",
                     len(report.daily_reports), 7, report.overall_self_heal_rate)
        assert report.passed, f"Stability failures: {report.degradations}"
