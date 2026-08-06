"""Tests for rule_freeze_zone.py — frozen targets, pareto, overrides."""
from __future__ import annotations

import time

import pytest

from maref.recursive.rule_freeze_zone import (
    ALL_FROZEN,
    FROZEN_TARGETS,
    FreezeBlockedError,
    ParetoComparison,
    RuleFreezeZone,
    compare_pareto,
    get_frozen_category,
    is_frozen,
)


class TestFreezeFunctions:
    @pytest.mark.parametrize("target,expected", [
        ("RL-001", True),
        ("safety_gate", True),
        ("hmac_key", True),
        ("RuleFreezeZone", True),
        ("rl_table", False),
        ("unknown_thing", False),
        ("random_param", False),
    ])
    def test_is_frozen(self, target, expected):
        assert is_frozen(target) is expected

    @pytest.mark.parametrize("target,expected", [
        ("RL-001", "rl_table"),
        ("hmac_key", "audit_immutability"),
        ("RuleFreezeZone", "meta_freeze"),
        ("unknown", None),
    ])
    def test_get_frozen_category(self, target, expected):
        result = get_frozen_category(target)
        if expected is None:
            assert result is None
        else:
            assert result == expected

    def test_all_frozen_contains_expected(self):
        assert "RL-001" in ALL_FROZEN
        assert "safety_gate" in ALL_FROZEN
        assert "hmac_key" in ALL_FROZEN
        assert "RuleFreezeZone" in ALL_FROZEN


class TestComparePareto:
    def test_strictly_better(self):
        result = compare_pareto(
            {"test_pass_rate": 0.8, "latency": 100},
            {"test_pass_rate": 0.9, "latency": 80},
        )
        assert result.strictly_better is True
        assert result.strictly_worse is False
        assert result.pareto_dominant is True

    def test_strictly_worse(self):
        result = compare_pareto(
            {"test_pass_rate": 0.8, "latency": 100},
            {"test_pass_rate": 0.7, "latency": 150},
        )
        assert result.strictly_better is False
        assert result.strictly_worse is True
        assert result.pareto_dominant is False

    def test_mixed_tradeoff(self):
        result = compare_pareto(
            {"test_pass_rate": 0.8, "latency": 100},
            {"test_pass_rate": 0.9, "latency": 150},
        )
        assert result.strictly_better is False
        assert result.strictly_worse is False
        assert result.pareto_dominant is False
        assert "test_pass_rate" in result.better_metrics
        assert "latency" in result.worse_metrics

    @pytest.mark.parametrize("higher_is_better", [None, frozenset({"test_pass_rate"})])
    def test_equal_metrics(self, higher_is_better):
        result = compare_pareto(
            {"test_pass_rate": 0.8, "latency": 100},
            {"test_pass_rate": 0.8, "latency": 100},
            higher_is_better=higher_is_better,
        )
        assert len(result.equal_metrics) > 0

    def test_empty_baseline(self):
        result = compare_pareto({}, {"test_pass_rate": 0.9})
        assert result.strictly_better is True

    def test_empty_proposal(self):
        result = compare_pareto({"test_pass_rate": 0.8}, {})
        assert result.strictly_worse is True

    def test_lower_is_better_metric(self):
        result = compare_pareto(
            {"latency": 200, "cost": 50},
            {"latency": 100, "cost": 25},
            higher_is_better=frozenset(),
        )
        assert result.strictly_better is True

    def test_to_dict(self):
        result = compare_pareto({"test_pass_rate": 0.8}, {"test_pass_rate": 0.9})
        d = result.to_dict()
        assert d["strictly_better"] is True
        assert d["better_metrics"] == ["test_pass_rate"]


class TestRuleFreezeZone:
    def test_check_not_frozen(self):
        zone = RuleFreezeZone()
        result = zone.check("my_param", "value")
        assert result.allowed is True
        assert result.frozen_reason == ""

    def test_check_frozen(self):
        zone = RuleFreezeZone()
        result = zone.check("hmac_key", "new_value")
        assert result.allowed is False
        assert "frozen" in result.frozen_reason

    def test_check_proposal(self):
        zone = RuleFreezeZone()
        result = zone.check_proposal("my_param", "old", "new")
        assert result.allowed is True

    def test_override(self):
        zone = RuleFreezeZone()
        zone.override("hmac_key", 10)
        result = zone.check("hmac_key", "new_value")
        assert result.allowed is True

    def test_override_expired(self):
        zone = RuleFreezeZone()
        zone._overrides["hmac_key"] = time.time() - 1
        result = zone.check("hmac_key", "new_value")
        assert result.allowed is False

    def test_clear_override(self):
        zone = RuleFreezeZone()
        zone.override("hmac_key", 10)
        zone.clear_override("hmac_key")
        result = zone.check("hmac_key", "new_value")
        assert result.allowed is False

    def test_clear_all_overrides(self):
        zone = RuleFreezeZone()
        zone.override("hmac_key", 10)
        zone.override("RL-001", 10)
        assert zone.clear_all_overrides() == 2
        assert zone._overrides == {}

    def test_temporary_override(self):
        zone = RuleFreezeZone()
        with zone.temporary_override("hmac_key", 5):
            result = zone.check("hmac_key", "new_value")
            assert result.allowed is True
        result = zone.check("hmac_key", "new_value")
        assert result.allowed is False

    def test_audit_trail(self):
        zone = RuleFreezeZone()
        zone.check("param_a", "v1")
        zone.check("hmac_key", "v2")
        trail = zone.audit_trail()
        assert len(trail) == 2
        assert trail[1].allowed is False

    def test_blocked_count(self):
        zone = RuleFreezeZone()
        zone.check("param_a", "v1")
        zone.check("hmac_key", "v2")
        assert zone.blocked_count() == 1
        assert zone.allowed_count() == 1

    def test_is_frozen_target(self):
        zone = RuleFreezeZone()
        assert zone.is_frozen_target("hmac_key") is True
        assert zone.is_frozen_target("random") is False

    def test_frozen_categories(self):
        zone = RuleFreezeZone()
        categories = zone.frozen_categories()
        assert "rl_table" in categories
        assert "hmac_key" in categories["audit_immutability"]

    def test_to_dict(self):
        zone = RuleFreezeZone()
        zone.check("hmac_key", "v")
        d = zone.to_dict()
        assert d["checks_blocked"] == 1
        assert d["checks_total"] == 1
        assert d["total_frozen_targets"] > 0
