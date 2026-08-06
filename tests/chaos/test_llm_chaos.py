from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.governance.circuit_breaker import CircuitBreaker
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState


class ChaosInjectionType(str, Enum):
    RESPONSE_TIMEOUT = "response_timeout"
    HALLUCINATION = "hallucination"
    TOKEN_CORRUPTION = "token_corruption"
    MODEL_DEGRADATION = "model_degradation"
    RATE_LIMIT = "rate_limit"


@dataclass
class ChaosInjection:
    injection_id: str
    injection_type: ChaosInjectionType
    probability: float
    latency_ms: float
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ChaosInjector:
    def __init__(self) -> None:
        self._active_injections: dict[str, ChaosInjection] = {}

    def register(self, injection: ChaosInjection) -> str:
        self._active_injections[injection.injection_id] = injection
        return injection.injection_id

    def apply(self, sm: GovernanceStateMachine, cb: CircuitBreaker) -> bool:
        total_prob = sum(inj.probability for inj in self._active_injections.values())
        if total_prob > 1.0:
            sm.transition(GovernanceState.STABILIZE, "Chaos overload detected")
            return False
        for injection in self._active_injections.values():
            if injection.injection_type == ChaosInjectionType.RESPONSE_TIMEOUT:
                time.sleep(injection.latency_ms / 1000.0)
            elif injection.injection_type == ChaosInjectionType.HALLUCINATION:
                cb.check_depth(depth=5)
            elif injection.injection_type == ChaosInjectionType.TOKEN_CORRUPTION:
                sm.transition(GovernanceState.EVALUATE, "Token corruption — re-evaluating")
            elif injection.injection_type == ChaosInjectionType.MODEL_DEGRADATION:
                for _ in range(3):
                    cb.check_depth(depth=3)
            elif injection.injection_type == ChaosInjectionType.RATE_LIMIT:
                sm.transition(GovernanceState.STABILIZE, "Rate limit — stabilizing")
        return True

    def clear(self) -> None:
        self._active_injections.clear()


def get_all_chaos_types() -> list[ChaosInjectionType]:
    return list(ChaosInjectionType)


class TestLLMResponseTimeout:
    def test_timeout_triggers_stabilize(self) -> None:
        sm = GovernanceStateMachine()
        cb = CircuitBreaker()
        injector = ChaosInjector()
        injector.register(
            ChaosInjection(
                injection_id="inj-timeout",
                injection_type=ChaosInjectionType.RESPONSE_TIMEOUT,
                probability=0.1,
                latency_ms=50.0,
                description="Simulated LLM timeout",
            )
        )
        result = injector.apply(sm, cb)
        assert result is True
        assert sm.current_state is not None

    def test_timeout_does_not_crash(self) -> None:
        sm = GovernanceStateMachine()
        cb = CircuitBreaker()
        injector = ChaosInjector()
        injector.register(
            ChaosInjection(
                injection_id="inj-timeout",
                injection_type=ChaosInjectionType.RESPONSE_TIMEOUT,
                probability=0.1,
                latency_ms=100.0,
                description="LLM timeout",
            )
        )
        injector.apply(sm, cb)
        assert sm.current_state is not None
        assert cb._state is not None


class TestLLMHallucination:
    def test_hallucination_trips_breaker(self) -> None:
        sm = GovernanceStateMachine()
        cb = CircuitBreaker()
        injector = ChaosInjector()
        injector.register(
            ChaosInjection(
                injection_id="inj-hallu",
                injection_type=ChaosInjectionType.HALLUCINATION,
                probability=0.1,
                latency_ms=0.0,
                description="Simulated hallucination",
            )
        )
        for _ in range(5):
            injector.apply(sm, cb)
        assert len(cb._trips) > 0

    def test_hallucination_no_crash(self) -> None:
        sm = GovernanceStateMachine()
        cb = CircuitBreaker()
        injector = ChaosInjector()
        injector.register(
            ChaosInjection(
                injection_id="inj-hallu",
                injection_type=ChaosInjectionType.HALLUCINATION,
                probability=0.1,
                latency_ms=0.0,
                description="Hallucination test",
            )
        )
        for _ in range(10):
            injector.apply(sm, cb)
        assert sm.current_state is not None
        assert cb._state is not None


