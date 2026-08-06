"""
MAREF DriftGuard Adaptive Threshold Module

Phase 8: Implements self-adjusting thresholds based on historical
drift detection performance. This enables the system to learn
from its own detection history and optimize sensitivity.

Key features:
- False positive/negative tracking
- Threshold auto-tuning with bounds
- Performance metric collection
- Safe rollback to baseline
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ThresholdPerformance:
    """Performance metrics for a threshold configuration."""

    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0

    @property
    def precision(self) -> float:
        """Precision = TP / (TP + FP)."""
        if self.true_positives + self.false_positives == 0:
            return 0.0
        return self.true_positives / (self.true_positives + self.false_positives)

    @property
    def recall(self) -> float:
        """Recall = TP / (TP + FN)."""
        if self.true_positives + self.false_negatives == 0:
            return 0.0
        return self.true_positives / (self.true_positives + self.false_negatives)

    @property
    def f1_score(self) -> float:
        """F1 = 2 * (precision * recall) / (precision + recall)."""
        if self.precision + self.recall == 0:
            return 0.0
        return 2 * (self.precision * self.recall) / (self.precision + self.recall)

    @property
    def false_positive_rate(self) -> float:
        """FPR = FP / (FP + TN)."""
        if self.false_positives + self.true_negatives == 0:
            return 0.0
        return self.false_positives / (self.false_positives + self.true_negatives)

    @property
    def false_negative_rate(self) -> float:
        """FNR = FN / (FN + TP)."""
        if self.false_negatives + self.true_positives == 0:
            return 0.0
        return self.false_negatives / (self.false_negatives + self.true_positives)


@dataclass
class AdaptiveThresholdConfig:
    """Configuration for adaptive threshold behavior."""

    # Learning rate for threshold adjustments (0.0 - 1.0)
    learning_rate: float = 0.1

    # Target false positive rate (0.0 - 1.0)
    target_fpr: float = 0.05

    # Target false negative rate (0.0 - 1.0)
    target_fnr: float = 0.02

    # Minimum allowed threshold values
    min_kl_warning: float = 0.01
    min_kl_critical: float = 0.1
    min_kl_max: float = 0.5

    # Maximum allowed threshold values
    max_kl_warning: float = 0.5
    max_kl_critical: float = 2.0
    max_kl_max: float = 5.0

    # Window size for performance evaluation
    evaluation_window: int = 100

    # Enable/disable adaptive behavior
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "learning_rate": self.learning_rate,
            "target_fpr": self.target_fpr,
            "target_fnr": self.target_fnr,
            "min_kl_warning": self.min_kl_warning,
            "min_kl_critical": self.min_kl_critical,
            "min_kl_max": self.min_kl_max,
            "max_kl_warning": self.max_kl_warning,
            "max_kl_critical": self.max_kl_critical,
            "max_kl_max": self.max_kl_max,
            "evaluation_window": self.evaluation_window,
            "enabled": self.enabled,
        }


class AdaptiveThresholdManager:
    """
    Manages adaptive threshold adjustment for drift detection.

    Tracks detection outcomes and adjusts thresholds to optimize
    the balance between sensitivity and specificity.
    """

    def __init__(self, config: AdaptiveThresholdConfig | None = None) -> None:
        self._config = config or AdaptiveThresholdConfig()
        self._performance = ThresholdPerformance()
        self._history: list[tuple[float, bool, bool]] = []
        # (threshold_used, was_alert, was_true_drift)

    def record_outcome(
        self,
        threshold_used: float,
        predicted_drift: bool,
        actual_drift: bool,
    ) -> None:
        """
        Record the outcome of a drift detection decision.

        Args:
            threshold_used: The threshold value that was applied
            predicted_drift: Whether the system predicted drift
            actual_drift: Whether there was actual drift (ground truth)
        """
        self._history.append((threshold_used, predicted_drift, actual_drift))

        # Update performance metrics
        if predicted_drift and actual_drift:
            self._performance.true_positives += 1
        elif predicted_drift and not actual_drift:
            self._performance.false_positives += 1
        elif not predicted_drift and not actual_drift:
            self._performance.true_negatives += 1
        else:  # not predicted_drift and actual_drift
            self._performance.false_negatives += 1

        # Trim history to evaluation window
        if len(self._history) > self._config.evaluation_window:
            self._history.pop(0)

    def should_adjust(self) -> bool:
        """Check if enough data exists to make an adjustment."""
        return len(self._history) >= self._config.evaluation_window

    def compute_adjustment(self, current_threshold: float) -> float:
        """
        Compute the recommended threshold adjustment.

        Returns:
            The delta to apply to the current threshold.
            Positive = increase threshold (less sensitive)
            Negative = decrease threshold (more sensitive)
        """
        if not self._config.enabled or not self.should_adjust():
            return 0.0

        fpr = self._performance.false_positive_rate
        fnr = self._performance.false_negative_rate

        adjustment = 0.0

        # If FPR is too high, increase threshold (make it harder to trigger)
        if fpr > self._config.target_fpr:
            adjustment += self._config.learning_rate * (fpr - self._config.target_fpr)

        # If FNR is too high, decrease threshold (make it easier to trigger)
        if fnr > self._config.target_fnr:
            adjustment -= self._config.learning_rate * (fnr - self._config.target_fnr)

        return adjustment

    def adjust_threshold(self, current_threshold: float, threshold_type: str) -> float:
        """
        Apply adaptive adjustment to a threshold with bounds checking.

        Args:
            current_threshold: Current threshold value
            threshold_type: One of "warning", "critical", "max"

        Returns:
            The adjusted threshold value
        """
        adjustment = self.compute_adjustment(current_threshold)
        new_threshold = current_threshold + adjustment

        # Apply bounds based on threshold type
        if threshold_type == "warning":
            new_threshold = max(
                self._config.min_kl_warning,
                min(self._config.max_kl_warning, new_threshold),
            )
        elif threshold_type == "critical":
            new_threshold = max(
                self._config.min_kl_critical,
                min(self._config.max_kl_critical, new_threshold),
            )
        elif threshold_type == "max":
            new_threshold = max(
                self._config.min_kl_max,
                min(self._config.max_kl_max, new_threshold),
            )

        return new_threshold

    def get_performance(self) -> ThresholdPerformance:
        """Get current performance metrics."""
        return self._performance

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive statistics."""
        return {
            "config": self._config.to_dict(),
            "performance": {
                "true_positives": self._performance.true_positives,
                "false_positives": self._performance.false_positives,
                "true_negatives": self._performance.true_negatives,
                "false_negatives": self._performance.false_negatives,
                "precision": self._performance.precision,
                "recall": self._performance.recall,
                "f1_score": self._performance.f1_score,
                "false_positive_rate": self._performance.false_positive_rate,
                "false_negative_rate": self._performance.false_negative_rate,
            },
            "history_size": len(self._history),
            "ready_to_adjust": self.should_adjust(),
        }

    def reset(self) -> None:
        """Reset all performance tracking."""
        self._performance = ThresholdPerformance()
        self._history.clear()
