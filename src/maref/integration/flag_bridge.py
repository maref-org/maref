"""
MAREF ↔ Feature Flag Bridge (GrowthBook-compatible)

M6.4: Translates MetaLearner.optimize_policy() outputs into
GrowthBook-compatible Feature Flag JSON definitions.

Supports the canary rollout flow:
  New Policy → GrowthBook Feature Flag → Canary 1% → 10% → 50% → 100%

Flag structure follows GrowthBook's JSON schema:
- key, description, enabled
- rules: canary percentage, targeting attributes
- variations: baseline vs. candidate config
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RolloutStage(Enum):
    CANARY_1 = 1
    CANARY_10 = 10
    CANARY_50 = 50
    FULL = 100
    ROLLED_BACK = 0


@dataclass
class FeatureFlag:
    key: str
    description: str
    enabled: bool = True
    default_variation: int = 0
    variations: list[dict[str, Any]] = field(default_factory=list)
    rules: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_growthbook_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "description": self.description,
            "enabled": self.enabled,
            "defaultVariation": self.default_variation,
            "variations": self.variations,
            "rules": self.rules,
            "meta": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_growthbook_json(), indent=2, default=str)


@dataclass
class PolicySnapshot:
    config: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    source: str = "meta_learner"
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config,
            "timestamp": self.timestamp,
            "source": self.source,
            "metrics": self.metrics,
        }


class FlagBridge:
    """
    Translates MAREF policies to GrowthBook Feature Flags.

    Each new policy becomes a Feature Flag with:
    - Baseline variation (current active policy)
    - Candidate variation (new proposed policy)
    - Canary rules (percentage-based rollout)

    Athena's GrowthBook instance consumes these flags for
    gradual, safe rollout of governance parameter changes.
    """

    def __init__(self, flag_prefix: str = "maref_policy_") -> None:
        self._flag_prefix = flag_prefix
        self._flags: list[FeatureFlag] = []

    def create_flag(
        self,
        baseline: PolicySnapshot,
        candidate: PolicySnapshot,
        policy_name: str = "",
        initial_stage: RolloutStage = RolloutStage.CANARY_1,
    ) -> FeatureFlag:
        name = policy_name or f"optimization_{int(time.time())}"
        flag_key = f"{self._flag_prefix}{name}"

        baseline_config = baseline.to_dict()
        candidate_config = candidate.to_dict()

        rules = []
        if initial_stage not in (RolloutStage.FULL, RolloutStage.ROLLED_BACK):
            rules.append(
                {
                    "name": f"canary_{initial_stage.value}pct",
                    "condition": {
                        "rolloutPercentage": float(initial_stage.value),
                        "hashAttribute": "agent_id",
                    },
                    "force": 1,
                    "coverage": float(initial_stage.value) / 100.0,
                }
            )

        flag = FeatureFlag(
            key=flag_key,
            description=f"MAREF policy optimization — {name}",
            variations=[
                {
                    "name": "baseline",
                    "config": baseline_config,
                    "weight": 100.0 - float(initial_stage.value),
                },
                {
                    "name": "candidate",
                    "config": candidate_config,
                    "weight": float(initial_stage.value),
                },
            ],
            rules=rules,
            metadata={
                "created_at": time.time(),
                "stage": initial_stage.value,
                "stage_name": initial_stage.name,
                "baseline_metrics": baseline.metrics,
                "candidate_metrics": candidate.metrics,
            },
        )
        self._flags.append(flag)
        return flag

    def advance_stage(
        self,
        flag: FeatureFlag,
        new_stage: RolloutStage,
        reason: str = "",
    ) -> FeatureFlag:
        if new_stage == RolloutStage.ROLLED_BACK:
            flag.rules = []
            flag.default_variation = 0
            flag.metadata["stage"] = 0
            flag.metadata["stage_name"] = "ROLLED_BACK"
        elif new_stage == RolloutStage.FULL:
            flag.rules = []
            flag.default_variation = 1
            flag.metadata["stage"] = 100
            flag.metadata["stage_name"] = "FULL"
        else:
            flag.rules = [
                {
                    "name": f"canary_{new_stage.value}pct",
                    "condition": {
                        "rolloutPercentage": float(new_stage.value),
                        "hashAttribute": "agent_id",
                    },
                    "force": 1,
                    "coverage": float(new_stage.value) / 100.0,
                }
            ]
            flag.metadata["stage"] = new_stage.value
            flag.metadata["stage_name"] = new_stage.name

        if reason:
            flag.metadata["stage_reason"] = reason
        flag.metadata["updated_at"] = time.time()
        return flag

    def rollback(self, flag: FeatureFlag, reason: str = "") -> FeatureFlag:
        return self.advance_stage(flag, RolloutStage.ROLLED_BACK, reason)

    def export_all(self) -> list[dict[str, Any]]:
        return [f.to_growthbook_json() for f in self._flags]

    def export_json(self) -> str:
        return json.dumps(self.export_all(), indent=2, default=str)

    def get_flag(self, key: str) -> FeatureFlag | None:
        for flag in self._flags:
            if flag.key == key:
                return flag
        return None

    def get_active_flags(self) -> list[FeatureFlag]:
        return [f for f in self._flags if f.enabled and f.metadata.get("stage", 0) > 0]

    def get_stats(self) -> dict[str, Any]:
        stages: dict[str, int] = {}
        for flag in self._flags:
            stage_name = flag.metadata.get("stage_name", "UNKNOWN")
            stages[stage_name] = stages.get(stage_name, 0) + 1
        return {
            "total_flags": len(self._flags),
            "active_count": len(self.get_active_flags()),
            "by_stage": stages,
        }

    def build_canary_pipeline(
        self,
        baseline: PolicySnapshot,
        candidate: PolicySnapshot,
        policy_name: str = "",
    ) -> list[dict[str, Any]]:
        stages = [
            RolloutStage.CANARY_1,
            RolloutStage.CANARY_10,
            RolloutStage.CANARY_50,
            RolloutStage.FULL,
        ]
        pipeline: list[dict[str, Any]] = []

        flag = self.create_flag(baseline, candidate, policy_name, RolloutStage.CANARY_1)
        pipeline.append(
            {
                "stage": 1,
                "flag_key": flag.key,
                "percentage": 1.0,
                "config": flag.to_growthbook_json(),
            }
        )

        for stage in stages[1:]:
            pipeline.append(
                {
                    "stage": stage.value,
                    "flag_key": flag.key,
                    "percentage": float(stage.value),
                    "promote_condition": "all_metrics_better_than_baseline",
                    "auto_rollback_on": [
                        "fnr_increase > 5%",
                        "fpr_increase > 3%",
                        "stability_decrease > 10%",
                    ],
                }
            )

        return pipeline
