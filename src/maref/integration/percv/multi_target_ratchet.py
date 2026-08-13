from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ImprovementTarget(str, Enum):
    PROMPT_DISTILL = "prompts/distill_v1.yaml"
    PROMPT_PROJECT = "prompts/project_v1.yaml"
    EVALUATION_WEIGHTS = "config/quality_config.yaml"
    DIMENSION_WEIGHTS = "percv_weights.yaml"
    GOVERNANCE_RULES = "governance_rules.yaml"


@dataclass
class ExperimentResult:
    commit: str
    metric_value: float
    previous_best: float
    delta: float
    status: str
    description: str
    memory_mb: float
    mas_ts_score: float = 0.0
    mas_ts_level: str = ""
    target_dimension: str = ""
    dimension_scores: dict[str, float] | None = None


@dataclass
class MultiTargetConfig:
    rotation_mode: str = "round_robin"
    rounds_per_target: int = 3
    max_consecutive_discards: int = 5
    cooldown_rounds: int = 20


class MultiTargetRatchet:
    def __init__(
        self,
        targets: list[ImprovementTarget] | None = None,
        config: MultiTargetConfig | None = None,
    ):
        self.targets = targets or [
            ImprovementTarget.PROMPT_DISTILL,
            ImprovementTarget.PROMPT_PROJECT,
            ImprovementTarget.EVALUATION_WEIGHTS,
        ]
        self.config = config or MultiTargetConfig()
        self.current_index = 0
        self.history: dict[str, list[ExperimentResult]] = {t.value: [] for t in self.targets}
        self._round_count: dict[str, int] = {t.value: 0 for t in self.targets}

    def next_target(self) -> ImprovementTarget:
        if self.config.rotation_mode == "round_robin":
            t = self.targets[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.targets)
        elif self.config.rotation_mode == "weighted":
            t = self._weighted_select()
        else:
            t = self.targets[0]
        return t

    def set_weight_registry(self, registry: Any) -> None:
        self._weight_registry = registry

    def _weighted_select(self) -> ImprovementTarget:
        registry = getattr(self, "_weight_registry", None)
        if registry is not None:
            return self._registry_weighted_select(registry)

        from random import choices

        weights = []
        for t in self.targets:
            recent = self.history.get(t.value, [])[-5:]
            if not recent:
                weights.append(1.0)
            else:
                discard_rate = sum(1 for r in recent if r.status == "discard") / len(recent)
                weights.append(1.0 - discard_rate)
        total = sum(weights) or 1.0
        probs = [w / total for w in weights]
        return (
            self.targets[0] if len(self.targets) == 1 else choices(self.targets, weights=probs)[0]
        )

    def _registry_weighted_select(self, registry: Any) -> ImprovementTarget:
        weights = registry.get_all_weights()
        if not weights:
            return self.targets[0]

        dim_target_map = getattr(registry, "DIMENSION_TARGET_MAP", {})
        candidates: list[tuple[ImprovementTarget, float]] = []
        for dim, data in weights.items():
            target_path = dim_target_map.get(dim)
            if target_path is None:
                continue
            matched = [t for t in self.targets if t.value == target_path]
            if not matched:
                continue
            weight = data.get("current_weight", 0.5)
            candidates.append((matched[0], 1.0 - weight))

        if not candidates:
            return self.targets[0]

        from random import choices

        targets_w = [c[0] for c in candidates]
        weights_w = [max(c[1], 0.01) for c in candidates]
        return choices(targets_w, weights=weights_w)[0]

    def record_result(self, target: ImprovementTarget, result: ExperimentResult) -> None:
        self.history.setdefault(target.value, []).append(result)
        self._round_count[target.value] = self._round_count.get(target.value, 0) + 1

    def should_escalate(self, target: ImprovementTarget) -> bool:
        recent = self.history.get(target.value, [])[-5:]
        if len(recent) < 5:
            return False
        discards = sum(1 for r in recent if r.status == "discard")
        return discards >= 4

    def get_target_summary(self) -> dict[str, Any]:
        summary = {}
        for target in self.targets:
            hist = self.history.get(target.value, [])
            if not hist:
                summary[target.value] = {"rounds": 0, "avg_score": 0.0, "discard_rate": 0.0}
                continue
            scores = [r.metric_value for r in hist if r.status == "keep"]
            discards = sum(1 for r in hist if r.status == "discard")
            summary[target.value] = {
                "rounds": len(hist),
                "avg_score": sum(scores) / len(scores) if scores else 0.0,
                "best_score": max(scores) if scores else 0.0,
                "discard_rate": discards / len(hist) if hist else 0.0,
                "mas_ts_avg": sum(r.mas_ts_score for r in hist if r.mas_ts_score)
                / max(sum(1 for r in hist if r.mas_ts_score), 1),
            }
        return summary
