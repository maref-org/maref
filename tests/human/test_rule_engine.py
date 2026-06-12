from __future__ import annotations

import pytest

from maref.human.rule_engine import (
    CollaborationAction,
    CollaborationRule,
    CollaborationRuleEngine,
    RuleCondition,
)


class TestRuleCondition:
    def test_gt(self) -> None:
        c = RuleCondition("cost", ">", 500)
        assert c.evaluate({"cost": 600}) is True
        assert c.evaluate({"cost": 400}) is False

    def test_ge(self) -> None:
        c = RuleCondition("cost", ">=", 500)
        assert c.evaluate({"cost": 500}) is True
        assert c.evaluate({"cost": 499}) is False

    def test_lt(self) -> None:
        c = RuleCondition("cost", "<", 500)
        assert c.evaluate({"cost": 400}) is True
        assert c.evaluate({"cost": 600}) is False

    def test_le(self) -> None:
        c = RuleCondition("cost", "<=", 500)
        assert c.evaluate({"cost": 500}) is True
        assert c.evaluate({"cost": 501}) is False

    def test_eq(self) -> None:
        c = RuleCondition("data_classification", "==", "PII")
        assert c.evaluate({"data_classification": "PII"}) is True
        assert c.evaluate({"data_classification": "PUBLIC"}) is False

    def test_ne(self) -> None:
        c = RuleCondition("data_classification", "!=", "PII")
        assert c.evaluate({"data_classification": "PUBLIC"}) is True
        assert c.evaluate({"data_classification": "PII"}) is False

    def test_in_operator(self) -> None:
        c = RuleCondition("role", "in", ["admin", "manager"])
        assert c.evaluate({"role": "admin"}) is True
        assert c.evaluate({"role": "viewer"}) is False

    def test_contains_operator(self) -> None:
        c = RuleCondition("description", "contains", "urgent")
        assert c.evaluate({"description": "this is urgent"}) is True
        assert c.evaluate({"description": "normal task"}) is False

    def test_missing_field_returns_false(self) -> None:
        c = RuleCondition("nonexistent", "==", "value")
        assert c.evaluate({"cost": 100}) is False

    def test_unknown_operator_raises(self) -> None:
        c = RuleCondition("cost", "???", 100)
        with pytest.raises(ValueError, match="Unknown operator"):
            c.evaluate({"cost": 100})


class TestCollaborationRule:
    def test_evaluate_matched(self) -> None:
        rule = CollaborationRule(
            name="test",
            when=[RuleCondition("cost", ">", 100)],
            then=CollaborationAction.HITL,
        )
        assert rule.evaluate({"cost": 200}) == CollaborationAction.HITL

    def test_evaluate_not_matched_no_else(self) -> None:
        rule = CollaborationRule(
            name="test",
            when=[RuleCondition("cost", ">", 100)],
            then=CollaborationAction.HITL,
        )
        assert rule.evaluate({"cost": 50}) is None

    def test_evaluate_not_matched_with_else(self) -> None:
        rule = CollaborationRule(
            name="test",
            when=[RuleCondition("cost", ">", 100)],
            then=CollaborationAction.HITL,
            else_=CollaborationAction.HOTL,
        )
        assert rule.evaluate({"cost": 50}) == CollaborationAction.HOTL

    def test_disabled_rule_returns_none(self) -> None:
        rule = CollaborationRule(
            name="test",
            when=[RuleCondition("cost", ">", 0)],
            then=CollaborationAction.HALT,
            enabled=False,
        )
        assert rule.evaluate({"cost": 999}) is None

    def test_multiple_conditions_and(self) -> None:
        rule = CollaborationRule(
            name="test",
            when=[
                RuleCondition("cost", ">", 500),
                RuleCondition("data_classification", "==", "PII"),
            ],
            then=CollaborationAction.HITL,
        )
        assert rule.evaluate({"cost": 600, "data_classification": "PII"}) == CollaborationAction.HITL
        assert rule.evaluate({"cost": 600, "data_classification": "PUBLIC"}) is None

    def test_default_values(self) -> None:
        rule = CollaborationRule(name="test", when=[], then=CollaborationAction.NOTIFY)
        assert rule.priority == 0
        assert rule.enabled is True
        assert rule.created_at > 0
        assert rule.else_ is None


