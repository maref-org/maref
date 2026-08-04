"""Tests for F2: Multi-Jurisdiction Governance Policy Router."""

from __future__ import annotations

from maref.federation.jurisdiction_router import (
    CrossJurisdictionResult,
    JurisdictionConfig,
    JurisdictionConflictStrategy,
    JurisdictionPolicyRouter,
)
from maref.federation.policy import PolicyDecision
from maref.recursive.eight_trigrams_governance import TrigramsGovernance

# ------------------------------------------------------------------ #
# JurisdictionConfig
# ------------------------------------------------------------------ #

class TestJurisdictionConfig:
    def test_defaults(self) -> None:
        c = JurisdictionConfig(name="eu_ai_act")
        assert c.name == "eu_ai_act"
        assert c.default_decision == PolicyDecision.DENY
        assert c.weight == 1
        assert c.allowed_trigrams == set()


# ------------------------------------------------------------------ #
# JurisdictionPolicyRouter — basic management
# ------------------------------------------------------------------ #

class TestRouterManagement:
    def test_empty_router(self) -> None:
        router = JurisdictionPolicyRouter()
        assert router.jurisdiction_count() == 0

    def test_register_jurisdiction(self) -> None:
        router = JurisdictionPolicyRouter()
        router.register_jurisdiction(JurisdictionConfig(name="eu_ai_act"))
        assert router.jurisdiction_count() == 1

    def test_register_auto_creates_engine(self) -> None:
        router = JurisdictionPolicyRouter()
        router.register_jurisdiction(JurisdictionConfig(name="eu"))
        cfg = router.get_jurisdiction("eu")
        assert cfg is not None
        assert cfg.policy_engine is not None

    def test_unregister_jurisdiction(self) -> None:
        router = JurisdictionPolicyRouter()
        router.register_jurisdiction(JurisdictionConfig(name="eu"))
        assert router.unregister_jurisdiction("eu") is True
        assert router.jurisdiction_count() == 0
        assert router.unregister_jurisdiction("nonexistent") is False

    def test_get_jurisdiction(self) -> None:
        router = JurisdictionPolicyRouter()
        router.register_jurisdiction(JurisdictionConfig(name="eu", weight=3))
        cfg = router.get_jurisdiction("eu")
        assert cfg is not None
        assert cfg.weight == 3
        assert router.get_jurisdiction("us") is None

    def test_list_jurisdictions(self) -> None:
        router = JurisdictionPolicyRouter()
        router.register_jurisdiction(JurisdictionConfig(name="eu"))
        router.register_jurisdiction(JurisdictionConfig(name="us"))
        assert len(router.list_jurisdictions()) == 2


# ------------------------------------------------------------------ #
# Add trigram-aware rules
# ------------------------------------------------------------------ #

class TestAddJurisdictionRule:
    def test_add_rule(self) -> None:
        router = JurisdictionPolicyRouter()
        router.register_jurisdiction(JurisdictionConfig(name="eu"))
        ok = router.add_jurisdiction_rule(
            jurisdiction="eu",
            rule_id="eu-001",
            action="cross_border_transfer",
            decision=PolicyDecision.DENY,
            trigram_filter=["dui", "li"],
            description="EU: DUI/LI may not transfer",
        )
        assert ok is True

    def test_add_rule_unknown_jurisdiction(self) -> None:
        router = JurisdictionPolicyRouter()
        ok = router.add_jurisdiction_rule(
            jurisdiction="nonexistent",
            rule_id="r1",
            action="test",
            decision=PolicyDecision.ALLOW,
        )
        assert ok is False

    def test_add_rule_filters_by_trigram(self) -> None:
        router = JurisdictionPolicyRouter()
        router.register_jurisdiction(JurisdictionConfig(name="eu"))
        router.add_jurisdiction_rule(
            jurisdiction="eu",
            rule_id="eu-001",
            action="evolve",
            decision=PolicyDecision.DENY,
            trigram_filter=["kun"],
        )
        # KUN should be denied
        r1 = router.route_action(trigram="kun", action="evolve")
        assert r1.final_decision == PolicyDecision.DENY
        # DUI has no matching rule → fail-closed DENY (v0.47 S3)
        r2 = router.route_action(trigram="dui", action="evolve")
        assert r2.final_decision == PolicyDecision.DENY


# ------------------------------------------------------------------ #
# Core routing
# ------------------------------------------------------------------ #

