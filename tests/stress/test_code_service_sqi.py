from __future__ import annotations

import pytest

from maref.stress.code_service_sqi import (
    WEIGHT_PROFILES,
    CodeQualityMetrics,
    CodeServiceSQI,
)


class TestCodeQualityMetrics:
    def test_defaults(self):
        m = CodeQualityMetrics()
        assert m.test_coverage_pct == 0.0
        assert m.lint_pass_rate == 0.0
        assert m.build_success_rate == 0.0
        assert m.doc_completeness == 0.0
        assert m.regression_free_rate == 0.0
        assert m.files_generated == 0
        assert m.files_with_tests == 0
        assert m.files_with_docs == 0
        assert m.lint_issues_count == 0
        assert m.build_errors_count == 0
        assert m.regression_failures == 0


class TestWeightProfiles:
    def test_all_profiles_have_all_keys(self):
        required = {"delivery_quality", "consistency", "cost_efficiency",
                    "convergence_speed", "stability", "test_coverage_rate",
                    "lint_pass_rate", "build_success_rate", "doc_completeness",
                    "regression_free_rate"}
        for name, profile in WEIGHT_PROFILES.items():
            assert set(profile.keys()) == required, f"Profile {name} missing keys"
            total = sum(profile.values())
            assert abs(total - 1.0) < 0.2, f"Profile {name} weights sum to {total:.2f}, expected ~1.0"

    def test_default_profile(self):
        for v in WEIGHT_PROFILES["default"].values():
            assert v == 0.10

    def test_enterprise_saas_prioritizes_stability(self):
        p = WEIGHT_PROFILES["enterprise_saas"]
        assert p["stability"] == 0.15
        assert p["consistency"] == 0.15
        assert p["convergence_speed"] == 0.05

    def test_startup_mvp_prioritizes_speed(self):
        p = WEIGHT_PROFILES["startup_mvp"]
        assert p["delivery_quality"] == 0.15
        assert p["convergence_speed"] == 0.15

    def test_regulated_industry_prioritizes_test_coverage(self):
        p = WEIGHT_PROFILES["regulated_industry"]
        assert p["test_coverage_rate"] == 0.15
        assert p["doc_completeness"] == 0.13

    def test_ai_ml_project_prioritizes_test_coverage(self):
        p = WEIGHT_PROFILES["ai_ml_project"]
        assert p["test_coverage_rate"] == 0.15
        assert p["delivery_quality"] == 0.12


