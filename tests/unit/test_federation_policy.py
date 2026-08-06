"""Unit tests for FederationPolicyEngine."""

from __future__ import annotations

import pytest

from maref.federation.policy import (
    ConflictStrategy,
    FederationPolicyEngine,
    PolicyDecision,
    PolicyEvaluationResult,
    PolicyRule,
    PolicyScope,
)


class TestPolicyRule:
    def test_matches_exact_action(self) -> None:
        rule = PolicyRule(
            rule_id="r1",
            action="dispatch_task",
            scope=PolicyScope.FEDERATION,
            decision=PolicyDecision.ALLOW,
        )
        assert rule.matches("dispatch_task") is True
        assert rule.matches("other_action") is False

    def test_wildcard_action_matches_anything(self) -> None:
        rule = PolicyRule(
            rule_id="r1",
            action="*",
            scope=PolicyScope.FEDERATION,
            decision=PolicyDecision.DENY,
        )
        assert rule.matches("anything") is True
        assert rule.matches("dispatch_task") is True

    def test_matches_with_conditions(self) -> None:
        rule = PolicyRule(
            rule_id="r1",
            action="cross_border_transfer",
            scope=PolicyScope.FEDERATION,
            decision=PolicyDecision.DENY,
            conditions={"data_type": "pii"},
        )
        assert rule.matches("cross_border_transfer", {"data_type": "pii"}) is True
        assert rule.matches("cross_border_transfer", {"data_type": "public"}) is False
        assert rule.matches("cross_border_transfer", None) is False

    def test_matches_with_list_condition(self) -> None:
        rule = PolicyRule(
            rule_id="r1",
            action="x",
            scope=PolicyScope.LOCAL,
            decision=PolicyDecision.ALLOW,
            conditions={"region": ["eu", "us"]},
        )
        assert rule.matches("x", {"region": "eu"}) is True
        assert rule.matches("x", {"region": "asia"}) is False

    def test_to_dict(self) -> None:
        rule = PolicyRule(
            rule_id="r1",
            action="x",
            scope=PolicyScope.AD_HOC,
            decision=PolicyDecision.DEFER,
            priority=5,
            description="test",
        )
        d = rule.to_dict()
        assert d["scope"] == "ad_hoc"
        assert d["decision"] == "defer"
        assert d["priority"] == 5
        assert d["description"] == "test"


class TestPolicyEvaluationDefault:
    def test_default_deny_when_no_rules(self) -> None:
        engine = FederationPolicyEngine()
        result = engine.evaluate("any_action")
        assert result.decision == PolicyDecision.DENY
        assert result.winning_rule is None
        assert result.matched_rules == []
        assert result.conflict_detected is False
        assert result.no_rule_match is True

    def test_no_matching_rule_defaults_to_deny(self) -> None:
        engine = FederationPolicyEngine()
        engine.add_federation_rule(
            "f1", "dispatch_task", PolicyDecision.DENY
        )
        result = engine.evaluate("unrelated_action")
        assert result.decision == PolicyDecision.DENY
        assert result.no_rule_match is True


class TestSingleLayerRules:
    def test_federation_rule_deny(self) -> None:
        engine = FederationPolicyEngine()
        engine.add_federation_rule("f1", "cross_border", PolicyDecision.DENY)
        result = engine.evaluate("cross_border")
        assert result.decision == PolicyDecision.DENY
        assert result.winning_rule is not None
        assert result.winning_rule.rule_id == "f1"
        assert result.conflict_detected is False

    def test_local_rule_allow(self) -> None:
        engine = FederationPolicyEngine()
        engine.add_local_rule("l1", "local_action", PolicyDecision.ALLOW)
        result = engine.evaluate("local_action")
        assert result.decision == PolicyDecision.ALLOW
        assert result.winning_rule.rule_id == "l1"

    def test_priority_within_layer(self) -> None:
        engine = FederationPolicyEngine()
        engine.add_federation_rule("low", "x", PolicyDecision.ALLOW, priority=1)
        engine.add_federation_rule("high", "x", PolicyDecision.DENY, priority=10)
        result = engine.evaluate("x")
        assert result.decision == PolicyDecision.DENY
        assert result.winning_rule.rule_id == "high"


