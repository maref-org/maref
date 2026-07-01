"""pytest conftest: ensure missing maref.stress.sqi module is stubbed before imports."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SQIDimension:
    name: str = ""
    score: float = 0.0
    weight: float = 0.0
    raw_value: float = 0.0
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SQIReport:
    dimensions: list[SQIDimension] = field(default_factory=list)
    overall_score: float = 0.0
    variance: float = 0.0
    round_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ServiceQualityIndex:
    def _compute_delivery_quality(self, stress_result=None):
        return SQIDimension(name="delivery_quality", score=50.0, weight=0.10)

    def _compute_consistency(self, emergence_report=None):
        return SQIDimension(name="consistency", score=50.0, weight=0.10)

    def _compute_cost_efficiency(self, budget_usage_pct=0.0, cost_trend_direction="stable"):
        return SQIDimension(name="cost_efficiency", score=50.0, weight=0.10)

    def _compute_convergence_speed(self, stress_result=None):
        return SQIDimension(name="convergence_speed", score=50.0, weight=0.10)

    def _compute_stability(self, stress_result=None):
        return SQIDimension(name="stability", score=50.0, weight=0.10)


_sqi_stub = type(sys)("maref.stress.sqi")
_sqi_stub.SQIDimension = SQIDimension
_sqi_stub.SQIReport = SQIReport
_sqi_stub.ServiceQualityIndex = ServiceQualityIndex
sys.modules["maref.stress.sqi"] = _sqi_stub
