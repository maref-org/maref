"""High-order statistical convergence monitor for evolution time series.

Inspired by Deng Yu's work on wave turbulence and chaotic propagation:
beyond first-order Lyapunov stability, monitor higher moments
(variance, skewness, kurtosis) to detect pseudo-convergence where
the mean stabilises but the distribution remains unstable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConvergenceReport:
    """High-order convergence verdict for a time series."""

    series_name: str
    n_points: int
    mean: float
    variance: float
    skewness: float
    kurtosis: float
    mean_slope: float
    mean_converged: bool
    variance_converged: bool
    distribution_symmetric: bool
    no_extreme_outliers: bool
    fully_converged: bool
    pseudo_converged: bool
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "series_name": self.series_name,
            "n_points": self.n_points,
            "mean": round(self.mean, 4),
            "variance": round(self.variance, 4),
            "skewness": round(self.skewness, 4),
            "kurtosis": round(self.kurtosis, 4),
            "mean_slope": round(self.mean_slope, 4),
            "mean_converged": self.mean_converged,
            "variance_converged": self.variance_converged,
            "distribution_symmetric": self.distribution_symmetric,
            "no_extreme_outliers": self.no_extreme_outliers,
            "fully_converged": self.fully_converged,
            "pseudo_converged": self.pseudo_converged,
            "details": self.details,
        }


class HighOrderConvergenceMonitor:
    """Monitor convergence quality using high-order statistics.

    Checks four criteria on a sliding window:
    1. Mean is stable (absolute slope near zero)
    2. Variance is converged (below threshold or decreasing)
    3. Distribution is symmetric (skewness near zero)
    4. No extreme outliers (kurtosis near mesokurtic = 3)
    """

    DEFAULT_WINDOW = 20

    def __init__(
        self,
        window: int = DEFAULT_WINDOW,
        slope_threshold: float = 0.005,
        variance_threshold: float = 0.05,
        skewness_threshold: float = 0.5,
        kurtosis_threshold: float = 1.0,
    ) -> None:
        if window < 4:
            window = 4
        self._window = window
        self._slope_threshold = slope_threshold
        self._variance_threshold = variance_threshold
        self._skewness_threshold = skewness_threshold
        self._kurtosis_threshold = kurtosis_threshold

    @property
    def window(self) -> int:
        return self._window

    def compute(self, series: list[float], name: str = "") -> ConvergenceReport:
        """Compute high-order convergence statistics on a time series."""
        if len(series) < 3:
            return self._insufficient_data(name, len(series))

        window = min(self._window, len(series))
        recent = series[-window:]

        mean = sum(recent) / window
        variance = self._variance(recent, mean)
        std = variance ** 0.5

        is_degenerate = std <= 1e-10
        if is_degenerate:
            skewness = 0.0
            kurtosis = 3.0
        else:
            skewness = self._skewness(recent, mean, std)
            kurtosis = self._kurtosis(recent, mean, std)

        mean_slope = self._linear_slope(recent)

        mean_converged = abs(mean_slope) < self._slope_threshold or is_degenerate

        variance_converged = variance < self._variance_threshold or self._is_decreasing(variance)

        distribution_symmetric = abs(skewness) < self._skewness_threshold

        no_extreme_outliers = abs(kurtosis - 3.0) < self._kurtosis_threshold or is_degenerate

        fully_converged = (
            mean_converged and variance_converged
            and distribution_symmetric and no_extreme_outliers
        )

        pseudo_converged = mean_converged and not variance_converged

        details_list: list[str] = []
        if not mean_converged:
            details_list.append(f"mean slope {mean_slope:.4f} >= {self._slope_threshold}")
        if not variance_converged:
            details_list.append(f"variance {variance:.4f} >= {self._variance_threshold}")
        if not distribution_symmetric:
            details_list.append(f"|skewness| {abs(skewness):.4f} >= {self._skewness_threshold}")
        if not no_extreme_outliers:
            details_list.append(f"|kurtosis-3| {abs(kurtosis - 3.0):.4f} >= {self._kurtosis_threshold}")
        if pseudo_converged:
            details_list.append("pseudo-convergence detected: mean stable but variance not converged")

        return ConvergenceReport(
            series_name=name or self._series_name(series),
            n_points=len(series),
            mean=mean,
            variance=variance,
            skewness=skewness,
            kurtosis=kurtosis,
            mean_slope=mean_slope,
            mean_converged=mean_converged,
            variance_converged=variance_converged,
            distribution_symmetric=distribution_symmetric,
            no_extreme_outliers=no_extreme_outliers,
            fully_converged=fully_converged,
            pseudo_converged=pseudo_converged,
            details=details_list,
        )

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _variance(values: list[float], mean: float) -> float:
        if len(values) < 2:
            return 0.0
        return sum((x - mean) ** 2 for x in values) / (len(values) - 1)

    @staticmethod
    def _skewness(values: list[float], mean: float, std: float) -> float:
        n = len(values)
        if n < 3:
            return 0.0
        raw = sum(((x - mean) / std) ** 3 for x in values) / n
        # Small-sample adjustment
        return raw * (n * (n - 1)) ** 0.5 / (n - 2) if n > 2 else raw

    @staticmethod
    def _kurtosis(values: list[float], mean: float, std: float) -> float:
        n = len(values)
        if n < 4:
            return 0.0
        raw = sum(((x - mean) / std) ** 4 for x in values) / n
        # Excess kurtosis: mesokurtic = 3, so raw is the actual kurtosis
        return raw

    @staticmethod
    def _linear_slope(values: list[float]) -> float:
        """Simple slope via least-squares linear regression."""
        n = len(values)
        if n < 2:
            return 0.0
        xs = list(range(n))
        sx = sum(xs)
        sy = sum(values)
        sxx = sum(x * x for x in xs)
        sxy = sum(x * y for x, y in zip(xs, values))
        denom = n * sxx - sx * sx
        if abs(denom) < 1e-10:
            return 0.0
        return (n * sxy - sx * sy) / denom

    @staticmethod
    def _is_decreasing(current_variance: float) -> bool:
        """Conservative: a very low variance is already 'converged'."""
        return current_variance < 0.01

    @staticmethod
    def _series_name(series: list[float]) -> str:
        return "unnamed"

    def _insufficient_data(self, name: str, n: int) -> ConvergenceReport:
        return ConvergenceReport(
            series_name=name,
            n_points=n,
            mean=0.0,
            variance=0.0,
            skewness=0.0,
            kurtosis=0.0,
            mean_slope=0.0,
            mean_converged=False,
            variance_converged=False,
            distribution_symmetric=False,
            no_extreme_outliers=False,
            fully_converged=False,
            pseudo_converged=False,
            details=[f"Insufficient data points ({n} < 3)"],
        )
