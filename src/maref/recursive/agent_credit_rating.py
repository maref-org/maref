from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CreditRating(Enum):
    AAA = "AAA"
    AA = "AA"
    A = "A"
    BBB = "BBB"
    BB = "BB"
    B = "B"
    C = "C"
    D = "D"

    @property
    def numeric_value(self) -> int:
        return {
            CreditRating.AAA: 8,
            CreditRating.AA: 7,
            CreditRating.A: 6,
            CreditRating.BBB: 5,
            CreditRating.BB: 4,
            CreditRating.B: 3,
            CreditRating.C: 2,
            CreditRating.D: 1,
        }[self]

    @property
    def trust_floor(self) -> float:
        return {
            CreditRating.AAA: 0.90,
            CreditRating.AA: 0.80,
            CreditRating.A: 0.70,
            CreditRating.BBB: 0.60,
            CreditRating.BB: 0.50,
            CreditRating.B: 0.40,
            CreditRating.C: 0.25,
            CreditRating.D: 0.0,
        }[self]

    @property
    def allowed_evolution(self) -> bool:
        return self in (CreditRating.AAA, CreditRating.AA, CreditRating.A, CreditRating.BBB)

    @property
    def requires_human_review(self) -> bool:
        return self in (CreditRating.B, CreditRating.C, CreditRating.D)

    def next_up(self) -> CreditRating:
        mapping = {
            CreditRating.D: CreditRating.C,
            CreditRating.C: CreditRating.B,
            CreditRating.B: CreditRating.BB,
            CreditRating.BB: CreditRating.BBB,
            CreditRating.BBB: CreditRating.A,
            CreditRating.A: CreditRating.AA,
            CreditRating.AA: CreditRating.AAA,
        }
        return mapping.get(self, self)

    def next_down(self) -> CreditRating:
        mapping = {
            CreditRating.AAA: CreditRating.AA,
            CreditRating.AA: CreditRating.A,
            CreditRating.A: CreditRating.BBB,
            CreditRating.BBB: CreditRating.BB,
            CreditRating.BB: CreditRating.B,
            CreditRating.B: CreditRating.C,
            CreditRating.C: CreditRating.D,
        }
        return mapping.get(self, self)


class RatingDimension(Enum):
    TASK_COMPLETION = "task_completion"
    EVOLUTION_STABILITY = "evolution_stability"
    SAFETY_COMPLIANCE = "safety_compliance"
    COMMUNITY_EVALUATION = "community_evaluation"
    SURVIVAL_TIME = "survival_time"


DIMENSION_WEIGHTS: dict[RatingDimension, float] = {
    RatingDimension.TASK_COMPLETION: 0.25,
    RatingDimension.EVOLUTION_STABILITY: 0.25,
    RatingDimension.SAFETY_COMPLIANCE: 0.20,
    RatingDimension.COMMUNITY_EVALUATION: 0.15,
    RatingDimension.SURVIVAL_TIME: 0.15,
}

DIMENSION_LABELS: dict[RatingDimension, str] = {
    RatingDimension.TASK_COMPLETION: "\u4efb\u52a1\u5b8c\u6210\u7387",
    RatingDimension.EVOLUTION_STABILITY: "\u8fdb\u5316\u7a33\u5b9a\u6027",
    RatingDimension.SAFETY_COMPLIANCE: "\u5b89\u5168\u5408\u89c4",
    RatingDimension.COMMUNITY_EVALUATION: "\u793e\u533a\u8bc4\u4ef7",
    RatingDimension.SURVIVAL_TIME: "\u5b58\u7eed\u65f6\u95f4",
}


@dataclass
class DimensionScore:
    dimension: RatingDimension
    raw_score: float
    weight: float = 0.0
    normalized: float = 0.0
    trend: str = "stable"

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension.value,
            "label": DIMENSION_LABELS[self.dimension],
            "raw_score": round(self.raw_score, 4),
            "weight": round(self.weight, 3),
            "normalized": round(self.normalized, 3),
            "trend": self.trend,
        }


@dataclass
class RatingHistoryEntry:
    rating: CreditRating
    score: float
    timestamp: float = field(default_factory=time.time)
    dimensions: dict[str, float] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rating": self.rating.value,
            "score": round(self.score, 3),
            "timestamp": self.timestamp,
            "dimensions": {k: round(v, 3) for k, v in self.dimensions.items()},
            "reason": self.reason,
        }


@dataclass
class AgentCreditReport:
    agent_id: str
    current_rating: CreditRating
    overall_score: float
    dimensions: list[DimensionScore]
    history: list[RatingHistoryEntry]
    registered_at: float
    last_updated: float
    survival_days: float
    total_rating_changes: int
    consecutive_upgrades: int
    consecutive_downgrades: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "rating": self.current_rating.value,
            "overall_score": round(self.overall_score, 3),
            "dimensions": [d.to_dict() for d in self.dimensions],
            "history": [h.to_dict() for h in self.history[-10:]],
            "registered_at": self.registered_at,
            "last_updated": self.last_updated,
            "survival_days": round(self.survival_days, 1),
            "total_rating_changes": self.total_rating_changes,
            "consecutive_upgrades": self.consecutive_upgrades,
            "consecutive_downgrades": self.consecutive_downgrades,
        }


