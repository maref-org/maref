"""
MAREF Strategy A/B Comparison Pipeline

M5.3: Compares two PipelineConfig strategies across key metrics
and determines the winner with confidence scoring.

Features:
- Multi-metric comparison (FNR, FPR, stability rate, avg reward)
- Confidence scoring (win ratio across metrics)
- Canary-stage decision logic (promote/hold/rollback)
- Metric history tracking for trend analysis
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ABDecision(Enum):
    PROMOTE = "promote"
    HOLD = "hold"
    ROLLBACK = "rollback"


class ABWinner(Enum):
    NONE = "none"
    STRATEGY_A = "strategy_a"
    STRATEGY_B = "strategy_b"


@dataclass
class MetricSnapshot:
    fnr: float = 0.0
    fpr: float = 0.0
    stability_rate: float = 0.0
    avg_reward: float = 0.0
    anomaly_count: int = 0
    oscillation_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "fnr": self.fnr,
            "fpr": self.fpr,
            "stability_rate": self.stability_rate,
            "avg_reward": self.avg_reward,
            "anomaly_count": self.anomaly_count,
            "oscillation_count": self.oscillation_count,
        }


@dataclass
class ABResult:
    winner: ABWinner
    confidence: float
    decisions: dict[str, ABDecision]
    metric_deltas: dict[str, float]
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "winner": self.winner.value,
            "confidence": self.confidence,
            "decisions": {k: v.value for k, v in self.decisions.items()},
            "metric_deltas": self.metric_deltas,
            "details": self.details,
        }


class StrategyComparator:
    """
    Compare two strategies (A=baseline, B=candidate) across metrics.

    Used for GrowthBook-style canary validation:
    1. Collect metric snapshots under each strategy
    2. Compare with configurable thresholds
    3. Decide: promote (B wins), hold (inconclusive), rollback (A wins)
    """

    def __init__(
        self,
        fnr_tolerance: float = 0.05,
        fpr_tolerance: float = 0.03,
        stability_tolerance: float = 0.10,
        reward_tolerance: float = 0.10,
    ) -> None:
        self._fnr_tolerance = fnr_tolerance
        self._fpr_tolerance = fpr_tolerance
        self._stability_tolerance = stability_tolerance
        self._reward_tolerance = reward_tolerance

        self._history_a: list[MetricSnapshot] = []
        self._history_b: list[MetricSnapshot] = []

    def record_a(self, snapshot: MetricSnapshot) -> None:
        self._history_a.append(snapshot)

    def record_b(self, snapshot: MetricSnapshot) -> None:
        self._history_b.append(snapshot)

    def compare(self) -> ABResult:
        if not self._history_a or not self._history_b:
            return ABResult(
                winner=ABWinner.NONE,
                confidence=0.0,
                decisions={},
                metric_deltas={},
                details={"error": "insufficient_data"},
            )

        avg_a = self._average_snapshot(self._history_a)
        avg_b = self._average_snapshot(self._history_b)

        deltas = {
            "fnr": avg_a.fnr - avg_b.fnr,
            "fpr": avg_a.fpr - avg_b.fpr,
            "stability_rate": avg_b.stability_rate - avg_a.stability_rate,
            "avg_reward": avg_b.avg_reward - avg_a.avg_reward,
            "oscillation_count": avg_a.oscillation_count - avg_b.oscillation_count,
        }

        decisions: dict[str, ABDecision] = {}

        if deltas["fnr"] > self._fnr_tolerance:
            decisions["fnr"] = ABDecision.PROMOTE
        elif deltas["fnr"] < -self._fnr_tolerance:
            decisions["fnr"] = ABDecision.ROLLBACK
        else:
            decisions["fnr"] = ABDecision.HOLD

        if deltas["fpr"] > self._fpr_tolerance:
            decisions["fpr"] = ABDecision.PROMOTE
        elif deltas["fpr"] < -self._fpr_tolerance:
            decisions["fpr"] = ABDecision.ROLLBACK
        else:
            decisions["fpr"] = ABDecision.HOLD

        if deltas["stability_rate"] > self._stability_tolerance:
            decisions["stability"] = ABDecision.PROMOTE
        elif deltas["stability_rate"] < -self._stability_tolerance:
            decisions["stability"] = ABDecision.ROLLBACK
        else:
            decisions["stability"] = ABDecision.HOLD

        if deltas["avg_reward"] > self._reward_tolerance:
            decisions["reward"] = ABDecision.PROMOTE
        elif deltas["avg_reward"] < -self._reward_tolerance:
            decisions["reward"] = ABDecision.ROLLBACK
        else:
            decisions["reward"] = ABDecision.HOLD

        prom_count = sum(1 for d in decisions.values() if d == ABDecision.PROMOTE)
        roll_count = sum(1 for d in decisions.values() if d == ABDecision.ROLLBACK)
        hold_count = sum(1 for d in decisions.values() if d == ABDecision.HOLD)

        total = len(decisions)
        confidence = max(prom_count, roll_count, hold_count) / total if total > 0 else 0.0

        if prom_count > roll_count and prom_count > hold_count:
            winner = ABWinner.STRATEGY_B
        elif roll_count > prom_count and roll_count > hold_count:
            winner = ABWinner.STRATEGY_A
        else:
            winner = ABWinner.NONE

        return ABResult(
            winner=winner,
            confidence=confidence,
            decisions=decisions,
            metric_deltas=deltas,
            details={
                "avg_a": avg_a.to_dict(),
                "avg_b": avg_b.to_dict(),
                "sample_count_a": len(self._history_a),
                "sample_count_b": len(self._history_b),
                "tolerances": {
                    "fnr": self._fnr_tolerance,
                    "fpr": self._fpr_tolerance,
                    "stability": self._stability_tolerance,
                    "reward": self._reward_tolerance,
                },
            },
        )

    def _average_snapshot(self, snapshots: list[MetricSnapshot]) -> MetricSnapshot:
        n = len(snapshots)
        if n == 0:
            return MetricSnapshot()
        return MetricSnapshot(
            fnr=sum(s.fnr for s in snapshots) / n,
            fpr=sum(s.fpr for s in snapshots) / n,
            stability_rate=sum(s.stability_rate for s in snapshots) / n,
            avg_reward=sum(s.avg_reward for s in snapshots) / n,
            anomaly_count=sum(s.anomaly_count for s in snapshots) // n,
            oscillation_count=sum(s.oscillation_count for s in snapshots) // n,
        )

    def clear(self) -> None:
        self._history_a.clear()
        self._history_b.clear()

    def get_stats(self) -> dict[str, Any]:
        return {
            "sample_count_a": len(self._history_a),
            "sample_count_b": len(self._history_b),
            "last_result": self.compare().to_dict() if self._history_a and self._history_b else None,
        }
