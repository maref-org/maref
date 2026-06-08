"""Tests for Service Quality Index (SQI) module."""

from __future__ import annotations

from maref.stress.emergence_harness import EmergenceReport, PerturbationResult
from maref.stress.sqi import ServiceQualityIndex, SQIDimension
from maref.stress.sqi_convergence import SQIConvergenceTracker
from maref.stress.stress_result import StressResult


def _make_stress_result(
    healer_success_rate: float = 0.8,
    resilience_score: float = 0.75,
    oscillation_resolved: bool = True,
    oscillation_detected: bool = False,
    ab_test_pass_rate: float = 0.9,
) -> StressResult:
    return StressResult(
        round_id="test-001",
        stress_level="L1",
        healer_success_rate=healer_success_rate,
        resilience_score=resilience_score,
        oscillation_resolved=oscillation_resolved,
        oscillation_detected=oscillation_detected,
        ab_test_pass_rate=ab_test_pass_rate,
    )


def _make_emergence_report(
    consistent: int = 85, total: int = 100,
) -> EmergenceReport:
    return EmergenceReport(
        scenario_name="test-scenario",
        run_count=total,
        consistent_runs=consistent,
        inconsistent_runs=total - consistent,
        p99_latency_ms=120.0,
    )


# ------------------------------------------------------------------ #
# Dimension tests
# ------------------------------------------------------------------ #


class TestDeliveryQuality:
    def test_high_healer_rate(self) -> None:
        sr = _make_stress_result(healer_success_rate=0.9)
        dim = ServiceQualityIndex._compute_delivery_quality(sr)
        assert dim.score == 90.0

    def test_zero_healer_rate(self) -> None:
        sr = _make_stress_result(healer_success_rate=0.0)
        dim = ServiceQualityIndex._compute_delivery_quality(sr)
        assert dim.score == 0.0

    def test_no_stress_data(self) -> None:
        dim = ServiceQualityIndex._compute_delivery_quality(None)
        assert dim.score == 0.0


class TestConsistency:
    def test_high_consistency(self) -> None:
        er = _make_emergence_report(consistent=95, total=100)
        dim = ServiceQualityIndex._compute_consistency(er)
        assert dim.score == 95.0

    def test_low_consistency(self) -> None:
        er = _make_emergence_report(consistent=20, total=100)
        dim = ServiceQualityIndex._compute_consistency(er)
        assert dim.score == 20.0

    def test_no_emergence_data(self) -> None:
        dim = ServiceQualityIndex._compute_consistency(None)
        assert dim.score == 50.0  # neutral default


class TestCostEfficiency:
    def test_low_usage_stable_trend(self) -> None:
        dim = ServiceQualityIndex._compute_cost_efficiency(0.3, "stable")
        assert dim.score == 70.0

    def test_high_usage(self) -> None:
        dim = ServiceQualityIndex._compute_cost_efficiency(0.95, "stable")
        assert dim.score == 5.0

    def test_increasing_trend_penalty(self) -> None:
        dim = ServiceQualityIndex._compute_cost_efficiency(0.5, "increasing")
        assert dim.score == 30.0  # 50 - 20

    def test_decreasing_trend_bonus(self) -> None:
        dim = ServiceQualityIndex._compute_cost_efficiency(0.5, "decreasing")
        assert dim.score == 60.0  # 50 + 10


class TestConvergenceSpeed:
    def test_high_resilience(self) -> None:
        sr = _make_stress_result(resilience_score=0.9)
        dim = ServiceQualityIndex._compute_convergence_speed(sr)
        assert dim.score == 90.0

    def test_no_stress_data(self) -> None:
        dim = ServiceQualityIndex._compute_convergence_speed(None)
        assert dim.score == 50.0


class TestStability:
    def test_oscillation_resolved(self) -> None:
        sr = _make_stress_result(oscillation_resolved=True, ab_test_pass_rate=1.0)
        dim = ServiceQualityIndex._compute_stability(sr)
        assert dim.score == 100.0

    def test_oscillation_not_detected(self) -> None:
        sr = _make_stress_result(
            oscillation_resolved=False,
            oscillation_detected=False,
            ab_test_pass_rate=0.5,
        )
        dim = ServiceQualityIndex._compute_stability(sr)
        assert dim.score == 50.0  # 0.6*50 + 0.4*50

    def test_oscillation_unresolved(self) -> None:
        sr = _make_stress_result(
            oscillation_resolved=False,
            oscillation_detected=True,
            ab_test_pass_rate=0.0,
        )
        dim = ServiceQualityIndex._compute_stability(sr)
        assert dim.score == 0.0


# ------------------------------------------------------------------ #
# Overall SQI tests
# ------------------------------------------------------------------ #


