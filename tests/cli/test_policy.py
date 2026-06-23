from __future__ import annotations

from maref_lite.policy import (
    PolicyAction,
    PolicyEngine,
    PolicyRule,
    PolicyTrigger,
    create_default_policies,
)
from maref_lite.state_machine import GovernanceState


class TestPolicyTrigger:
    def test_values(self) -> None:
        assert PolicyTrigger.ENTROPY_THRESHOLD.name == "ENTROPY_THRESHOLD"
        assert PolicyTrigger.ANOMALY_DETECTED.name == "ANOMALY_DETECTED"
        assert PolicyTrigger.DRIFT_DETECTED.name == "DRIFT_DETECTED"
        assert PolicyTrigger.STATE_TIMEOUT.name == "STATE_TIMEOUT"
        assert PolicyTrigger.MANUAL_OVERRIDE.name == "MANUAL_OVERRIDE"


class TestPolicyAction:
    def test_values(self) -> None:
        assert PolicyAction.TRANSITION.name == "TRANSITION"
        assert PolicyAction.FORCE_STABILIZE.name == "FORCE_STABILIZE"
        assert PolicyAction.FORCE_HALT.name == "FORCE_HALT"
        assert PolicyAction.ALERT.name == "ALERT"
        assert PolicyAction.NOOP.name == "NOOP"


class TestPolicyRule:
    def test_evaluate_condition_true(self) -> None:
        rule = PolicyRule(
            name="test",
            trigger=PolicyTrigger.ENTROPY_THRESHOLD,
            condition=lambda ctx: ctx.get("entropy", 0) > 3,
            action=PolicyAction.FORCE_STABILIZE,
        )
        result = rule.evaluate({"entropy": 4})
        assert result == PolicyAction.FORCE_STABILIZE

    def test_evaluate_condition_false(self) -> None:
        rule = PolicyRule(
            name="test",
            trigger=PolicyTrigger.ENTROPY_THRESHOLD,
            condition=lambda ctx: ctx.get("entropy", 0) > 3,
            action=PolicyAction.FORCE_STABILIZE,
        )
        result = rule.evaluate({"entropy": 2})
        assert result is None

    def test_evaluate_disabled(self) -> None:
        rule = PolicyRule(
            name="test",
            trigger=PolicyTrigger.ENTROPY_THRESHOLD,
            condition=lambda ctx: True,
            action=PolicyAction.ALERT,
            enabled=False,
        )
        assert rule.evaluate({"entropy": 5}) is None

    def test_evaluate_enabled(self) -> None:
        rule = PolicyRule(
            name="test",
            trigger=PolicyTrigger.ENTROPY_THRESHOLD,
            condition=lambda ctx: True,
            action=PolicyAction.ALERT,
            enabled=True,
        )
        assert rule.evaluate({"entropy": 0}) == PolicyAction.ALERT

    def test_priority_default(self) -> None:
        rule = PolicyRule(
            name="test",
            trigger=PolicyTrigger.MANUAL_OVERRIDE,
            condition=lambda ctx: True,
            action=PolicyAction.NOOP,
        )
        assert rule.priority == 0

    def test_full_constructor(self) -> None:
        rule = PolicyRule(
            name="full",
            trigger=PolicyTrigger.DRIFT_DETECTED,
            condition=lambda ctx: True,
            action=PolicyAction.TRANSITION,
            target_state=GovernanceState.VERIFY,
            priority=100,
            enabled=True,
        )
        assert rule.name == "full"
        assert rule.target_state == GovernanceState.VERIFY
        assert rule.priority == 100
        assert rule.enabled is True