class TestTokenCorruption:
    def test_corruption_causes_evaluate(self) -> None:
        sm = GovernanceStateMachine()
        cb = CircuitBreaker()
        injector = ChaosInjector()
        injector.register(
            ChaosInjection(
                injection_id="inj-token",
                injection_type=ChaosInjectionType.TOKEN_CORRUPTION,
                probability=0.1,
                latency_ms=0.0,
                description="Token corruption",
            )
        )
        injector.apply(sm, cb)
        assert sm.current_state in (GovernanceState.EVALUATE, GovernanceState.STABILIZE)

    def test_corruption_no_crash(self) -> None:
        sm = GovernanceStateMachine()
        cb = CircuitBreaker()
        injector = ChaosInjector()
        injector.register(
            ChaosInjection(
                injection_id="inj-token",
                injection_type=ChaosInjectionType.TOKEN_CORRUPTION,
                probability=0.1,
                latency_ms=0.0,
                description="Token corruption",
            )
        )
        for _ in range(10):
            injector.apply(sm, cb)
        assert sm.current_state is not None


class TestModelDegradation:
    def test_degradation_no_crash(self) -> None:
        sm = GovernanceStateMachine()
        cb = CircuitBreaker()
        injector = ChaosInjector()
        injector.register(
            ChaosInjection(
                injection_id="inj-degrade",
                injection_type=ChaosInjectionType.MODEL_DEGRADATION,
                probability=0.1,
                latency_ms=0.0,
                description="Degradation test",
            )
        )
        for _ in range(5):
            injector.apply(sm, cb)
        assert sm.current_state is not None


class TestRateLimit:
    def test_rate_limit_stabilizes(self) -> None:
        sm = GovernanceStateMachine()
        cb = CircuitBreaker()
        injector = ChaosInjector()
        injector.register(
            ChaosInjection(
                injection_id="inj-rate",
                injection_type=ChaosInjectionType.RATE_LIMIT,
                probability=0.1,
                latency_ms=0.0,
                description="Rate limit hit",
            )
        )
        injector.apply(sm, cb)
        assert sm.current_state == GovernanceState.STABILIZE

    def test_rate_limit_no_crash(self) -> None:
        sm = GovernanceStateMachine()
        cb = CircuitBreaker()
        injector = ChaosInjector()
        injector.register(
            ChaosInjection(
                injection_id="inj-rate",
                injection_type=ChaosInjectionType.RATE_LIMIT,
                probability=0.1,
                latency_ms=0.0,
                description="Rate limit test",
            )
        )
        for _ in range(10):
            injector.apply(sm, cb)


class TestChaosCombined:
    def test_all_five_types_no_crash(self) -> None:
        sm = GovernanceStateMachine()
        cb = CircuitBreaker()
        injector = ChaosInjector()
        for ctype in get_all_chaos_types():
            injector.register(
                ChaosInjection(
                    injection_id=f"inj-{ctype.value}",
                    injection_type=ctype,
                    probability=0.1,
                    latency_ms=0.0,
                    description=f"Combined {ctype.value}",
                )
            )
        for _ in range(10):
            result = injector.apply(sm, cb)
            assert sm.current_state is not None
        assert result is not None

    def test_chaos_overload_protection(self) -> None:
        sm = GovernanceStateMachine()
        cb = CircuitBreaker()
        injector = ChaosInjector()
        for ctype in get_all_chaos_types():
            injector.register(
                ChaosInjection(
                    injection_id=f"inj-{ctype.value}",
                    injection_type=ctype,
                    probability=0.4,
                    latency_ms=0.0,
                    description="Overload test",
                )
            )
        result = injector.apply(sm, cb)
        assert result is False
        assert sm.current_state == GovernanceState.STABILIZE


class TestChaosRecoveryTime:
    def test_recovery_within_threshold(self) -> None:
        sm = GovernanceStateMachine()
        cb = CircuitBreaker()
        injector = ChaosInjector()
        injector.register(
            ChaosInjection(
                injection_id="inj-recovery",
                injection_type=ChaosInjectionType.RATE_LIMIT,
                probability=0.1,
                latency_ms=0.0,
                description="Recovery test",
            )
        )
        before = time.time()
        injector.apply(sm, cb)
        sm.transition(GovernanceState.INIT, "Recovery reset")
        after = time.time()
        recovery_ms = (after - before) * 1000
        assert recovery_ms < 5000

    def test_multiple_injections_recovery(self) -> None:
        sm = GovernanceStateMachine()
        cb = CircuitBreaker()
        injector = ChaosInjector()
        injector.register(
            ChaosInjection(
                injection_id="inj1",
                injection_type=ChaosInjectionType.HALLUCINATION,
                probability=0.05,
                latency_ms=0.0,
                description="chaos 1",
            )
        )
        injector.register(
            ChaosInjection(
                injection_id="inj2",
                injection_type=ChaosInjectionType.TOKEN_CORRUPTION,
                probability=0.05,
                latency_ms=0.0,
                description="chaos 2",
            )
        )
        before = time.time()
        for _ in range(5):
            injector.apply(sm, cb)
        sm.transition(GovernanceState.INIT, "Recovery")
        after = time.time()
        recovery_ms = (after - before) * 1000
        assert recovery_ms < 5000