class TestAdhocOverride:
    def test_adhoc_same_priority_fails_closed(self) -> None:
        """Ad-hoc no longer unconditionally overrides federation: on equal
        priority the most restrictive decision (DENY) wins."""
        engine = FederationPolicyEngine()
        engine.add_federation_rule("f1", "x", PolicyDecision.DENY)
        engine.add_rule(
            PolicyRule(
                rule_id="a1",
                action="x",
                scope=PolicyScope.AD_HOC,
                decision=PolicyDecision.ALLOW,
            )
        )
        result = engine.evaluate("x")
        assert result.decision == PolicyDecision.DENY
        assert result.winning_rule.rule_id == "f1"
        assert result.conflict_detected is False

    def test_adhoc_higher_priority_overrides_federation(self) -> None:
        engine = FederationPolicyEngine()
        engine.add_federation_rule("f1", "x", PolicyDecision.DENY, priority=1)
        engine.add_rule(
            PolicyRule(
                rule_id="a1",
                action="x",
                scope=PolicyScope.AD_HOC,
                decision=PolicyDecision.ALLOW,
                priority=10,
            )
        )
        result = engine.evaluate("x")
        assert result.decision == PolicyDecision.ALLOW
        assert result.winning_rule.rule_id == "a1"

    def test_adhoc_overrides_local(self) -> None:
        engine = FederationPolicyEngine()
        engine.add_local_rule("l1", "x", PolicyDecision.DENY)
        engine.add_rule(
            PolicyRule(
                rule_id="a1",
                action="x",
                scope=PolicyScope.AD_HOC,
                decision=PolicyDecision.ALLOW,
            )
        )
        result = engine.evaluate("x")
        assert result.decision == PolicyDecision.ALLOW


class TestConflictResolution:
    @pytest.fixture
    def conflicting_engine(self) -> FederationPolicyEngine:
        """Engine with federation DENY and local ALLOW on the same action."""
        engine = FederationPolicyEngine()
        engine.add_federation_rule("f1", "x", PolicyDecision.DENY)
        engine.add_local_rule("l1", "x", PolicyDecision.ALLOW)
        return engine

    def test_federation_wins(self, conflicting_engine: FederationPolicyEngine) -> None:
        conflicting_engine.set_conflict_strategy(ConflictStrategy.FEDERATION_WINS)
        result = conflicting_engine.evaluate("x")
        assert result.decision == PolicyDecision.DENY
        assert result.conflict_detected is True
        assert result.conflict_strategy == ConflictStrategy.FEDERATION_WINS

    def test_local_wins(self, conflicting_engine: FederationPolicyEngine) -> None:
        conflicting_engine.set_conflict_strategy(ConflictStrategy.LOCAL_WINS)
        result = conflicting_engine.evaluate("x")
        assert result.decision == PolicyDecision.ALLOW
        assert result.conflict_detected is True

    def test_deny_if_conflict(self, conflicting_engine: FederationPolicyEngine) -> None:
        conflicting_engine.set_conflict_strategy(ConflictStrategy.DENY_IF_CONFLICT)
        result = conflicting_engine.evaluate("x")
        assert result.decision == PolicyDecision.DENY
        assert result.conflict_detected is True
        assert result.winning_rule.rule_id == "conflict-deny"

    def test_most_restrictive_picks_deny(
        self, conflicting_engine: FederationPolicyEngine
    ) -> None:
        conflicting_engine.set_conflict_strategy(ConflictStrategy.MOST_RESTRICTIVE)
        result = conflicting_engine.evaluate("x")
        assert result.decision == PolicyDecision.DENY

    def test_most_restrictive_deny_vs_defer(self) -> None:
        engine = FederationPolicyEngine(
            conflict_strategy=ConflictStrategy.MOST_RESTRICTIVE
        )
        engine.add_federation_rule("f1", "x", PolicyDecision.DEFER)
        engine.add_local_rule("l1", "x", PolicyDecision.DENY)
        result = engine.evaluate("x")
        assert result.decision == PolicyDecision.DENY

    def test_no_conflict_when_decisions_agree(self) -> None:
        engine = FederationPolicyEngine()
        engine.add_federation_rule("f1", "x", PolicyDecision.ALLOW, priority=1)
        engine.add_local_rule("l1", "x", PolicyDecision.ALLOW, priority=5)
        result = engine.evaluate("x")
        assert result.decision == PolicyDecision.ALLOW
        assert result.conflict_detected is False
        # Higher priority wins.
        assert result.winning_rule.rule_id == "l1"


