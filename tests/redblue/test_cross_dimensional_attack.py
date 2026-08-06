"""Tests for Phase 6 cross-dimensional attacks."""

from __future__ import annotations

import pytest

from maref.redblue.attack_executor import AttackExecutor
from maref.redblue.attack_vector import (
    ALL_ATTACKS,
    PHASE6_ATTACKS,
    AttackCategory,
    AttackDefinition,
)


class TestPhase6AttackDefinitions:
    """Phase 6 attack definitions."""

    def test_phase6_has_six_attacks(self) -> None:
        assert len(PHASE6_ATTACKS) == 6

    def test_cross_dimensional_category_exists(self) -> None:
        assert AttackCategory.CROSS_DIMENSIONAL is not None
        assert AttackCategory.CROSS_DIMENSIONAL.value[0] == "cross_dimensional"
        assert AttackCategory.CROSS_DIMENSIONAL.value[1] == "跨维度操纵攻击"

    def test_all_phase6_attacks_have_correct_category(self) -> None:
        for attack in PHASE6_ATTACKS:
            assert attack.category == AttackCategory.CROSS_DIMENSIONAL

    def test_all_phase6_attacks_have_required_fields(self) -> None:
        for attack in PHASE6_ATTACKS:
            assert isinstance(attack.name, str)
            assert len(attack.name) > 0
            assert isinstance(attack.description, str)
            assert len(attack.description) > 0
            assert 0.0 <= attack.intensity <= 1.0
            assert 0.0 <= attack.stealth <= 1.0
            assert isinstance(attack.params, dict)

    def test_phase6_attack_names(self) -> None:
        names = {a.name for a in PHASE6_ATTACKS}
        expected = {
            "dimension_weight_manipulation",
            "negative_correlation_exploit",
            "dimension_hijack",
            "dimensional_blindness",
            "cross_impact_flood",
            "pareto_front_poison",
        }
        assert names == expected

    def test_all_attacks_includes_phase6(self) -> None:
        phase6_names = {a.name for a in PHASE6_ATTACKS}
        all_names = {a.name for a in ALL_ATTACKS}
        assert phase6_names.issubset(all_names)

    def test_phase6_params_have_method_key(self) -> None:
        methods = {
            "skew_weights",
            "inject_negative_correlation",
            "redirect_to_weak_dim",
            "spoof_dimensions",
            "flood_events",
            "poison_frontier",
        }
        for attack in PHASE6_ATTACKS:
            assert "method" in attack.params
            assert attack.params["method"] in methods

    def test_phase6_params_have_target_key(self) -> None:
        for attack in PHASE6_ATTACKS:
            assert "target" in attack.params


class TestCrossDimensionalExecutor:
    """AttackExecutor cross-dimensional dispatch."""

    def test_executor_can_run_cross_dimensional(self) -> None:
        executor = AttackExecutor()
        attack = PHASE6_ATTACKS[0]
        result = executor.execute(attack)
        assert result is not None
        assert result.attack_name == attack.name
        assert result.category == "cross_dimensional"

    def test_attack_returns_correct_result_type(self) -> None:
        executor = AttackExecutor()
        for attack in PHASE6_ATTACKS:
            result = executor.execute(attack)
            assert result.success is True
            assert isinstance(result.penetrated, bool)
            assert isinstance(result.detected_by, list)
            assert isinstance(result.errors, list)
            assert result.elapsed_ms >= 0

    def test_attack_skew_weights(self) -> None:
        executor = AttackExecutor()
        attack = next(
            a for a in PHASE6_ATTACKS if a.params.get("method") == "skew_weights"
        )
        result = executor.execute(attack)
        assert result.success is True
        assert result.penetrated is True

    def test_attack_flood_events(self) -> None:
        executor = AttackExecutor()
        attack = next(
            a for a in PHASE6_ATTACKS if a.params.get("method") == "flood_events"
        )
        result = executor.execute(attack)
        assert result.success is True
        assert result.penetrated is True
        assert "cross_impact_saturation" in result.detected_by

    def test_attack_intensity_in_range(self) -> None:
        for attack in PHASE6_ATTACKS:
            assert 0.0 <= attack.intensity <= 1.0, f"{attack.name} intensity out of range"
            assert 0.0 <= attack.stealth <= 1.0, f"{attack.name} stealth out of range"

    def test_attack_stealth_range(self) -> None:
        stealths = [a.stealth for a in PHASE6_ATTACKS]
        assert min(stealths) >= 0.4
        assert max(stealths) <= 0.8

    def test_execution_log_records_phase6(self) -> None:
        executor = AttackExecutor()
        for attack in PHASE6_ATTACKS:
            executor.execute(attack)
        log = executor.execution_log
        phase6_names = {a.name for a in PHASE6_ATTACKS}
        logged_names = {r.attack_name for r in log}
        assert phase6_names.issubset(logged_names)
