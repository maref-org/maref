"""Math assurance toolkit — conformal / Lyapunov / branching-ratio (P2-12).

三件独立的数学增强，全部挂在现有治理读数上：

1. :class:`ConformalCalibrator` — split-conformal 无分布有限样本覆盖保证（1−α），
   给 Trust Engine 之类的标量分数加**统计有效置信区间**：``0.72±0.30`` 与
   ``0.72±0.02`` 应触发不同治理动作。
2. :class:`LyapunovCertificate` — 把 entropy profile 当作势能函数 V(state)。
   完整 profile 是山形（上升段有意为之），因此证书针对**耗散段**（峰值 ACT 之后）
   验证 V 非增，即"一旦达到峰值能量，治理必须单调耗散到 HALT"。
3. :class:`BranchingRatioEstimator` — 级联故障建模为分支过程，分支比 σ̂ ≥ 1 持续
   即告警（借鉴流行病 R₀ / 神经雪崩临界性），治理 OWASP ASI08。
"""

from __future__ import annotations

import math
import statistics
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from maref.governance.constants import ENTROPY_LEVELS, MAX_ENTROPY
from maref.governance.types import GovernanceState


@dataclass
class ConformalInterval:
    """A conformal prediction interval around a point estimate."""

    point: float
    lower: float
    upper: float
    alpha: float

    @property
    def width(self) -> float:
        """Total interval width (``inf`` when uncalibrated)."""
        return self.upper - self.lower

    def to_dict(self) -> dict[str, float]:
        return {
            "point": self.point,
            "lower": self.lower,
            "upper": self.upper,
            "alpha": self.alpha,
            "width": self.width,
        }


class ConformalCalibrator:
    """Split-conformal calibrator over absolute residuals."""

    def __init__(self, residuals: Iterable[float] | None = None) -> None:
        self._residuals: list[float] = [abs(residual) for residual in (residuals or [])]

    def update(self, residual: float) -> None:
        """Add an absolute calibration residual."""
        self._residuals.append(abs(residual))

    @property
    def count(self) -> int:
        """Number of calibration residuals."""
        return len(self._residuals)

    def quantile(self, alpha: float = 0.1) -> float:
        """Conformal quantile giving finite-sample 1−α coverage (inf if uncalibrated)."""
        if not 0.0 < alpha < 1.0:
            raise ValueError("alpha must be in (0, 1)")
        n = len(self._residuals)
        if n == 0:
            return float("inf")
        level = min(1.0, math.ceil((n + 1) * (1.0 - alpha)) / n)
        ordered = sorted(self._residuals)
        index = min(n - 1, max(0, math.ceil(level * n) - 1))
        return ordered[index]

    def interval(self, point: float, alpha: float = 0.1) -> ConformalInterval:
        """Prediction interval around ``point`` at miscoverage ``alpha``."""
        half_width = self.quantile(alpha)
        return ConformalInterval(point, point - half_width, point + half_width, alpha)


class LyapunovCertificate:
    """Potential-function certificate over the governance entropy profile.

    ``V(state)`` is the state's entropy level. The intended profile rises
    INIT→ACT and must then dissipate ACT→HALT, so :meth:`dissipation_violations`
    checks non-increase from the peak onward.
    """

    def __init__(
        self,
        entropy_levels: dict[GovernanceState, int] | None = None,
        peak_state: GovernanceState = GovernanceState.ACT,
        controlled_exceptions: Iterable[tuple[GovernanceState, GovernanceState]] | None = None,
    ) -> None:
        if entropy_levels is None:
            entropy_levels = {
                GovernanceState(state_id): level for state_id, level in ENTROPY_LEVELS.items()
            }
        self._entropy = dict(entropy_levels)
        self._peak = peak_state
        self._exceptions = set(controlled_exceptions or ())

    def value(self, state: GovernanceState) -> int:
        """Potential V(state) = entropy level."""
        return self._entropy[state]

    def margin(self, state: GovernanceState) -> int:
        """Distance from the entropy ceiling (headroom before max energy)."""
        return MAX_ENTROPY - self.value(state)

    def is_dissipative(self, from_state: GovernanceState, to_state: GovernanceState) -> bool:
        """Whether V does not increase across a transition (controlled exceptions allowed)."""
        if (from_state, to_state) in self._exceptions:
            return True
        return self.value(to_state) <= self.value(from_state)

    def dissipation_violations(
        self, transitions: Iterable[tuple[GovernanceState, GovernanceState]]
    ) -> list[tuple[GovernanceState, GovernanceState]]:
        """Transitions after the peak that increase V (certificate violations)."""
        violations: list[tuple[GovernanceState, GovernanceState]] = []
        past_peak = False
        for from_state, to_state in transitions:
            if from_state == self._peak:
                past_peak = True
            if past_peak and not self.is_dissipative(from_state, to_state):
                violations.append((from_state, to_state))
        return violations


class BranchingRatioEstimator:
    """Estimates the branching ratio σ̂ of a cascade (offspring per incident)."""

    def __init__(self, window: int = 20, threshold: float = 1.0) -> None:
        if window < 1:
            raise ValueError("window must be >= 1")
        self._window = window
        self._threshold = threshold
        self._offspring: deque[float] = deque(maxlen=window)

    def observe(self, offspring: int) -> None:
        """Record the number of secondary incidents spawned by one incident."""
        self._offspring.append(float(max(0, offspring)))

    @property
    def sample_count(self) -> int:
        """Number of recorded offspring observations."""
        return len(self._offspring)

    def estimate(self) -> float | None:
        """σ̂ = mean offspring; None when no samples."""
        if not self._offspring:
            return None
        return statistics.fmean(self._offspring)

    def is_critical(self) -> bool:
        """Whether σ̂ ≥ threshold (sustained super-critical cascade)."""
        estimate = self.estimate()
        return estimate is not None and estimate >= self._threshold

    def snapshot(self) -> dict[str, Any]:
        return {
            "estimate": self.estimate(),
            "critical": self.is_critical(),
            "threshold": self._threshold,
            "samples": self.sample_count,
        }
