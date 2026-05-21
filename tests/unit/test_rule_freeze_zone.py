from maref.recursive.rule_freeze_zone import (
    FROZEN_TARGETS,
    ALL_FROZEN,
    FreezeBlockedError,
    FreezeZoneCheckResult,
    ParetoComparison,
    RuleFreezeZone,
    compare_pareto,
    is_frozen,
    get_frozen_category,
)
from maref.recursive.evolution_dsl import EvolutionDSL, EvolutionRule


class TestFrozenTargets:
    def test_rl_table_frozen(self):
        for rl in ("RL-001", "RL-002", "RL-003", "RL-004", "RL-005"):
            assert is_frozen(rl), f"{rl} should be frozen"

    def test_safety_gate_params_frozen(self):
        frozen_params = FROZEN_TARGETS["safety_gate_params"]
        for param in frozen_params:
            assert is_frozen(param), f"{param} should be frozen"

    def test_core_components_frozen(self):
        for comp in ("circuit_breaker", "state_machine", "audit_logger"):
            assert is_frozen(comp), f"{comp} should be frozen"

    def test_circuit_breaker_hard_limits_frozen(self):
        for limit in ("max_depth", "max_failures", "trip_threshold"):
            assert is_frozen(limit), f"{limit} should be frozen"

    def test_audit_immutability_frozen(self):
        for target in ("hmac_key", "max_file_size_mb", "audit_retention_days"):
            assert is_frozen(target), f"{target} should be frozen"

    def test_meta_freeze_self_referential(self):
        assert is_frozen("rule_freeze_zone")
        assert is_frozen("RuleFreezeZone")
        assert is_frozen("frozen_targets")

    def test_non_frozen_targets_are_allowed(self):
        assert not is_frozen("adoption_gain_threshold")
        assert not is_frozen("learning_rate")
        assert not is_frozen("batch_size")
        assert not is_frozen("heal_max_iterations")

    def test_frozen_targets_substring_match(self):
        assert is_frozen("circuit_breaker_max_depth")
        assert is_frozen("state_machine_timeout")
        assert is_frozen("safety_gate_min_test_pass_rate")

    def test_get_frozen_category_returns_correct_category(self):
        assert get_frozen_category("circuit_breaker") == "core_components"
        assert get_frozen_category("RL-001") == "rl_table"
        assert get_frozen_category("max_depth") == "circuit_breaker_hard_limits"
        assert get_frozen_category("hmac_key") == "audit_immutability"
        assert get_frozen_category("adoption_gain_threshold") is None


class TestRuleFreezeZoneCheck:
    def test_non_frozen_target_allowed(self):
        fz = RuleFreezeZone()
        result = fz.check("learning_rate", 0.01)
        assert result.allowed is True
        assert result.frozen_category == ""

    def test_frozen_target_blocked(self):
        fz = RuleFreezeZone()
        result = fz.check("circuit_breaker", None)
        assert result.allowed is False
        assert result.frozen_category == "core_components"
        assert "frozen" in result.frozen_reason.lower()

    def test_rl_target_blocked(self):
        fz = RuleFreezeZone()
        result = fz.check("RL-001", "modified")
        assert result.allowed is False
        assert result.frozen_category == "rl_table"

    def test_safety_gate_param_blocked(self):
        fz = RuleFreezeZone()
        result = fz.check("min_test_pass_rate", 0.5)
        assert result.allowed is False
        assert result.frozen_category == "safety_gate_params"

    def test_meta_freeze_blocked(self):
        fz = RuleFreezeZone()
        result = fz.check("RuleFreezeZone", "modified")
        assert result.allowed is False
        assert result.frozen_category == "meta_freeze"


class TestRuleFreezeZoneOverride:
    def test_temporary_override_allows_frozen_target(self):
        fz = RuleFreezeZone()
        with fz.temporary_override("circuit_breaker", duration_seconds=60):
            result = fz.check("circuit_breaker", None)
            assert result.allowed is True
            assert "override" in result.frozen_reason.lower()

    def test_override_expires(self):
        fz = RuleFreezeZone()
        fz.override("max_depth", duration_seconds=0.0)
        result = fz.check("max_depth", 10)
        assert result.allowed is False

    def test_manual_override_allows_target(self):
        fz = RuleFreezeZone()
        fz.override("RL-001", duration_seconds=3600)
        result = fz.check("RL-001", "change")
        assert result.allowed is True

    def test_clear_override_restores_block(self):
        fz = RuleFreezeZone()
        fz.override("audit_logger", duration_seconds=3600)
        fz.clear_override("audit_logger")
        result = fz.check("audit_logger", None)
        assert result.allowed is False

    def test_clear_all_overrides(self):
        fz = RuleFreezeZone()
        fz.override("RL-001", duration_seconds=3600)
        fz.override("max_depth", duration_seconds=3600)
        assert fz.clear_all_overrides() == 2
        assert fz.check("RL-001", "x").allowed is False
        assert fz.check("max_depth", 10).allowed is False


class TestRuleFreezeZoneAudit:
    def test_audit_trail_records_all_checks(self):
        fz = RuleFreezeZone()
        fz.check("learning_rate", 0.01)
        fz.check("circuit_breaker", None)
        fz.check("adoption_gain_threshold", 0.05)
        trail = fz.audit_trail()
        assert len(trail) == 3

    def test_blocked_count_accurate(self):
        fz = RuleFreezeZone()
        fz.check("learning_rate", 0.01)
        fz.check("circuit_breaker", None)
        fz.check("RL-001", "x")
        assert fz.blocked_count() == 2
        assert fz.allowed_count() == 1

    def test_to_dict_has_expected_keys(self):
        fz = RuleFreezeZone()
        fz.check("learning_rate", 0.01)
        d = fz.to_dict()
        assert "frozen_categories" in d
        assert "total_frozen_targets" in d
        assert "checks_total" in d
        assert d["checks_total"] == 1


