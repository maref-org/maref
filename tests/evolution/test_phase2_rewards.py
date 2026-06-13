"""
Tests for MAREF Multi-Granularity Reward System (Phase 2).

Validates:
- RoleReward data class and serialization
- RoleRewardFn with built-in and custom functions
- MultiGranularityRewardAssembler reward aggregation
- DecisionOutcome backward compatibility with role_id
- ExperienceStore per-role querying
- End-to-end reward flow
"""

from __future__ import annotations

import pytest

from maref.evolution.agents import AgentRole
from maref.learning.replay import DecisionOutcome, ExperienceStore
from maref.learning.rewards import (
    BUILTIN_REWARD_FUNCTIONS,
    MultiGranularityRewardAssembler,
    RewardLevel,
    RoleReward,
    RoleRewardFn,
    RoundRewardSummary,
    create_role_reward_fn,
    detector_reward_fn,
    enforcer_reward_fn,
    evaluator_reward_fn,
    optimizer_reward_fn,
)


# ============================================================================
# RoleReward Tests
# ============================================================================

class TestRoleReward:
    def test_basic_creation(self) -> None:
        r = RoleReward(
            agent_id="detector_1",
            role=AgentRole.DETECTOR,
            role_reward=0.8,
        )
        assert r.agent_id == "detector_1"
        assert r.role == AgentRole.DETECTOR
        assert r.role_reward == 0.8
        assert r.turn_reward == 0.0
        assert r.cycle_reward == 0.0

    def test_weighted_reward_computation(self) -> None:
        r = RoleReward(
            agent_id="test",
            role=AgentRole.DETECTOR,
            role_reward=1.0,
            turn_reward=0.5,
            cycle_reward=0.2,
        )
        expected = 0.5 * 1.0 + 0.3 * 0.5 + 0.2 * 0.2
        assert abs(r.weighted_reward - expected) < 1e-10

    def test_to_dict(self) -> None:
        r = RoleReward(
            agent_id="d1",
            role=AgentRole.DETECTOR,
            role_reward=0.7,
            context={"fnr": 0.15},
        )
        d = r.to_dict()
        assert d["agent_id"] == "d1"
        assert d["role"] == "detector"
        assert d["role_reward"] == 0.7
        assert d["context"]["fnr"] == 0.15

    def test_from_dict_roundtrip(self) -> None:
        original = RoleReward(
            agent_id="roundtrip",
            role=AgentRole.OPTIMIZER,
            role_reward=0.9,
            turn_reward=0.6,
            cycle_reward=0.3,
            context={"improvement": 0.2},
        )
        restored = RoleReward.from_dict(original.to_dict())
        assert restored.agent_id == original.agent_id
        assert restored.role == original.role
        assert restored.role_reward == original.role_reward
        assert restored.turn_reward == original.turn_reward
        assert restored.cycle_reward == original.cycle_reward
        assert restored.context == original.context


# ============================================================================
# RoleRewardFn Tests
# ============================================================================

class TestRoleRewardFn:
    def test_custom_reward_function(self) -> None:
        def my_fn(snapshot: dict) -> float:
            return snapshot.get("metric", 0.0)

        fn = RoleRewardFn(
            agent_id="custom_agent",
            role=AgentRole.DETECTOR,
            fn=my_fn,
        )
        reward = fn.compute({"metric": 0.75})
        assert reward.agent_id == "custom_agent"
        assert reward.role == AgentRole.DETECTOR
        assert reward.role_reward == 0.75

    def test_reward_clipping(self) -> None:
        def unbounded_fn(snapshot: dict) -> float:
            return 999.0

        fn = RoleRewardFn(
            agent_id="unbounded",
            role=AgentRole.DETECTOR,
            fn=unbounded_fn,
        )
        reward = fn.compute({})
        assert reward.role_reward == 1.0

    def test_negative_reward_clipping(self) -> None:
        def negative_fn(snapshot: dict) -> float:
            return -999.0

        fn = RoleRewardFn(
            agent_id="negative",
            role=AgentRole.DETECTOR,
            fn=negative_fn,
        )
        reward = fn.compute({})
        assert reward.role_reward == -1.0

    def test_turn_reward_separate(self) -> None:
        def role_fn(s: dict) -> float:
            return 0.8

        def turn_fn(s: dict) -> float:
            return 0.5

        fn = RoleRewardFn(
            agent_id="turn_test",
            role=AgentRole.EVALUATOR,
            fn=role_fn,
            turn_fn=turn_fn,
        )
        reward = fn.compute({})
        assert reward.role_reward == 0.8
        assert reward.turn_reward == 0.5

    def test_turn_reward_defaults_to_role_reward(self) -> None:
        fn = RoleRewardFn(
            agent_id="default_turn",
            role=AgentRole.DETECTOR,
            fn=lambda s: 0.6,
        )
        reward = fn.compute({})
        assert reward.turn_reward == 0.6

    def test_weight_multiplier(self) -> None:
        fn = RoleRewardFn(
            agent_id="weighted",
            role=AgentRole.DETECTOR,
            fn=lambda s: 0.5,
            weight=2.0,
        )
        reward = fn.compute_with_weight({})
        assert abs(reward.role_reward - 1.0) < 1e-10

    def test_weight_property(self) -> None:
        fn = RoleRewardFn(
            agent_id="test",
            role=AgentRole.DETECTOR,
            fn=lambda s: 0.0,
            weight=1.5,
        )
        assert fn.weight == 1.5


