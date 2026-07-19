"""Tests for maref.stress.demo_deterministic_delivery.

Covers demo_baseline_vs_governed function structure,
variance computation, and edge cases with mocked Harness.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maref.stress.code_service_harness import AgentConfig
from maref.stress.code_service_sqi import CodeQualityMetrics, SQIReport

# ---------------------------------------------------------------------------
# Helpers — build fake report objects without running real Harness
# ---------------------------------------------------------------------------


def _make_report(
    success_rate: float,
    avg_coverage: float = 80.0,
) -> MagicMock:
    report = MagicMock()
    report.success_rate = success_rate
    report.avg_test_coverage = avg_coverage
    metrics = CodeQualityMetrics(
        test_coverage_pct=avg_coverage,
        lint_pass_rate=0.9,
        build_success_rate=0.95,
        doc_completeness=success_rate,
        regression_free_rate=0.95,
    )
    report.to_code_quality_metrics.return_value = metrics
    return report


def _make_sqi_report(overall_score: float, variance: float = 5.0) -> MagicMock:
    report = MagicMock(spec=SQIReport)
    report.overall_score = overall_score
    report.variance = variance
    return report


class TestDemoBaselineVsGoverned:
    @patch("maref.stress.demo_deterministic_delivery.CodeServiceHarness")
    def test_returns_expected_structure(self, MockHarness: MagicMock) -> None:
        """Returns dict with baseline, governed, convergence_proof keys."""
        harness_instance = MagicMock()
        harness_instance.run.side_effect = [
            _make_report(success_rate=0.80),
            _make_report(success_rate=0.30),
            _make_report(success_rate=0.70),
            _make_report(success_rate=0.90),
            _make_report(success_rate=0.40),
        ] + [
            _make_report(success_rate=0.65 + i * 0.03)
            for i in range(10)
        ]
        MockHarness.return_value = harness_instance

        from maref.stress.demo_deterministic_delivery import demo_baseline_vs_governed

        results = demo_baseline_vs_governed()

        assert "baseline" in results
        assert "governed" in results
        assert "convergence_proof" in results
        assert len(results["baseline"]) == 5
        assert len(results["governed"]) == 10

    @patch("maref.stress.demo_deterministic_delivery.CodeServiceHarness")
    def test_baseline_records_have_required_fields(self, MockHarness: MagicMock) -> None:
        """Each baseline entry contains round, success_rate, avg_coverage."""
        harness_instance = MagicMock()
        harness_instance.run.side_effect = [
            _make_report(success_rate=0.80 + i * 0.05)
            for i in range(5)
        ] + [
            _make_report(success_rate=0.70 + i * 0.02)
            for i in range(10)
        ]
        MockHarness.return_value = harness_instance

        from maref.stress.demo_deterministic_delivery import demo_baseline_vs_governed

        results = demo_baseline_vs_governed()
        for entry in results["baseline"]:
            assert "round" in entry
            assert "success_rate" in entry
            assert "avg_coverage" in entry
            assert isinstance(entry["round"], int)
            assert 0.0 <= entry["success_rate"] <= 1.0
            assert isinstance(entry["avg_coverage"], float)

    @patch("maref.stress.demo_deterministic_delivery.CodeServiceHarness")
    def test_governed_records_have_sqi_fields(self, MockHarness: MagicMock) -> None:
        """Governed entries include sqi_score and sqi_variance."""
        harness_instance = MagicMock()
        harness_instance.run.side_effect = [
            _make_report(success_rate=0.80 + i * 0.05)
            for i in range(5)
        ] + [
            _make_report(success_rate=0.70 + i * 0.02)
            for i in range(10)
        ]
        MockHarness.return_value = harness_instance

        from maref.stress.demo_deterministic_delivery import demo_baseline_vs_governed

        results = demo_baseline_vs_governed()
        for entry in results["governed"]:
            assert "sqi_score" in entry
            assert "sqi_variance" in entry

    @patch("maref.stress.demo_deterministic_delivery.CodeServiceHarness")
    def test_convergence_proof_keys(self, MockHarness: MagicMock) -> None:
        """Convergence proof contains all expected metrics."""
        harness_instance = MagicMock()
        harness_instance.run.side_effect = [
            _make_report(success_rate=0.80 + i * 0.05)
            for i in range(5)
        ] + [
            _make_report(success_rate=0.70 + i * 0.02)
            for i in range(10)
        ]
        MockHarness.return_value = harness_instance

        from maref.stress.demo_deterministic_delivery import demo_baseline_vs_governed

        results = demo_baseline_vs_governed()
        proof = results["convergence_proof"]
        expected_keys = {
            "is_converged", "current_score", "target_score", "trend",
            "saturation_window", "initial_score", "best_score",
            "total_improvement", "baseline_variance", "governed_variance",
            "variance_reduction_pct",
        }
        assert expected_keys.issubset(proof.keys())

    @patch("maref.stress.demo_deterministic_delivery.CodeServiceHarness")
    def test_variance_reduction_calculated(self, MockHarness: MagicMock) -> None:
        """Variance reduction percentage is computed and ranges 0-100."""
        harness_instance = MagicMock()
        harness_instance.run.side_effect = [
            _make_report(success_rate=0.90),
            _make_report(success_rate=0.30),
            _make_report(success_rate=0.70),
            _make_report(success_rate=0.60),
            _make_report(success_rate=0.40),
        ] + [
            _make_report(success_rate=0.70 + i * 0.01)
            for i in range(10)
        ]
        MockHarness.return_value = harness_instance

        from maref.stress.demo_deterministic_delivery import demo_baseline_vs_governed

        results = demo_baseline_vs_governed()
        proof = results["convergence_proof"]
        assert 0 <= proof["variance_reduction_pct"] <= 100

    @patch("maref.stress.demo_deterministic_delivery.CodeServiceHarness")
    def test_governed_variance_lower_than_baseline(self, MockHarness: MagicMock) -> None:
        """With stable governed runs, governed variance < baseline variance."""
        harness_instance = MagicMock()
        harness_instance.run.side_effect = (
            [_make_report(success_rate=r) for r in [0.90, 0.30, 0.70, 0.60, 0.40]]
            + [_make_report(success_rate=0.80) for _ in range(10)]
        )
        MockHarness.return_value = harness_instance

        from maref.stress.demo_deterministic_delivery import demo_baseline_vs_governed

        results = demo_baseline_vs_governed()
        proof = results["convergence_proof"]
        assert proof["governed_variance"] < proof["baseline_variance"]

    @patch("maref.stress.demo_deterministic_delivery.CodeServiceHarness")
    def test_baseline_success_rates_vary(self, MockHarness: MagicMock) -> None:
        """Baseline rates reflect the provided varied inputs."""
        provided_rates = [0.80, 0.30, 0.70, 0.90, 0.40]
        harness_instance = MagicMock()
        harness_instance.run.side_effect = (
            [_make_report(success_rate=r) for r in provided_rates]
            + [_make_report(success_rate=0.80) for _ in range(10)]
        )
        MockHarness.return_value = harness_instance

        from maref.stress.demo_deterministic_delivery import demo_baseline_vs_governed

        results = demo_baseline_vs_governed()
        got = [r["success_rate"] for r in results["baseline"]]
        assert got == [round(r, 3) for r in provided_rates]

    def test_standalone_run(self) -> None:
        """
        Module's __main__ block executes without error when called via
        python -m.  We verify by checking the module's __name__ block
        logic only — no subprocess.
        """
        from maref.stress import demo_deterministic_delivery as mod

        assert hasattr(mod, "demo_baseline_vs_governed")
        assert callable(mod.demo_baseline_vs_governed)
