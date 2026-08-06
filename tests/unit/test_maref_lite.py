"""Unit tests for MAREF-Lite core components."""

import pytest

from maref_lite.governance import GovernanceOverlay
from maref_lite.policy import (
    PolicyAction,
    PolicyEngine,
    PolicyRule,
    PolicyTrigger,
    create_default_policies,
)
from maref_lite.state_machine import (
    ENTROPY_LEVELS,
    GovernanceState,
    GovernanceStateMachine,
)


class TestGovernanceState:
    """Tests for governance state enum."""

    def test_ten_states(self) -> None:
        assert len(GovernanceState) == 10

    def test_entropy_levels(self) -> None:
        assert ENTROPY_LEVELS[GovernanceState.INIT] == 0
        assert ENTROPY_LEVELS[GovernanceState.ACT] == 4
        assert ENTROPY_LEVELS[GovernanceState.HALT] == 0


class TestGovernanceStateMachine:
    """Tests for governance state machine."""

    @pytest.fixture
    def sm(self) -> GovernanceStateMachine:
        return GovernanceStateMachine()

    def test_initial_state(self, sm: GovernanceStateMachine) -> None:
        assert sm.current_state == GovernanceState.INIT
        assert sm.current_entropy == 0

    def test_valid_transition(self, sm: GovernanceStateMachine) -> None:
        result = sm.transition(GovernanceState.OBSERVE)
        assert result is True
        assert sm.current_state == GovernanceState.OBSERVE

    def test_invalid_transition(self, sm: GovernanceStateMachine) -> None:
        # Cannot jump from INIT to ACT
        result = sm.transition(GovernanceState.ACT)
        assert result is False
        assert sm.current_state == GovernanceState.INIT

    def test_halt_is_absorbing(self, sm: GovernanceStateMachine) -> None:
        # Navigate to HALT
        sm.transition(GovernanceState.OBSERVE)
        sm.transition(GovernanceState.ANALYZE)
        sm.transition(GovernanceState.EVALUATE)
        sm.transition(GovernanceState.DECIDE)
        sm.transition(GovernanceState.ACT)
        sm.transition(GovernanceState.VERIFY)
        sm.transition(GovernanceState.STABILIZE)
        sm.transition(GovernanceState.REPORT)
        sm.transition(GovernanceState.HALT)
        assert sm.is_terminal()
        # Cannot leave HALT
        result = sm.transition(GovernanceState.REPORT)
        assert result is False

    def test_force_stabilize(self, sm: GovernanceStateMachine) -> None:
        sm.transition(GovernanceState.OBSERVE)
        result = sm.force_stabilize()
        assert result is True
        assert sm.current_state == GovernanceState.STABILIZE

    def test_force_halt(self, sm: GovernanceStateMachine) -> None:
        sm.transition(GovernanceState.OBSERVE)
        result = sm.force_halt()
        assert result is True
        assert sm.is_terminal()

    def test_transition_callback(self, sm: GovernanceStateMachine) -> None:
        transitions = []

        def callback(t):
            transitions.append(t)

        sm.add_callback(callback)
        sm.transition(GovernanceState.OBSERVE)
        assert len(transitions) == 1
        assert transitions[0].from_state == GovernanceState.INIT
        assert transitions[0].to_state == GovernanceState.OBSERVE

    def test_history(self, sm: GovernanceStateMachine) -> None:
        sm.transition(GovernanceState.OBSERVE)
        sm.transition(GovernanceState.ANALYZE)
        history = sm.get_history()
        assert len(history) == 2

    def test_entropy_trend(self, sm: GovernanceStateMachine) -> None:
        sm.transition(GovernanceState.OBSERVE)
        sm.transition(GovernanceState.ANALYZE)
        trend = sm.get_entropy_trend()
        assert trend["current"] == 2
        assert trend["max"] == 2

    def test_valid_next_states(self, sm: GovernanceStateMachine) -> None:
        next_states = sm.get_valid_next_states()
        assert GovernanceState.OBSERVE in next_states
        assert GovernanceState.HALT not in next_states