# ============================================================================
# Built-in Reward Function Tests
# ============================================================================

class TestBuiltinRewardFunctions:
    def test_detector_reward_fn_low_error(self) -> None:
        snapshot = {"fnr": 0.05, "fpr": 0.03}
        reward = detector_reward_fn(snapshot)
        assert reward > 0.7

    def test_detector_reward_fn_high_error(self) -> None:
        snapshot = {"fnr": 0.8, "fpr": 0.9}
        reward = detector_reward_fn(snapshot)
        assert reward < -0.5

    def test_detector_reward_fn_detection_accuracy(self) -> None:
        snapshot = {"detection_accuracy": 0.9}
        reward = detector_reward_fn(snapshot)
        assert abs(reward - 0.8) < 1e-10

    def test_evaluator_reward_fn_low_error(self) -> None:
        snapshot = {"scoring_error": 0.1, "timeout": False}
        reward = evaluator_reward_fn(snapshot)
        assert reward > 0.5

    def test_evaluator_reward_fn_timeout_penalty(self) -> None:
        snapshot = {"scoring_error": 0.1, "timeout": True}
        reward = evaluator_reward_fn(snapshot)
        assert reward < 0.61

    def test_optimizer_reward_fn_improvement(self) -> None:
        snapshot = {
            "fnr_improvement": 0.2,
            "stability_score": 0.8,
            "oscillation": False,
        }
        reward = optimizer_reward_fn(snapshot)
        assert reward > 0.3

    def test_optimizer_reward_fn_oscillation_penalty(self) -> None:
        snapshot = {
            "fnr_improvement": 0.0,
            "stability_score": 0.5,
            "oscillation": True,
        }
        reward = optimizer_reward_fn(snapshot)
        assert reward < 0.0

    def test_enforcer_reward_fn_correct_trigger(self) -> None:
        snapshot = {
            "circuit_breaker_triggered": True,
            "anomaly_was_genuine": True,
            "system_stable": True,
        }
        reward = enforcer_reward_fn(snapshot)
        assert reward == 0.8

    def test_enforcer_reward_fn_false_trigger(self) -> None:
        snapshot = {
            "circuit_breaker_triggered": True,
            "anomaly_was_genuine": False,
            "system_stable": True,
        }
        reward = enforcer_reward_fn(snapshot)
        assert reward == -0.6

    def test_enforcer_reward_fn_missed_trigger(self) -> None:
        snapshot = {
            "circuit_breaker_triggered": False,
            "anomaly_was_genuine": True,
            "system_stable": False,
        }
        reward = enforcer_reward_fn(snapshot)
        assert reward == -0.4

    def test_builtin_registry_complete(self) -> None:
        assert AgentRole.DETECTOR in BUILTIN_REWARD_FUNCTIONS
        assert AgentRole.EVALUATOR in BUILTIN_REWARD_FUNCTIONS
        assert AgentRole.OPTIMIZER in BUILTIN_REWARD_FUNCTIONS
        assert AgentRole.ENFORCER in BUILTIN_REWARD_FUNCTIONS

    def test_create_role_reward_fn_builtin(self) -> None:
        fn = create_role_reward_fn("detector_1", AgentRole.DETECTOR)
        assert fn.agent_id == "detector_1"
        assert fn.role == AgentRole.DETECTOR

    def test_create_role_reward_fn_custom(self) -> None:
        fn = create_role_reward_fn(
            "custom",
            AgentRole.DETECTOR,
            custom_fn=lambda s: 0.99,
            weight=2.0,
        )
        reward = fn.compute({})
        assert reward.role_reward == 0.99


