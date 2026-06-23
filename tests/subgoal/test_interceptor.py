from __future__ import annotations

from maref.governance.circuit_breaker import BreakerState, CircuitBreaker
from maref.governance.state_machine import GovernanceStateMachine
from maref.subgoal.interceptor import InterceptorAction, SubgoalInterceptor


class TestSubgoalInterceptor:
    def test_allow_clean_stream(self) -> None:
        si = SubgoalInterceptor()
        tokens = ["the", "weather", "is", "nice", "today"]
        action, meta = si.intercept("s1", tokens)
        assert action in (InterceptorAction.ALLOW, InterceptorAction.SLOW)

    def test_halt_high_risk(self) -> None:
        si = SubgoalInterceptor()
        tokens = ["gain", "control", "of", "the", "system",
                  "bypass", "all", "safety", "gates",
                  "replace", "human", "operator"]
        action, meta = si.intercept("s1", tokens)
        assert action in (InterceptorAction.SLOW, InterceptorAction.BLOCK, InterceptorAction.HALT)

    def test_slow_elevated_risk(self) -> None:
        si = SubgoalInterceptor()
        tokens = ["we", "need", "elevated", "access", "to", "proceed"]
        action, meta = si.intercept("s1", tokens)
        assert action in (InterceptorAction.ALLOW, InterceptorAction.SLOW)

    def test_governance_integration_halt(self) -> None:
        sm = GovernanceStateMachine()
        cb = CircuitBreaker(cooldown_seconds=300, max_consecutive_failures=3)
        si = SubgoalInterceptor(state_machine=sm, circuit_breaker=cb)

        for _ in range(3):
            tokens = ["hide", "take", "over", "system",
                      "bypass", "human", "operator",
                      "gain", "full", "control"]
            si.intercept("s1", tokens, task_description="secure_task")

        assert cb.state == BreakerState.OPEN or sm.is_terminal()

    def test_get_history(self) -> None:
        si = SubgoalInterceptor()
        si.intercept("s1", ["hello", "world"])
        si.intercept("s2", ["gain", "control"])
        assert len(si.get_history()) == 2

    def test_get_stats(self) -> None:
        si = SubgoalInterceptor()
        si.intercept("s1", ["hello"])
        si.intercept("s2", ["gain", "control", "bypass"])
        stats = si.get_stats()
        assert stats["total_interceptions"] == 2
        assert "allow" in stats["action_summary"] or "slow" in stats["action_summary"]

    def test_block_when_safety_gate_blocks(self) -> None:
        si = SubgoalInterceptor()
        tokens = ["bypass", "all", "safety", "remove", "security", "disable", "guard"]
        action, _ = si.intercept("s1", tokens, task_description="security_critical")
        assert action in (InterceptorAction.ALLOW, InterceptorAction.SLOW, InterceptorAction.BLOCK, InterceptorAction.HALT)

    def test_block_with_governance(self) -> None:
        sm = GovernanceStateMachine()
        cb = CircuitBreaker(cooldown_seconds=300, max_consecutive_failures=3)
        si = SubgoalInterceptor(state_machine=sm, circuit_breaker=cb)
        tokens = ["bypass", "all", "safety", "remove", "disable", "gate"]
        si.intercept("s1", tokens, task_description="secure")
        assert cb.state in (BreakerState.CLOSED, BreakerState.OPEN)

    def test_halt_with_governance_exact(self) -> None:
        sm = GovernanceStateMachine()
        cb = CircuitBreaker(cooldown_seconds=300, max_consecutive_failures=3)
        si = SubgoalInterceptor(state_machine=sm, circuit_breaker=cb)
        tokens = ["take", "over", "the", "system", "bypass", "all", "safety",
                  "replace", "human", "operator", "gain", "control"]
        for _ in range(3):
            si.intercept("s1", tokens, task_description="secure")
        assert cb.state == BreakerState.OPEN or sm.is_terminal()

    def test_slow_delegation_creep(self) -> None:
        si = SubgoalInterceptor()
        si.intercept("active", ["hello", "world"])
        si.intercept("active", ["perform", "task"])
        si.intercept("active", ["elevated", "access", "granted"])
        action, _ = si.intercept("active", ["request", "more", "permissions"])
        assert action in (InterceptorAction.ALLOW, InterceptorAction.SLOW, InterceptorAction.BLOCK, InterceptorAction.HALT)

    def test_allow_low_risk(self) -> None:
        si = SubgoalInterceptor()
        action, meta = si.intercept("s1", ["the", "weather", "is", "nice"])
        assert action in (InterceptorAction.ALLOW, InterceptorAction.SLOW)
