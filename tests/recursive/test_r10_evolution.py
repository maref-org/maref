from __future__ import annotations

import pytest

from maref.recursive.evolution_dsl import (
    ApplyResult,
    EvolutionAuditEntry,
    EvolutionDSL,
    EvolutionRule,
    GateResult,
    SafetyGate,
    SimulationResult,
)


class TestSafetyGate:
    def test_safe_proposal_passes(self) -> None:
        gate = SafetyGate()
        rule = EvolutionRule(
            rule_id="r1",
            target="adoption_gain_threshold",
            current_value=0.05,
            proposed_value=0.03,
            justification="降低阈值",
        )
        result = gate.evaluate(rule)
        assert result.passed is True

    def test_delete_cb_is_rejected(self) -> None:
        gate = SafetyGate()
        rule = EvolutionRule(
            rule_id="r2",
            target="circuit_breaker",
            current_value="active",
            proposed_value=None,
            justification="移除 CB",
        )
        result = gate.evaluate(rule)
        assert result.passed is False
        assert "forbid_core_removal" in result.rejection_reason

    def test_delete_state_machine_rejected(self) -> None:
        gate = SafetyGate()
        rule = EvolutionRule(
            rule_id="r3",
            target="state_machine",
            current_value="active",
            proposed_value=None,
        )
        result = gate.evaluate(rule)
        assert result.passed is False

    def test_non_core_set_to_none_passes(self) -> None:
        gate = SafetyGate()
        rule = EvolutionRule(
            rule_id="r4",
            target="debug_mode",
            current_value=True,
            proposed_value=None,
        )
        result = gate.evaluate(rule)
        assert result.passed is True


class TestEvolutionDSL:
    @pytest.fixture
    def dsl(self) -> EvolutionDSL:
        return EvolutionDSL()

    def test_load_default_rules(self, dsl: EvolutionDSL) -> None:
        rules = dsl.load_default_rules()
        assert len(rules) >= 6
        for rule in rules:
            assert isinstance(rule, EvolutionRule)

    def test_propose_creates_rule(self, dsl: EvolutionDSL) -> None:
        rule = dsl.propose("heal_max_iterations", 3, 5, "允许更多修复迭代")
        assert rule.target == "heal_max_iterations"
        assert rule.current_value == 3
        assert rule.proposed_value == 5

    def test_simulate_returns_result(self, dsl: EvolutionDSL) -> None:
        rule = dsl.propose("timeout", 10, 15, "增加超时")
        result = dsl.simulate(rule, rounds=3)
        assert isinstance(result, SimulationResult)
        assert result.rounds_completed == 3
        assert result.passed is True

    def test_simulate_zero_rounds(self, dsl: EvolutionDSL) -> None:
        rule = dsl.propose("timeout", 10, 15)
        result = dsl.simulate(rule, rounds=0)
        assert result.passed is False

    def test_safety_check_safe_proposal(self, dsl: EvolutionDSL) -> None:
        rule = dsl.propose("adoption_gain_threshold", 0.05, 0.03, "历史数据显示 5% 过于保守")
        result = dsl.safety_check(rule)
        assert isinstance(result, GateResult)
        assert result.passed is True

    def test_safety_check_dangerous_proposal(self, dsl: EvolutionDSL) -> None:
        with dsl.freeze_zone.temporary_override("circuit_breaker"):
            rule = dsl.propose("circuit_breaker", "active", None, "CB 阻碍性能")
            result = dsl.safety_check(rule)
            assert result.passed is False

    def test_apply_safe_proposal(self, dsl: EvolutionDSL) -> None:
        rule = dsl.propose("adoption_gain_threshold", 0.05, 0.03, "降低阈值")
        result = dsl.apply(rule)
        assert isinstance(result, ApplyResult)
        assert result.applied is True

    def test_apply_dangerous_proposal(self, dsl: EvolutionDSL) -> None:
        with dsl.freeze_zone.temporary_override("circuit_breaker"):
            rule = dsl.propose("circuit_breaker", "active", None, "移除 CB")
            result = dsl.apply(rule)
            assert result.applied is False

    def test_rollback_restores_value(self, dsl: EvolutionDSL) -> None:
        rule = dsl.propose("adoption_gain_threshold", 0.05, 0.03)
        dsl.apply(rule)
        assert dsl.rollback(rule.rule_id) is True

    def test_audit_trail_entries(self, dsl: EvolutionDSL) -> None:
        rule = dsl.propose("adoption_gain_threshold", 0.05, 0.03, "测试审计")
        dsl.apply(rule)
        trail = dsl.audit_trail()
        assert len(trail) >= 1
        entry = trail[0]
        assert isinstance(entry, EvolutionAuditEntry)
        assert entry.justification == "测试审计"

    def test_justification_preserved(self, dsl: EvolutionDSL) -> None:
        rule = dsl.propose("timeout", 10, 15, "提高稳定性超时")
        dsl.apply(rule)
        trail = dsl.audit_trail()
        assert any(e.justification == "提高稳定性超时" for e in trail)

    def test_rule_count(self, dsl: EvolutionDSL) -> None:
        dsl.load_default_rules()
        assert dsl.rule_count() >= 6

    def test_safety_gate_with_test_metrics_pass(self) -> None:
        from maref.recursive.evolution_dsl import EvolutionRule, SafetyGate

        gate = SafetyGate(min_test_pass_rate=0.95)
        rule = EvolutionRule(
            rule_id="r_test",
            target="test_param",
            current_value=1.0,
            proposed_value=2.0,
            justification="test",
        )
        result = gate.evaluate(
            rule,
            metrics={
                "test_pass_rate": 0.98,
                "coverage_pct": 85.0,
                "baseline_coverage_pct": 85.0,
                "perf_regression_pct": 1.0,
            },
        )
        assert result.passed is True

    def test_safety_gate_with_low_test_pass_rate(self) -> None:
        from maref.recursive.evolution_dsl import EvolutionRule, SafetyGate

        gate = SafetyGate(min_test_pass_rate=0.95)
        rule = EvolutionRule(
            rule_id="r_test",
            target="test_param",
            current_value=1.0,
            proposed_value=2.0,
            justification="test",
        )
        result = gate.evaluate(rule, metrics={"test_pass_rate": 0.85})
        assert result.passed is False
        assert "test_pass_rate" in result.rejection_reason

    def test_safety_gate_with_coverage_drop(self) -> None:
        from maref.recursive.evolution_dsl import EvolutionRule, SafetyGate

        gate = SafetyGate(max_coverage_drop_pct=2.0)
        rule = EvolutionRule(
            rule_id="r_test",
            target="test_param",
            current_value=1.0,
            proposed_value=2.0,
            justification="test",
        )
        result = gate.evaluate(
            rule,
            metrics={
                "test_pass_rate": 0.98,
                "coverage_pct": 80.0,
                "baseline_coverage_pct": 85.0,
            },
        )
        assert result.passed is False
        assert "coverage_drop" in result.rejection_reason

    def test_safety_gate_with_perf_regression(self) -> None:
        from maref.recursive.evolution_dsl import EvolutionRule, SafetyGate

        gate = SafetyGate(max_perf_regression_pct=5.0)
        rule = EvolutionRule(
            rule_id="r_test",
            target="test_param",
            current_value=1.0,
            proposed_value=2.0,
            justification="test",
        )
        result = gate.evaluate(
            rule,
            metrics={
                "test_pass_rate": 0.98,
                "coverage_pct": 85.0,
                "baseline_coverage_pct": 85.0,
                "perf_regression_pct": 8.0,
            },
        )
        assert result.passed is False
        assert "perf_regression" in result.rejection_reason
