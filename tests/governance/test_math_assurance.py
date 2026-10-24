"""数学增强单元测试 — conformal / Lyapunov / σ̂ (P2-12)."""

from __future__ import annotations

import math

import pytest

from maref.governance.math_assurance import (
    BranchingRatioEstimator,
    ConformalCalibrator,
    LyapunovCertificate,
)
from maref.governance.types import GovernanceState


class TestConformal:
    def test_uncalibrated_is_infinite(self) -> None:
        interval = ConformalCalibrator().interval(0.7)
        assert math.isinf(interval.width)

    def test_quantile_shrinks_with_alpha(self) -> None:
        residuals = [0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
        calibrator = ConformalCalibrator(residuals)
        assert calibrator.quantile(0.5) <= calibrator.quantile(0.1)

    def test_interval_centered_on_point(self) -> None:
        calibrator = ConformalCalibrator([0.1, 0.2, 0.3, 0.4])
        interval = calibrator.interval(0.72, alpha=0.25)
        assert interval.lower <= 0.72 <= interval.upper
        assert interval.width == pytest.approx(2 * calibrator.quantile(0.25))

    def test_update_and_count(self) -> None:
        calibrator = ConformalCalibrator()
        calibrator.update(-0.5)
        calibrator.update(0.5)
        assert calibrator.count == 2

    def test_invalid_alpha(self) -> None:
        with pytest.raises(ValueError):
            ConformalCalibrator([0.1]).quantile(0.0)

    def test_to_dict(self) -> None:
        payload = ConformalCalibrator([0.1]).interval(0.5).to_dict()
        assert set(payload) == {"point", "lower", "upper", "alpha", "width"}


class TestLyapunov:
    def test_value_is_entropy(self) -> None:
        cert = LyapunovCertificate()
        assert cert.value(GovernanceState.ACT) == 4
        assert cert.value(GovernanceState.INIT) == 0

    def test_margin(self) -> None:
        cert = LyapunovCertificate()
        assert cert.margin(GovernanceState.ACT) == 0
        assert cert.margin(GovernanceState.INIT) == 4

    def test_dissipation_chain_has_no_violation(self) -> None:
        cert = LyapunovCertificate()
        chain = [
            (GovernanceState.ACT, GovernanceState.VERIFY),
            (GovernanceState.VERIFY, GovernanceState.STABILIZE),
            (GovernanceState.STABILIZE, GovernanceState.REPORT),
            (GovernanceState.REPORT, GovernanceState.HALT),
        ]
        assert cert.dissipation_violations(chain) == []

    def test_post_peak_increase_is_flagged(self) -> None:
        cert = LyapunovCertificate()
        chain = [
            (GovernanceState.ACT, GovernanceState.REPORT),
            (GovernanceState.REPORT, GovernanceState.OBSERVE),
        ]
        violations = cert.dissipation_violations(chain)
        assert (GovernanceState.REPORT, GovernanceState.OBSERVE) in violations

    def test_controlled_exception_allowed(self) -> None:
        cert = LyapunovCertificate(
            controlled_exceptions=[(GovernanceState.REPORT, GovernanceState.OBSERVE)]
        )
        chain = [
            (GovernanceState.ACT, GovernanceState.REPORT),
            (GovernanceState.REPORT, GovernanceState.OBSERVE),
        ]
        assert cert.dissipation_violations(chain) == []


class TestBranchingRatio:
    def test_no_samples(self) -> None:
        estimator = BranchingRatioEstimator()
        assert estimator.estimate() is None
        assert estimator.is_critical() is False

    def test_supercritical_detected(self) -> None:
        estimator = BranchingRatioEstimator()
        for _ in range(5):
            estimator.observe(2)
        assert estimator.estimate() == 2.0
        assert estimator.is_critical() is True

    def test_subcritical_not_flagged(self) -> None:
        estimator = BranchingRatioEstimator()
        for _ in range(5):
            estimator.observe(0)
        estimator.observe(1)
        assert estimator.is_critical() is False

    def test_window_bounds_samples(self) -> None:
        estimator = BranchingRatioEstimator(window=3)
        for value in (1, 2, 3, 4, 5):
            estimator.observe(value)
        assert estimator.sample_count == 3

    def test_invalid_window(self) -> None:
        with pytest.raises(ValueError):
            BranchingRatioEstimator(window=0)

    def test_snapshot(self) -> None:
        estimator = BranchingRatioEstimator()
        estimator.observe(1)
        payload = estimator.snapshot()
        assert payload["estimate"] == 1.0
        assert payload["critical"] is True
