"""
CollaborationRuleEngine 扩展测试

补充覆盖：RuleCondition 所有操作符、RuleCondition 未知操作符、
CollaborationRule.evaluate disabled、CollaborationRule.evaluate else_、
list_rules、enable_rule 不存在、disable_rule 不存在、
remove_rule 不存在、evaluate 无匹配返回 HATL、
_parse_value 各种类型、parse_rule 无效 DSL、
get_history limit、history 记录。
"""

from __future__ import annotations

import pytest

from maref.human.rule_engine import (
    CollaborationAction,
    CollaborationRule,
    CollaborationRuleEngine,
    RuleCondition,
)


class TestRuleConditionOperators:
    def test_gt(self) -> None:
        cond = RuleCondition("cost", ">", 500)
        assert cond.evaluate({"cost": 600}) is True
        assert cond.evaluate({"cost": 400}) is False

    def test_ge(self) -> None:
        cond = RuleCondition("cost", ">=", 500)
        assert cond.evaluate({"cost": 500}) is True
        assert cond.evaluate({"cost": 499}) is False

    def test_lt(self) -> None:
        cond = RuleCondition("cost", "<", 500)
        assert cond.evaluate({"cost": 400}) is True
        assert cond.evaluate({"cost": 600}) is False

    def test_le(self) -> None:
        cond = RuleCondition("cost", "<=", 500)
        assert cond.evaluate({"cost": 500}) is True
        assert cond.evaluate({"cost": 501}) is False

    def test_eq(self) -> None:
        cond = RuleCondition("type", "==", "PII")
        assert cond.evaluate({"type": "PII"}) is True
        assert cond.evaluate({"type": "PUBLIC"}) is False

    def test_ne(self) -> None:
        cond = RuleCondition("type", "!=", "PII")
        assert cond.evaluate({"type": "PUBLIC"}) is True
        assert cond.evaluate({"type": "PII"}) is False

    def test_in(self) -> None:
        cond = RuleCondition("type", "in", ["PII", "INTERNAL"])
        assert cond.evaluate({"type": "PII"}) is True
        assert cond.evaluate({"type": "PUBLIC"}) is False

    def test_contains(self) -> None:
        cond = RuleCondition("tags", "contains", "sensitive")
        assert cond.evaluate({"tags": "sensitive data"}) is True
        assert cond.evaluate({"tags": "public data"}) is False

    def test_missing_field(self) -> None:
        cond = RuleCondition("cost", ">", 500)
        assert cond.evaluate({"other": 600}) is False

    def test_unknown_operator(self) -> None:
        cond = RuleCondition("cost", "~~", 500)
        with pytest.raises(ValueError, match="Unknown operator"):
            cond.evaluate({"cost": 600})


class TestCollaborationRule:
    def test_evaluate_disabled(self) -> None:
        rule = CollaborationRule(
            name="test",
            when=[RuleCondition("x", "==", 1)],
            then=CollaborationAction.HALT,
            enabled=False,
        )
        assert rule.evaluate({"x": 1}) is None

    def test_evaluate_else(self) -> None:
        rule = CollaborationRule(
            name="test",
            when=[RuleCondition("x", ">", 10)],
            then=CollaborationAction.HITL,
            else_=CollaborationAction.HOTL,
        )
        assert rule.evaluate({"x": 5}) == CollaborationAction.HOTL

    def test_evaluate_no_else(self) -> None:
        rule = CollaborationRule(
            name="test",
            when=[RuleCondition("x", ">", 10)],
            then=CollaborationAction.HITL,
        )
        assert rule.evaluate({"x": 5}) is None

    def test_evaluate_multiple_conditions(self) -> None:
        rule = CollaborationRule(
            name="test",
            when=[
                RuleCondition("x", ">", 5),
                RuleCondition("y", "<", 10),
            ],
            then=CollaborationAction.HALT,
        )
        assert rule.evaluate({"x": 6, "y": 5}) == CollaborationAction.HALT
        assert rule.evaluate({"x": 6, "y": 15}) is None


