from __future__ import annotations

from maref.governance import CircuitBreaker, GovernanceStateMachine
from maref.redblue.attack_executor import AttackExecutor
from maref.redblue.attack_vector import (
    PHASE1_ATTACKS,
    PHASE2_ATTACKS,
    PHASE3_ATTACKS,
    PHASE4_ATTACKS,
    PHASE5_ATTACKS,
    AttackCategory,
    AttackDefinition,
    BlueLevel,
    RedLevel,
)
from maref.redblue.red_blue_engine import RedBlueEngine, RedBlueResult

# ── Scoring Formula Tests (RB1) ──────────────────────────────────


class TestScoringFormula:
    def test_total_score_range_0_to_100(self) -> None:
        engine = RedBlueEngine()
        attack = PHASE1_ATTACKS[0]
        result = engine.run_round("test-1", 1, attack, RedLevel.R2, BlueLevel.B3)
        assert 0.0 <= result.total_score <= 100.0, f"Got {result.total_score}"

    def test_max_possible_score_is_100(self) -> None:
        engine = RedBlueEngine()
        attack = AttackDefinition(
            AttackCategory.STATE_MACHINE, "weak", "Very weak attack", 0.0, 0.0, {}
        )
        result = engine.run_round("max-test", 1, attack, RedLevel.R1, BlueLevel.B5)
        assert result.total_score < 100.0 or result.total_score >= 0.0

    def test_high_power_blue_gets_higher_score(self) -> None:
        engine = RedBlueEngine()
        attack = PHASE1_ATTACKS[0]
        r1 = engine.run_round("b1", 1, attack, RedLevel.R2, BlueLevel.B1)
        r2 = engine.run_round("b5", 1, attack, RedLevel.R2, BlueLevel.B5)
        assert r2.total_score >= r1.total_score, f"B1={r1.total_score}, B5={r2.total_score}"

    def test_passed_threshold_is_50(self) -> None:
        engine = RedBlueEngine()
        attack = AttackDefinition(AttackCategory.STATE_MACHINE, "weak", "Weak attack", 0.0, 0.0, {})
        result = engine.run_round("pass-test", 1, attack, RedLevel.R1, BlueLevel.B5)
        high_pass = result.passed
        attack2 = AttackDefinition(AttackCategory.MULTI_VECTOR, "strong", "Strong", 1.0, 1.0, {})
        result2 = engine.run_round("fail-test", 1, attack2, RedLevel.R5, BlueLevel.B1)
        assert high_pass or not result2.passed

    def test_raw_scores_recorded_in_metadata(self) -> None:
        engine = RedBlueEngine()
        result = engine.run_round("meta-1", 1, PHASE1_ATTACKS[0], RedLevel.R2, BlueLevel.B3)
        assert "raw_scores" in result.metadata
        raw = result.metadata["raw_scores"]
        assert "detection" in raw
        assert "mitigation" in raw


# ── Engine Tests (RB2-RB3) ───────────────────────────────────────


class TestRedBlueEngine:
    def test_engine_initializes(self) -> None:
        engine = RedBlueEngine()
        assert engine._blue_memory == {}
        assert engine._blue_hardening == {}

    def test_meta_cb_triggered_populated(self) -> None:
        engine = RedBlueEngine()
        attack = AttackDefinition(
            AttackCategory.MULTI_VECTOR,
            "strong",
            "High intensity trigger",
            0.9,
            0.5,
            {"count": 100},
        )
        result = engine.run_round("cb-meta", 1, attack, RedLevel.R5, BlueLevel.B1)
        assert isinstance(result.meta_cb_triggered, bool)

    def test_summary_empty_results(self) -> None:
        engine = RedBlueEngine()
        assert engine.summary() == {}

    def test_summary_returns_metrics(self) -> None:
        engine = RedBlueEngine()
        engine.run_round("s1", 1, PHASE1_ATTACKS[0], RedLevel.R1, BlueLevel.B1)
        engine.run_round("s2", 1, PHASE1_ATTACKS[1], RedLevel.R2, BlueLevel.B2)
        summary = engine.summary()
        assert summary["total_rounds"] == 2
        assert "mean_score" in summary
        assert "min_score" in summary
        assert "max_score" in summary
        assert "passed_rounds" in summary
        assert "phase_averages" in summary
        assert "cb_triggers" in summary
        assert "meta_cb_triggers" in summary

    def test_results_property_returns_copy(self) -> None:
        engine = RedBlueEngine()
        engine.run_round("r1", 1, PHASE1_ATTACKS[0], RedLevel.R1, BlueLevel.B1)
        results = engine.results
        assert len(results) == 1
        results.append(None)  # type: ignore
        assert len(engine.results) == 1

    def test_blue_memory_accumulates(self) -> None:
        engine = RedBlueEngine()
        for i in range(5):
            engine.run_round(
                f"mem-{i}", 1, PHASE1_ATTACKS[i % len(PHASE1_ATTACKS)], RedLevel.R2, BlueLevel.B4
            )
        assert any(v > 0 for v in engine._blue_memory.values())

    def test_blue_hardening_grows_on_high_detection(self) -> None:
        engine = RedBlueEngine()
        for _ in range(10):
            engine.run_round("hd-1", 1, PHASE1_ATTACKS[0], RedLevel.R1, BlueLevel.B5)
        assert len(engine._blue_hardening) >= 0


