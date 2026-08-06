"""Adaptive goal discovery — automatically finds new improvement
targets from RSI results and validation records.

L3 feature: PERCV-RSI-ACCEPT-L3-004 / P5.5
"""

import datetime
from dataclasses import dataclass, field


@dataclass
class ImprovementGoal:
    """A discovered improvement goal."""
    name: str
    dimension: str
    current_score: float
    target_score: float
    priority: int  # 1=high, 2=medium, 3=low
    source: str  # e.g., "rsi_gap", "conflict_pattern", "degradation_trend"
    rationale: str
    created_at: str = ""
    status: str = "proposed"  # proposed, active, completed, abandoned


@dataclass
class GoalDiscoveryReport:
    goals: list[ImprovementGoal] = field(default_factory=list)
    total_discovered: int = 0
    dimensions_covered: list[str] = field(default_factory=list)
    generated_at: str = ""


class AdaptiveGoalDiscoverer:
    """Discovers improvement goals from RSI results.

    Sources:
    1. Score gaps: dimensions below threshold generate improvement goals
    2. Conflict patterns: detected conflicts suggest mediation goals
    3. Degradation trends: declining metrics trigger recovery goals
    4. Coverage gaps: untested dimensions suggest exploration goals
    """

    def __init__(self, min_score_threshold: float = 70.0,
                 max_goals_per_run: int = 5,
                 cooldown_hours: int = 24):
        self.min_score_threshold = min_score_threshold
        self.max_goals_per_run = max_goals_per_run
        self.cooldown_hours = cooldown_hours
        self._recent_goals: list[str] = []

    def discover_from_scores(self, scores: dict[str, float]) -> list[ImprovementGoal]:
        """Discover goals from score gaps."""
        goals = []
        for dim, score in scores.items():
            if score < self.min_score_threshold and dim not in self._recent_goals:
                goals.append(ImprovementGoal(
                    name=f"Improve {dim}",
                    dimension=dim,
                    current_score=score,
                    target_score=self.min_score_threshold,
                    priority=1 if score < self.min_score_threshold * 0.8 else 2,
                    source="rsi_gap",
                    rationale=f"Score {score:.1f} below threshold {self.min_score_threshold}",
                    created_at=datetime.datetime.now().isoformat(),
                ))
                self._recent_goals.append(dim)
        return self._deduplicate_and_limit(goals)

    def discover_from_conflicts(self, conflicts: list[dict]) -> list[ImprovementGoal]:
        """Discover goals from conflict patterns."""
        goals = []
        for conflict in conflicts:
            dim_a = conflict.get("dimension_a", "")
            dim_b = conflict.get("dimension_b", "")
            if dim_a and dim_b and f"conflict_{dim_a}_{dim_b}" not in self._recent_goals:
                goals.append(ImprovementGoal(
                    name=f"Resolve {dim_a}\u2194{dim_b} conflict",
                    dimension=f"{dim_a}_{dim_b}",
                    current_score=0.0,
                    target_score=1.0,
                    priority=1,
                    source="conflict_pattern",
                    rationale=f"Negative cross-impact between {dim_a} and {dim_b}",
                    created_at=datetime.datetime.now().isoformat(),
                ))
                self._recent_goals.append(f"conflict_{dim_a}_{dim_b}")
        return self._deduplicate_and_limit(goals)

    def discover_from_trends(self, trend_data: dict[str, list[float]]) -> list[ImprovementGoal]:
        """Discover goals from degradation trends."""
        goals = []
        for dim, values in trend_data.items():
            if len(values) >= 3:
                recent = values[-3:]
                if recent[0] > recent[-1] and dim not in self._recent_goals:
                    goals.append(ImprovementGoal(
                        name=f"Reverse {dim} decline",
                        dimension=dim,
                        current_score=recent[-1],
                        target_score=recent[0],
                        priority=1,
                        source="degradation_trend",
                        rationale=f"Consistent decline over 3 periods: {recent}",
                        created_at=datetime.datetime.now().isoformat(),
                    ))
                    self._recent_goals.append(dim)
        return self._deduplicate_and_limit(goals)

    def discover_all(self, scores: dict[str, float] | None = None,
                     conflicts: list[dict] | None = None,
                     trends: dict[str, list[float]] | None = None) -> GoalDiscoveryReport:
        """Run all discovery strategies and return combined report."""
        all_goals: list[ImprovementGoal] = []

        if scores:
            all_goals.extend(self.discover_from_scores(scores))
        if conflicts:
            all_goals.extend(self.discover_from_conflicts(conflicts))
        if trends:
            all_goals.extend(self.discover_from_trends(trends))

        dims = list({g.dimension for g in all_goals})

        return GoalDiscoveryReport(
            goals=all_goals,
            total_discovered=len(all_goals),
            dimensions_covered=dims,
            generated_at=datetime.datetime.now().isoformat(),
        )

    def _deduplicate_and_limit(self, goals: list[ImprovementGoal]) -> list[ImprovementGoal]:
        seen = set()
        unique = []
        for g in goals:
            if g.name not in seen:
                seen.add(g.name)
                unique.append(g)
        return unique[:self.max_goals_per_run]

    def clear_cooldown(self):
        """Clear recent goals cooldown."""
        self._recent_goals.clear()
