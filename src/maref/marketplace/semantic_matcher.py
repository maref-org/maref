"""Semantic Matcher — task-to-skill matching engine.

Sorts skills by: relevance × reputation × cost
Production: use embedding vectors. Here: keyword overlap as placeholder.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from maref.marketplace.registry import SkillManifest


@dataclass
class MatchScore:
    """Score for a skill-task match."""

    skill_id: str
    relevance: float  # 0.0-1.0, semantic similarity
    reputation: float  # 0.0-1.0, historical success rate
    cost: float  # normalized cost (lower is better)
    composite: float  # relevance * reputation / (1 + cost)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "relevance": round(self.relevance, 3),
            "reputation": round(self.reputation, 3),
            "cost": round(self.cost, 3),
            "composite": round(self.composite, 3),
        }


class SemanticMatcher:
    """Match tasks to skills using semantic similarity.

    Usage:
        matcher = SemanticMatcher()
        scores = matcher.match("make a chart from csv", skills, reputation_map)
        best = scores[0]
    """

    def match(
        self,
        task_description: str,
        skills: list[SkillManifest],
        reputation_map: dict[str, float] | None = None,
        cost_map: dict[str, float] | None = None,
    ) -> list[MatchScore]:
        """Rank skills for a given task.

        Formula: composite = relevance * reputation / (1 + cost)
        """
        rep = reputation_map or {}
        costs = cost_map or {}
        task_words = set(task_description.lower().split())
        scores: list[MatchScore] = []

        for skill in skills:
            text = f"{skill.name} {skill.description}".lower()
            skill_words = set(text.split())
            overlap = task_words & skill_words
            relevance = len(overlap) / max(len(task_words), 1)

            reputation = rep.get(skill.skill_id, 0.5)
            cost = costs.get(skill.skill_id, 0.0)
            composite = relevance * reputation / (1.0 + cost)

            scores.append(
                MatchScore(
                    skill_id=skill.skill_id,
                    relevance=relevance,
                    reputation=reputation,
                    cost=cost,
                    composite=composite,
                )
            )

        scores.sort(key=lambda s: -s.composite)
        return scores

    def match_multi_skill(
        self,
        task_description: str,
        skills: list[SkillManifest],
        reputation_map: dict[str, float] | None = None,
        cost_map: dict[str, float] | None = None,
    ) -> list[list[MatchScore]]:
        """Decompose a task and match multiple skills.

        Example: "make a chart from csv" → [data_cleaning_skill, visualization_skill]
        """
        # Simple decomposition: split by "and", "then", ","
        subtasks = [s.strip() for s in task_description.replace(",", " and ").split(" and ")]
        return [self.match(st, skills, reputation_map, cost_map) for st in subtasks if st]