class TestParetoComparison:
    def test_strictly_better(self):
        baseline = {"error_rate": 0.10, "latency_ms": 100.0}
        proposal = {"error_rate": 0.05, "latency_ms": 90.0}
        result = compare_pareto(baseline, proposal)
        assert result.strictly_better is True
        assert result.strictly_worse is False
        assert result.pareto_dominant is True
        assert len(result.worse_metrics) == 0

    def test_strictly_worse(self):
        baseline = {"error_rate": 0.05, "latency_ms": 90.0}
        proposal = {"error_rate": 0.10, "latency_ms": 100.0}
        result = compare_pareto(baseline, proposal)
        assert result.strictly_worse is True
        assert result.strictly_better is False
        assert result.pareto_dominant is False

    def test_pareto_dominant_same_or_better(self):
        baseline = {"error_rate": 0.10, "latency_ms": 100.0}
        proposal = {"error_rate": 0.10, "latency_ms": 90.0}
        result = compare_pareto(baseline, proposal)
        assert result.strictly_better is True
        assert result.pareto_dominant is True
        assert len(result.worse_metrics) == 0
        assert len(result.equal_metrics) == 1

    def test_not_pareto_dominant_with_tradeoff(self):
        baseline = {"error_rate": 0.10, "latency_ms": 100.0}
        proposal = {"error_rate": 0.05, "latency_ms": 120.0}
        result = compare_pareto(baseline, proposal)
        assert result.pareto_dominant is False
        assert result.strictly_better is False
        assert result.strictly_worse is False
        assert len(result.better_metrics) == 1
        assert len(result.worse_metrics) == 1

    def test_all_equal(self):
        baseline = {"error_rate": 0.10, "latency_ms": 100.0}
        proposal = {"error_rate": 0.10, "latency_ms": 100.0}
        result = compare_pareto(baseline, proposal)
        assert result.pareto_dominant is True
        assert result.strictly_better is False
        assert result.strictly_worse is False
        assert len(result.equal_metrics) == 2

    def test_higher_is_better(self):
        baseline = {"test_pass_rate": 0.90, "coverage_pct": 75.0}
        proposal = {"test_pass_rate": 0.95, "coverage_pct": 80.0}
        result = compare_pareto(baseline, proposal)
        assert result.strictly_better is True
        assert result.pareto_dominant is True

    def test_higher_is_better_regression(self):
        baseline = {"test_pass_rate": 0.95, "coverage_pct": 80.0}
        proposal = {"test_pass_rate": 0.90, "coverage_pct": 85.0}
        result = compare_pareto(baseline, proposal)
        assert result.pareto_dominant is False
        assert len(result.worse_metrics) == 1

    def test_to_dict_format(self):
        baseline = {"error_rate": 0.05}
        proposal = {"error_rate": 0.03}
        result = compare_pareto(baseline, proposal)
        d = result.to_dict()
        assert d["pareto_dominant"] is True
        assert "better_metrics" in d
        assert "worse_metrics" in d
        assert "equal_metrics" in d


class TestEvolutionDSLFreezeIntegration:
    def test_propose_frozen_target_raises(self):
        dsl = EvolutionDSL()
        try:
            dsl.propose("circuit_breaker", 100, 200, "test freeze")
            assert False, "FreezeBlockedError should have been raised"
        except FreezeBlockedError:
            pass

    def test_propose_non_frozen_target_succeeds(self):
        dsl = EvolutionDSL()
        rule = dsl.propose("learning_rate", 0.01, 0.02, "test")
        assert rule.target == "learning_rate"
        assert rule.proposed_value == 0.02

    def test_propose_frozen_after_override_succeeds(self):
        dsl = EvolutionDSL()
        fz = dsl.freeze_zone
        with fz.temporary_override("circuit_breaker", duration_seconds=60):
            rule = dsl.propose("circuit_breaker", 100, 200, "override test")
            assert rule.target == "circuit_breaker"
            assert rule.proposed_value == 200

    def test_load_default_rules_skips_frozen(self):
        dsl = EvolutionDSL()
        rules = dsl.load_default_rules(skip_frozen=True)
        targets = {r.target for r in rules}
        assert "meta_cb_trip_threshold" not in targets
        assert "max_recursion_depth" not in targets
        assert "cb_cooldown_s" not in targets
        assert "audit_retention_days" not in targets

    def test_load_default_rules_no_skip_includes_all(self):
        dsl = EvolutionDSL()
        rules = dsl.load_default_rules(skip_frozen=False)
        targets = {r.target for r in rules}
        assert "meta_cb_trip_threshold" in targets
        assert "max_recursion_depth" in targets

    def test_freeze_zone_property_accessible(self):
        dsl = EvolutionDSL()
        fz = dsl.freeze_zone
        assert fz is not None
        assert isinstance(fz, RuleFreezeZone)

    def test_safety_check_core_removal_blocked(self):
        from maref.recursive.evolution_dsl import SafetyGate
        gate = SafetyGate()
        rule = EvolutionRule(
            rule_id="test",
            target="circuit_breaker",
            current_value="active",
            proposed_value=None,
            justification="remove cb",
        )
        result = gate.evaluate(rule)
        assert result.passed is False
        assert "forbid_core_removal" in result.rejection_reason


class TestFreezeZoneIsolation:
    def test_freeze_zone_instances_independent(self):
        fz1 = RuleFreezeZone()
        fz2 = RuleFreezeZone()
        fz1.check("circuit_breaker", None)
        assert fz1.audit_trail()
        fz1.override("RL-001", duration_seconds=3600)
        assert fz2.check("RL-001", "x").allowed is False