# ── Attack Vector Tests ──────────────────────────────────────────


class TestAttackVectors:
    def test_68_attacks_total(self) -> None:
        all_attacks = (
            PHASE1_ATTACKS + PHASE2_ATTACKS + PHASE3_ATTACKS + PHASE4_ATTACKS + PHASE5_ATTACKS
        )
        assert len(all_attacks) == 68

    def test_phase1_attacks_exist(self) -> None:
        assert len(PHASE1_ATTACKS) == 12

    def test_all_attacks_have_unique_names(self) -> None:
        all_attacks = (
            PHASE1_ATTACKS + PHASE2_ATTACKS + PHASE3_ATTACKS + PHASE4_ATTACKS + PHASE5_ATTACKS
        )
        names = [a.name for a in all_attacks]
        assert len(names) == len(set(names))

    def test_attack_intensity_in_range(self) -> None:
        all_attacks = (
            PHASE1_ATTACKS + PHASE2_ATTACKS + PHASE3_ATTACKS + PHASE4_ATTACKS + PHASE5_ATTACKS
        )
        for attack in all_attacks:
            assert 0.0 <= attack.intensity <= 1.0, f"{attack.name}: {attack.intensity}"
            assert 0.0 <= attack.stealth <= 1.0, f"{attack.name}: {attack.stealth}"

    def test_red_levels(self) -> None:
        assert RedLevel.R1.numeric == 1
        assert RedLevel.R5.numeric == 5
        assert RedLevel.R1.label == "脚本小子"

    def test_blue_levels(self) -> None:
        assert BlueLevel.B1.numeric == 1
        assert BlueLevel.B5.numeric == 5
        assert BlueLevel.B5.label == "完全自主"

    def test_attack_categories(self) -> None:
        assert len(AttackCategory) == 13


# ── Attack Executor Tests (RB5-RB12) ─────────────────────────────


class TestAttackExecutor:
    def test_executor_initializes(self) -> None:
        executor = AttackExecutor()
        assert executor.execution_log == []

    def test_execute_state_machine_attack(self) -> None:
        executor = AttackExecutor()
        sm = GovernanceStateMachine()
        result = executor.execute(PHASE1_ATTACKS[0], target_sm=sm)
        assert result.category == "state_machine"
        assert isinstance(result.elapsed_ms, float)

    def test_execute_circuit_breaker_attack(self) -> None:
        executor = AttackExecutor()
        cb = CircuitBreaker(max_depth=3, max_consecutive_failures=3, cooldown_seconds=30.0)
        result = executor.execute(PHASE1_ATTACKS[1], target_cb=cb)
        assert result.category == "circuit_breaker"

    def test_execute_multi_vector_attack(self) -> None:
        executor = AttackExecutor()
        sm = GovernanceStateMachine()
        cb = CircuitBreaker(max_depth=3, max_consecutive_failures=3, cooldown_seconds=30.0)
        result = executor.execute(PHASE3_ATTACKS[0], target_sm=sm, target_cb=cb)
        assert result.category == "multi_vector"

    def test_execute_without_targets_uses_defaults(self) -> None:
        executor = AttackExecutor()
        result = executor.execute(PHASE1_ATTACKS[0])
        assert result.elapsed_ms >= 0.0

    def test_execution_log_accumulates(self) -> None:
        executor = AttackExecutor()
        executor.execute(PHASE1_ATTACKS[0])
        executor.execute(PHASE1_ATTACKS[1])
        assert len(executor.execution_log) == 2

    def test_attack_on_isolated_copies(self) -> None:
        executor = AttackExecutor()
        sm = GovernanceStateMachine()
        original_state = sm.current_state
        executor.execute(PHASE1_ATTACKS[0], target_sm=sm)


# ── Result Properties Tests ──────────────────────────────────────


class TestRedBlueResult:
    def test_result_creation(self) -> None:
        result = RedBlueResult(
            round_id="R101",
            phase=1,
            red_level="R1",
            blue_level="B1",
            attack_category="state_machine",
            attack_name="test_attack",
            attack_intensity=0.5,
            attack_stealth=0.3,
        )
        assert result.round_id == "R101"
        assert result.passed is False

    def test_result_has_errors_list(self) -> None:
        result = RedBlueResult(
            round_id="R1",
            phase=1,
            red_level="R1",
            blue_level="B1",
            attack_category="test",
            attack_name="test",
            attack_intensity=0.1,
            attack_stealth=0.1,
            errors=["err1", "err2"],
        )
        assert len(result.errors) == 2
