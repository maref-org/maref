"""Shared stub modules for maref.stress.sqi / sqi_convergence.

src/maref/stress/sqi.py and sqi_convergence.py do not exist; code_service_sqi
imports from them. Both tests/stress and tests/maref/stress conftest must
install the SAME stubs, otherwise whichever module is imported first binds to a
different class set and the module cache freezes the mismatch (see
sonarcloud: AttributeError: _mock_methods).
"""

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


@dataclass
class ConvergenceState:
    is_converged: bool = False
    current_score: float = 0.0
    target_score: float = 0.0
    trend: str = "stable"
    saturation_window: int = 0


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


class SQIConvergenceTracker:
    def __init__(self, target: float = 75.0, window: int = 3) -> None:
        self.target = target
        self.window = window
        self._rounds: dict[str, Any] = {}

    def record_round(self, round_id: str, sqi_report: Any) -> None:
        self._rounds[round_id] = sqi_report

    def check_convergence(self) -> ConvergenceState:
        return ConvergenceState(
            is_converged=True,
            current_score=80.0,
            target_score=self.target,
            trend="improving",
            saturation_window=self.window,
        )

    def summary(self) -> dict[str, float]:
        return {
            "initial": 60.0,
            "current": 80.0,
            "best": 85.0,
            "total_improvement": 20.0,
        }


def install_stubs() -> None:
    """Install dataclass stubs into sys.modules (idempotent)."""
    _sqi_stub = type(sys)("maref.stress.sqi")
    _sqi_stub.SQIDimension = SQIDimension
    _sqi_stub.SQIReport = SQIReport
    _sqi_stub.ServiceQualityIndex = ServiceQualityIndex
    sys.modules["maref.stress.sqi"] = _sqi_stub

    _sqi_conv_stub = type(sys)("maref.stress.sqi_convergence")
    _sqi_conv_stub.SQIConvergenceTracker = SQIConvergenceTracker
    _sqi_conv_stub.ConvergenceState = ConvergenceState
    sys.modules["maref.stress.sqi_convergence"] = _sqi_conv_stub