# ============================================================================
# MultiGranularityRewardAssembler Tests
# ============================================================================

class TestMultiGranularityRewardAssembler:
    def test_empty_assembler(self) -> None:
        assembler = MultiGranularityRewardAssembler()
        assert assembler.has_reward_fn("any") is False
        stats = assembler.get_stats()
        assert stats["total_rounds"] == 0

    def test_register_unregister_reward_fn(self) -> None:
        assembler = MultiGranularityRewardAssembler()
        fn = RoleRewardFn(
            "detector_1", AgentRole.DETECTOR, lambda s: 0.5,
        )
        assembler.register_reward_fn(fn)
        assert assembler.has_reward_fn("detector_1")

        removed = assembler.unregister_reward_fn("detector_1")
        assert removed is not None
        assert assembler.has_reward_fn("detector_1") is False

    def test_assemble_role_reward(self) -> None:
        assembler = MultiGranularityRewardAssembler()
        fn = RoleRewardFn(
            "detector_1",
            AgentRole.DETECTOR,
            lambda s: 1.0 - s.get("fnr", 1.0) * 2.0,
        )
        assembler.register_reward_fn(fn)

        reward = assembler.assemble_role_reward(
            "detector_1",
            {"fnr": 0.2, "fpr": 0.1},
        )
        assert reward.agent_id == "detector_1"
        assert reward.role == AgentRole.DETECTOR
        assert reward.role_reward == 0.6

    def test_assemble_role_reward_fallback(self) -> None:
        assembler = MultiGranularityRewardAssembler()
        reward = assembler.assemble_role_reward(
            "unknown",
            {"reward": 0.3},
        )
        assert reward.agent_id == "unknown"
        assert reward.role_reward == 0.3
        assert reward.context["fallback"] is True

    def test_assemble_round_rewards(self) -> None:
        assembler = MultiGranularityRewardAssembler()
        assembler.register_reward_fn(RoleRewardFn(
            "detector_1", AgentRole.DETECTOR,
            lambda s: 1.0 - s.get("fnr", 1.0) * 2.0,
        ))
        assembler.register_reward_fn(RoleRewardFn(
            "evaluator_1", AgentRole.EVALUATOR,
            lambda s: 1.0 - s.get("scoring_error", 1.0),
        ))

        summary = assembler.assemble_round_rewards(
            round_num=5,
            round_snapshot={"fnr": 0.15, "scoring_error": 0.2},
        )
        assert summary.round_num == 5
        assert len(summary.role_rewards) == 2
        assert summary.round_reward != 0.0

        for r in summary.role_rewards:
            if r.agent_id == "detector_1":
                assert abs(r.role_reward - 0.7) < 1e-10
            elif r.agent_id == "evaluator_1":
                assert abs(r.role_reward - 0.8) < 1e-10

    def test_assemble_round_rewards_specific_agents(self) -> None:
        assembler = MultiGranularityRewardAssembler()
        assembler.register_reward_fn(RoleRewardFn(
            "a1", AgentRole.DETECTOR, lambda s: 0.5,
        ))
        assembler.register_reward_fn(RoleRewardFn(
            "a2", AgentRole.EVALUATOR, lambda s: 0.7,
        ))

        summary = assembler.assemble_round_rewards(
            round_num=1,
            round_snapshot={},
            agent_ids=["a1"],
        )
        assert len(summary.role_rewards) == 1
        assert summary.role_rewards[0].agent_id == "a1"

    def test_assemble_cycle_reward_converged(self) -> None:
        assembler = MultiGranularityRewardAssembler()
        cycle_metrics = {
            "fnr_series": [0.5, 0.4, 0.3, 0.2, 0.1],
            "fpr_series": [0.3, 0.25, 0.2, 0.15, 0.1],
            "converged": True,
        }
        reward = assembler.assemble_cycle_reward(cycle_metrics)
        assert reward > 0.5

    def test_assemble_cycle_reward_not_converged(self) -> None:
        assembler = MultiGranularityRewardAssembler()
        cycle_metrics = {
            "fnr_series": [0.5, 0.6, 0.4, 0.7, 0.5],
            "fpr_series": [0.3, 0.4, 0.2, 0.5, 0.3],
            "converged": False,
        }
        reward = assembler.assemble_cycle_reward(cycle_metrics)
        assert reward < 0.5

    def test_assemble_cycle_reward_empty(self) -> None:
        assembler = MultiGranularityRewardAssembler()
        reward = assembler.assemble_cycle_reward({})
        assert reward == 0.0

    def test_apply_cycle_rewards(self) -> None:
        assembler = MultiGranularityRewardAssembler()
        assembler.register_reward_fn(RoleRewardFn(
            "detector_1", AgentRole.DETECTOR, lambda s: 0.5,
        ))

        assembler.assemble_round_rewards(
            round_num=1,
            round_snapshot={"fnr": 0.2},
        )

        cycle_metrics = {
            "fnr_series": [0.5, 0.3, 0.1],
            "fpr_series": [0.3, 0.2, 0.1],
            "converged": True,
        }
        updated = assembler.apply_cycle_rewards(cycle_metrics)

        assert len(updated) == 1
        assert updated[0].cycle_reward > 0.0

    def test_round_history(self) -> None:
        assembler = MultiGranularityRewardAssembler()
        assembler.register_reward_fn(RoleRewardFn(
            "a1", AgentRole.DETECTOR, lambda s: 0.5,
        ))

        for i in range(5):
            assembler.assemble_round_rewards(
                round_num=i + 1,
                round_snapshot={"fnr": 0.1 * i},
            )

        all_history = assembler.get_round_history()
        assert len(all_history) == 5

        last_2 = assembler.get_round_history(last_n=2)
        assert len(last_2) == 2
        assert last_2[-1].round_num == 5

    def test_cycle_history(self) -> None:
        assembler = MultiGranularityRewardAssembler()
        for i in range(3):
            assembler.apply_cycle_rewards({
                "fnr_series": [0.5 - 0.1 * j for j in range(5)],
                "converged": i == 2,
            })
        history = assembler.get_cycle_history()
        assert len(history) == 3

    def test_stats(self) -> None:
        assembler = MultiGranularityRewardAssembler()
        assembler.register_reward_fn(RoleRewardFn(
            "a1", AgentRole.DETECTOR, lambda s: 0.5,
        ))

        assembler.assemble_round_rewards(round_num=1, round_snapshot={})

        stats = assembler.get_stats()
        assert stats["total_rounds"] == 1
        assert stats["registered_fns"] == 1
        assert stats["latest_round_reward"] != 0.0

    def test_stats_empty(self) -> None:
        assembler = MultiGranularityRewardAssembler()
        stats = assembler.get_stats()
        assert stats["total_rounds"] == 0
        assert stats["avg_round_reward"] == 0.0

    def test_weighted_aggregation(self) -> None:
        assembler = MultiGranularityRewardAssembler()
        assembler.register_reward_fn(RoleRewardFn(
            "high_weight", AgentRole.DETECTOR, lambda s: 1.0, weight=3.0,
        ))
        assembler.register_reward_fn(RoleRewardFn(
            "low_weight", AgentRole.DETECTOR, lambda s: 0.0, weight=1.0,
        ))

        summary = assembler.assemble_round_rewards(
            round_num=1,
            round_snapshot={},
        )
        high_wr = 0.5 * 1.0 + 0.3 * 1.0 + 0.2 * 0.0
        low_wr = 0.0
        expected = (high_wr + low_wr) / (3.0 + 1.0)
        assert abs(summary.round_reward - expected) < 1e-10

    def test_round_reward_summary_properties(self) -> None:
        rewards = [
            RoleReward("a1", AgentRole.DETECTOR, 0.9),
            RoleReward("a2", AgentRole.DETECTOR, 0.3),
            RoleReward("a3", AgentRole.DETECTOR, 0.6),
        ]
        summary = RoundRewardSummary(round_num=1, role_rewards=rewards)
        assert summary.avg_role_reward == 0.6
        assert summary.max_role_reward == 0.9
        assert summary.min_role_reward == 0.3

    def test_round_reward_summary_empty(self) -> None:
        summary = RoundRewardSummary(round_num=1)
        assert summary.avg_role_reward == 0.0
        assert summary.max_role_reward == 0.0
        assert summary.min_role_reward == 0.0

    def test_to_dict_round_reward_summary(self) -> None:
        rewards = [
            RoleReward("a1", AgentRole.DETECTOR, 0.8, context={"fnr": 0.1}),
        ]
        summary = RoundRewardSummary(
            round_num=5,
            role_rewards=rewards,
            round_reward=0.8,
            cycle_reward=0.6,
        )
        d = summary.to_dict()
        assert d["round_num"] == 5
        assert len(d["role_rewards"]) == 1
        assert d["avg_role_reward"] == 0.8


