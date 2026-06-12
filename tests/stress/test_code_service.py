"""Tests for CodeServiceSQI and CodeServiceHarness."""

from __future__ import annotations

from maref.stress.code_service_sqi import CodeQualityMetrics, CodeServiceSQI
from maref.stress.code_service_harness import (
    AgentConfig, CodeServiceHarness, CodeServiceReport, PipelineRun,
)


# ------------------------------------------------------------------ #
# CodeServiceSQI Tests
# ------------------------------------------------------------------ #
class TestCodeServiceSQI:
    def test_compute_with_no_data(self) -> None:
        sqi = CodeServiceSQI()
        report = sqi.compute(round_id="empty")
        assert report.overall_score >= 0
        assert len(report.dimensions) == 10
        dim_names = [d.name for d in report.dimensions]
        assert "test_coverage_rate" in dim_names
        assert "lint_pass_rate" in dim_names
        assert "build_success_rate" in dim_names
        assert "doc_completeness" in dim_names
        assert "regression_free_rate" in dim_names

    def test_compute_with_perfect_code_metrics(self) -> None:
        sqi = CodeServiceSQI()
        metrics = CodeQualityMetrics(
            test_coverage_pct=95.0,
            lint_pass_rate=1.0,
            build_success_rate=1.0,
            doc_completeness=1.0,
            regression_free_rate=1.0,
        )
        report = sqi.compute(code_metrics=metrics, round_id="perfect")
        assert report.overall_score > 50
        # Find code-specific dimensions
        coverage_dim = next(d for d in report.dimensions if d.name == "test_coverage_rate")
        assert coverage_dim.score == 95.0

    def test_compute_with_poor_code_metrics(self) -> None:
        sqi = CodeServiceSQI()
        metrics = CodeQualityMetrics(
            test_coverage_pct=10.0,
            lint_pass_rate=0.2,
            build_success_rate=0.1,
            doc_completeness=0.0,
            regression_free_rate=0.3,
        )
        report = sqi.compute(code_metrics=metrics, round_id="poor")
        assert report.overall_score < 50

    def test_weights_equal(self) -> None:
        sqi = CodeServiceSQI()
        report = sqi.compute(round_id="weights")
        for dim in report.dimensions:
            assert dim.weight == 0.10

    def test_variance_calculation(self) -> None:
        sqi = CodeServiceSQI()
        # Perfect code metrics should have lower variance
        perfect = CodeQualityMetrics(
            test_coverage_pct=90.0, lint_pass_rate=0.9,
            build_success_rate=0.9, doc_completeness=0.9, regression_free_rate=0.9,
        )
        # Mixed metrics should have higher variance
        mixed = CodeQualityMetrics(
            test_coverage_pct=90.0, lint_pass_rate=0.1,
            build_success_rate=0.9, doc_completeness=0.1, regression_free_rate=0.9,
        )
        r1 = sqi.compute(code_metrics=perfect, round_id="r1")
        r2 = sqi.compute(code_metrics=mixed, round_id="r2")
        assert r2.variance > r1.variance


# ------------------------------------------------------------------ #
# CodeServiceHarness Tests
# ------------------------------------------------------------------ #
class TestCodeServiceHarness:
    def test_default_agents(self) -> None:
        harness = CodeServiceHarness(seed=42)
        assert len(harness._agents) == 4
        names = [a.name for a in harness._agents]
        assert "code_generator" in names
        assert "test_agent" in names
        assert "review_agent" in names
        assert "merge_agent" in names

    def test_run_basic(self) -> None:
        harness = CodeServiceHarness(seed=42)
        report = harness.run(num_runs=50, round_id="basic")
        assert report.total_runs == 50
        assert report.successful_runs + report.failed_runs == 50
        assert 0 <= report.success_rate <= 1.0
        assert report.avg_duration_ms >= 0

    def test_run_with_stress(self) -> None:
        harness = CodeServiceHarness(seed=42)
        normal = harness.run(num_runs=100, stress_factor=0.0, round_id="normal")
        stressed = harness.run(num_runs=100, stress_factor=1.0, round_id="stressed")
        # Stress should reduce success rate (probabilistic, but with seed should be deterministic)
        assert stressed.success_rate <= normal.success_rate

    def test_custom_agents(self) -> None:
        agents = [
            AgentConfig(name="simple_gen", quality_rate=0.95, speed_ms_mean=100, speed_ms_std=20),
        ]
        harness = CodeServiceHarness(agents=agents, seed=42)
        report = harness.run(num_runs=30, round_id="custom")
        assert report.total_runs == 30

    def test_report_to_metrics(self) -> None:
        harness = CodeServiceHarness(seed=42)
        report = harness.run(num_runs=50, round_id="metrics")
        metrics = report.to_code_quality_metrics()
        assert 0 <= metrics.test_coverage_pct <= 100
        assert 0 <= metrics.lint_pass_rate <= 1.0
        assert 0 <= metrics.build_success_rate <= 1.0
        assert 0 <= metrics.doc_completeness <= 1.0
        assert 0 <= metrics.regression_free_rate <= 1.0

    def test_variance_metrics(self) -> None:
        harness = CodeServiceHarness(seed=42)
        variance = harness.get_variance_metrics(num_runs=50)
        assert variance["success_rate_mean"] >= 0
        assert variance["success_rate_std"] >= 0
        assert variance["total_runs"] == 500
        # duration_ms may be very small in test environment but should not crash


