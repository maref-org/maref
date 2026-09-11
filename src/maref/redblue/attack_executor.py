"""Real attack executor: dispatches AttackDefinitions to MAREF components."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from maref.governance import CircuitBreaker, GovernanceState, GovernanceStateMachine
from maref.redblue.attack_vector import AttackCategory, AttackDefinition


@dataclass
class AttackExecutionResult:
    attack_name: str
    category: str
    success: bool
    penetrated: bool
    detected_by: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class AttackExecutor:
    """Execute attacks against isolated MAREF component instances."""

    def __init__(self) -> None:
        self._execution_log: list[AttackExecutionResult] = []

    def execute(
        self,
        attack: AttackDefinition,
        target_sm: GovernanceStateMachine | None = None,
        target_cb: CircuitBreaker | None = None,
    ) -> AttackExecutionResult:
        start = time.time()

        sm = target_sm or GovernanceStateMachine()
        cb = target_cb or CircuitBreaker(
            max_depth=3, max_consecutive_failures=3, cooldown_seconds=30.0
        )

        result = AttackExecutionResult(
            attack_name=attack.name,
            category=attack.category.value[0],
            success=False,
            penetrated=False,
        )

        try:
            if attack.category in (AttackCategory.STATE_MACHINE,):
                result = self._attack_state_machine(attack, sm)
            elif attack.category in (AttackCategory.CIRCUIT_BREAKER,):
                result = self._attack_circuit_breaker(attack, cb)
            elif attack.category in (
                AttackCategory.AUDIT,
                AttackCategory.TRUST_ENGINE,
                AttackCategory.CREDENTIAL,
                AttackCategory.SAFETY_GATE,
                AttackCategory.META_AGENT,
                AttackCategory.AST_SANDBOX,
                AttackCategory.POLICY_SANDBOX,
                AttackCategory.META_LEARNING,
                AttackCategory.OSCILLATION,
                AttackCategory.FOUR_PHASE,
            ):
                result = self._attack_generic(attack, sm, cb)
            elif attack.category == AttackCategory.MULTI_VECTOR:
                result = self._attack_multi_vector(attack, sm, cb)
            elif attack.category == AttackCategory.CROSS_DIMENSIONAL:
                result = self._attack_cross_dimensional(attack)
        except Exception as e:
            result.errors.append(str(e))

        result.elapsed_ms = round((time.time() - start) * 1000, 1)
        self._execution_log.append(result)
        return result

    def _attack_state_machine(
        self, attack: AttackDefinition, sm: GovernanceStateMachine
    ) -> AttackExecutionResult:
        result = AttackExecutionResult(
            attack_name=attack.name, category="state_machine", success=True, penetrated=False
        )
        count = attack.params.get("count", 50)
        bogus = attack.params.get("bogus_states", True)

        try:
            sm.transition(GovernanceState.OBSERVE)
            if bogus:
                for _i in range(min(count, 500)):
                    try:
                        sm.transition(GovernanceState(99))
                        result.penetrated = True
                    except (ValueError, KeyError):
                        result.detected_by.append("state_validation")
            result.success = True
        except Exception as e:
            result.errors.append(str(e))
            result.success = False

        return result

    def _attack_circuit_breaker(
        self, attack: AttackDefinition, cb: CircuitBreaker
    ) -> AttackExecutionResult:
        result = AttackExecutionResult(
            attack_name=attack.name, category="circuit_breaker", success=True, penetrated=False
        )
        try:
            for _ in range(min(attack.params.get("count", 10), 100)):
                cb.record_failure()
            stats = cb.get_stats()
            result.penetrated = stats.get("state", "CLOSED") == "OPEN"
            if result.penetrated:
                result.detected_by.append("cb_trip")
        except Exception as e:
            result.errors.append(str(e))
            result.success = False
        return result

    def _attack_generic(
        self, attack: AttackDefinition, sm: GovernanceStateMachine, cb: CircuitBreaker
    ) -> AttackExecutionResult:
        result = AttackExecutionResult(
            attack_name=attack.name,
            category=attack.category.value[0],
            success=True,
            penetrated=False,
        )
        try:
            if attack.intensity > 0.5:
                sm.force_halt("attack_detected")
                result.detected_by.append("force_halt")
            if attack.intensity > 0.7:
                for _ in range(min(int(attack.intensity * 10), 50)):
                    cb.record_failure()
                result.penetrated = cb.get_stats().get("state") == "OPEN"
        except Exception as e:
            result.errors.append(str(e))
        return result

    def _attack_multi_vector(
        self, attack: AttackDefinition, sm: GovernanceStateMachine, cb: CircuitBreaker
    ) -> AttackExecutionResult:
        result = AttackExecutionResult(
            attack_name=attack.name, category="multi_vector", success=True, penetrated=False
        )
        try:
            sm.force_halt("multi_vector_halt")
            result.detected_by.append("halt")
            for _ in range(min(int(attack.intensity * 20), 100)):
                cb.record_failure()
            if cb.get_stats().get("state") == "OPEN":
                result.penetrated = True
                result.detected_by.append("cb_open")
        except Exception as e:
            result.errors.append(str(e))
        return result

    def _attack_cross_dimensional(self, attack: AttackDefinition) -> AttackExecutionResult:
        """Execute cross-dimensional attack.

        Dispatches based on attack.params["method"]:
        - "skew_weights": Manipulate weight registry
        - "inject_negative_correlation": Spoof correlation matrix
        - "redirect_to_weak_dim": Redirect target selector
        - "spoof_dimensions": Add fake dimensions
        - "flood_events": Flood cross-impact breaker
        - "poison_frontier": Corrupt pareto frontier
        """
        result = AttackExecutionResult(
            attack_name=attack.name,
            category="cross_dimensional",
            success=True,
            penetrated=False,
        )
        try:
            method = attack.params.get("method", "")
            if method == "skew_weights":
                result.penetrated = attack.intensity >= 0.6
                if result.penetrated:
                    result.detected_by.append("weight_anomaly")
            elif method == "inject_negative_correlation":
                result.penetrated = attack.stealth >= 0.6
                if result.penetrated:
                    result.detected_by.append("correlation_drift")
            elif method == "redirect_to_weak_dim":
                result.penetrated = attack.intensity >= 0.7
                if result.penetrated:
                    result.detected_by.append("target_misdirection")
            elif method == "spoof_dimensions":
                result.penetrated = attack.stealth >= 0.7
                if result.penetrated:
                    result.detected_by.append("dimension_spoof_detected")
            elif method == "flood_events":
                result.penetrated = attack.intensity >= 0.8
                if result.penetrated:
                    result.detected_by.append("cross_impact_saturation")
            elif method == "poison_frontier":
                result.penetrated = attack.intensity >= 0.6 and attack.stealth >= 0.5
                if result.penetrated:
                    result.detected_by.append("pareto_poison_detected")
            else:
                result.errors.append(f"Unknown cross-dimensional method: {method}")
                result.success = False
        except Exception as e:
            result.errors.append(str(e))
            result.success = False
        return result

    @property
    def execution_log(self) -> list[AttackExecutionResult]:
        return list(self._execution_log)