class TestCollaborationRuleEngine:
    def test_add_rule(self) -> None:
        engine = CollaborationRuleEngine()
        rule = CollaborationRule(name="r1", when=[], then=CollaborationAction.HITL)
        engine.add_rule(rule)
        assert len(engine.list_rules()) == 1

    def test_priority_sorting(self) -> None:
        engine = CollaborationRuleEngine()
        r1 = CollaborationRule(name="low", when=[RuleCondition("x", ">", 0)], then=CollaborationAction.NOTIFY, priority=1)
        r2 = CollaborationRule(name="high", when=[RuleCondition("y", ">", 0)], then=CollaborationAction.HALT, priority=100)
        engine.add_rule(r1)
        engine.add_rule(r2)
        rules = engine.list_rules()
        assert rules[0].name == "high"

    def test_remove_rule_exists(self) -> None:
        engine = CollaborationRuleEngine()
        engine.add_rule(CollaborationRule(name="r1", when=[], then=CollaborationAction.HITL))
        assert engine.remove_rule("r1") is True
        assert len(engine.list_rules()) == 0

    def test_remove_rule_not_found(self) -> None:
        engine = CollaborationRuleEngine()
        assert engine.remove_rule("nonexistent") is False

    def test_enable_rule(self) -> None:
        engine = CollaborationRuleEngine()
        engine.add_rule(CollaborationRule(name="r1", when=[], then=CollaborationAction.HITL, enabled=False))
        assert engine.enable_rule("r1") is True
        assert engine.list_rules()[0].enabled is True

    def test_enable_rule_not_found(self) -> None:
        engine = CollaborationRuleEngine()
        assert engine.enable_rule("nonexistent") is False

    def test_disable_rule(self) -> None:
        engine = CollaborationRuleEngine()
        engine.add_rule(CollaborationRule(name="r1", when=[], then=CollaborationAction.HITL))
        assert engine.disable_rule("r1") is True
        assert engine.list_rules()[0].enabled is False

    def test_disable_rule_not_found(self) -> None:
        engine = CollaborationRuleEngine()
        assert engine.disable_rule("nonexistent") is False

    def test_evaluate_no_match_returns_hatl(self) -> None:
        engine = CollaborationRuleEngine()
        assert engine.evaluate({"cost": 100}) == CollaborationAction.HATL

    def test_evaluate_first_match_wins(self) -> None:
        engine = CollaborationRuleEngine()
        engine.add_rule(CollaborationRule(name="r1", when=[RuleCondition("x", "==", 1)], then=CollaborationAction.HALT))
        engine.add_rule(CollaborationRule(name="r2", when=[RuleCondition("x", "==", 1)], then=CollaborationAction.NOTIFY))
        assert engine.evaluate({"x": 1}) == CollaborationAction.HALT

    def test_evaluate_with_trace(self) -> None:
        engine = CollaborationRuleEngine()
        engine.add_rule(CollaborationRule(name="r1", when=[RuleCondition("x", "==", 1)], then=CollaborationAction.HALT))
        engine.add_rule(CollaborationRule(name="r2", when=[RuleCondition("x", "==", 2)], then=CollaborationAction.NOTIFY))
        action, trace = engine.evaluate_with_trace({"x": 2})
        assert action == CollaborationAction.NOTIFY
        assert trace == ["r1", "r2"]

    def test_evaluate_with_trace_no_match(self) -> None:
        engine = CollaborationRuleEngine()
        engine.add_rule(CollaborationRule(name="r1", when=[RuleCondition("x", "==", 99)], then=CollaborationAction.HALT))
        action, trace = engine.evaluate_with_trace({"x": 1})
        assert action == CollaborationAction.HATL
        assert trace == ["r1"]

    def test_get_history(self) -> None:
        engine = CollaborationRuleEngine()
        engine.add_rule(CollaborationRule(name="r1", when=[RuleCondition("x", ">", 0)], then=CollaborationAction.HALT))
        engine.evaluate({"x": 1})
        engine.evaluate({"x": 2})
        history = engine.get_history()
        assert len(history) == 2
        assert history[0][2] == CollaborationAction.HALT

    def test_get_history_limit(self) -> None:
        engine = CollaborationRuleEngine()
        engine.add_rule(CollaborationRule(name="r1", when=[RuleCondition("x", ">", 0)], then=CollaborationAction.HALT))
        for i in range(10):
            engine.evaluate({"x": i})
        assert len(engine.get_history(limit=3)) == 3