class TestRouteAction:
    def test_route_single_jurisdiction_deny_by_default(self) -> None:
        """Empty jurisdiction with no rules fails closed to DENY (v0.47 S3)."""
        router = JurisdictionPolicyRouter()
        router.register_jurisdiction(JurisdictionConfig(name="eu"))
        result = router.route_action(trigram="dui", action="train_model")
        assert result.final_decision == PolicyDecision.DENY
        assert result.agent_trigram == "dui"
        assert len(result.jurisdiction_results) == 1

    def test_route_with_trigram_enum(self) -> None:
        router = JurisdictionPolicyRouter()
        router.register_jurisdiction(JurisdictionConfig(name="eu"))
        result = router.route_action(
            trigram=TrigramsGovernance.DUI, action="deploy"
        )
        assert result.final_decision == PolicyDecision.DENY

    def test_route_blocked_by_allowed_trigrams(self) -> None:
        router = JurisdictionPolicyRouter()
        router.register_jurisdiction(JurisdictionConfig(
            name="eu",
            allowed_trigrams={"qian", "gen"},
        ))
        # KUN is not allowed in EU
        result = router.route_action(trigram="kun", action="deploy")
        assert result.final_decision == PolicyDecision.DENY
        # QIAN is allowed but no rule matches → fail-closed DENY
        result2 = router.route_action(trigram="qian", action="deploy")
        assert result2.final_decision == PolicyDecision.DENY

    def test_multiple_jurisdictions_agree(self) -> None:
        router = JurisdictionPolicyRouter()
        router.register_jurisdiction(JurisdictionConfig(name="eu"))
        router.register_jurisdiction(JurisdictionConfig(name="us"))
        result = router.route_action(trigram="dui", action="train")
        assert result.final_decision == PolicyDecision.DENY
        assert result.conflict_detected is False

    def test_cross_jurisdiction_conflict(self) -> None:
        router = JurisdictionPolicyRouter()
        router.register_jurisdiction(JurisdictionConfig(name="eu"))
        router.register_jurisdiction(JurisdictionConfig(name="us"))
        router.add_jurisdiction_rule(
            "eu", "eu-block", "deploy", PolicyDecision.DENY,
            trigram_filter=["dui"],
        )
        router.add_jurisdiction_rule(
            "us", "us-allow", "deploy", PolicyDecision.ALLOW,
            trigram_filter=["dui"],
        )
        result = router.route_action(trigram="dui", action="deploy")
        assert result.conflict_detected is True
        # Default strategy is MOST_RESTRICTIVE → DENY
        assert result.final_decision == PolicyDecision.DENY

    def test_no_compatible_jurisdictions(self) -> None:
        router = JurisdictionPolicyRouter()
        router.register_jurisdiction(JurisdictionConfig(
            name="eu",
            allowed_trigrams={"qian"},
        ))
        result = router.route_action(trigram="kun", action="anything")
        assert result.final_decision == PolicyDecision.DENY


# ------------------------------------------------------------------ #
# Conflict strategies
# ------------------------------------------------------------------ #

class TestConflictStrategies:
    def test_most_permissive(self) -> None:
        router = JurisdictionPolicyRouter(
            conflict_strategy=JurisdictionConflictStrategy.MOST_PERMISSIVE,
        )
        router.register_jurisdiction(JurisdictionConfig(name="eu"))
        router.register_jurisdiction(JurisdictionConfig(name="us"))
        router.add_jurisdiction_rule(
            "eu", "eu-block", "deploy", PolicyDecision.DENY,
            trigram_filter=["dui"],
        )
        router.add_jurisdiction_rule(
            "us", "us-allow", "deploy", PolicyDecision.ALLOW,
            trigram_filter=["dui"],
        )
        result = router.route_action(trigram="dui", action="deploy")
        assert result.final_decision == PolicyDecision.ALLOW

    def test_prefer_jurisdiction(self) -> None:
        router = JurisdictionPolicyRouter(
            conflict_strategy=JurisdictionConflictStrategy.PREFER_JURISDICTION,
            prefer_jurisdiction="us",
        )
        router.register_jurisdiction(JurisdictionConfig(name="eu"))
        router.register_jurisdiction(JurisdictionConfig(name="us"))
        router.add_jurisdiction_rule(
            "eu", "eu-block", "deploy", PolicyDecision.DENY,
        )
        router.add_jurisdiction_rule(
            "us", "us-allow", "deploy", PolicyDecision.ALLOW,
        )
        result = router.route_action(trigram="dui", action="deploy")
        assert result.final_decision == PolicyDecision.ALLOW

    def test_deny_if_conflict(self) -> None:
        router = JurisdictionPolicyRouter(
            conflict_strategy=JurisdictionConflictStrategy.DENY_IF_CONFLICT,
        )
        router.register_jurisdiction(JurisdictionConfig(name="eu"))
        router.register_jurisdiction(JurisdictionConfig(name="us"))
        router.add_jurisdiction_rule(
            "eu", "eu-block", "deploy", PolicyDecision.DENY,
        )
        router.add_jurisdiction_rule(
            "us", "us-allow", "deploy", PolicyDecision.ALLOW,
        )
        result = router.route_action(trigram="dui", action="deploy")
        assert result.final_decision == PolicyDecision.DENY

    def test_set_conflict_strategy(self) -> None:
        router = JurisdictionPolicyRouter()
        router.set_conflict_strategy(
            JurisdictionConflictStrategy.PREFER_JURISDICTION,
            prefer_jurisdiction="eu",
        )
        router.register_jurisdiction(JurisdictionConfig(name="eu", weight=2))
        router.register_jurisdiction(JurisdictionConfig(name="us", weight=1))
        router.add_jurisdiction_rule(
            "eu", "eu-deny", "evolve", PolicyDecision.DENY,
        )
        router.add_jurisdiction_rule(
            "us", "us-allow", "evolve", PolicyDecision.ALLOW,
        )
        result = router.route_action(trigram="dui", action="evolve")
        assert result.final_decision == PolicyDecision.DENY


