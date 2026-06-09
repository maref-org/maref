from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any


class DegradationScenario(Enum):
    GOVERNANCE = "governance_degraded"
    OBSERVATION = "observation_degraded"
    FEDERATION = "federation_degraded"


DEGRADATION_STRATEGIES: dict[str, dict[str, Any]] = {
    "governance_degraded": {
        "trigger": "meta_cb.open or resilience < 40",
        "actions": [
            "halt_recursive_layer",
            "fallback_to_flat_gov",
            "increase_cb_cooldown",
        ],
        "auto_recover": True,
    },
    "observation_degraded": {
        "trigger": "survival_rate < 0.5",
        "actions": [
            "reduce_probe_frequency",
            "prioritize_critical_probes",
            "batch_observations",
        ],
    },
    "federation_degraded": {
        "trigger": "cross_framework_sync_failure > 3",
        "actions": [
            "isolate_failing_framework",
            "operate_in_solo_mode",
            "periodic_rejoin_attempt",
        ],
    },
}


@dataclass
class ResilienceScore:
    total_score: float
    factors: dict[str, float]
    thresholds: dict[str, float]
    passed: bool


@dataclass
class DegradationPlan:
    scenario: str
    trigger_met: bool
    strategy: str
    actions: list[str]
    auto_recover: bool = False


class ResilienceEvaluatorV2:
    _FACTORS = {
        "survival_rate": 0.20,
        "recovery_time_ms": 0.20,
        "false_positive_rate": 0.15,
        "meta_protection_rate": 0.15,
        "graceful_degradation_rate": 0.12,
        "data_consistency_rate": 0.10,
        "throughput_under_stress": 0.08,
    }

    _THRESHOLDS = {
        "survival_rate": 0.7,
        "recovery_time_ms": 500.0,
        "false_positive_rate": 0.3,
        "meta_protection_rate": 0.6,
        "graceful_degradation_rate": 0.5,
        "data_consistency_rate": 0.8,
        "throughput_under_stress": 0.5,
    }

    def __init__(self) -> None:
        self._history: list[ResilienceScore] = []
        self._circuit_breaker: Any = None
        self._collector: Any = None
        self._federation_coordinator: Any = None

    def attach_circuit_breaker(self, cb: Any) -> None:
        self._circuit_breaker = cb

    def attach_collector(self, collector: Any) -> None:
        self._collector = collector

    def attach_federation_coordinator(self, coordinator: Any) -> None:
        self._federation_coordinator = coordinator

    _INVERSE_METRICS = {"recovery_time_ms", "false_positive_rate"}

    def evaluate(self, factor_values: dict[str, float]) -> ResilienceScore:
        normalized: dict[str, float] = {}
        total = 0.0

        for factor, weight in self._FACTORS.items():
            value = factor_values.get(factor, 0.0)
            if not math.isfinite(value):
                value = 0.0
            threshold = self._THRESHOLDS.get(factor, 1.0)
            if factor in self._INVERSE_METRICS:
                norm = min(threshold / max(value, 1e-6), 1.0)
            else:
                norm = min(max(value, 0.0) / threshold, 1.0) if threshold > 0 else 1.0
            normalized[factor] = norm
            total += norm * weight * 100.0

        score = ResilienceScore(
            total_score=round(total, 2),
            factors=normalized,
            thresholds=self._THRESHOLDS,
            passed=total >= 65.0,
        )
        self._history.append(score)
        return score

    def auto_recommend_degradation(self, score: ResilienceScore) -> list[DegradationPlan]:
        plans: list[DegradationPlan] = []

        if score.total_score < 40 or score.factors.get("meta_protection_rate", 1.0) < 0.4:
            plans.append(DegradationPlan(
                scenario="governance_degraded",
                trigger_met=True,
                strategy="governance_degraded",
                actions=DEGRADATION_STRATEGIES["governance_degraded"]["actions"],
                auto_recover=True,
            ))

        if score.factors.get("survival_rate", 1.0) < 0.5:
            plans.append(DegradationPlan(
                scenario="observation_degraded",
                trigger_met=True,
                strategy="observation_degraded",
                actions=DEGRADATION_STRATEGIES["observation_degraded"]["actions"],
            ))

        if score.factors.get("throughput_under_stress", 1.0) < 0.3:
            plans.append(DegradationPlan(
                scenario="federation_degraded",
                trigger_met=True,
                strategy="federation_degraded",
                actions=DEGRADATION_STRATEGIES["federation_degraded"]["actions"],
            ))

        return plans

    def execute_degradation_plan(
        self,
        plan: DegradationPlan,
        circuit_breaker_opener: Any = None,
        collector_stopper: Any = None,
        federation_isolator: Any = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "plan": plan.strategy,
            "executed": False,
            "actions_performed": [],
            "errors": [],
        }

        if not plan.trigger_met:
            result["detail"] = "trigger not met, skipped"
            return result

        try:
            if "governance_degraded" in plan.strategy:
                if circuit_breaker_opener and hasattr(circuit_breaker_opener, "force_open"):
                    circuit_breaker_opener.force_open()
                    result["actions_performed"].append("circuit_breaker_forced_open")

            if "observation_degraded" in plan.strategy:
                if collector_stopper and hasattr(collector_stopper, "stop"):
                    collector_stopper.stop()
                    result["actions_performed"].append("collector_stopped")

            if "federation_degraded" in plan.strategy:
                if federation_isolator and hasattr(federation_isolator, "isolate"):
                    federation_isolator.isolate()
                    result["actions_performed"].append("federation_isolated")

            result["executed"] = True
        except Exception as e:
            result["errors"].append(str(e))

        return result

    def evaluate_and_respond(self, factor_values: dict[str, float]) -> dict[str, Any]:
        score = self.evaluate(factor_values)
        plans = self.auto_recommend_degradation(score)
        results: list[dict[str, Any]] = []
        for plan in plans:
            r = self.execute_degradation_plan(
                plan,
                circuit_breaker_opener=self._circuit_breaker,
                collector_stopper=self._collector,
                federation_isolator=self._federation_coordinator,
            )
            results.append(r)
        return {
            "resilience_score": score.total_score,
            "passed": score.passed,
            "degradation_plans_triggered": len(plans),
            "execution_results": results,
        }

    def historical_resilience_trend(self) -> list[float]:
        return [s.total_score for s in self._history]

    @property
    def factors(self) -> dict[str, float]:
        return dict(self._FACTORS)

    @property
    def history(self) -> list[ResilienceScore]:
        return list(self._history)