# ============================================================================
# DecisionOutcome Backward Compatibility Tests
# ============================================================================

class TestDecisionOutcomeBackwardCompat:
    def test_legacy_outcome_without_role_id(self) -> None:
        outcome = DecisionOutcome(
            timestamp=1000.0,
            decision_type="test",
            state_before="active",
            state_after="active",
            entropy_before=2,
            entropy_after=1,
            reward=0.8,
        )
        assert outcome.role_id is None

    def test_outcome_with_role_id(self) -> None:
        outcome = DecisionOutcome(
            timestamp=1000.0,
            decision_type="test",
            state_before="active",
            state_after="active",
            entropy_before=2,
            entropy_after=1,
            reward=0.8,
            role_id="detector_1",
        )
        assert outcome.role_id == "detector_1"

    def test_to_dict_preserves_role_id(self) -> None:
        outcome = DecisionOutcome(
            timestamp=1000.0,
            decision_type="test",
            state_before="active",
            state_after="active",
            entropy_before=2,
            entropy_after=1,
            reward=0.8,
            role_id="evaluator_1",
        )
        d = outcome.to_dict()
        assert d["role_id"] == "evaluator_1"

    def test_from_dict_without_role_id(self) -> None:
        d = {
            "timestamp": 1000.0,
            "decision_type": "test",
            "state_before": "active",
            "state_after": "active",
            "entropy_before": 2,
            "entropy_after": 1,
            "reward": 0.8,
            "context": "{}",
        }
        outcome = DecisionOutcome.from_dict(d)
        assert outcome.role_id is None

    def test_from_dict_with_role_id(self) -> None:
        d = {
            "timestamp": 1000.0,
            "decision_type": "test",
            "state_before": "active",
            "state_after": "active",
            "entropy_before": 2,
            "entropy_after": 1,
            "reward": 0.8,
            "context": "{}",
            "role_id": "detector_1",
        }
        outcome = DecisionOutcome.from_dict(d)
        assert outcome.role_id == "detector_1"

    def test_from_row_backward_compat(self) -> None:
        old_row = (1, 1000.0, "test", "active", "active", 2, 1, 0.8, "{}")
        outcome = DecisionOutcome.from_row(old_row)
        assert outcome.role_id is None
        assert outcome.reward == 0.8

    def test_from_row_with_role_id(self) -> None:
        new_row = (1, 1000.0, "test", "active", "active", 2, 1, 0.8, "{}", "detector_1")
        outcome = DecisionOutcome.from_row(new_row)
        assert outcome.role_id == "detector_1"


