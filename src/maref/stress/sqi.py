"""Service Quality Index (SQI): Unified deterministic delivery scoring.

Aggregates StressHarness, EmergenceTestHarness, and CostTracker metrics
into a single 0-100 score representing "deterministic delivery capability."

5 dimensions (equal weight 0.2 each):
  1. delivery_quality: First-pass yield from healer_success_rate
  2. consistency: Output variance from consistency_rate
  3. cost_efficiency: Budget adherence from GasMeter/BudgetGuard
  4. convergence_speed: Recovery speed from resilience_score
  5. stability: Lyapunov stability from oscillation + ab_test_pass_rate
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SQIDimension:
    """Single dimension of the Service Quality Index."""

    name: str
    score: float  # 0.0 - 100.0
    weight: float  # contribution to overall SQI
    raw_value: float = 0.0
    description: str = ""


@dataclass
class SQIReport:
    """Complete Service Quality Index report."""

    timestamp: float = field(default_factory=time.time)
    dimensions: list[SQIDimension] = field(default_factory=list)
    overall_score: float = 0.0
    variance: float = 0.0  # variance across dimensions (lower = more balanced)
    round_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": round(self.overall_score, 2),
            "variance": round(self.variance, 2),
            "dimensions": {
                d.name: {
                    "score": round(d.score, 2),
                    "weight": d.weight,
                    "raw_value": d.raw_value,
                    "description": d.description,
                }
                for d in self.dimensions
            },
            "round_id": self.round_id,
            "timestamp": self.timestamp,
        }


class ServiceQualityIndex:
    """Compute deterministic delivery scores from MAREF Harness metrics.

    Usage:
        sqi = ServiceQualityIndex()
        report = sqi.compute(
            stress_result=stress_result,
            emergence_report=emergence_report,
            budget_usage_pct=0.65,
            round_id="test-001",
        )
    """

    DEFAULT_WEIGHTS = {
        "delivery_quality": 0.20,
        "consistency": 0.20,
        "cost_efficiency": 0.20,
        "convergence_speed": 0.20,
        "stability": 0.20,
    }

    def compute(
        self,
        stress_result: Any = None,
        emergence_report: Any = None,
        budget_usage_pct: float = 0.0,
        cost_trend_direction: str = "stable",
        round_id: str = "",
    ) -> SQIReport:
        """Compute SQI from available MAREF metrics.

        Args:
            stress_result: StressResult from StressHarness.run()
            emergence_report: EmergenceReport from EmergenceTestHarness
            budget_usage_pct: Budget consumption ratio (0.0-1.0)
            cost_trend_direction: "stable", "increasing", "decreasing"
            round_id: Identifier for this evaluation round
        """
        dimensions = [
            self._compute_delivery_quality(stress_result),
            self._compute_consistency(emergence_report),
            self._compute_cost_efficiency(budget_usage_pct, cost_trend_direction),
            self._compute_convergence_speed(stress_result),
            self._compute_stability(stress_result),
        ]

        overall = sum(d.score * d.weight for d in dimensions)
        scores = [d.score for d in dimensions]
        variance = statistics.variance(scores) if len(scores) > 1 else 0.0

        return SQIReport(
            dimensions=dimensions,
            overall_score=overall,
            variance=variance,
            round_id=round_id,
        )

    # ------------------------------------------------------------------ #
    # Dimension 1: delivery_quality
    # ------------------------------------------------------------------ #
    @classmethod
    def _compute_delivery_quality(cls, stress_result: Any | None) -> SQIDimension:
        """First-pass yield: how often the healer fixes issues on first try."""
        if stress_result is None or stress_result.healer_success_rate <= 0:
            return SQIDimension(
                name="delivery_quality", score=0.0, weight=cls.DEFAULT_WEIGHTS["delivery_quality"],
                description="No stress data available",
            )
        # Map healer_success_rate (0-1) to 0-100
        raw = stress_result.healer_success_rate
        score = raw * 100.0
        return SQIDimension(
            name="delivery_quality",
            score=min(100.0, max(0.0, score)),
            weight=cls.DEFAULT_WEIGHTS["delivery_quality"],
            raw_value=raw,
            description=f"Healer success rate: {raw:.2%}",
        )

    # ------------------------------------------------------------------ #
    # Dimension 2: consistency
    # ------------------------------------------------------------------ #
    @classmethod
    def _compute_consistency(cls, emergence_report: Any | None) -> SQIDimension:
        """Output variance: consistency rate from emergence testing."""
        if emergence_report is None:
            return SQIDimension(
                name="consistency", score=50.0, weight=cls.DEFAULT_WEIGHTS["consistency"],
                description="No emergence data, defaulting to neutral",
            )
        raw = emergence_report.consistency_rate
        score = raw * 100.0
        return SQIDimension(
            name="consistency",
            score=min(100.0, max(0.0, score)),
            weight=cls.DEFAULT_WEIGHTS["consistency"],
            raw_value=raw,
            description=f"Consistency rate: {raw:.2%} ({emergence_report.consistent_runs}/{emergence_report.run_count})",
        )

    # ------------------------------------------------------------------ #
    # Dimension 3: cost_efficiency
    # ------------------------------------------------------------------ #
    @classmethod
    def _compute_cost_efficiency(
        cls, budget_usage_pct: float, cost_trend_direction: str,
    ) -> SQIDimension:
        """Budget adherence: lower usage + stable trend = higher score."""
        # Budget usage: 100% usage = 0 score, 0% usage = 100 score (linear)
        usage_score = max(0.0, 100.0 - budget_usage_pct * 100.0)

        # Trend penalty: increasing = -20, stable = 0, decreasing = +10
        trend_penalty = {"increasing": -20, "stable": 0, "decreasing": 10}
        trend_adj = trend_penalty.get(cost_trend_direction, 0)

        raw = budget_usage_pct
        score = max(0.0, min(100.0, usage_score + trend_adj))
        return SQIDimension(
            name="cost_efficiency",
            score=score,
            weight=cls.DEFAULT_WEIGHTS["cost_efficiency"],
            raw_value=raw,
            description=f"Budget usage: {budget_usage_pct:.0%}, trend: {cost_trend_direction}",
        )

    # ------------------------------------------------------------------ #
    # Dimension 4: convergence_speed
    # ------------------------------------------------------------------ #
    @classmethod
    def _compute_convergence_speed(cls, stress_result: Any | None) -> SQIDimension:
        """Recovery speed: resilience_score maps directly."""
        if stress_result is None:
            return SQIDimension(
                name="convergence_speed", score=50.0,
                weight=cls.DEFAULT_WEIGHTS["convergence_speed"],
                description="No stress data available",
            )
        raw = stress_result.resilience_score
        score = raw * 100.0
        return SQIDimension(
            name="convergence_speed",
            score=min(100.0, max(0.0, score)),
            weight=cls.DEFAULT_WEIGHTS["convergence_speed"],
            raw_value=raw,
            description=f"Resilience score: {raw:.2f}",
        )

    # ------------------------------------------------------------------ #
    # Dimension 5: stability
    # ------------------------------------------------------------------ #
    @classmethod
    def _compute_stability(cls, stress_result: Any | None) -> SQIDimension:
        """Lyapunov stability: oscillation resolution + A/B test pass rate."""
        if stress_result is None:
            return SQIDimension(
                name="stability", score=50.0, weight=cls.DEFAULT_WEIGHTS["stability"],
                description="No stress data available",
            )
        # Weighted: 60% oscillation resolution, 40% A/B test pass
        oscillation_score = 100.0 if stress_result.oscillation_resolved else (50.0 if not stress_result.oscillation_detected else 0.0)
        ab_score = stress_result.ab_test_pass_rate * 100.0
        raw = 0.6 * (1.0 if stress_result.oscillation_resolved else 0.0) + 0.4 * stress_result.ab_test_pass_rate
        score = 0.6 * oscillation_score + 0.4 * ab_score
        return SQIDimension(
            name="stability",
            score=min(100.0, max(0.0, score)),
            weight=cls.DEFAULT_WEIGHTS["stability"],
            raw_value=raw,
            description=f"Oscillation resolved: {stress_result.oscillation_resolved}, A/B pass: {stress_result.ab_test_pass_rate:.2%}",
        )
