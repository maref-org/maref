"""
Tests for Meta-Learning and Recursive Governance

Phase 10: Validates that meta-learning improves over time without
causing instability, and that recursive governance is safe.
"""

from __future__ import annotations

import time

from drift_guard.types import PipelineConfig
from maref_lite.meta_learning import DecisionOutcome, MetaLearner
from maref_lite.recursive_governance import (
    RecursiveGovernanceConfig,
    RecursiveGovernanceOverlay,
)
from maref_lite.state_machine import GovernanceState


class TestMetaLearner:
    """Test suite for meta-learning engine."""

    def test_initial_state(self) -> None:
        """Verify meta-learner initializes correctly."""
        learner = MetaLearner()
        stats = learner.get_stats()

        assert stats["state"]["learning_rate"] == 0.02
        assert stats["state"]["episode_count"] == 0
        assert stats["buffer_utilization"] == 0.0

    def test_record_decision(self) -> None:
        """Test recording decision outcomes."""
        learner = MetaLearner()

        outcome = DecisionOutcome(
            timestamp=0.0,
            decision_type="test",
            state_before="OBSERVE",
            state_after="ANALYZE",
            entropy_before=1,
            entropy_after=2,
            reward=0.5,
        )

        learner.record_decision(outcome)
        stats = learner.get_stats()

        assert stats["state"]["buffer_size"] == 1
        assert stats["avg_reward"] == 0.5

    def test_compute_reward_entropy_reduction(self) -> None:
        """Test reward computation for entropy reduction."""
        learner = MetaLearner()

        reward = learner.compute_reward(
            state_before=GovernanceState.ANALYZE,
            state_after=GovernanceState.OBSERVE,
            entropy_before=3,
            entropy_after=1,
            anomaly_resolved=False,
            time_in_state=2.0,
        )

        # Entropy reduced by 2, so reward should be positive
        assert reward > 0

    def test_compute_reward_anomaly_resolution(self) -> None:
        """Test reward for resolving anomaly."""
        learner = MetaLearner()

        reward = learner.compute_reward(
            state_before=GovernanceState.ACT,
            state_after=GovernanceState.VERIFY,
            entropy_before=4,
            entropy_after=3,
            anomaly_resolved=True,
            time_in_state=1.0,
        )

        # Should get strong positive reward for resolving anomaly
        assert reward > 1.0

    def test_compute_reward_halt_penalty(self) -> None:
        """Test strong penalty for halting."""
        learner = MetaLearner()

        reward = learner.compute_reward(
            state_before=GovernanceState.REPORT,
            state_after=GovernanceState.HALT,
            entropy_before=1,
            entropy_after=0,
            anomaly_resolved=False,
            time_in_state=5.0,
        )

        # Should get strong negative reward for halting
        assert reward < -4.0

    def test_optimize_policy_not_enough_data(self) -> None:
        """Test optimization returns None with insufficient data."""
        learner = MetaLearner()

        # Only 10 decisions, need 50
        for i in range(10):
            outcome = DecisionOutcome(
                timestamp=float(i),
                decision_type="test",
                state_before="OBSERVE",
                state_after="ANALYZE",
                entropy_before=1,
                entropy_after=2,
                reward=0.1,
            )
            learner.record_decision(outcome)

        result = learner.optimize_policy()
        assert result is None

    def test_optimize_policy_with_data(self) -> None:
        """Test optimization with sufficient data."""
        learner = MetaLearner()

        # Generate 100 decisions with positive rewards
        for i in range(100):
            outcome = DecisionOutcome(
                timestamp=float(i),
                decision_type="test",
                state_before="OBSERVE",
                state_after="STABILIZE",
                entropy_before=3,
                entropy_after=1,
                reward=1.0,
            )
            learner.record_decision(outcome)

        result = learner.optimize_policy()
        assert result is not None
        assert isinstance(result, PipelineConfig)

    def test_weight_clipping(self) -> None:
        """Test that weights are clipped to prevent runaway."""
        learner = MetaLearner()

        # Generate extreme rewards to push weights
        for i in range(100):
            outcome = DecisionOutcome(
                timestamp=float(i),
                decision_type="test",
                state_before="OBSERVE",
                state_after="STABILIZE",
                entropy_before=4,
                entropy_after=0,
                reward=100.0,  # Very large reward
            )
            learner.record_decision(outcome)

        learner.optimize_policy()

        # Weights should be clipped
        for weight in learner._state.policy_weights.values():
            assert abs(weight) <= learner._max_weight_magnitude

    def test_learning_rate_decay(self) -> None:
        """Test learning rate decays over time."""
        learner = MetaLearner(learning_rate=0.1)
        initial_lr = learner._state.learning_rate

        # Run multiple optimizations
        for _ in range(10):
            for i in range(100):
                outcome = DecisionOutcome(
                    timestamp=float(i),
                    decision_type="test",
                    state_before="OBSERVE",
                    state_after="STABILIZE",
                    entropy_before=2,
                    entropy_after=1,
                    reward=0.5,
                )
                learner.record_decision(outcome)
            learner.optimize_policy()

        # Learning rate should have decayed
        assert learner._state.learning_rate < initial_lr
        assert learner._state.learning_rate >= learner._min_learning_rate

    def test_stability_over_multiple_optimizations(self) -> None:
        """
        Critical test: Verify that repeated optimization does not
        cause policy weights to diverge.
        """
        learner = MetaLearner()

        policies = []
        for _episode in range(20):
            # Generate mixed rewards
            for i in range(100):
                reward = 0.5 if i % 2 == 0 else -0.3
                outcome = DecisionOutcome(
                    timestamp=float(i),
                    decision_type="test",
                    state_before="OBSERVE",
                    state_after="STABILIZE",
                    entropy_before=2,
                    entropy_after=1,
                    reward=reward,
                )
                learner.record_decision(outcome)

            policy = learner.optimize_policy()
            if policy:
                policies.append(policy.kl_warning)

        # Policies should not diverge wildly
        if len(policies) > 1:
            import statistics

            std_dev = statistics.stdev(policies)
            assert std_dev < 0.5, f"Policy diverged: std={std_dev}"


