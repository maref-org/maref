from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

FROZEN_TARGETS: dict[str, frozenset[str]] = {
    "rl_table": frozenset(
        {
            "RL-001",
            "RL-002",
            "RL-003",
            "RL-004",
            "RL-005",
        }
    ),
    "safety_gate_params": frozenset(
        {
            "safety_gate",
            "safety gate",
            "min_test_pass_rate",
            "max_coverage_drop_pct",
            "max_perf_regression_pct",
            "forbid_core_removal",
            "min_simulation_rounds",
            "require_sandbox_simulation",
        }
    ),
    "core_components": frozenset(
        {
            "circuit_breaker",
            "state_machine",
            "audit_logger",
            "meta_governance",
            "evolution_dsl",
        }
    ),
    "circuit_breaker_hard_limits": frozenset(
        {
            "max_depth",
            "max_failures",
            "trip_threshold",
            "cooldown_s",
            "max_consecutive_failures",
            "max_recursion_depth",
            "meta_cb_trip_threshold",
        }
    ),
    "audit_immutability": frozenset(
        {
            "hmac_key",
            "max_file_size_mb",
            "audit_retention_days",
        }
    ),
    "meta_freeze": frozenset(
        {
            "rule_freeze_zone",
            "RuleFreezeZone",
            "frozen_targets",
        }
    ),
}

ALL_FROZEN: frozenset[str] = frozenset().union(*FROZEN_TARGETS.values())


class FreezeBlockedError(Exception):
    pass


@dataclass
class FreezeZoneCheckResult:
    allowed: bool
    frozen_reason: str
    frozen_category: str
    timestamp: float = field(default_factory=time.time)
    check_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


@dataclass
class ParetoComparison:
    baseline: dict[str, float]
    proposal: dict[str, float]
    strictly_better: bool
    strictly_worse: bool
    better_metrics: list[str]
    worse_metrics: list[str]
    equal_metrics: list[str]
    pareto_dominant: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "strictly_better": self.strictly_better,
            "strictly_worse": self.strictly_worse,
            "better_metrics": self.better_metrics,
            "worse_metrics": self.worse_metrics,
            "equal_metrics": self.equal_metrics,
            "pareto_dominant": self.pareto_dominant,
        }


def is_frozen(target: str) -> bool:
    target_lower = target.lower().replace("_", " ").replace("-", " ")
    for frozen_word in ALL_FROZEN:
        frozen_lower = frozen_word.lower().replace("_", " ").replace("-", " ")
        if frozen_lower in target_lower or target_lower in frozen_lower:
            return True
    return False


def get_frozen_category(target: str) -> str | None:
    target_lower = target.lower().replace("_", " ").replace("-", " ")
    for category, words in FROZEN_TARGETS.items():
        for word in words:
            word_lower = word.lower().replace("_", " ").replace("-", " ")
            if word_lower in target_lower or target_lower in word_lower:
                return category
    return None


def compare_pareto(
    baseline: dict[str, float],
    proposal: dict[str, float],
    higher_is_better: frozenset[str] | None = None,
) -> ParetoComparison:
    if higher_is_better is None:
        higher_is_better = frozenset(
            {
                "test_pass_rate",
                "coverage_pct",
                "stability",
            }
        )

    all_keys = set(baseline.keys()) | set(proposal.keys())
    better_metrics: list[str] = []
    worse_metrics: list[str] = []
    equal_metrics: list[str] = []

    for key in sorted(all_keys):
        base_val = baseline.get(key, 0.0)
        prop_val = proposal.get(key, 0.0)
        if key in higher_is_better:
            if prop_val > base_val:
                better_metrics.append(key)
            elif prop_val < base_val:
                worse_metrics.append(key)
            else:
                equal_metrics.append(key)
        else:
            if prop_val < base_val:
                better_metrics.append(key)
            elif prop_val > base_val:
                worse_metrics.append(key)
            else:
                equal_metrics.append(key)

    strictly_better = len(worse_metrics) == 0 and len(better_metrics) > 0
    strictly_worse = len(better_metrics) == 0 and len(worse_metrics) > 0
    pareto_dominant = len(worse_metrics) == 0

    return ParetoComparison(
        baseline=baseline,
        proposal=proposal,
        strictly_better=strictly_better,
        strictly_worse=strictly_worse,
        better_metrics=better_metrics,
        worse_metrics=worse_metrics,
        equal_metrics=equal_metrics,
        pareto_dominant=pareto_dominant,
    )


class RuleFreezeZone:
    def __init__(self) -> None:
        self._audit: list[FreezeZoneCheckResult] = []
        self._overrides: dict[str, float] = {}
        self._override_count: int = 0

    def check(self, target: str, proposed_value: Any) -> FreezeZoneCheckResult:
        frozen = is_frozen(target)
        if not frozen:
            result = FreezeZoneCheckResult(
                allowed=True,
                frozen_reason="",
                frozen_category="",
            )
            self._audit.append(result)
            return result

        category = get_frozen_category(target) or "unknown"

        if target in self._overrides:
            expires_at = self._overrides[target]
            if time.time() < expires_at:
                result = FreezeZoneCheckResult(
                    allowed=True,
                    frozen_reason=f"override active until {expires_at}",
                    frozen_category=category,
                )
                self._audit.append(result)
                return result
            del self._overrides[target]

        result = FreezeZoneCheckResult(
            allowed=False,
            frozen_reason=f"target '{target}' is frozen in category '{category}'",
            frozen_category=category,
        )
        self._audit.append(result)
        return result

    def check_proposal(
        self, target: str, current_value: Any, proposed_value: Any
    ) -> FreezeZoneCheckResult:
        return self.check(target, proposed_value)

    def override(self, target: str, duration_seconds: float) -> None:
        self._overrides[target] = time.time() + duration_seconds
        self._override_count += 1

    def clear_override(self, target: str) -> None:
        self._overrides.pop(target, None)

    def clear_all_overrides(self) -> int:
        count = len(self._overrides)
        self._overrides.clear()
        return count

    @contextmanager
    def temporary_override(self, target: str, duration_seconds: float = 5.0) -> Iterator[None]:
        self.override(target, duration_seconds)
        try:
            yield
        finally:
            self.clear_override(target)

    def audit_trail(self) -> list[FreezeZoneCheckResult]:
        return list(self._audit)

    def blocked_count(self) -> int:
        return sum(1 for r in self._audit if not r.allowed)

    def allowed_count(self) -> int:
        return sum(1 for r in self._audit if r.allowed)

    def is_frozen_target(self, target: str) -> bool:
        return is_frozen(target)

    def frozen_categories(self) -> dict[str, frozenset[str]]:
        return dict(FROZEN_TARGETS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frozen_categories": list(FROZEN_TARGETS.keys()),
            "total_frozen_targets": len(ALL_FROZEN),
            "checks_total": len(self._audit),
            "checks_blocked": self.blocked_count(),
            "checks_allowed": self.allowed_count(),
            "active_overrides": len(self._overrides),
            "total_overrides_applied": self._override_count,
        }