class TestCodeServiceSQI:
    def test_init_default(self):
        sqi = CodeServiceSQI()
        assert len(sqi._weights) == 10
        assert sqi._weights["delivery_quality"] == 0.10

    def test_init_with_profile(self):
        sqi = CodeServiceSQI(weight_profile="enterprise_saas")
        assert sqi._weights["stability"] == 0.15

    def test_init_with_custom_weights(self):
        sqi = CodeServiceSQI(custom_weights={"test_coverage_rate": 0.20})
        assert sqi._weights["test_coverage_rate"] == 0.20
        assert sqi._weights["delivery_quality"] == 0.10

    def test_set_weight_profile(self):
        sqi = CodeServiceSQI()
        sqi.set_weight_profile("startup_mvp")
        assert sqi._weights["convergence_speed"] == 0.15

    def test_set_weight_profile_unknown_raises(self):
        sqi = CodeServiceSQI()
        with pytest.raises(ValueError, match="Unknown weight profile"):
            sqi.set_weight_profile("nonexistent")

    def test_set_custom_weights_valid(self):
        sqi = CodeServiceSQI()
        weights = {k: 0.10 for k in WEIGHT_PROFILES["default"].keys()}
        sqi.set_custom_weights(weights)
        assert sqi._weights["consistency"] == 0.10

    def test_set_custom_weights_missing_keys(self):
        sqi = CodeServiceSQI()
        with pytest.raises(ValueError, match="Missing weights"):
            sqi.set_custom_weights({"delivery_quality": 1.0})

    def test_set_custom_weights_wrong_sum(self):
        sqi = CodeServiceSQI()
        weights = {k: 0.05 for k in WEIGHT_PROFILES["default"].keys()}
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            sqi.set_custom_weights(weights)

    def test_current_weights_property(self):
        sqi = CodeServiceSQI()
        w = sqi.current_weights
        assert w["delivery_quality"] == 0.10
        w["delivery_quality"] = 99.0
        assert sqi._weights["delivery_quality"] == 0.10

    def test_compute_with_only_code_metrics(self):
        sqi = CodeServiceSQI(weight_profile="default")
        metrics = CodeQualityMetrics(
            test_coverage_pct=85.0,
            lint_pass_rate=0.95,
            build_success_rate=0.98,
            doc_completeness=0.80,
            regression_free_rate=0.90,
        )
        report = sqi.compute(code_metrics=metrics, round_id="test-round")
        assert report.round_id == "test-round"
        assert report.overall_score > 0
        assert report.variance >= 0
        assert len(report.dimensions) == 10

    def test_compute_with_all_none_metrics(self):
        sqi = CodeServiceSQI()
        report = sqi.compute(round_id="no-metrics")
        assert report.overall_score >= 0
        assert len(report.dimensions) == 10

    def test_compute_with_partial_metrics(self):
        sqi = CodeServiceSQI()
        metrics = CodeQualityMetrics(test_coverage_pct=50.0)
        report = sqi.compute(code_metrics=metrics, round_id="partial")
        assert report.overall_score > 0

    def test_compute_test_coverage_with_metrics(self):
        sqi = CodeServiceSQI()
        metrics = CodeQualityMetrics(test_coverage_pct=75.0)
        dim = sqi._compute_test_coverage(metrics)
        assert dim.name == "test_coverage_rate"
        assert dim.score == 75.0
        assert dim.weight == 0.10

    def test_compute_test_coverage_no_metrics(self):
        sqi = CodeServiceSQI()
        dim = sqi._compute_test_coverage(None)
        assert dim.score == 0.0
        assert dim.weight == 0.10
        assert "No coverage" in dim.description

    def test_compute_lint_pass_with_metrics(self):
        sqi = CodeServiceSQI()
        metrics = CodeQualityMetrics(lint_pass_rate=0.90)
        dim = sqi._compute_lint_pass(metrics)
        assert dim.score == 90.0

    def test_compute_lint_pass_no_metrics(self):
        sqi = CodeServiceSQI()
        dim = sqi._compute_lint_pass(None)
        assert dim.score == 50.0

    def test_compute_build_success_with_metrics(self):
        sqi = CodeServiceSQI()
        metrics = CodeQualityMetrics(build_success_rate=0.85)
        dim = sqi._compute_build_success(metrics)
        assert dim.score == 85.0

    def test_compute_build_success_no_metrics(self):
        sqi = CodeServiceSQI()
        dim = sqi._compute_build_success(None)
        assert dim.score == 50.0

    def test_compute_doc_completeness_with_metrics(self):
        sqi = CodeServiceSQI()
        metrics = CodeQualityMetrics(doc_completeness=0.70)
        dim = sqi._compute_doc_completeness(metrics)
        assert dim.score == 70.0

    def test_compute_doc_completeness_no_metrics(self):
        sqi = CodeServiceSQI()
        dim = sqi._compute_doc_completeness(None)
        assert dim.score == 50.0

    def test_compute_regression_free_with_metrics(self):
        sqi = CodeServiceSQI()
        metrics = CodeQualityMetrics(regression_free_rate=0.95)
        dim = sqi._compute_regression_free(metrics)
        assert dim.score == 95.0

    def test_compute_regression_free_no_metrics(self):
        sqi = CodeServiceSQI()
        dim = sqi._compute_regression_free(None)
        assert dim.score == 50.0

    def test_compute_clamps_scores(self):
        sqi = CodeServiceSQI()
        metrics = CodeQualityMetrics(
            test_coverage_pct=150.0,
            lint_pass_rate=2.0,
            build_success_rate=-0.5,
            doc_completeness=-1.0,
            regression_free_rate=3.0,
        )
        report = sqi.compute(code_metrics=metrics, round_id="clamp")
        for d in report.dimensions:
            assert 0.0 <= d.score <= 100.0

    def test_compute_metadata_weight_profile_default(self):
        sqi = CodeServiceSQI()
        report = sqi.compute(round_id="meta-test")
        assert report.metadata["weight_profile"] == "default"

    def test_compute_metadata_weight_profile_custom(self):
        sqi = CodeServiceSQI(weight_profile="enterprise_saas")
        report = sqi.compute(round_id="custom-profile")
        assert report.metadata["weight_profile"] == "custom"

    def test_compute_with_budget_usage(self):
        sqi = CodeServiceSQI()
        report = sqi.compute(budget_usage_pct=50.0, cost_trend_direction="increasing",
                             round_id="budget")
        assert report.overall_score >= 0
