from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StressResult:
    round_id: str
    stress_level: str
    axes_applied: dict[str, float] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    latency_p50: float = 0.0
    latency_p99: float = 0.0
    latency_p99_9: float = 0.0

    cb_state: str = "CLOSED"
    meta_cb_state: str = "CLOSED"

    healer_success_rate: float = 0.0
    healer_strategy_rates: dict[str, float] = field(default_factory=dict)

    oscillation_detected: bool = False
    oscillation_resolved: bool = False
    revert_rate: float = 0.0
    ab_test_pass_rate: float = 0.0

    resilience_score: float = 0.0
    degradation_plans: list[str] = field(default_factory=list)

    duration_s: float = 0.0
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_id": self.round_id,
            "stress_level": self.stress_level,
            "axes_applied": self.axes_applied,
            "timestamp": self.timestamp,
            "latency_p50": self.latency_p50,
            "latency_p99": self.latency_p99,
            "latency_p99_9": self.latency_p99_9,
            "cb_state": self.cb_state,
            "meta_cb_state": self.meta_cb_state,
            "healer_success_rate": self.healer_success_rate,
            "healer_strategy_rates": self.healer_strategy_rates,
            "oscillation_detected": self.oscillation_detected,
            "oscillation_resolved": self.oscillation_resolved,
            "revert_rate": self.revert_rate,
            "ab_test_pass_rate": self.ab_test_pass_rate,
            "resilience_score": self.resilience_score,
            "degradation_plans": self.degradation_plans,
            "duration_s": self.duration_s,
            "errors": self.errors,
            "metadata": self.metadata,
        }