class TestPolicyEngine:
    def test_empty_evaluate(self) -> None:
        engine = PolicyEngine()
        result = engine.evaluate({"entropy": 5})
        assert result == []

    def test_add_and_evaluate(self) -> None:
        engine = PolicyEngine()
        engine.add_rule(
            PolicyRule(
                name="high_entropy",
                trigger=PolicyTrigger.ENTROPY_THRESHOLD,
                condition=lambda ctx: ctx.get("entropy", 0) >= 3,
                action=PolicyAction.TRANSITION,
                priority=10,
            )
        )
        result = engine.evaluate({"entropy": 4})
        assert len(result) == 1
        assert result[0].name == "high_entropy"

    def test_multiple_rules_priority_order(self) -> None:
        engine = PolicyEngine()
        engine.add_rule(
            PolicyRule(
                name="low",
                trigger=PolicyTrigger.MANUAL_OVERRIDE,
                condition=lambda ctx: True,
                action=PolicyAction.NOOP,
                priority=1,
            )
        )
        engine.add_rule(
            PolicyRule(
                name="high",
                trigger=PolicyTrigger.MANUAL_OVERRIDE,
                condition=lambda ctx: True,
                action=PolicyAction.ALERT,
                priority=100,
            )
        )
        result = engine.evaluate({})
        assert len(result) == 2
        assert result[0].name == "high"
        assert result[1].name == "low"

    def test_no_triggered_rules(self) -> None:
        engine = PolicyEngine()
        engine.add_rule(
            PolicyRule(
                name="never",
                trigger=PolicyTrigger.ENTROPY_THRESHOLD,
                condition=lambda ctx: False,
                action=PolicyAction.NOOP,
            )
        )
        result = engine.evaluate({"entropy": 10})
        assert result == []

    def test_get_rules_empty(self) -> None:
        engine = PolicyEngine()
        assert engine.get_rules() == []

    def test_get_rules_after_add(self) -> None:
        engine = PolicyEngine()
        rule = PolicyRule(
            name="test",
            trigger=PolicyTrigger.MANUAL_OVERRIDE,
            condition=lambda ctx: True,
            action=PolicyAction.ALERT,
        )
        engine.add_rule(rule)
        rules = engine.get_rules()
        assert len(rules) == 1
        assert rules[0].name == "test"

    def test_default_policy_in_evaluate(self) -> None:
        engine = PolicyEngine()
        engine.add_rule(
            PolicyRule(
                name="always",
                trigger=PolicyTrigger.MANUAL_OVERRIDE,
                condition=lambda ctx: True,
                action=PolicyAction.ALERT,
            )
        )
        result = engine.evaluate({})
        assert len(result) == 1


class TestCreateDefaultPolicies:
    def test_engine_has_rules(self) -> None:
        engine = create_default_policies()
        rules = engine.get_rules()
        assert len(rules) > 0

    def test_critical_entropy_rule(self) -> None:
        engine = create_default_policies()
        result = engine.evaluate({"entropy": 5})
        names = [r.name for r in result]
        assert "critical_entropy" in names

    def test_no_trigger_low_entropy(self) -> None:
        engine = create_default_policies()
        result = engine.evaluate({"entropy": 1})
        assert result == []

    def test_high_entropy_triggers(self) -> None:
        engine = create_default_policies()
        result = engine.evaluate({"entropy": 3})
        names = [r.name for r in result]
        assert "high_entropy" in names

    def test_critical_anomaly(self) -> None:
        engine = create_default_policies()
        result = engine.evaluate({"anomaly_severity": "critical"})
        names = [r.name for r in result]
        assert "critical_anomaly" in names

    def test_drift_high(self) -> None:
        engine = create_default_policies()
        result = engine.evaluate({"drift_severity": "high"})
        names = [r.name for r in result]
        assert "drift_verify" in names

    def test_drift_low_no_trigger(self) -> None:
        engine = create_default_policies()
        result = engine.evaluate({"drift_severity": "low"})
        assert "drift_verify" not in [r.name for r in result]

    def test_state_timeout(self) -> None:
        engine = create_default_policies()
        result = engine.evaluate({"state_duration": 400})
        names = [r.name for r in result]
        assert "state_timeout" in names

    def test_no_state_timeout(self) -> None:
        engine = create_default_policies()
        result = engine.evaluate({"state_duration": 100})
        assert "state_timeout" not in [r.name for r in result]
