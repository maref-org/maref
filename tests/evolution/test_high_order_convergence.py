"""Tests for high-order convergence monitor (task ⑤).

Inspired by Deng Yu's wave turbulence and chaotic propagation:
detects pseudo-convergence where mean stabilises but
higher-order moments remain unstable.
"""

from __future__ import annotations

import math
import random

from maref.evolution.high_order_convergence import ConvergenceReport, HighOrderConvergenceMonitor


class TestHighOrderConvergenceMonitor:
    def test_constant_series_fully_converged(self) -> None:
        report = HighOrderConvergenceMonitor().compute([50.0] * 50, "constant")
        assert report.fully_converged, f"details: {report.details}"
        assert report.mean_converged
        assert report.variance_converged
        assert report.distribution_symmetric
        assert report.no_extreme_outliers
        assert not report.pseudo_converged

    def test_near_constant_series_converged(self) -> None:
        random.seed(42)
        series = [50.0 + random.gauss(0, 0.005) for _ in range(100)]
        report = HighOrderConvergenceMonitor().compute(series, "near_const")
        assert report.fully_converged, f"details: {report.details}"

    def test_divergent_series_not_converged(self) -> None:
        series = [float(i) for i in range(100)]
        report = HighOrderConvergenceMonitor().compute(series, "divergent")
        assert not report.fully_converged
        assert not report.mean_converged
        assert abs(report.mean_slope) > 0.005

    def test_pseudo_convergence_detected(self) -> None:
        """Deterministic series: mean strictly 50, variance jumps at midpoint."""
        base = [50.0] * 300
        noisy = [50.0 + (15.0 if j % 2 == 0 else -15.0) for j in range(300)]
        series = base + noisy  # 600 pts total
        report = HighOrderConvergenceMonitor(window=200).compute(series, "pseudo")
        assert report.pseudo_converged, (
            f"Expected pseudo-convergence. "
            f"mean_converged={report.mean_converged}, "
            f"variance_converged={report.variance_converged}, "
            f"variance={report.variance:.4f}"
        )

    def test_converging_series_ok(self) -> None:
        """Flat series with tiny noise."""
        random.seed(42)
        decay = [50.0 + random.gauss(0, 0.05) for _ in range(100)]
        report = HighOrderConvergenceMonitor(window=20).compute(decay, "decay")
        assert report.fully_converged, f"details: {report.details}"

    def test_insufficient_data(self) -> None:
        report = HighOrderConvergenceMonitor().compute([1.0, 2.0], "short")
        assert not report.fully_converged
        assert report.n_points == 2

    def test_report_to_dict(self) -> None:
        report = ConvergenceReport(
            series_name="test",
            n_points=50,
            mean=45.0,
            variance=2.0,
            skewness=0.1,
            kurtosis=3.2,
            mean_slope=0.001,
            mean_converged=True,
            variance_converged=True,
            distribution_symmetric=True,
            no_extreme_outliers=True,
            fully_converged=True,
            pseudo_converged=False,
            details=[],
        )
        d = report.to_dict()
        assert d["series_name"] == "test"
        assert d["mean"] == 45.0
        assert d["fully_converged"] is True

    def test_skewness_detects_asymmetry(self) -> None:
        """Heavily skewed series should fail symmetry check."""
        skewed = [0.1] * 40 + [10.0] * 10  # strong positive skew
        report = HighOrderConvergenceMonitor(window=50).compute(skewed, "skewed")
        assert not report.distribution_symmetric, f"skewness={report.skewness:.4f}"

    def test_kurtosis_detects_outliers(self) -> None:
        """Series with extreme outliers should fail kurtosis check."""
        random.seed(42)
        normal = [random.gauss(50, 3) for _ in range(95)]
        outliers = normal + [10.0, 90.0, 5.0, 95.0, 3.0]
        report = HighOrderConvergenceMonitor(window=100).compute(outliers, "outliers")
        assert not report.no_extreme_outliers, f"kurtosis={report.kurtosis:.4f}"

    def test_custom_window_and_thresholds(self) -> None:
        monitor = HighOrderConvergenceMonitor(
            window=5,
            slope_threshold=0.001,
            variance_threshold=0.01,
        )
        series = [50.0 + i * 0.0005 for i in range(30)]
        report = monitor.compute(series, "custom")
        assert isinstance(report.fully_converged, bool)
        assert monitor.window == 5
