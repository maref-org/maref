"""BlastRadiusController: limit the scope of saga compensation.

When a step fails, the controller decides which previously-completed steps
must be compensated.  The default policy is "compensate everything", but
with blast-radius control we can restrict the rollback to a configurable
number of agents/steps.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any


class CompensationStrategy(Enum):
    FULL = "full"               # compensate all completed steps
    PARTIAL = "partial"         # compensate up to max_radius steps
    SELECTIVE = "selective"     # only steps matching a predicate
    SKIP_NON_CRITICAL = "skip_non_critical"  # skip steps marked non-critical


@dataclass
class BlastRadiusConfig:
    """Configuration for blast-radius-limited compensation."""

    strategy: CompensationStrategy = CompensationStrategy.FULL
    max_radius: int = 2           # max number of steps to compensate
    skip_on_partial_failure: bool = True
    # Human-confirmation gate for large-radius compensations
    confirm_radius_threshold: int = 3
    # Predicate for SELECTIVE strategy: step_id -> bool
    select_predicate: Callable[[str], bool] | None = None


@dataclass
class CompensationDecision:
    """Outcome of the blast-radius controller."""

    steps_to_compensate: list[str]
    skipped_steps: list[str]
    strategy: CompensationStrategy
    requires_human_confirm: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps_to_compensate": self.steps_to_compensate,
            "skipped_steps": self.skipped_steps,
            "strategy": self.strategy.value,
            "requires_human_confirm": self.requires_human_confirm,
            "reason": self.reason,
        }


class BlastRadiusController:
    """Decides how far back a saga should compensate on failure.

    The ideal blast radius is 1 (only the failing agent's state is rolled
    back).  In practice dependencies may force a larger radius, which this
    controller caps and audits.
    """

    def __init__(self, config: BlastRadiusConfig | None = None) -> None:
        self._config = config or BlastRadiusConfig()

    def decide(
        self,
        failed_step_id: str,
        completed_step_ids: list[str],
        criticality_map: dict[str, bool] | None = None,
    ) -> CompensationDecision:
        """Return the list of step IDs that should be compensated.

        Args:
            failed_step_id: the step that just failed
            completed_step_ids: ordered list of successfully completed steps
            criticality_map: step_id -> True if step is critical
        """
        strategy = self._config.strategy
        max_radius = self._config.max_radius
        critical = criticality_map or {}

        # Reverse order: most recent first
        candidates = list(reversed(completed_step_ids))
        to_compensate: list[str] = []
        skipped: list[str] = []

        if strategy == CompensationStrategy.FULL:
            to_compensate = list(completed_step_ids)
        elif strategy == CompensationStrategy.PARTIAL:
            to_compensate = candidates[:max_radius]
            skipped = candidates[max_radius:]
        elif strategy == CompensationStrategy.SELECTIVE:
            predicate = self._config.select_predicate
            if predicate is None:
                # No predicate provided -> fall back to PARTIAL
                to_compensate = candidates[:max_radius]
                skipped = candidates[max_radius:]
            else:
                for sid in candidates:
                    if predicate(sid):
                        to_compensate.append(sid)
                    else:
                        skipped.append(sid)
                    if len(to_compensate) >= max_radius:
                        skipped.extend(candidates[candidates.index(sid) + 1:])
                        break
        elif strategy == CompensationStrategy.SKIP_NON_CRITICAL:
            for sid in candidates:
                if critical.get(sid, True):
                    to_compensate.append(sid)
                else:
                    skipped.append(sid)
                    if len(to_compensate) >= max_radius:
                        # Once we hit the radius cap, everything else is skipped
                        skipped.extend(candidates[candidates.index(sid) + 1:])
                        break
        else:
            to_compensate = candidates[:max_radius]
            skipped = candidates[max_radius:]

        requires_confirm = len(to_compensate) >= self._config.confirm_radius_threshold

        return CompensationDecision(
            steps_to_compensate=list(reversed(to_compensate)),
            skipped_steps=list(reversed(skipped)),
            strategy=strategy,
            requires_human_confirm=requires_confirm,
            reason=f"failed_step={failed_step_id}, radius={len(to_compensate)}",
        )

    @property
    def config(self) -> BlastRadiusConfig:
        return self._config
