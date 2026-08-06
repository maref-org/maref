"""Tests for Collaboration Rule Engine."""

from maref.human.rule_engine import (
    CollaborationAction,
    CollaborationRule,
    CollaborationRuleEngine,
    RuleCondition,
)


class TestCollaborationRuleEngine:
    def test_hitl_on_high_cost(self):
        engine = CollaborationRuleEngine()
        engine.add_rule(
            CollaborationRule(
                name="high_cost",
                when=[RuleCondition("cost", ">", 500)],
                then=CollaborationAction.HITL,
                else_=CollaborationAction.HOTL,
            )
        )

        action = engine.evaluate({"cost": 600})
        assert action == CollaborationAction.HITL

        action = engine.evaluate({"cost": 100})
        assert action == CollaborationAction.HOTL

    def test_pii_requires_hitl(self):
        engine = CollaborationRuleEngine()
        engine.add_rule(
            CollaborationRule(
                name="pii_rule",
                when=[
                    RuleCondition("data_classification", "==", "PII"),
                ],
                then=CollaborationAction.HITL,
            )
        )

        action = engine.evaluate({"data_classification": "PII", "cost": 10})
        assert action == CollaborationAction.HITL

        action = engine.evaluate({"data_classification": "PUBLIC"})
        assert action == CollaborationAction.HATL  # Default

    def test_multiple_conditions_and(self):
        engine = CollaborationRuleEngine()
        engine.add_rule(
            CollaborationRule(
                name="complex",
                when=[
                    RuleCondition("cost", ">", 500),
                    RuleCondition("risk_score", ">", 0.7),
                ],
                then=CollaborationAction.HALT,
            )
        )

        action = engine.evaluate({"cost": 600, "risk_score": 0.8})
        assert action == CollaborationAction.HALT

        action = engine.evaluate({"cost": 600, "risk_score": 0.5})
        assert action == CollaborationAction.HATL  # Default

    def test_priority_order(self):
        engine = CollaborationRuleEngine()
        engine.add_rule(
            CollaborationRule(
                name="low_priority",
                when=[RuleCondition("cost", ">", 100)],
                then=CollaborationAction.HOTL,
                priority=1,
            )
        )
        engine.add_rule(
            CollaborationRule(
                name="high_priority",
                when=[RuleCondition("cost", ">", 500)],
                then=CollaborationAction.HITL,
                priority=10,
            )
        )

        action = engine.evaluate({"cost": 600})
        assert action == CollaborationAction.HITL  # High priority wins

    def test_disable_rule(self):
        engine = CollaborationRuleEngine()
        engine.add_rule(
            CollaborationRule(
                name="test",
                when=[RuleCondition("x", "==", 1)],
                then=CollaborationAction.HALT,
            )
        )

        assert engine.evaluate({"x": 1}) == CollaborationAction.HALT
        engine.disable_rule("test")
        assert engine.evaluate({"x": 1}) == CollaborationAction.HATL
        engine.enable_rule("test")
        assert engine.evaluate({"x": 1}) == CollaborationAction.HALT

    def test_remove_rule(self):
        engine = CollaborationRuleEngine()
        engine.add_rule(
            CollaborationRule(
                name="to_remove",
                when=[RuleCondition("x", "==", 1)],
                then=CollaborationAction.HALT,
            )
        )
        assert engine.remove_rule("to_remove") is True
        assert engine.evaluate({"x": 1}) == CollaborationAction.HATL

    def test_dsl_parser(self):
        rule = CollaborationRuleEngine.parse_rule(
            "cost_check", "WHEN cost > 500 AND data_classification == PII THEN HITL ELSE HOTL"
        )
        assert rule.name == "cost_check"
        assert rule.then == CollaborationAction.HITL
        assert rule.else_ == CollaborationAction.HOTL
        assert len(rule.when) == 2

        action = rule.evaluate({"cost": 600, "data_classification": "PII"})
        assert action == CollaborationAction.HITL

        action = rule.evaluate({"cost": 100, "data_classification": "PII"})
        assert action == CollaborationAction.HOTL

    def test_evaluate_with_trace(self):
        engine = CollaborationRuleEngine()
        engine.add_rule(
            CollaborationRule(
                name="rule1",
                when=[RuleCondition("a", ">", 1)],
                then=CollaborationAction.HITL,
            )
        )
        engine.add_rule(
            CollaborationRule(
                name="rule2",
                when=[RuleCondition("b", ">", 1)],
                then=CollaborationAction.HOTL,
            )
        )

        action, trace = engine.evaluate_with_trace({"a": 2, "b": 2})
        assert action == CollaborationAction.HITL
        assert trace == ["rule1"]  # First match, stop

    def test_history(self):
        engine = CollaborationRuleEngine()
        engine.add_rule(
            CollaborationRule(
                name="hist",
                when=[RuleCondition("x", "==", 1)],
                then=CollaborationAction.HITL,
            )
        )
        engine.evaluate({"x": 1})
        history = engine.get_history()
        assert len(history) == 1
        assert history[0][2] == CollaborationAction.HITL