# ------------------------------------------------------------------ #
# Jurisdiction suggestion
# ------------------------------------------------------------------ #

class TestSuggestion:
    def test_suggest_jurisdiction(self) -> None:
        router = JurisdictionPolicyRouter()
        router.register_jurisdiction(JurisdictionConfig(
            name="eu", weight=3, description="EU AI Act",
        ))
        router.register_jurisdiction(JurisdictionConfig(
            name="us", weight=1, description="US Executive Order",
        ))
        router.add_jurisdiction_rule(
            "eu", "eu-allow", "train", PolicyDecision.ALLOW,
        )
        router.add_jurisdiction_rule(
            "us", "us-deny", "train", PolicyDecision.DENY,
        )
        suggested = router.suggest_jurisdiction(trigram="qian", action="train")
        assert suggested == "eu"

    def test_suggest_via_route(self) -> None:
        router = JurisdictionPolicyRouter()
        router.register_jurisdiction(JurisdictionConfig(
            name="eu", weight=2,
        ))
        router.register_jurisdiction(JurisdictionConfig(
            name="us", weight=1,
        ))
        result = router.route_action(trigram="dui", action="test")
        # Both allow, EU has higher weight → suggested is EU
        assert result.suggested_jurisdiction == "eu"

    def test_get_compatible_jurisdictions(self) -> None:
        router = JurisdictionPolicyRouter()
        router.register_jurisdiction(JurisdictionConfig(
            name="eu", allowed_trigrams={"qian", "gen", "dui"},
        ))
        router.register_jurisdiction(JurisdictionConfig(
            name="us", allowed_trigrams=set(),  # all allowed
        ))
        compat = router.get_compatible_jurisdictions(trigram="dui")
        assert len(compat) == 2

        # KUN is not allowed in EU but is allowed in US
        compat2 = router.get_compatible_jurisdictions(trigram="kun")
        assert len(compat2) == 1
        assert compat2[0]["name"] == "us"

    def test_get_compatible_with_enum(self) -> None:
        router = JurisdictionPolicyRouter()
        router.register_jurisdiction(JurisdictionConfig(
            name="eu", allowed_trigrams={"dui"},
        ))
        compat = router.get_compatible_jurisdictions(TrigramsGovernance.DUI)
        assert len(compat) == 1


# ------------------------------------------------------------------ #
# CrossJurisdictionResult
# ------------------------------------------------------------------ #

class TestCrossJurisdictionResult:
    def test_result_defaults(self) -> None:
        r = CrossJurisdictionResult(
            action="test",
            agent_trigram="dui",
            final_decision=PolicyDecision.ALLOW,
            jurisdiction_results=[],
        )
        assert r.conflict_detected is False
        assert r.suggested_jurisdiction == ""


# ------------------------------------------------------------------ #
# Router summary
# ------------------------------------------------------------------ #

class TestRouterSummary:
    def test_summary_empty(self) -> None:
        router = JurisdictionPolicyRouter()
        s = router.router_summary()
        assert s["jurisdiction_count"] == 0
        assert s["jurisdictions"] == []

    def test_summary_with_jurisdictions(self) -> None:
        router = JurisdictionPolicyRouter()
        router.register_jurisdiction(JurisdictionConfig(
            name="eu",
            description="EU AI Act",
            allowed_trigrams={"dui", "li"},
            weight=2,
        ))
        s = router.router_summary()
        assert s["jurisdiction_count"] == 1
        assert s["jurisdictions"][0]["name"] == "eu"
        assert s["jurisdictions"][0]["weight"] == 2