class TestOverallSQI:
    def test_all_dimensions_weighted(self) -> None:
        sqi = ServiceQualityIndex()
        report = sqi.compute(
            stress_result=_make_stress_result(),
            emergence_report=_make_emergence_report(),
            budget_usage_pct=0.4,
            cost_trend_direction="stable",
            round_id="r1",
        )
        # delivery_quality=80, consistency=85, cost=60, convergence=75, stability=~94
        assert 70.0 <= report.overall_score <= 80.0
        assert report.round_id == "r1"

    def test_perfect_scenario(self) -> None:
        sqi = ServiceQualityIndex()
        report = sqi.compute(
            stress_result=_make_stress_result(
                healer_success_rate=1.0,
                resilience_score=1.0,
                oscillation_resolved=True,
                ab_test_pass_rate=1.0,
            ),
            emergence_report=_make_emergence_report(consistent=100, total=100),
            budget_usage_pct=0.0,
            cost_trend_direction="decreasing",
        )
        assert report.overall_score >= 95.0

    def test_worst_scenario(self) -> None:
        sqi = ServiceQualityIndex()
        report = sqi.compute(
            stress_result=_make_stress_result(
                healer_success_rate=0.0,
                resilience_score=0.0,
                oscillation_resolved=False,
                oscillation_detected=True,
                ab_test_pass_rate=0.0,
            ),
            emergence_report=_make_emergence_report(consistent=0, total=100),
            budget_usage_pct=1.0,
            cost_trend_direction="increasing",
        )
        assert report.overall_score <= 20.0

    def test_all_weights_sum_to_1(self) -> None:
        weights = ServiceQualityIndex.DEFAULT_WEIGHTS
        assert abs(sum(weights.values()) - 1.0) < 1e-9

    def test_to_dict(self) -> None:
        sqi = ServiceQualityIndex()
        report = sqi.compute(
            stress_result=_make_stress_result(),
            emergence_report=_make_emergence_report(),
        )
        d = report.to_dict()
        assert "overall_score" in d
        assert "dimensions" in d
        assert len(d["dimensions"]) == 5

    def test_dimension_count(self) -> None:
        sqi = ServiceQualityIndex()
        report = sqi.compute(stress_result=_make_stress_result())
        assert len(report.dimensions) == 5


# ------------------------------------------------------------------ #
# Convergence tracker tests
# ------------------------------------------------------------------ #


class TestConvergenceTracker:
    def test_empty_tracker(self) -> None:
        tracker = SQIConvergenceTracker()
        state = tracker.check_convergence()
        assert not state.is_converged
        assert state.rounds_tracked == 0

    def test_single_round_not_converged(self) -> None:
        tracker = SQIConvergenceTracker(target=90.0)
        sqi = ServiceQualityIndex()
        report = sqi.compute(
            stress_result=_make_stress_result(healer_success_rate=0.6),
            emergence_report=_make_emergence_report(consistent=60),
        )
        tracker.record_round("r1", report)
        state = tracker.check_convergence()
        assert not state.is_converged
        assert state.rounds_tracked == 1

    def test_convergence_after_target_reached(self) -> None:
        tracker = SQIConvergenceTracker(target=80.0, window=3, gain_threshold=0.3)
        sqi = ServiceQualityIndex()

        # Simulate 5 rounds converging to 85
        for i in range(5):
            score = 70.0 + i * 4.0  # 70, 74, 78, 82, 86
            # Fake a report with this score
            report = sqi.compute(
                stress_result=_make_stress_result(
                    healer_success_rate=score / 100,
                    resilience_score=score / 100,
                    oscillation_resolved=score > 75,
                    ab_test_pass_rate=score / 100,
                ),
                emergence_report=_make_emergence_report(
                    consistent=int(score), total=100,
                ),
            )
            tracker.record_round(f"r{i+1}", report)

        state = tracker.check_convergence()
        # After 5 rounds, score should be ~86, above target 80
        assert state.current_score >= 80.0

    def test_summary_statistics(self) -> None:
        tracker = SQIConvergenceTracker()
        sqi = ServiceQualityIndex()
        for i in range(3):
            report = sqi.compute(
                stress_result=_make_stress_result(
                    healer_success_rate=0.5 + i * 0.1,
                    resilience_score=0.5 + i * 0.1,
                    oscillation_resolved=True,
                    ab_test_pass_rate=0.5 + i * 0.1,
                ),
                emergence_report=_make_emergence_report(consistent=50 + i * 10),
            )
            tracker.record_round(f"r{i+1}", report)

        summary = tracker.summary()
        assert summary["rounds"] == 3
        assert summary["total_improvement"] > 0

    def test_delta_tracking(self) -> None:
        tracker = SQIConvergenceTracker()
        sqi = ServiceQualityIndex()

        report1 = sqi.compute(
            stress_result=_make_stress_result(healer_success_rate=0.5, resilience_score=0.5),
            emergence_report=_make_emergence_report(consistent=50),
        )
        r1 = tracker.record_round("r1", report1)
        assert r1.delta > 0  # first round delta = score - 0 baseline

        report2 = sqi.compute(
            stress_result=_make_stress_result(healer_success_rate=0.7, resilience_score=0.7),
            emergence_report=_make_emergence_report(consistent=70),
        )
        r2 = tracker.record_round("r2", report2)
        assert r2.delta > 0  # improvement
