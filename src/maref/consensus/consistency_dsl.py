"""ConsistencyLevel DSL for MAREF orchestration.

Allows workflow authors to declare desired consistency per step,
with automatic cost estimation and dynamic degradation under load.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ConsistencyLevel(Enum):
    STRICT = "strict"       # synchronous replication, full barrier
    CAUSAL = "causal"       # vector-clock bounded staleness
    EVENTUAL = "eventual"   # best-effort, no barrier


@dataclass(frozen=True)
class ConsistencyCost:
    """Estimated overhead of a consistency level."""

    level: ConsistencyLevel
    latency_ms: float
    communication_multiplier: float
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "latency_ms": self.latency_ms,
            "communication_multiplier": self.communication_multiplier,
            "description": self.description,
        }


class CostEstimator:
    """Rough-cut cost model for consistency levels.

    In production this would be calibrated against real latency benchmarks.
    """

    BASELINE_LATENCY_MS = 100.0

    COSTS: dict[ConsistencyLevel, ConsistencyCost] = {
        ConsistencyLevel.STRICT: ConsistencyCost(
            level=ConsistencyLevel.STRICT,
            latency_ms=BASELINE_LATENCY_MS + 300.0,
            communication_multiplier=3.0,
            description="Synchronous replication, full barrier, highest correctness",
        ),
        ConsistencyLevel.CAUSAL: ConsistencyCost(
            level=ConsistencyLevel.CAUSAL,
            latency_ms=BASELINE_LATENCY_MS + 80.0,
            communication_multiplier=1.5,
            description="Vector-clock bounded staleness, partial barrier",
        ),
        ConsistencyLevel.EVENTUAL: ConsistencyCost(
            level=ConsistencyLevel.EVENTUAL,
            latency_ms=BASELINE_LATENCY_MS,
            communication_multiplier=1.0,
            description="Best-effort, no barrier, lowest latency",
        ),
    }

    @classmethod
    def estimate(cls, level: ConsistencyLevel) -> ConsistencyCost:
        return cls.COSTS[level]

    @classmethod
    def compare(cls, a: ConsistencyLevel, b: ConsistencyLevel) -> dict[str, Any]:
        ca = cls.estimate(a)
        cb = cls.estimate(b)
        return {
            "from": a.value,
            "to": b.value,
            "latency_delta_ms": round(cb.latency_ms - ca.latency_ms, 1),
            "comm_ratio": round(cb.communication_multiplier / ca.communication_multiplier, 2),
        }


class DynamicDegrader:
    """Automatically degrade non-critical paths when load exceeds thresholds.

    The degrader monitors a load signal and steps down consistency for
    steps that are not marked critical.
    """

    def __init__(
        self,
        high_load_threshold: float = 0.8,
        critical_path_levels: dict[str, ConsistencyLevel] | None = None,
    ) -> None:
        self._high_load_threshold = high_load_threshold
        self._critical_path_levels = critical_path_levels or {}

    def resolve(
        self,
        step_id: str,
        requested: ConsistencyLevel,
        current_load: float,
        is_critical: bool = False,
    ) -> ConsistencyLevel:
        """Return the effective consistency level for *step_id*.

        Rules:
        1. Critical paths keep their requested level regardless of load.
        2. If load < threshold, keep requested level.
        3. If load >= threshold, degrade one level (strict -> causal, causal -> eventual).
        """
        if is_critical:
            return self._critical_path_levels.get(step_id, requested)

        if current_load < self._high_load_threshold:
            return requested

        # Degrade one step
        if requested == ConsistencyLevel.STRICT:
            return ConsistencyLevel.CAUSAL
        if requested == ConsistencyLevel.CAUSAL:
            return ConsistencyLevel.EVENTUAL
        return ConsistencyLevel.EVENTUAL

    def explain(
        self,
        step_id: str,
        requested: ConsistencyLevel,
        current_load: float,
        is_critical: bool = False,
    ) -> dict[str, Any]:
        """Human-readable explanation of the degradation decision."""
        effective = self.resolve(step_id, requested, current_load, is_critical)
        cost_before = CostEstimator.estimate(requested)
        cost_after = CostEstimator.estimate(effective)
        return {
            "step_id": step_id,
            "requested": requested.value,
            "effective": effective.value,
            "is_critical": is_critical,
            "current_load": round(current_load, 2),
            "latency_before_ms": cost_before.latency_ms,
            "latency_after_ms": cost_after.latency_ms,
            "reason": (
                "load below threshold"
                if effective == requested
                else "degraded due to high load"
            ),
        }