class TestRuleManagement:
    def test_remove_rule(self) -> None:
        engine = FederationPolicyEngine()
        engine.add_federation_rule("f1", "x", PolicyDecision.DENY)
        assert engine.remove_rule("f1") is True
        result = engine.evaluate("x")
        assert result.decision == PolicyDecision.DENY  # default is now deny
        assert result.no_rule_match is True
        assert engine.remove_rule("nonexistent") is False

    def test_add_federation_rule_helper(self) -> None:
        engine = FederationPolicyEngine()
        rule = engine.add_federation_rule("f1", "x", PolicyDecision.DENY, priority=3)
        assert rule.rule_id == "f1"
        assert rule.scope == PolicyScope.FEDERATION
        assert rule.priority == 3
        assert engine.rule_count(PolicyScope.FEDERATION) == 1

    def test_add_local_rule_helper(self) -> None:
        engine = FederationPolicyEngine()
        rule = engine.add_local_rule("l1", "y", PolicyDecision.ALLOW)
        assert rule.scope == PolicyScope.LOCAL
        assert engine.rule_count(PolicyScope.LOCAL) == 1

    def test_list_rules_filtered_by_scope(self) -> None:
        engine = FederationPolicyEngine()
        engine.add_federation_rule("f1", "x", PolicyDecision.ALLOW)
        engine.add_local_rule("l1", "x", PolicyDecision.ALLOW)
        engine.add_rule(
            PolicyRule(
                rule_id="a1",
                action="x",
                scope=PolicyScope.AD_HOC,
                decision=PolicyDecision.ALLOW,
            )
        )
        assert len(engine.list_rules(PolicyScope.FEDERATION)) == 1
        assert len(engine.list_rules(PolicyScope.LOCAL)) == 1
        assert len(engine.list_rules(PolicyScope.AD_HOC)) == 1
        assert len(engine.list_rules()) == 3

    def test_policy_summary(self) -> None:
        engine = FederationPolicyEngine(
            conflict_strategy=ConflictStrategy.MOST_RESTRICTIVE
        )
        engine.add_federation_rule("f1", "x", PolicyDecision.ALLOW)
        engine.add_local_rule("l1", "y", PolicyDecision.DENY)
        summary = engine.policy_summary()
        assert summary["conflict_strategy"] == "most_restrictive"
        assert summary["federation_rules"] == 1
        assert summary["local_rules"] == 1
        assert summary["adhoc_rules"] == 0
        assert summary["total_rules"] == 2


class TestPolicyEvaluationResult:
    def test_to_dict(self) -> None:
        rule = PolicyRule(
            rule_id="r1",
            action="x",
            scope=PolicyScope.FEDERATION,
            decision=PolicyDecision.ALLOW,
        )
        result = PolicyEvaluationResult(
            action="x",
            decision=PolicyDecision.ALLOW,
            matched_rules=[rule],
            winning_rule=rule,
        )
        d = result.to_dict()
        assert d["action"] == "x"
        assert d["decision"] == "allow"
        assert d["winning_rule"] is not None
        assert len(d["matched_rules"]) == 1
        assert d["conflict_detected"] is False
