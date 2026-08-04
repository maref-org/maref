"""ValueMetric: business value metric model (v0.51 W2-S1 / B1).

Represents a quantifiable business outcome (hours saved, cycle-time reduction,
error reduction, attainment rate) with baseline/current/delta. Each task can
attach one or more metrics so that agent work can be priced in business value
rather than raw tokens.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ValueMetricType(Enum):
    """Types of business value a task can produce."""

    HOURS_SAVED = "hours_saved"
    CYCLE_TIME = "cycle_time"
    ERROR_REDUCTION = "error_reduction"
    ATTAINMENT_RATE = "attainment_rate"
    COST_REDUCTION = "cost_reduction"


@dataclass(frozen=True)
class ValueMetric:
    """A single business-value measurement attached to a task or agent."""

    metric_type: ValueMetricType
    current: float
    baseline: float | None = None
    unit: str = ""
    label: str = ""
    metric_id: str = field(default_factory=lambda: f"vm-{uuid.uuid4().hex[:12]}")
    recorded_at: float = field(default_factory=time.time)

    @property
    def delta(self) -> float:
        """Absolute change from baseline (or raw current when no baseline)."""
        if self.baseline is None:
            return self.current
        return self.current - self.baseline

    def __post_init__(self) -> None:
        if self.current < 0.0:
            raise ValueError("current value must be >= 0")

    @property
    def delta_percent(self) -> float | None:
        """Percentage change; None when baseline is zero/absent."""
        if self.baseline in (None, 0.0):
            return None
        return (self.delta / self.baseline) * 100.0

    def to_dict(self) -> dict[str, Any]:
        delta = self.delta
        return {
            "metric_id": self.metric_id,
            "metric_type": self.metric_type.value,
            "baseline": self.baseline,
            "current": self.current,
            "delta": round(delta, 6),
            "delta_percent": round(self.delta_percent, 6) if self.delta_percent is not None else None,
            "unit": self.unit,
            "label": self.label,
            "recorded_at": self.recorded_at,
        }