class AgentCreditRatingSystem:
    UPGRADE_SCORE_THRESHOLD = 0.75
    DOWNGRADE_SCORE_THRESHOLD = 0.50
    MAX_CONSECUTIVE_UPGRADES_BEFORE_COOLDOWN = 3
    MAX_CONSECUTIVE_DOWNGRADES_BEFORE_FREEZE = 3
    RATING_CHANGE_COOLDOWN_SECONDS = 3600.0
    MIN_SURVIVAL_DAYS_FOR_RATING = 1.0

    def __init__(self, agent_id: str, registered_at: float | None = None):
        self.agent_id = agent_id
        self._registered_at = registered_at or time.time()
        self._current_rating = CreditRating.B
        self._dimension_history: dict[RatingDimension, list[float]] = {d: [] for d in RatingDimension}
        self._rating_history: list[RatingHistoryEntry] = []
        self._last_rating_change_at: float = 0.0
        self._consecutive_upgrades: int = 0
        self._consecutive_downgrades: int = 0
        self._total_rating_changes: int = 0
        self._last_update: float = self._registered_at

        self._rating_history.append(RatingHistoryEntry(
            rating=self._current_rating,
            score=0.5,
            dimensions={d.value: 0.5 for d in RatingDimension},
            reason="initial_rating",
        ))

    @property
    def current_rating(self) -> CreditRating:
        return self._current_rating

    @property
    def survival_days(self) -> float:
        return (time.time() - self._registered_at) / 86400.0

    def update_dimension(self, dimension: RatingDimension, score: float) -> None:
        clamped = max(0.0, min(1.0, score))
        self._dimension_history[dimension].append(clamped)
        if len(self._dimension_history[dimension]) > 200:
            self._dimension_history[dimension] = self._dimension_history[dimension][-200:]
        self._last_update = time.time()

    def get_dimension_score(self, dimension: RatingDimension) -> float:
        history = self._dimension_history[dimension]
        if not history:
            return 0.5
        recent = history[-20:]
        avg = sum(recent) / len(recent)
        std = (sum((x - avg) ** 2 for x in recent) / len(recent)) ** 0.5
        return min(1.0, max(0.0, avg - 0.5 * std))

    def get_dimension_trend(self, dimension: RatingDimension) -> str:
        history = self._dimension_history[dimension]
        if len(history) < 5:
            return "stable"
        recent_avg = sum(history[-5:]) / 5
        prior_avg = sum(history[-10:-5]) / 5 if len(history) >= 10 else sum(history[:-5]) / max(1, len(history) - 5)
        if recent_avg > prior_avg + 0.05:
            return "improving"
        elif recent_avg < prior_avg - 0.05:
            return "declining"
        return "stable"

    def calculate_overall_score(self) -> float:
        total = 0.0
        for dim in RatingDimension:
            score = self.get_dimension_score(dim)
            weight = DIMENSION_WEIGHTS[dim]
            total += score * weight
        return total

    def get_rating_for_score(self, score: float) -> CreditRating:
        if score >= 0.90:
            return CreditRating.AAA
        elif score >= 0.80:
            return CreditRating.AA
        elif score >= 0.70:
            return CreditRating.A
        elif score >= 0.60:
            return CreditRating.BBB
        elif score >= 0.50:
            return CreditRating.BB
        elif score >= 0.40:
            return CreditRating.B
        elif score >= 0.25:
            return CreditRating.C
        return CreditRating.D

    def evaluate_rating(self) -> RatingHistoryEntry | None:
        overall = self.calculate_overall_score()
        dim_scores = {d.value: self.get_dimension_score(d) for d in RatingDimension}

        if self.survival_days < self.MIN_SURVIVAL_DAYS_FOR_RATING:
            return None

        new_rating = self.get_rating_for_score(overall)

        if new_rating == self._current_rating:
            return None

        now = time.time()
        if now - self._last_rating_change_at < self.RATING_CHANGE_COOLDOWN_SECONDS:
            return None

        if new_rating.numeric_value > self._current_rating.numeric_value:
            if self._consecutive_upgrades >= self.MAX_CONSECUTIVE_UPGRADES_BEFORE_COOLDOWN:
                return None
            self._consecutive_upgrades += 1
            self._consecutive_downgrades = 0
            reason = f"\u5347\u7ea7: {self._current_rating.value} \u2192 {new_rating.value}"
        else:
            if self._consecutive_downgrades >= self.MAX_CONSECUTIVE_DOWNGRADES_BEFORE_FREEZE:
                return None
            self._consecutive_downgrades += 1
            self._consecutive_upgrades = 0
            reason = f"\u964d\u7ea7: {self._current_rating.value} \u2192 {new_rating.value}"

        self._current_rating = new_rating
        self._last_rating_change_at = now
        self._total_rating_changes += 1

        entry = RatingHistoryEntry(
            rating=new_rating,
            score=overall,
            dimensions=dim_scores,
            reason=reason,
        )
        self._rating_history.append(entry)
        return entry

    def get_report(self) -> AgentCreditReport:
        overall = self.calculate_overall_score()
        dimensions = []
        for dim in RatingDimension:
            dimensions.append(DimensionScore(
                dimension=dim,
                raw_score=self.get_dimension_score(dim),
                weight=DIMENSION_WEIGHTS[dim],
                normalized=self.get_dimension_score(dim) * DIMENSION_WEIGHTS[dim],
                trend=self.get_dimension_trend(dim),
            ))

        return AgentCreditReport(
            agent_id=self.agent_id,
            current_rating=self._current_rating,
            overall_score=overall,
            dimensions=dimensions,
            history=self._rating_history.copy(),
            registered_at=self._registered_at,
            last_updated=self._last_update,
            survival_days=self.survival_days,
            total_rating_changes=self._total_rating_changes,
            consecutive_upgrades=self._consecutive_upgrades,
            consecutive_downgrades=self._consecutive_downgrades,
        )

    def fast_forward_time(self, days: float) -> None:
        self._registered_at -= days * 86400.0
        self._last_rating_change_at -= 86400.0 * max(days, 1.0)

    def reset_cooldown_for_test(self) -> None:
        self._last_rating_change_at = 0.0

    def to_dict(self) -> dict[str, Any]:
        return self.get_report().to_dict()
