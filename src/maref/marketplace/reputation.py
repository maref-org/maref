"""Reputation Tracker — skill success/failure scoring and fraud detection.

Formula: reputation = weighted_average(recent) - security_violation_penalty
Abnormal patterns (same agent high-frequency calling same skill) trigger freeze.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReputationRecord:
    """Single invocation feedback."""

    skill_id: str
    agent_id: str
    success: bool
    latency_ms: float = 0.0
    output_quality: float = 0.0  # 0.0-1.0, human or auto-rated
    notes: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "agent_id": self.agent_id,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "output_quality": self.output_quality,
            "notes": self.notes,
            "timestamp": self.timestamp,
        }


class ReputationTracker:
    """Track skill reputation and detect abnormal usage.

    Usage:
        rt = ReputationTracker()
        rt.record(ReputationRecord("skill-1", "agent-a", success=True, latency_ms=120))
        score = rt.get_score("skill-1")
        # Detect fraud
        if rt.is_abnormal("skill-1", "agent-a"):
            rt.freeze_skill("skill-1")
    """

    ABNORMAL_THRESHOLD = 10  # calls per hour
    DECAY_HALF_LIFE_HOURS = 168  # 1 week

    def __init__(self) -> None:
        self._records: list[ReputationRecord] = []
        self._frozen_skills: set[str] = set()
        self._call_counts: dict[tuple[str, str], list[float]] = {}
        # (skill_id, agent_id) -> list of timestamps

    def record(self, feedback: ReputationRecord) -> None:
        """Record invocation feedback."""
        self._records.append(feedback)
        key = (feedback.skill_id, feedback.agent_id)
        self._call_counts.setdefault(key, []).append(feedback.timestamp)

    def get_score(self, skill_id: str, window_hours: float = 168) -> float:
        """Calculate reputation score for a skill.

        Formula: weighted average of recent success rates, with recency weighting.
        Penalty applied for security violations.
        """
        if skill_id in self._frozen_skills:
            return 0.0

        cutoff = time.time() - window_hours * 3600
        relevant = [r for r in self._records if r.skill_id == skill_id and r.timestamp >= cutoff]
        if not relevant:
            return 0.5  # Default neutral score

        # Recency-weighted average
        total_weight = 0.0
        weighted_sum = 0.0
        for record in relevant:
            age_hours = (time.time() - record.timestamp) / 3600.0
            weight = 0.5 ** (age_hours / self.DECAY_HALF_LIFE_HOURS)
            score = 1.0 if record.success else 0.0
            # Incorporate output quality if available
            if record.output_quality > 0:
                score = 0.7 * score + 0.3 * record.output_quality
            weighted_sum += score * weight
            total_weight += weight

        base_score = weighted_sum / total_weight if total_weight > 0 else 0.5

        # Penalty for security violations
        violations = sum(1 for r in relevant if "security" in r.notes.lower())
        penalty = min(violations * 0.1, 0.5)

        return max(0.0, base_score - penalty)

    def get_agent_score(self, agent_id: str, window_hours: float = 168) -> float:
        """Calculate reputation score for an agent (inverse: how well it uses skills)."""
        cutoff = time.time() - window_hours * 3600
        relevant = [r for r in self._records if r.agent_id == agent_id and r.timestamp >= cutoff]
        if not relevant:
            return 0.5
        successes = sum(1 for r in relevant if r.success)
        return successes / len(relevant)

    def is_abnormal(self, skill_id: str, agent_id: str) -> bool:
        """Detect abnormal calling patterns.

        Triggers: same agent calls same skill > threshold times per hour.
        """
        key = (skill_id, agent_id)
        timestamps = self._call_counts.get(key, [])
        if not timestamps:
            return False
        one_hour_ago = time.time() - 3600
        recent_calls = [t for t in timestamps if t >= one_hour_ago]
        return len(recent_calls) > self.ABNORMAL_THRESHOLD

    def freeze_skill(self, skill_id: str) -> None:
        """Freeze a skill due to abnormal usage or security concerns."""
        self._frozen_skills.add(skill_id)

    def unfreeze_skill(self, skill_id: str) -> None:
        self._frozen_skills.discard(skill_id)

    def is_frozen(self, skill_id: str) -> bool:
        return skill_id in self._frozen_skills

    def get_stats(self, skill_id: str) -> dict[str, Any]:
        records = [r for r in self._records if r.skill_id == skill_id]
        total = len(records)
        if total == 0:
            return {"skill_id": skill_id, "total_calls": 0, "score": 0.5}
        successes = sum(1 for r in records if r.success)
        avg_latency = sum(r.latency_ms for r in records) / total
        return {
            "skill_id": skill_id,
            "total_calls": total,
            "success_rate": successes / total,
            "avg_latency_ms": round(avg_latency, 2),
            "score": round(self.get_score(skill_id), 3),
            "frozen": skill_id in self._frozen_skills,
        }