class TestRuleEngineManagement:
    def test_list_rules(self) -> None:
        engine = CollaborationRuleEngine()
        rule = CollaborationRule(
            name="test",
            when=[RuleCondition("x", "==", 1)],
            then=CollaborationAction.HALT,
        )
        engine.add_rule(rule)
        rules = engine.list_rules()
        assert len(rules) == 1
        assert rules[0].name == "test"

    def test_enable_rule_not_found(self) -> None:
        engine = CollaborationRuleEngine()
        assert engine.enable_rule("nonexistent") is False

    def test_disable_rule_not_found(self) -> None:
        engine = CollaborationRuleEngine()
        assert engine.disable_rule("nonexistent") is False

    def test_remove_rule_not_found(self) -> None:
        engine = CollaborationRuleEngine()
        assert engine.remove_rule("nonexistent") is False

    def test_add_rule_sorts_by_priority(self) -> None:
        engine = CollaborationRuleEngine()
        engine.add_rule(CollaborationRule(
            name="low",
            when=[RuleCondition("x", "==", 1)],
            then=CollaborationAction.HATL,
            priority=1,
        ))
        engine.add_rule(CollaborationRule(
            name="high",
            when=[RuleCondition("x", "==", 1)],
            then=CollaborationAction.HALT,
            priority=10,
        ))
        rules = engine.list_rules()
        assert rules[0].name == "high"
        assert rules[1].name == "low"


class TestRuleEngineEvaluate:
    def test_evaluate_no_rules(self) -> None:
        engine = CollaborationRuleEngine()
        assert engine.evaluate({"x": 1}) == CollaborationAction.HATL

    def test_evaluate_first_match_wins(self) -> None:
        engine = CollaborationRuleEngine()
        engine.add_rule(CollaborationRule(
            name="first",
            when=[RuleCondition("x", ">", 0)],
            then=CollaborationAction.HITL,
            priority=10,
        ))
        engine.add_rule(CollaborationRule(
            name="second",
            when=[RuleCondition("x", ">", 0)],
            then=CollaborationAction.HALT,
            priority=1,
        ))
        assert engine.evaluate({"x": 1}) == CollaborationAction.HITL

    def test_evaluate_with_trace_no_match(self) -> None:
        engine = CollaborationRuleEngine()
        engine.add_rule(CollaborationRule(
            name="test",
            when=[RuleCondition("x", ">", 10)],
            then=CollaborationAction.HALT,
        ))
        action, trace = engine.evaluate_with_trace({"x": 1})
        assert action == CollaborationAction.HATL
        assert trace == ["test"]


class TestDSLParser:
    def test_parse_value_int(self) -> None:
        engine = CollaborationRuleEngine()
        assert engine._parse_value("42") == 42

    def test_parse_value_float(self) -> None:
        engine = CollaborationRuleEngine()
        assert engine._parse_value("3.14") == 3.14

    def test_parse_value_quoted_string(self) -> None:
        engine = CollaborationRuleEngine()
        assert engine._parse_value("'hello'") == "hello"
        assert engine._parse_value('"world"') == "world"

    def test_parse_value_unquoted_string(self) -> None:
        engine = CollaborationRuleEngine()
        assert engine._parse_value("PII") == "PII"

    def test_parse_rule_invalid_dsl(self) -> None:
        engine = CollaborationRuleEngine()
        with pytest.raises(ValueError, match="Invalid DSL"):
            engine.parse_rule("test", "INVALID DSL")

    def test_parse_rule_no_else(self) -> None:
        engine = CollaborationRuleEngine()
        rule = engine.parse_rule("test", "WHEN cost > 500 THEN HITL")
        assert rule.else_ is None

    def test_parse_rule_complex(self) -> None:
        engine = CollaborationRuleEngine()
        rule = engine.parse_rule(
            "complex",
            "WHEN cost > 500 AND risk_score > 0.8 THEN HALT ELSE NOTIFY"
        )
        assert rule.name == "complex"
        assert rule.then == CollaborationAction.HALT
        assert rule.else_ == CollaborationAction.NOTIFY
        assert len(rule.when) == 2


class TestHistory:
    def test_get_history_limit(self) -> None:
        engine = CollaborationRuleEngine()
        engine.add_rule(CollaborationRule(
            name="test",
            when=[RuleCondition("x", ">", 0)],
            then=CollaborationAction.HITL,
        ))
        for i in range(5):
            engine.evaluate({"x": i + 1})
        history = engine.get_history(limit=3)
        assert len(history) == 3

    def test_history_records_action(self) -> None:
        engine = CollaborationRuleEngine()
        engine.add_rule(CollaborationRule(
            name="test",
            when=[RuleCondition("x", "==", 1)],
            then=CollaborationAction.HALT,
        ))
        engine.evaluate({"x": 1})
        history = engine.get_history()
        assert len(history) == 1
        assert history[0][2] == CollaborationAction.HALT