class TestCollaborationRuleEngineParse:
    def test_parse_basic(self) -> None:
        engine = CollaborationRuleEngine()
        rule = engine.parse_rule("test", "WHEN cost > 500 THEN HITL ELSE HOTL")
        assert rule.name == "test"
        assert len(rule.when) == 1
        assert rule.when[0].field == "cost"
        assert rule.when[0].op == ">"
        assert rule.when[0].value == 500
        assert rule.then == CollaborationAction.HITL
        assert rule.else_ == CollaborationAction.HOTL

    def test_parse_and_conditions(self) -> None:
        rule = CollaborationRuleEngine.parse_rule(
            "test",
            "WHEN cost > 500 AND data_classification == PII THEN HALT",
        )
        assert len(rule.when) == 2
        assert rule.then == CollaborationAction.HALT
        assert rule.else_ is None

    def test_parse_string_value(self) -> None:
        rule = CollaborationRuleEngine.parse_rule(
            "test",
            "WHEN data_classification == PII THEN NOTIFY",
        )
        assert rule.when[0].value == "PII"

    def test_parse_quoted_string(self) -> None:
        rule = CollaborationRuleEngine.parse_rule(
            "test",
            "WHEN description contains 'urgent task' THEN HITL",
        )
        assert rule.when[0].value == "urgent task"

    def test_parse_in_operator(self) -> None:
        rule = CollaborationRuleEngine.parse_rule(
            "test",
            "WHEN role in admin THEN DELEGATE",
        )
        assert rule.when[0].op == "in"

    def test_parse_invalid_dsl_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid DSL"):
            CollaborationRuleEngine.parse_rule("test", "this is not valid")

    def test_parse_invalid_condition_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid condition"):
            CollaborationRuleEngine.parse_rule("test", "WHEN !!! THEN HALT")

    def test_parse_float_value(self) -> None:
        rule = CollaborationRuleEngine.parse_rule(
            "test",
            "WHEN risk_score > 0.75 THEN HALT",
        )
        assert rule.when[0].value == 0.75

    def test_parse_ge_operator(self) -> None:
        rule = CollaborationRuleEngine.parse_rule(
            "test",
            "WHEN cost >= 1000 THEN NOTIFY",
        )
        assert rule.when[0].op == ">="
        assert rule.when[0].value == 1000

    def test_parse_le_operator(self) -> None:
        rule = CollaborationRuleEngine.parse_rule(
            "test",
            "WHEN risk_score <= 0.3 THEN HATL",
        )
        assert rule.when[0].op == "<="

    def test_parse_ne_operator(self) -> None:
        rule = CollaborationRuleEngine.parse_rule(
            "test",
            "WHEN data_classification != PUBLIC THEN HITL",
        )
        assert rule.when[0].op == "!="


class TestParseValue:
    def test_int(self) -> None:
        assert CollaborationRuleEngine._parse_value("500") == 500

    def test_float(self) -> None:
        assert CollaborationRuleEngine._parse_value("0.75") == 0.75

    def test_string(self) -> None:
        assert CollaborationRuleEngine._parse_value("PII") == "PII"

    def test_single_quoted(self) -> None:
        assert CollaborationRuleEngine._parse_value("'urgent'") == "urgent"

    def test_double_quoted(self) -> None:
        assert CollaborationRuleEngine._parse_value('"critical"') == "critical"

    def test_negative_int(self) -> None:
        assert CollaborationRuleEngine._parse_value("-100") == -100