class TestPolicyEngine:
    """Tests for policy engine."""

    @pytest.fixture
    def engine(self) -> PolicyEngine:
        return PolicyEngine()

    def test_add_rule(self, engine: PolicyEngine) -> None:
        rule = PolicyRule(
            name="test",
            trigger=PolicyTrigger.ENTROPY_THRESHOLD,
            condition=lambda ctx: True,
            action=PolicyAction.ALERT,
        )
        engine.add_rule(rule)
        assert len(engine.get_rules()) == 1

    def test_evaluate_matching(self, engine: PolicyEngine) -> None:
        engine.add_rule(
            PolicyRule(
                name="high_entropy",
                trigger=PolicyTrigger.ENTROPY_THRESHOLD,
                condition=lambda ctx: ctx.get("entropy", 0) >= 3,
                action=PolicyAction.FORCE_STABILIZE,
            )
        )
        triggered = engine.evaluate({"entropy": 4})
        assert len(triggered) == 1
        assert triggered[0].name == "high_entropy"

    def test_evaluate_not_matching(self, engine: PolicyEngine) -> None:
        engine.add_rule(
            PolicyRule(
                name="high_entropy",
                trigger=PolicyTrigger.ENTROPY_THRESHOLD,
                condition=lambda ctx: ctx.get("entropy", 0) >= 3,
                action=PolicyAction.FORCE_STABILIZE,
            )
        )
        triggered = engine.evaluate({"entropy": 1})
        assert len(triggered) == 0

    def test_priority_sorting(self, engine: PolicyEngine) -> None:
        engine.add_rule(
            PolicyRule(
                name="low",
                trigger=PolicyTrigger.ENTROPY_THRESHOLD,
                condition=lambda ctx: True,
                action=PolicyAction.ALERT,
                priority=10,
            )
        )
        engine.add_rule(
            PolicyRule(
                name="high",
                trigger=PolicyTrigger.ENTROPY_THRESHOLD,
                condition=lambda ctx: True,
                action=PolicyAction.FORCE_HALT,
                priority=100,
            )
        )
        rules = engine.get_rules()
        assert rules[0].name == "high"
        assert rules[1].name == "low"

    def test_disabled_rule(self, engine: PolicyEngine) -> None:
        engine.add_rule(
            PolicyRule(
                name="disabled",
                trigger=PolicyTrigger.ENTROPY_THRESHOLD,
                condition=lambda ctx: True,
                action=PolicyAction.ALERT,
                enabled=False,
            )
        )
        triggered = engine.evaluate({})
        assert len(triggered) == 0


class TestDefaultPolicies:
    """Tests for default policy set."""

    @pytest.fixture
    def policies(self) -> PolicyEngine:
        return create_default_policies()

    def test_critical_entropy(self, policies: PolicyEngine) -> None:
        triggered = policies.evaluate({"entropy": 4})
        assert any(r.name == "critical_entropy" for r in triggered)

    def test_high_entropy(self, policies: PolicyEngine) -> None:
        triggered = policies.evaluate({"entropy": 3})
        assert any(r.name == "high_entropy" for r in triggered)

    def test_critical_anomaly(self, policies: PolicyEngine) -> None:
        triggered = policies.evaluate({"anomaly_severity": "critical"})
        assert any(r.name == "critical_anomaly" for r in triggered)

    def test_drift_detected(self, policies: PolicyEngine) -> None:
        triggered = policies.evaluate({"drift_severity": "high"})
        assert any(r.name == "drift_verify" for r in triggered)

    def test_no_trigger(self, policies: PolicyEngine) -> None:
        triggered = policies.evaluate({"entropy": 1})
        assert len(triggered) == 0


class TestGovernanceOverlay:
    """Tests for governance overlay."""

    @pytest.fixture
    def overlay(self) -> GovernanceOverlay:
        return GovernanceOverlay()

    def test_initial_status(self, overlay: GovernanceOverlay) -> None:
        status = overlay.get_status()
        assert status["state"] == "INIT"
        assert status["entropy"] == 0
        assert status["is_terminal"] is False

    def test_get_decisions_empty(self, overlay: GovernanceOverlay) -> None:
        assert len(overlay.get_decisions()) == 0

    def test_status_after_init(self, overlay: GovernanceOverlay) -> None:
        status = overlay.get_status()
        assert "anomaly_count" in status
        assert "critical_count" in status
        assert "decision_count" in status
