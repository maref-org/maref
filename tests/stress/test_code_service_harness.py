from __future__ import annotations

import pytest

from maref.stress.code_service_harness import (
    AgentConfig,
    CodeServiceHarness,
    CodeServiceReport,
    PipelineRun,
)


class TestAgentConfig:
    def test_defaults(self):
        c = AgentConfig(name="test_agent")
        assert c.quality_rate == 0.8
        assert c.speed_ms_mean == 500.0
        assert c.speed_ms_std == 100.0
        assert c.error_types == []


class TestPipelineRun:
    def test_defaults(self):
        r = PipelineRun(
            run_id=0, success=True, duration_ms=100.0,
            code_generated=True, tests_passed=True, review_passed=True, merged=True,
            test_coverage_pct=80.0, lint_issues=0, build_errors=0, regression_failures=0,
        )
        assert r.agent_results == {}


class TestCodeServiceReport:
    def test_to_code_quality_metrics_zero_values(self):
        r = CodeServiceReport(
            total_runs=100, successful_runs=0, failed_runs=100,
            success_rate=0.0, avg_duration_ms=0.0, p99_duration_ms=0.0,
            avg_test_coverage=0.0, avg_lint_issues=0.0, avg_build_errors=0.0,
            avg_regression_failures=0.0,
        )
        m = r.to_code_quality_metrics()
        assert m.test_coverage_pct == 0.0
        assert m.lint_pass_rate == 1.0
        assert m.build_success_rate == 1.0
        assert m.doc_completeness == 0.0
        assert m.regression_free_rate == 1.0

    def test_to_code_quality_metrics_high_values(self):
        r = CodeServiceReport(
            total_runs=100, successful_runs=90, failed_runs=10,
            success_rate=0.9, avg_duration_ms=500.0, p99_duration_ms=1000.0,
            avg_test_coverage=80.0, avg_lint_issues=5.0, avg_build_errors=3.0,
            avg_regression_failures=2.0,
        )
        m = r.to_code_quality_metrics()
        assert m.test_coverage_pct == 80.0
        assert m.lint_pass_rate == pytest.approx(0.95)
        assert m.build_success_rate == pytest.approx(0.97)
        assert m.doc_completeness == 0.9
        assert m.regression_free_rate == pytest.approx(0.98)

    def test_to_code_quality_metrics_clamps_negative(self):
        r = CodeServiceReport(
            total_runs=100, successful_runs=0, failed_runs=100,
            success_rate=0.0, avg_duration_ms=0.0, p99_duration_ms=0.0,
            avg_test_coverage=0.0, avg_lint_issues=200.0, avg_build_errors=200.0,
            avg_regression_failures=200.0,
        )
        m = r.to_code_quality_metrics()
        assert m.lint_pass_rate == 0.0
        assert m.build_success_rate == 0.0
        assert m.regression_free_rate == 0.0


class TestCodeServiceHarness:
    def test_default_agents(self):
        h = CodeServiceHarness()
        assert len(h._agents) == 4
        assert h._agents[0].name == "code_generator"
        assert h._agents[1].name == "test_agent"
        assert h._agents[2].name == "review_agent"
        assert h._agents[3].name == "merge_agent"

    def test_custom_agents(self):
        agents = [AgentConfig(name="custom", quality_rate=0.5)]
        h = CodeServiceHarness(agents=agents)
        assert len(h._agents) == 1
        assert h._agents[0].name == "custom"

    def test_run_basic(self):
        h = CodeServiceHarness(seed=42)
        report = h.run(num_runs=10, round_id="test-round")
        assert isinstance(report, CodeServiceReport)
        assert report.total_runs == 10
        assert 0 <= report.success_rate <= 1.0
        assert report.avg_duration_ms >= 0
        assert len(report.runs) == 10

    def test_run_with_stress(self):
        h = CodeServiceHarness(seed=42)
        report = h.run(num_runs=10, stress_factor=1.0)
        low_stress = h.run(num_runs=10, stress_factor=0.0)
        assert report.success_rate <= low_stress.success_rate

    def test_run_single_run(self):
        h = CodeServiceHarness(seed=42)
        report = h.run(num_runs=1)
        assert report.total_runs == 1
        assert len(report.runs) == 1

    def test_run_zero_runs(self):
        h = CodeServiceHarness(seed=42)
        report = h.run(num_runs=0)
        assert report.total_runs == 0
        assert report.success_rate == 0.0
        assert report.avg_duration_ms == 0.0
        assert report.p99_duration_ms == 0.0

    def test_execute_pipeline_all_succeed(self):
        h = CodeServiceHarness(seed=42)
        run = h._execute_pipeline(0, stress_factor=0.0)
        assert isinstance(run, PipelineRun)

    def test_execute_pipeline_with_high_stress(self):
        h = CodeServiceHarness(seed=42)
        run = h._execute_pipeline(0, stress_factor=1.0)
        assert isinstance(run, PipelineRun)

    def test_get_variance_metrics(self):
        h = CodeServiceHarness(seed=42)
        metrics = h.get_variance_metrics(num_runs=2)
        assert "success_rate_mean" in metrics
        assert "success_rate_std" in metrics
        assert "coverage_mean" in metrics
        assert "coverage_std" in metrics
        assert "total_runs" in metrics
        assert metrics["total_runs"] == 20

    def test_round_id_stored(self):
        h = CodeServiceHarness(seed=42)
        report = h.run(num_runs=5, round_id="my-round")
        assert report.success_rate >= 0
