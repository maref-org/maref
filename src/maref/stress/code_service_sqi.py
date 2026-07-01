"""Code Service SQI: deterministic delivery scoring for code generation.

Extends the base SQI with code-service-specific dimensions:
  6. test_coverage_rate: Unit test coverage percentage
  7. lint_pass_rate: Static analysis pass rate
  8. build_success_rate: Build/compile success rate
  9. doc_completeness: Documentation completeness score
  10. regression_free_rate: No-regression pass rate across versions

These 5 additional dimensions (0.1 weight each) combine with the original
5 dimensions (0.1 weight each) for a total 10-dimension CodeServiceSQI.

Supports dynamic weight profiles for different industry scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from maref.stress.sqi import ServiceQualityIndex, SQIDimension, SQIReport


@dataclass
class CodeQualityMetrics:
    """Code-specific quality metrics from the generation pipeline."""
    test_coverage_pct: float = 0.0          # 0-100
    lint_pass_rate: float = 0.0             # 0.0-1.0
    build_success_rate: float = 0.0         # 0.0-1.0
    doc_completeness: float = 0.0           # 0.0-1.0
    regression_free_rate: float = 0.0       # 0.0-1.0
    files_generated: int = 0
    files_with_tests: int = 0
    files_with_docs: int = 0
    lint_issues_count: int = 0
    build_errors_count: int = 0
    regression_failures: int = 0


# Industry-specific weight profiles
WEIGHT_PROFILES = {
    # Default: equal weights for all dimensions
    "default": {
        "delivery_quality": 0.10,
        "consistency": 0.10,
        "cost_efficiency": 0.10,
        "convergence_speed": 0.10,
        "stability": 0.10,
        "test_coverage_rate": 0.10,
        "lint_pass_rate": 0.10,
        "build_success_rate": 0.10,
        "doc_completeness": 0.10,
        "regression_free_rate": 0.10,
    },
    # Enterprise SaaS: prioritize stability and consistency
    "enterprise_saas": {
        "delivery_quality": 0.08,
        "consistency": 0.15,
        "cost_efficiency": 0.07,
        "convergence_speed": 0.05,
        "stability": 0.15,
        "test_coverage_rate": 0.12,
        "lint_pass_rate": 0.10,
        "build_success_rate": 0.10,
        "doc_completeness": 0.08,
        "regression_free_rate": 0.10,
    },
    # Startup/MVP: prioritize speed and delivery quality
    "startup_mvp": {
        "delivery_quality": 0.15,
        "consistency": 0.08,
        "cost_efficiency": 0.12,
        "convergence_speed": 0.15,
        "stability": 0.05,
        "test_coverage_rate": 0.08,
        "lint_pass_rate": 0.07,
        "build_success_rate": 0.10,
        "doc_completeness": 0.05,
        "regression_free_rate": 0.05,
    },
    # Fintech/Healthcare: prioritize stability, regression-free, and lint compliance
    "regulated_industry": {
        "delivery_quality": 0.08,
        "consistency": 0.10,
        "cost_efficiency": 0.05,
        "convergence_speed": 0.05,
        "stability": 0.12,
        "test_coverage_rate": 0.15,
        "lint_pass_rate": 0.12,
        "build_success_rate": 0.10,
        "doc_completeness": 0.13,
        "regression_free_rate": 0.10,
    },
    # AI/ML projects: prioritize delivery quality and test coverage
    "ai_ml_project": {
        "delivery_quality": 0.12,
        "consistency": 0.10,
        "cost_efficiency": 0.08,
        "convergence_speed": 0.10,
        "stability": 0.08,
        "test_coverage_rate": 0.15,
        "lint_pass_rate": 0.07,
        "build_success_rate": 0.10,
        "doc_completeness": 0.10,
        "regression_free_rate": 0.10,
    },
}


class CodeServiceSQI(ServiceQualityIndex):
    """SQI specialized for code service factory scenarios.

    10 dimensions with configurable weights (default 0.1 each):
      Original 5: delivery_quality, consistency, cost_efficiency,
                  convergence_speed, stability
      Code-specific 5: test_coverage_rate, lint_pass_rate,
                       build_success_rate, doc_completeness,
                       regression_free_rate

    Supports industry-specific weight profiles via set_weight_profile().
    """

    CODE_WEIGHTS = WEIGHT_PROFILES["default"]

    def __init__(self, weight_profile: str = "default", custom_weights: dict[str, float] | None = None) -> None:
        """Initialize with weight configuration.

        Args:
            weight_profile: Name of predefined weight profile
            custom_weights: Custom weight overrides (must sum to 1.0)
        """
        self._weights = dict(WEIGHT_PROFILES.get(weight_profile, WEIGHT_PROFILES["default"]))
        if custom_weights:
            self._weights.update(custom_weights)

    def set_weight_profile(self, profile: str) -> None:
        """Switch to a predefined weight profile.

        Args:
            profile: Profile name (default, enterprise_saas, startup_mvp,
                     regulated_industry, ai_ml_project)
        """
        if profile not in WEIGHT_PROFILES:
            raise ValueError(
                f"Unknown weight profile: {profile}. "
                f"Available: {list(WEIGHT_PROFILES.keys())}"
            )
        self._weights = dict(WEIGHT_PROFILES[profile])

    def set_custom_weights(self, weights: dict[str, float]) -> None:
        """Set custom dimension weights.

        Args:
            weights: Dimension weights (must include all 10 dimensions and sum to 1.0)
        """
        required_keys = set(WEIGHT_PROFILES["default"].keys())
        if not required_keys.issubset(weights.keys()):
            missing = required_keys - set(weights.keys())
            raise ValueError(f"Missing weights for dimensions: {missing}")

        total = sum(weights.values())
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total:.4f}")

        self._weights = dict(weights)

    @property
    def current_weights(self) -> dict[str, float]:
        """Get current weight configuration."""
        return dict(self._weights)

    def compute(
        self,
        stress_result: Any = None,
        emergence_report: Any = None,
        budget_usage_pct: float = 0.0,
        cost_trend_direction: str = "stable",
        code_metrics: CodeQualityMetrics | None = None,
        round_id: str = "",
    ) -> SQIReport:
        """Compute CodeService SQI from Harness metrics + code quality metrics.

        When stress_result, emergence_report are None and budget_usage_pct is 0,
        only code-specific dimensions are used (6 dims, re-normalized weights).
        """
        dimensions = [
            self._compute_delivery_quality(stress_result),
            self._compute_consistency(emergence_report),
            self._compute_cost_efficiency(budget_usage_pct, cost_trend_direction),
            self._compute_convergence_speed(stress_result),
            self._compute_stability(stress_result),
            self._compute_test_coverage(code_metrics),
            self._compute_lint_pass(code_metrics),
            self._compute_build_success(code_metrics),
            self._compute_doc_completeness(code_metrics),
            self._compute_regression_free(code_metrics),
        ]

        for d in dimensions:
            if d.name in self._weights:
                d.weight = self._weights[d.name]

        import statistics
        overall = sum(d.score * d.weight for d in dimensions)
        scores = [d.score for d in dimensions]
        variance = statistics.variance(scores) if len(scores) > 1 else 0.0

        return SQIReport(
            dimensions=dimensions,
            overall_score=overall,
            variance=variance,
            round_id=round_id,
            metadata={"weight_profile": "custom" if self._weights != WEIGHT_PROFILES.get("default") else "default", "mode": "full"},
        )

    # ------------------------------------------------------------------ #
    # Code-specific dimensions
    # ------------------------------------------------------------------ #
    def _compute_test_coverage(self, metrics: CodeQualityMetrics | None) -> SQIDimension:
        """Test coverage: percentage of code covered by unit tests."""
        if metrics is None or metrics.test_coverage_pct <= 0:
            return SQIDimension(
                name="test_coverage_rate", score=0.0,
                weight=self._weights["test_coverage_rate"],
                description="No coverage data available",
            )
        score = metrics.test_coverage_pct
        return SQIDimension(
            name="test_coverage_rate",
            score=min(100.0, max(0.0, score)),
            weight=self._weights["test_coverage_rate"],
            raw_value=metrics.test_coverage_pct,
            description=f"Test coverage: {metrics.test_coverage_pct:.1f}%",
        )

    def _compute_lint_pass(self, metrics: CodeQualityMetrics | None) -> SQIDimension:
        """Lint pass rate: static analysis compliance."""
        if metrics is None:
            return SQIDimension(
                name="lint_pass_rate", score=50.0,
                weight=self._weights["lint_pass_rate"],
                description="No lint data available",
            )
        score = metrics.lint_pass_rate * 100.0
        return SQIDimension(
            name="lint_pass_rate",
            score=min(100.0, max(0.0, score)),
            weight=self._weights["lint_pass_rate"],
            raw_value=metrics.lint_pass_rate,
            description=f"Lint pass rate: {metrics.lint_pass_rate:.2%}",
        )

    def _compute_build_success(self, metrics: CodeQualityMetrics | None) -> SQIDimension:
        """Build success rate: compilation/build pipeline pass rate."""
        if metrics is None:
            return SQIDimension(
                name="build_success_rate", score=50.0,
                weight=self._weights["build_success_rate"],
                description="No build data available",
            )
        score = metrics.build_success_rate * 100.0
        return SQIDimension(
            name="build_success_rate",
            score=min(100.0, max(0.0, score)),
            weight=self._weights["build_success_rate"],
            raw_value=metrics.build_success_rate,
            description=f"Build success rate: {metrics.build_success_rate:.2%}",
        )

    def _compute_doc_completeness(self, metrics: CodeQualityMetrics | None) -> SQIDimension:
        """Documentation completeness: ratio of documented files."""
        if metrics is None:
            return SQIDimension(
                name="doc_completeness", score=50.0,
                weight=self._weights["doc_completeness"],
                description="No documentation data available",
            )
        score = metrics.doc_completeness * 100.0
        return SQIDimension(
            name="doc_completeness",
            score=min(100.0, max(0.0, score)),
            weight=self._weights["doc_completeness"],
            raw_value=metrics.doc_completeness,
            description=f"Doc completeness: {metrics.doc_completeness:.2%}",
        )

    def _compute_regression_free(self, metrics: CodeQualityMetrics | None) -> SQIDimension:
        """Regression-free rate: percentage of changes that don't break existing tests."""
        if metrics is None:
            return SQIDimension(
                name="regression_free_rate", score=50.0,
                weight=self._weights["regression_free_rate"],
                description="No regression data available",
            )
        score = metrics.regression_free_rate * 100.0
        return SQIDimension(
            name="regression_free_rate",
            score=min(100.0, max(0.0, score)),
            weight=self._weights["regression_free_rate"],
            raw_value=metrics.regression_free_rate,
            description=f"Regression-free rate: {metrics.regression_free_rate:.2%}",
        )