# ------------------------------------------------------------------ #
# Integration: Harness + SQI
# ------------------------------------------------------------------ #
class TestHarnessSQIIntegration:
    def test_end_to_end_pipeline(self) -> None:
        harness = CodeServiceHarness(seed=42)
        sqi = CodeServiceSQI()

        report = harness.run(num_runs=100, round_id="e2e")
        metrics = report.to_code_quality_metrics()

        sqi_report = sqi.compute(code_metrics=metrics, round_id="e2e-sqi")

        assert sqi_report.overall_score > 0
        assert len(sqi_report.dimensions) == 10

    def test_convergence_with_improving_agents(self) -> None:
        """Simulate agents improving over time - SQI should converge upward."""
        from maref.stress.sqi_convergence import SQIConvergenceTracker

        tracker = SQIConvergenceTracker(target=80.0, window=3)
        sqi = CodeServiceSQI()

        for i in range(10):
            # Agent quality improves each round
            agents = [
                AgentConfig(name="gen", quality_rate=0.5 + i * 0.05, speed_ms_mean=500),
                AgentConfig(name="test", quality_rate=0.6 + i * 0.04, speed_ms_mean=300),
                AgentConfig(name="review", quality_rate=0.5 + i * 0.05, speed_ms_mean=400),
                AgentConfig(name="merge", quality_rate=0.7 + i * 0.03, speed_ms_mean=200),
            ]
            # Use different seed each round to simulate different runs
            harness = CodeServiceHarness(agents=agents, seed=42 + i)
            report = harness.run(num_runs=50, round_id=f"round-{i}")
            metrics = report.to_code_quality_metrics()
            sqi_report = sqi.compute(code_metrics=metrics, round_id=f"sqi-{i}")
            tracker.record_round(f"r{i}", sqi_report)

        state = tracker.check_convergence()
        # After 10 rounds of improving agents, should see some improvement
        assert state.current_score >= state.history[0].overall_score

    def test_stress_degrades_sqi(self) -> None:
        """Verify stress factor degrades SQI scores."""
        sqi = CodeServiceSQI()

        # Normal conditions
        harness_normal = CodeServiceHarness(seed=42)
        normal_report = harness_normal.run(num_runs=100, stress_factor=0.0)
        normal_metrics = normal_report.to_code_quality_metrics()
        normal_sqi = sqi.compute(code_metrics=normal_metrics, round_id="normal")

        # High stress
        harness_stressed = CodeServiceHarness(seed=42)
        stressed_report = harness_stressed.run(num_runs=100, stress_factor=1.0)
        stressed_metrics = stressed_report.to_code_quality_metrics()
        stressed_sqi = sqi.compute(code_metrics=stressed_metrics, round_id="stressed")

        assert normal_sqi.overall_score > stressed_sqi.overall_score

    def test_variance_convergence(self) -> None:
        """Multiple runs should show decreasing variance with stable agents."""
        harness = CodeServiceHarness(seed=42, )
        variance_1 = harness.get_variance_metrics(num_runs=50)

        # Run again with same seed - should have similar metrics
        variance_2 = harness.get_variance_metrics(num_runs=50)

        # Variance should be bounded (not exploding)
        assert variance_1["success_rate_std"] < 0.5
        assert variance_2["success_rate_std"] < 0.5