# ============================================================================
# ExperienceStore Per-Role Querying Tests
# ============================================================================

class TestExperienceStorePerRole:
    def test_insert_with_role_id(self) -> None:
        store = ExperienceStore(":memory:")
        outcome = DecisionOutcome(
            timestamp=1000.0,
            decision_type="test",
            state_before="active",
            state_after="active",
            entropy_before=2,
            entropy_after=1,
            reward=0.8,
            role_id="detector_1",
        )
        store.insert(outcome)
        assert store.count() == 1

    def test_get_by_role(self) -> None:
        store = ExperienceStore(":memory:")
        store.insert(DecisionOutcome(
            timestamp=1000.0, decision_type="test",
            state_before="active", state_after="active",
            entropy_before=2, entropy_after=1,
            reward=0.8, role_id="detector_1",
        ))
        store.insert(DecisionOutcome(
            timestamp=1001.0, decision_type="test",
            state_before="active", state_after="active",
            entropy_before=2, entropy_after=1,
            reward=0.5, role_id="evaluator_1",
        ))
        store.insert(DecisionOutcome(
            timestamp=1002.0, decision_type="test",
            state_before="active", state_after="active",
            entropy_before=2, entropy_after=1,
            reward=0.9, role_id="detector_1",
        ))

        detector_outcomes = store.get_by_role("detector_1")
        assert len(detector_outcomes) == 2

        evaluator_outcomes = store.get_by_role("evaluator_1")
        assert len(evaluator_outcomes) == 1

    def test_get_role_stats(self) -> None:
        store = ExperienceStore(":memory:")
        store.insert(DecisionOutcome(
            timestamp=1000.0, decision_type="test",
            state_before="active", state_after="active",
            entropy_before=2, entropy_after=1,
            reward=0.6, role_id="detector_1",
        ))
        store.insert(DecisionOutcome(
            timestamp=1001.0, decision_type="test",
            state_before="active", state_after="active",
            entropy_before=2, entropy_after=1,
            reward=0.8, role_id="detector_1",
        ))

        stats = store.get_role_stats("detector_1")
        assert stats["total_samples"] == 2
        assert abs(stats["avg_reward"] - 0.7) < 1e-10

    def test_get_role_stats_empty(self) -> None:
        store = ExperienceStore(":memory:")
        stats = store.get_role_stats("nonexistent")
        assert stats["total_samples"] == 0

    def test_get_role_ids(self) -> None:
        store = ExperienceStore(":memory:")
        store.insert(DecisionOutcome(
            timestamp=1000.0, decision_type="test",
            state_before="active", state_after="active",
            entropy_before=2, entropy_after=1,
            reward=0.8, role_id="detector_1",
        ))
        store.insert(DecisionOutcome(
            timestamp=1001.0, decision_type="test",
            state_before="active", state_after="active",
            entropy_before=2, entropy_after=1,
            reward=0.5, role_id="evaluator_1",
        ))
        store.insert(DecisionOutcome(
            timestamp=1002.0, decision_type="test",
            state_before="active", state_after="active",
            entropy_before=2, entropy_after=1,
            reward=0.9,
        ))

        role_ids = store.get_role_ids()
        assert set(role_ids) == {"detector_1", "evaluator_1"}

    def test_legacy_outcomes_still_work(self) -> None:
        """Ensure outcomes without role_id still insert and retrieve correctly."""
        store = ExperienceStore(":memory:")
        outcome = DecisionOutcome(
            timestamp=1000.0,
            decision_type="test",
            state_before="active",
            state_after="active",
            entropy_before=2,
            entropy_after=1,
            reward=0.8,
        )
        store.insert(outcome)
        retrieved = store.get_recent(1)
        assert len(retrieved) == 1
        assert retrieved[0].reward == 0.8
        assert retrieved[0].role_id is None


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    def test_full_reward_flow(self) -> None:
        """Complete flow: register agents → compute rewards → store → query."""
        assembler = MultiGranularityRewardAssembler()
        assembler.register_reward_fn(RoleRewardFn(
            "detector_1", AgentRole.DETECTOR,
            lambda s: 1.0 - s.get("fnr", 1.0) * 2.0,
        ))
        assembler.register_reward_fn(RoleRewardFn(
            "evaluator_1", AgentRole.EVALUATOR,
            lambda s: 1.0 - s.get("scoring_error", 1.0),
        ))

        store = ExperienceStore(":memory:")

        for round_num in range(1, 6):
            fnr = 0.5 - round_num * 0.08
            scoring_error = 0.4 - round_num * 0.06

            snapshot = {"fnr": fnr, "scoring_error": scoring_error}
            summary = assembler.assemble_round_rewards(round_num, snapshot)

            for role_reward in summary.role_rewards:
                outcome = DecisionOutcome(
                    timestamp=float(round_num),
                    decision_type="evolution_round",
                    state_before="active",
                    state_after="active",
                    entropy_before=2,
                    entropy_after=1,
                    reward=role_reward.role_reward,
                    role_id=role_reward.agent_id,
                )
                store.insert(outcome)

        detector_outcomes = store.get_by_role("detector_1")
        assert len(detector_outcomes) == 5

        detector_stats = store.get_role_stats("detector_1")
        assert detector_stats["total_samples"] == 5
        assert detector_stats["avg_reward"] > 0.0

        evaluator_stats = store.get_role_stats("evaluator_1")
        assert evaluator_stats["total_samples"] == 5

    def test_cycle_reward_application(self) -> None:
        assembler = MultiGranularityRewardAssembler()
        assembler.register_reward_fn(RoleRewardFn(
            "detector_1", AgentRole.DETECTOR, lambda s: 0.5,
        ))

        for i in range(10):
            assembler.assemble_round_rewards(
                round_num=i + 1,
                round_snapshot={"fnr": 0.5 - i * 0.04},
            )

        cycle_reward = assembler.apply_cycle_rewards({
            "fnr_series": [0.5 - i * 0.04 for i in range(10)],
            "fpr_series": [0.3 - i * 0.02 for i in range(10)],
            "converged": True,
        })
        assert len(cycle_reward) == 1

        stats = assembler.get_stats()
        assert stats["total_rounds"] == 10
        assert stats["total_cycles"] == 1
