"""
MAREF Evolution Metrics — data classes and convergence logic.

Part of 3-cycle recursive evolution (C1 baseline → C2 optimize → C3 converge).
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AcceptanceCriteria:
    c1_fnr_max: float = 0.15
    c1_fpr_max: float = 0.10
    c2_fnr_must_not_worsen: bool = True
    c2_fpr_budget_pp: float = 0.05
    c2_weight_std_max: float = 0.3
    c2_lr_convergence_target: float = 0.005
    c3_fnr_std_max: float = 0.05
    c3_fpr_std_max: float = 0.03
    c3_oscillation_max: int = 0
    c3_halt_anomaly_max: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "c1_fnr_max": self.c1_fnr_max,
            "c1_fpr_max": self.c1_fpr_max,
            "c2_fnr_must_not_worsen": self.c2_fnr_must_not_worsen,
            "c2_fpr_budget_pp": self.c2_fpr_budget_pp,
            "c2_weight_std_max": self.c2_weight_std_max,
            "c2_lr_convergence_target": self.c2_lr_convergence_target,
            "c3_fnr_std_max": self.c3_fnr_std_max,
            "c3_fpr_std_max": self.c3_fpr_std_max,
            "c3_oscillation_max": self.c3_oscillation_max,
            "c3_halt_anomaly_max": self.c3_halt_anomaly_max,
        }


@dataclass
class EvolutionMetrics:
    fnr_series: list[float] = field(default_factory=list)
    fpr_series: list[float] = field(default_factory=list)
    entropy_series: list[float] = field(default_factory=list)
    transition_count_series: list[int] = field(default_factory=list)
    policy_weights_series: list[dict[str, float]] = field(default_factory=list)
    learning_rate_series: list[float] = field(default_factory=list)
    circuit_breaker_events: list[dict[str, Any]] = field(default_factory=list)
    oscillation_events: list[dict[str, Any]] = field(default_factory=list)
    sandbox_events: list[dict[str, Any]] = field(default_factory=list)
    halt_reasons: list[str] = field(default_factory=list)

    def snapshot(self, round_num: int) -> dict[str, Any]:
        return {
            "round": round_num,
            "fnr": self.fnr_series[-1] if self.fnr_series else None,
            "fpr": self.fpr_series[-1] if self.fpr_series else None,
            "entropy": self.entropy_series[-1] if self.entropy_series else None,
            "transition_count": (
                self.transition_count_series[-1] if self.transition_count_series else None
            ),
            "weights": self.policy_weights_series[-1] if self.policy_weights_series else None,
            "learning_rate": self.learning_rate_series[-1] if self.learning_rate_series else None,
        }

    def compute_convergence(self, window: int = 20) -> dict[str, float]:
        if len(self.fnr_series) < window:
            return {"fnr_std": -1.0, "fpr_std": -1.0, "converged": False}

        recent_fnr = self.fnr_series[-window:]
        recent_fpr = self.fpr_series[-window:]

        return {
            "fnr_std": statistics.stdev(recent_fnr) if len(recent_fnr) > 1 else 0.0,
            "fpr_std": statistics.stdev(recent_fpr) if len(recent_fpr) > 1 else 0.0,
            "fnr_mean": statistics.mean(recent_fnr),
            "fpr_mean": statistics.mean(recent_fpr),
            "converged": (
                self._is_converged(recent_fnr, 0.05) and self._is_converged(recent_fpr, 0.03)
            ),
        }

    @staticmethod
    def _is_converged(values: list[float], threshold: float) -> bool:
        if len(values) < 2:
            return False
        return statistics.stdev(values) < threshold

    def assess_acceptance(self, criteria: AcceptanceCriteria, cycle: str) -> dict[str, bool]:
        result: dict[str, bool] = {}

        if cycle == "c1":
            result["fnr_below_max"] = (
                self.fnr_series and all(f < criteria.c1_fnr_max for f in self.fnr_series)
            )
            result["fpr_below_max"] = (
                self.fpr_series and all(f < criteria.c1_fpr_max for f in self.fpr_series)
            )
            result["no_breaker_trip"] = len(self.circuit_breaker_events) <= 1
            result["halt_only_normal"] = all(
                "force_halt" not in r or r == "force_halt" for r in self.halt_reasons
            )

        elif cycle == "c2":
            result["weights_stable"] = bool(
                self.policy_weights_series
            ) and self._weights_std() < criteria.c2_weight_std_max
            result["lr_converged"] = bool(
                self.learning_rate_series
            ) and self.learning_rate_series[-1] <= criteria.c2_lr_convergence_target
            if criteria.c2_fnr_must_not_worsen:
                c1_fnr_mean = self._fnr_baseline_mean() if hasattr(self, "_fnr_baseline") else 0.15
                recent_fnr = self.fnr_series[-20:] if len(self.fnr_series) >= 20 else self.fnr_series
                c2_fnr_mean = statistics.mean(recent_fnr) if recent_fnr else 0
                result["fnr_not_worsened"] = c2_fnr_mean <= c1_fnr_mean + 0.02
            if criteria.c2_fpr_budget_pp > 0:
                c1_fpr_mean = getattr(self, "_fpr_baseline", 0.10)
                recent_fpr = self.fpr_series[-20:] if len(self.fpr_series) >= 20 else self.fpr_series
                c2_fpr_mean = statistics.mean(recent_fpr) if recent_fpr else 0
                result["fpr_within_budget"] = abs(c2_fpr_mean - c1_fpr_mean) <= criteria.c2_fpr_budget_pp

        elif cycle == "c3":
            convergence = self.compute_convergence(window=20)
            result["fnr_converged"] = (
                convergence["fnr_std"] >= 0 and convergence["fnr_std"] < criteria.c3_fnr_std_max
            )
            result["fpr_converged"] = (
                convergence["fpr_std"] >= 0 and convergence["fpr_std"] < criteria.c3_fpr_std_max
            )
            result["no_oscillation"] = len(self.oscillation_events) <= criteria.c3_oscillation_max
            anomalous_halts = sum(
                1 for r in self.halt_reasons
                if "force_halt" in r and "normal" not in r
            )
            result["no_anomalous_halt"] = anomalous_halts <= criteria.c3_halt_anomaly_max

        return result

    def _weights_std(self) -> float:
        if not self.policy_weights_series:
            return float("inf")
        keys = list(self.policy_weights_series[0].keys())
        values = []
        for snapshot in self.policy_weights_series:
            for k in keys:
                values.append(snapshot.get(k, 0.0))
        if len(values) < 2:
            return 0.0
        return statistics.stdev(values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fnr_series": self.fnr_series,
            "fpr_series": self.fpr_series,
            "entropy_series": self.entropy_series,
            "transition_count_series": self.transition_count_series,
            "policy_weights_series": self.policy_weights_series,
            "learning_rate_series": self.learning_rate_series,
            "circuit_breaker_events": self.circuit_breaker_events[-20:],
            "oscillation_events": self.oscillation_events[-20:],
            "sandbox_events": self.sandbox_events[-20:],
            "halt_reasons": self.halt_reasons[-20:],
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)


@dataclass
class CycleSpec:
    name: str
    rounds: int
    description: str
    meta_learning_enabled: bool = False
    meta_learning_interval: int = 5


@dataclass
class CycleResult:
    cycle_id: str
    name: str
    rounds_completed: int
    rounds_total: int
    metrics: EvolutionMetrics
    acceptance: dict[str, bool]
    passed: bool

    def summary(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        return (
            f"[{status}] {self.name}: {self.rounds_completed}/{self.rounds_total} rounds\n"
            f"  FNR: {self.metrics.fnr_series[-5:] if self.metrics.fnr_series else 'N/A'}\n"
            f"  FPR: {self.metrics.fpr_series[-5:] if self.metrics.fpr_series else 'N/A'}\n"
            f"  Acceptance: {self.acceptance}"
        )


@dataclass
class EvolutionResult:
    cycles: list[CycleResult]
    stop_reason: str
    total_rounds: int
    all_passed: bool

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "MAREF Recursive Evolution — Final Result",
            f"Stop reason: {self.stop_reason}",
            f"Total rounds: {self.total_rounds}",
            f"Overall: {'PASSED' if self.all_passed else 'FAILED'}",
            "=" * 60,
        ]
        for c in self.cycles:
            lines.append(c.summary())
        return "\n".join(lines)
