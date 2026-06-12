"""SQI Convergence Tracker: monitors SQI improvement across rounds.

Tracks whether deterministic delivery capability converges over time
using Lyapunov-style decrease conditions.

Usage:
    tracker = SQIConvergenceTracker(target=90.0, window=5)
    tracker.record_round("r1", sqi_report)
    ...
    is_converged = tracker.check_convergence()
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from maref.stress.sqi import SQIReport


@dataclass
class ConvergenceRecord:
    round_id: str
    timestamp: float
    overall_score: float
    dimension_scores: dict[str, float]
    delta: float = 0.0  # change from previous round


@dataclass
class ConvergenceState:
    is_converged: bool
    rounds_tracked: int
    current_score: float
    target_score: float
    trend: str  # "improving", "stable", "degrading"
    saturation_window: int  # consecutive rounds with gain < threshold
    history: list[ConvergenceRecord] = field(default_factory=list)


class SQIConvergenceTracker:
    """Track SQI convergence across evaluation rounds."""

    def __init__(
        self,
        target: float = 90.0,
        window: int = 5,
        gain_threshold: float = 0.5,
    ) -> None:
        self._target = target
        self._window = window
        self._gain_threshold = gain_threshold
        self._history: list[ConvergenceRecord] = []

    def record_round(self, round_id: str, report: SQIReport) -> ConvergenceRecord:
        prev_score = self._history[-1].overall_score if self._history else 0.0
        delta = report.overall_score - prev_score

        dim_scores = {d.name: d.score for d in report.dimensions}
        record = ConvergenceRecord(
            round_id=round_id,
            timestamp=time.time(),
            overall_score=report.overall_score,
            dimension_scores=dim_scores,
            delta=delta,
        )
        self._history.append(record)
        return record

    def check_convergence(self) -> ConvergenceState:
        if not self._history:
            return ConvergenceState(
                is_converged=False,
                rounds_tracked=0,
                current_score=0.0,
                target_score=self._target,
                trend="unknown",
                saturation_window=0,
            )

        current = self._history[-1].overall_score
        recent = [r.delta for r in self._history[-self._window:]]

        # Saturation: consecutive rounds with gain < threshold
        saturation = 0
        for delta in reversed(recent):
            if abs(delta) < self._gain_threshold:
                saturation += 1
            else:
                break

        # Trend
        if len(recent) >= 2:
            avg_recent = sum(recent) / len(recent)
            if avg_recent > self._gain_threshold:
                trend = "improving"
            elif avg_recent < -self._gain_threshold:
                trend = "degrading"
            else:
                trend = "stable"
        else:
            trend = "stable"

        is_converged = current >= self._target and saturation >= self._window

        return ConvergenceState(
            is_converged=is_converged,
            rounds_tracked=len(self._history),
            current_score=current,
            target_score=self._target,
            trend=trend,
            saturation_window=saturation,
            history=list(self._history),
        )

    def summary(self) -> dict[str, float]:
        """Return summary statistics of tracked rounds."""
        if not self._history:
            return {}
        scores = [r.overall_score for r in self._history]
        deltas = [r.delta for r in self._history[1:]]
        return {
            "rounds": len(self._history),
            "initial": scores[0],
            "current": scores[-1],
            "best": max(scores),
            "total_improvement": scores[-1] - scores[0],
            "avg_delta": sum(deltas) / len(deltas) if deltas else 0.0,
        }