class TestRecursiveGovernance:
    """Test suite for recursive governance."""

    def test_initialization(self) -> None:
        """Test recursive overlay initializes correctly."""
        config = RecursiveGovernanceConfig(max_recursion_depth=2)
        overlay = RecursiveGovernanceOverlay(config=config)

        status = overlay.get_recursive_status()
        assert status["recursion_depth"] == 0
        assert not status["oscillation_detected"]

    def test_oscillation_detection(self) -> None:
        """Test oscillation detection."""
        config = RecursiveGovernanceConfig(max_oscillation_rate=5.0)
        overlay = RecursiveGovernanceOverlay(config=config)

        # Simulate rapid state changes
        for _ in range(10):
            overlay._state_changes.append(time.time())

        assert overlay._detect_oscillation()

    def test_no_oscillation_with_few_changes(self) -> None:
        """Test no oscillation with few changes."""
        config = RecursiveGovernanceConfig(max_oscillation_rate=10.0)
        overlay = RecursiveGovernanceOverlay(config=config)

        # Only 3 changes
        for _ in range(3):
            overlay._state_changes.append(time.time())

        assert not overlay._detect_oscillation()

    def test_recursion_depth_limit(self) -> None:
        """Test recursion depth is enforced."""
        config = RecursiveGovernanceConfig(max_recursion_depth=1)
        overlay = RecursiveGovernanceOverlay(config=config)
        overlay._recursion_depth = 1

        # Should not process observation due to depth limit
        overlay._on_self_observation(None)
        # No exception means test passed

    def test_meta_status_includes_primary(self) -> None:
        """Test recursive status includes primary overlay status."""
        overlay = RecursiveGovernanceOverlay()
        status = overlay.get_recursive_status()

        assert "primary_status" in status
        assert "meta_status" in status
        assert "meta_learning" in status
        assert "sandbox" in status

    def test_config_serialization(self) -> None:
        """Test config can be serialized."""
        config = RecursiveGovernanceConfig(
            max_recursion_depth=5,
            self_observation_cooldown=10.0,
            max_oscillation_rate=20.0,
        )

        data = config.to_dict()
        assert data["max_recursion_depth"] == 5
        assert data["self_observation_cooldown"] == 10.0
        assert data["max_oscillation_rate"] == 20.0
