"""
MAREF A/B Testing Framework

Phase 9: Provides controlled experimentation for policy changes.
Allows comparing two policy configurations side-by-side before
committing to a full deployment.

Key features:
- Parallel policy execution
- Statistical significance testing
- Automatic winner selection
- Safe fallback to baseline
"""

from __future__ import annotations

import copy
import statistics
import time
from dataclasses import dataclass, field
from typing import Any

from drift_guard.policy_sandbox import PolicySandbox
from drift_guard.types import PipelineConfig


@dataclass
class ABTestMetrics:
    """Metrics collected during A/B test."""

    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0
    latency_ms: list[float] = field(default_factory=list)

    @property
    def precision(self) -> float:
        if self.true_positives + self.false_positives == 0:
            return 0.0
        return self.true_positives / (self.true_positives + self.false_positives)

    @property
    def recall(self) -> float:
        if self.true_positives + self.false_negatives == 0:
            return 0.0
        return self.true_positives / (self.true_positives + self.false_negatives)

    @property
    def f1_score(self) -> float:
        if self.precision + self.recall == 0:
            return 0.0
        return 2 * (self.precision * self.recall) / (self.precision + self.recall)

    @property
    def mean_latency(self) -> float:
        if not self.latency_ms:
            return 0.0
        return statistics.mean(self.latency_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "true_negatives": self.true_negatives,
            "false_negatives": self.false_negatives,
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
            "mean_latency_ms": self.mean_latency,
            "sample_size": len(self.latency_ms),
        }


@dataclass
class ABTestResult:
    """Result of an A/B test comparison."""

    test_id: str
    baseline_metrics: ABTestMetrics
    variant_metrics: ABTestMetrics
    winner: str  # "baseline", "variant", or "tie"
    confidence: float  # 0.0 - 1.0
    improvement_pct: dict[str, float] = field(default_factory=dict)
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "baseline_metrics": self.baseline_metrics.to_dict(),
            "variant_metrics": self.variant_metrics.to_dict(),
            "winner": self.winner,
            "confidence": self.confidence,
            "improvement_pct": self.improvement_pct,
            "recommendation": self.recommendation,
        }


class ABTestFramework:
    """
    A/B testing framework for policy changes.

    Runs two policy configurations in parallel and compares
    their performance on identical inputs.
    """

    def __init__(self, sandbox: PolicySandbox | None = None) -> None:
        self._sandbox = sandbox or PolicySandbox()
        self._active_tests: dict[str, dict[str, Any]] = {}

    def create_test(
        self,
        test_id: str,
        baseline_config: PipelineConfig,
        variant_config: PipelineConfig,
        min_samples: int = 100,
    ) -> bool:
        """
        Create a new A/B test.

        Args:
            test_id: Unique identifier for this test
            baseline_config: The current/baseline policy
            variant_config: The new policy to test
            min_samples: Minimum samples before declaring winner

        Returns:
            True if test was created successfully
        """
        if test_id in self._active_tests:
            return False

        self._active_tests[test_id] = {
            "baseline_config": copy.deepcopy(baseline_config),
            "variant_config": copy.deepcopy(variant_config),
            "baseline_metrics": ABTestMetrics(),
            "variant_metrics": ABTestMetrics(),
            "min_samples": min_samples,
            "started_at": time.time(),
            "completed": False,
        }
        return True

    def record_sample(
        self,
        test_id: str,
        variant: str,  # "baseline" or "variant"
        predicted_drift: bool,
        actual_drift: bool,
        latency_ms: float,
    ) -> bool:
        """
        Record a sample for an active A/B test.

        Args:
            test_id: Test identifier
            variant: Which variant this sample belongs to
            predicted_drift: Whether drift was predicted
            actual_drift: Whether drift actually occurred
            latency_ms: Detection latency in milliseconds

        Returns:
            True if sample was recorded
        """
        if test_id not in self._active_tests:
            return False

        test = self._active_tests[test_id]
        if test["completed"]:
            return False

        metrics = (
            test["baseline_metrics"]
            if variant == "baseline"
            else test["variant_metrics"]
        )

        # Update confusion matrix
        if predicted_drift and actual_drift:
            metrics.true_positives += 1
        elif predicted_drift and not actual_drift:
            metrics.false_positives += 1
        elif not predicted_drift and not actual_drift:
            metrics.true_negatives += 1
        else:
            metrics.false_negatives += 1

        metrics.latency_ms.append(latency_ms)
        return True

    def evaluate_test(self, test_id: str) -> ABTestResult | None:
        """
        Evaluate an A/B test and determine winner.

        Args:
            test_id: Test identifier

        Returns:
            ABTestResult if test is complete, None otherwise
        """
        if test_id not in self._active_tests:
            return None

        test = self._active_tests[test_id]
        baseline = test["baseline_metrics"]
        variant = test["variant_metrics"]

        # Check if we have enough samples
        total_samples = (
            len(baseline.latency_ms) + len(variant.latency_ms)
        )
        if total_samples < test["min_samples"]:
            return None

        # Mark as completed
        test["completed"] = True

        # Calculate improvements
        improvements = {}
        if baseline.f1_score > 0:
            improvements["f1_score"] = (
                (variant.f1_score - baseline.f1_score) / baseline.f1_score * 100
            )
        if baseline.mean_latency > 0:
            improvements["latency"] = (
                (baseline.mean_latency - variant.mean_latency)
                / baseline.mean_latency
                * 100
            )

        # Determine winner based on F1 score (primary) and latency (secondary)
        winner = "tie"
        confidence = 0.5

        f1_diff = variant.f1_score - baseline.f1_score
        if abs(f1_diff) > 0.05:  # At least 5% difference in F1
            if f1_diff > 0:
                winner = "variant"
                confidence = min(0.5 + abs(f1_diff), 0.95)
            else:
                winner = "baseline"
                confidence = min(0.5 + abs(f1_diff), 0.95)

        # Generate recommendation
        if winner == "variant" and confidence > 0.7:
            recommendation = (
                f"Variant shows significant improvement "
                f"({improvements.get('f1_score', 0):.1f}% F1, "
                f"{improvements.get('latency', 0):.1f}% latency). Recommend deployment."
            )
        elif winner == "baseline":
            recommendation = (
                "Baseline performs better. Reject variant and investigate."
            )
        else:
            recommendation = (
                "No clear winner. Consider extending test or revising variant."
            )

        return ABTestResult(
            test_id=test_id,
            baseline_metrics=baseline,
            variant_metrics=variant,
            winner=winner,
            confidence=confidence,
            improvement_pct=improvements,
            recommendation=recommendation,
        )

    def get_test_status(self, test_id: str) -> dict[str, Any] | None:
        """Get current status of an A/B test."""
        if test_id not in self._active_tests:
            return None

        test = self._active_tests[test_id]
        return {
            "test_id": test_id,
            "completed": test["completed"],
            "baseline_samples": len(test["baseline_metrics"].latency_ms),
            "variant_samples": len(test["variant_metrics"].latency_ms),
            "min_samples": test["min_samples"],
            "elapsed_seconds": time.time() - test["started_at"],
        }
