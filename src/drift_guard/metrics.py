"""
MAREF DriftGuard Metrics Computation

Implements statistical divergence metrics for detecting LoRA weight drift:
- KL Divergence: Measures information loss between distributions
- JS Divergence: Symmetric and bounded variant of KL
- Hellinger Distance: Bounded metric for distribution similarity

All computations are done on probability distributions derived from
model weight tensors, enabling drift detection without full inference.
"""

from __future__ import annotations

import math
from typing import Protocol

import numpy as np


class Distribution(Protocol):
    """Protocol for probability distributions."""

    def pdf(self, x: float) -> float: ...


def kl_divergence(p: np.ndarray, q: np.ndarray, epsilon: float = 1e-10) -> float:
    """
    Compute KL divergence D_KL(P || Q).

    KL divergence measures how much information is lost when Q is used
    to approximate P. Non-symmetric and unbounded.

    Args:
        p: Reference probability distribution
        q: Approximation probability distribution
        epsilon: Small value to avoid log(0)

    Returns:
        KL divergence value (>= 0)
    """
    # Ensure valid probability distributions
    p = np.clip(p, epsilon, 1.0)
    q = np.clip(q, epsilon, 1.0)

    # Normalize
    p = p / np.sum(p)
    q = q / np.sum(q)

    return float(np.sum(p * np.log(p / q)))


def js_divergence(p: np.ndarray, q: np.ndarray, epsilon: float = 1e-10) -> float:
    """
    Compute Jensen-Shannon divergence.

    JS divergence is a symmetric and bounded variant of KL divergence:
    JS(P, Q) = 0.5 * KL(P || M) + 0.5 * KL(Q || M)
    where M = 0.5 * (P + Q)

    Bounded: 0 <= JS(P, Q) <= ln(2)

    Args:
        p: First probability distribution
        q: Second probability distribution
        epsilon: Small value to avoid log(0)

    Returns:
        JS divergence value in [0, ln(2)]
    """
    p = np.clip(p, epsilon, 1.0)
    q = np.clip(q, epsilon, 1.0)
    p = p / np.sum(p)
    q = q / np.sum(q)

    m = 0.5 * (p + q)
    return 0.5 * kl_divergence(p, m, epsilon) + 0.5 * kl_divergence(q, m, epsilon)


def hellinger_distance(p: np.ndarray, q: np.ndarray) -> float:
    """
    Compute Hellinger distance.

    Hellinger distance is a bounded metric measuring similarity
    between two probability distributions:
    H(P, Q) = (1/sqrt(2)) * ||sqrt(P) - sqrt(Q)||_2

    Bounded: 0 <= H(P, Q) <= 1

    Args:
        p: First probability distribution
        q: Second probability distribution

    Returns:
        Hellinger distance in [0, 1]
    """
    p = np.asarray(p, dtype=np.float64)
    q = np.asarray(q, dtype=np.float64)

    # Normalize
    p = p / np.sum(p)
    q = q / np.sum(q)

    bc = np.sum(np.sqrt(p * q))  # Bhattacharyya coefficient
    return math.sqrt(1.0 - bc)


def weights_to_distribution(
    weights: np.ndarray, num_bins: int = 100
) -> np.ndarray:
    """
    Convert weight tensor to probability distribution via histogram.

    Args:
        weights: Flattened weight array
        num_bins: Number of histogram bins

    Returns:
        Probability distribution over bins
    """
    weights = np.asarray(weights).flatten()
    hist, _ = np.histogram(weights, bins=num_bins, density=False)
    # Convert to probability distribution
    total = np.sum(hist)
    if total == 0:
        return np.ones(num_bins) / num_bins
    return hist / total


def compute_drift_metrics(
    baseline_weights: np.ndarray,
    current_weights: np.ndarray,
    num_bins: int = 100,
) -> dict[str, float]:
    """
    Compute all drift metrics between baseline and current weights.

    Args:
        baseline_weights: Baseline model weight tensor
        current_weights: Current model weight tensor
        num_bins: Number of histogram bins for distribution

    Returns:
        Dictionary with kl_divergence, js_divergence, hellinger_distance
    """
    p = weights_to_distribution(baseline_weights, num_bins)
    q = weights_to_distribution(current_weights, num_bins)

    return {
        "kl_divergence": kl_divergence(p, q),
        "js_divergence": js_divergence(p, q),
        "hellinger_distance": hellinger_distance(p, q),
    }


def compute_lora_drift(
    base_weights: dict[str, np.ndarray],
    lora_a: dict[str, np.ndarray],
    lora_b: dict[str, np.ndarray],
    scaling: float = 1.0,
) -> dict[str, float]:
    """
    Compute drift metrics for LoRA weights.

    LoRA update: W' = W + scaling * B * A
    We compare the distribution of the delta (B * A) against
    the baseline distribution to detect drift.

    Args:
        base_weights: Base model weights dictionary
        lora_a: LoRA A matrices dictionary
        lora_b: LoRA B matrices dictionary
        scaling: LoRA scaling factor

    Returns:
        Drift metrics dictionary
    """
    # Compute effective weight deltas
    deltas = []
    for key in lora_a:
        if key in lora_b:
            delta = scaling * (lora_b[key] @ lora_a[key])
            deltas.append(delta.flatten())

    if not deltas:
        return {
            "kl_divergence": 0.0,
            "js_divergence": 0.0,
            "hellinger_distance": 0.0,
        }

    delta_weights = np.concatenate(deltas)
    base_flat = np.concatenate([w.flatten() for w in base_weights.values()])

    return compute_drift_metrics(base_flat, delta_weights)


class DriftMetricsCollector:
    """Collects and tracks drift metrics over time."""

    def __init__(self, window_size: int = 100) -> None:
        self._window_size = window_size
        self._history: list[dict[str, float]] = []

    def record(self, metrics: dict[str, float]) -> None:
        """Record a set of drift metrics."""
        self._history.append(metrics)
        if len(self._history) > self._window_size:
            self._history.pop(0)

    def get_trend(self, metric: str = "kl_divergence") -> dict[str, float]:
        """Get trend statistics for a metric."""
        if not self._history:
            return {"mean": 0.0, "max": 0.0, "min": 0.0, "slope": 0.0}

        values = [h[metric] for h in self._history if metric in h]
        if not values:
            return {"mean": 0.0, "max": 0.0, "min": 0.0, "slope": 0.0}

        return {
            "mean": float(np.mean(values)),
            "max": float(np.max(values)),
            "min": float(np.min(values)),
            "slope": self._compute_slope(values),
        }

    def _compute_slope(self, values: list[float]) -> float:
        """Compute linear trend slope using least squares."""
        if len(values) < 2:
            return 0.0
        x = np.arange(len(values))
        y = np.array(values)
        return float(np.polyfit(x, y, 1)[0])

    def is_increasing(self, metric: str = "kl_divergence", threshold: float = 0.01) -> bool:
        """Check if a metric is trending upward."""
        trend = self.get_trend(metric)
        return trend["slope"] > threshold

    def get_history(self) -> list[dict[str, float]]:
        """Get full metrics history."""
        return list(self._history)
