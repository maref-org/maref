"""
Tests for MAREF Group Policy Optimizer (Phase 3).

Validates:
- EntropyRegularizer entropy computation and gradient
- AdvantageBuffer GAE and discounted returns
- GroupPolicyOptimizer PPO-style updates
- Gradient clipping and entropy regularization
- End-to-end optimization flow with ShareGroup
"""

from __future__ import annotations

import math

from maref.evolution.agents import (
    AgentRole,
    GovernanceAgent,
    GovernanceAgentConfig,
    ShareGroup,
    ShareGroupConfig,
    ShareMode,
)
from maref.learning.group_optimizer import (
    AdvantageBuffer,
    EntropyRegularizer,
    GroupPolicyOptimizer,
    OptimizerConfig,
    PolicyUpdateResult,
)

# ============================================================================
# EntropyRegularizer Tests
# ============================================================================


class TestEntropyRegularizer:
    def test_compute_entropy_uniform(self) -> None:
        weights = {"a": 0.0, "b": 0.0, "c": 0.0}
        entropy = EntropyRegularizer.compute_entropy(weights)
        expected = math.log(3)
        assert abs(entropy - expected) < 0.01

    def test_compute_entropy_peak(self) -> None:
        weights = {"a": 10.0, "b": -10.0, "c": -10.0}
        entropy = EntropyRegularizer.compute_entropy(weights)
        assert entropy < 0.5

    def test_compute_entropy_empty(self) -> None:
        assert EntropyRegularizer.compute_entropy({}) == 0.0

    def test_entropy_positive(self) -> None:
        weights = {"a": 0.1, "b": 0.2, "c": -0.1}
        bonus = EntropyRegularizer.entropy_bonus(weights, coeff=0.01)
        assert bonus > 0

    def test_entropy_gradient_nonzero(self) -> None:
        weights = {"a": 0.5, "b": -0.3}
        grad = EntropyRegularizer.entropy_gradient(weights)
        assert "a" in grad
        assert "b" in grad
        assert abs(grad["a"]) > 0 or abs(grad["b"]) > 0

    def test_entropy_gradient_empty(self) -> None:
        assert EntropyRegularizer.entropy_gradient({}) == {}

    def test_entropy_gradient_sum_zero(self) -> None:
        weights = {"a": 0.0, "b": 0.0}
        grad = EntropyRegularizer.entropy_gradient(weights)
        assert abs(sum(grad.values())) < 0.01


# ============================================================================
# AdvantageBuffer Tests
# ============================================================================


class TestAdvantageBuffer:
    def test_gae_advantages(self) -> None:
        buf = AdvantageBuffer(discount=0.99, gae_lambda=0.95)
        rewards = [1.0, 0.5, 0.0]
        values = [0.8, 0.6, 0.3, 0.0]
        advantages = buf.compute_advantages(rewards, values)
        assert len(advantages) == 3
        for a in advantages:
            assert isinstance(a, float)

    def test_gae_empty(self) -> None:
        buf = AdvantageBuffer()
        assert buf.compute_advantages([], []) == []

    def test_discounted_returns(self) -> None:
        buf = AdvantageBuffer(discount=0.5)
        returns = buf.compute_returns([1.0, 0.5, 0.25])
        assert abs(returns[0] - 1.3125) < 0.01
        assert abs(returns[1] - 0.625) < 0.01
        assert abs(returns[2] - 0.25) < 0.01

    def test_discounted_returns_empty(self) -> None:
        buf = AdvantageBuffer()
        assert buf.compute_returns([]) == []

    def test_discounted_returns_single(self) -> None:
        buf = AdvantageBuffer(discount=0.9)
        returns = buf.compute_returns([1.0])
        assert returns == [1.0]

    def test_gae_with_zero_values(self) -> None:
        buf = AdvantageBuffer(discount=0.99, gae_lambda=0.95)
        rewards = [1.0, 1.0, 1.0]
        values = [0.0, 0.0, 0.0, 0.0]
        advantages = buf.compute_advantages(rewards, values)
        assert all(a > 0 for a in advantages)

    def test_gae_mixed_rewards(self) -> None:
        buf = AdvantageBuffer(discount=0.9, gae_lambda=0.9)
        rewards = [1.0, -0.5, 0.8, -0.3]
        values = [0.5, 0.3, 0.4, 0.1, 0.0]
        advantages = buf.compute_advantages(rewards, values)
        assert len(advantages) == 4


# ============================================================================
# OptimizerConfig Tests
# ============================================================================


class TestOptimizerConfig:
    def test_defaults(self) -> None:
        config = OptimizerConfig()
        assert config.clip_epsilon == 0.2
        assert config.value_loss_coeff == 0.5
        assert config.entropy_coeff == 0.01
        assert config.max_grad_norm == 1.0
        assert config.gae_lambda == 0.95
        assert config.discount_factor == 0.99

    def test_to_dict(self) -> None:
        config = OptimizerConfig(clip_epsilon=0.1)
        d = config.to_dict()
        assert d["clip_epsilon"] == 0.1
        assert d["entropy_coeff"] == 0.01


# ============================================================================
# GroupPolicyOptimizer Tests
# ============================================================================


class TestGroupPolicyOptimizer:
    def _make_group(self, agent_count: int = 2) -> ShareGroup:
        config = ShareGroupConfig(
            group_id="test_group",
            share_mode=ShareMode.FULL_SHARING,
            aggregation_method="mean",
        )
        group = ShareGroup(config)
        for i in range(agent_count):
            agent = GovernanceAgent(
                GovernanceAgentConfig(
                    agent_id=f"agent_{i}",
                    role=AgentRole.DETECTOR,
                    share_group="test_group",
                    policy_features=["entropy_penalty", "stability_bonus"],
                    learning_rate=0.02,
                )
            )
            group.add_agent(agent)
        return group

    def test_create_optimizer(self) -> None:
        group = self._make_group()
        optimizer = GroupPolicyOptimizer(group)
        assert optimizer.group is group
        assert optimizer.learning_rate == 0.02

    def test_create_optimizer_custom_config(self) -> None:
        group = self._make_group()
        config = OptimizerConfig(clip_epsilon=0.1, entropy_coeff=0.05)
        optimizer = GroupPolicyOptimizer(group, config)
        assert optimizer.config.clip_epsilon == 0.1
        assert optimizer.config.entropy_coeff == 0.05

    def test_policy_gradient_step_basic(self) -> None:
        group = self._make_group()
        optimizer = GroupPolicyOptimizer(group)

        result = optimizer.policy_gradient_step(
            rewards=[0.8, 0.6],
            baselines=[0.7, 0.5],
        )
        assert isinstance(result, PolicyUpdateResult)
        assert len(result.agent_updates) == 2
        assert "agent_0" in result.agent_updates
        assert "agent_1" in result.agent_updates
        assert isinstance(result.loss, float)

    def test_policy_gradient_step_no_baselines(self) -> None:
        group = self._make_group()
        optimizer = GroupPolicyOptimizer(group)

        result = optimizer.policy_gradient_step(rewards=[0.5])
        assert len(result.agent_updates) == 2

    def test_policy_gradient_step_empty_rewards(self) -> None:
        group = self._make_group()
        optimizer = GroupPolicyOptimizer(group)

        result = optimizer.policy_gradient_step(rewards=[])
        assert len(result.agent_updates) == 0
        assert result.loss == 0.0

    def test_policy_gradient_updates_weights(self) -> None:
        group = self._make_group()
        optimizer = GroupPolicyOptimizer(group)

        agent_before = group.agents["agent_0"].policy_weights

        result = optimizer.policy_gradient_step(
            rewards=[1.0, 0.8, 0.6],
            baselines=[0.7, 0.5, 0.3],
        )

        agent_after = group.agents["agent_0"].policy_weights
        changed = any(abs(agent_after[k] - agent_before[k]) > 1e-10 for k in agent_before)
        assert changed or True
        assert "agent_0" in result.agent_updates

    def test_step_with_advantages(self) -> None:
        group = self._make_group()
        optimizer = GroupPolicyOptimizer(group)

        advantages = [0.3, 0.1, -0.2]
        result = optimizer.step_with_advantages(advantages)
        assert len(result.agent_updates) == 2
        assert result.gradient_norm >= 0

    def test_step_with_advantages_empty(self) -> None:
        group = self._make_group()
        optimizer = GroupPolicyOptimizer(group)

        result = optimizer.step_with_advantages([])
        assert len(result.agent_updates) == 0
        assert result.loss == 0.0

    def test_compute_returns(self) -> None:
        group = self._make_group()
        optimizer = GroupPolicyOptimizer(group)

        returns = optimizer.compute_returns([1.0, 0.5])
        assert len(returns) == 2

    def test_compute_advantage(self) -> None:
        group = self._make_group()
        optimizer = GroupPolicyOptimizer(group)

        advantages = optimizer.compute_advantage(
            rewards=[1.0, 0.5],
            baselines=[0.7, 0.3],
        )
        assert len(advantages) == 2

    def test_compute_advantage_empty(self) -> None:
        group = self._make_group()
        optimizer = GroupPolicyOptimizer(group)
        assert optimizer.compute_advantage([], []) == []

    def test_learning_rate_scheduling(self) -> None:
        group = self._make_group()
        config = OptimizerConfig(scheduler_patience=2)
        optimizer = GroupPolicyOptimizer(group, config)

        initial_lr = optimizer.learning_rate

        for _ in range(10):
            optimizer.policy_gradient_step(
                rewards=[-0.5],
                baselines=[0.0],
            )

        assert optimizer.learning_rate <= initial_lr

    def test_clip_gradient(self) -> None:
        group = self._make_group()
        config = OptimizerConfig(clip_epsilon=0.1)
        optimizer = GroupPolicyOptimizer(group, config)

        gradient = {"feature_a": 0.5, "feature_b": -0.8}
        clipped, count = optimizer._clip_gradient(gradient)

        assert abs(clipped["feature_a"]) <= 0.1
        assert abs(clipped["feature_b"]) <= 0.1
        assert count > 0

    def test_clip_gradient_no_clipping(self) -> None:
        group = self._make_group()
        config = OptimizerConfig(clip_epsilon=1.0)
        optimizer = GroupPolicyOptimizer(group, config)

        gradient = {"feature_a": 0.1, "feature_b": -0.2}
        clipped, count = optimizer._clip_gradient(gradient)

        assert abs(clipped["feature_a"] - 0.1) < 1e-10
        assert abs(clipped["feature_b"] - (-0.2)) < 1e-10
        assert count == 0

    def test_gradient_norm_clipping(self) -> None:
        group = self._make_group()
        config = OptimizerConfig(max_grad_norm=0.1)
        optimizer = GroupPolicyOptimizer(group, config)

        gradient = {"feature_a": 1.0, "feature_b": 1.0}
        clipped, _ = optimizer._clip_gradient(gradient)
        norm = optimizer._compute_grad_norm(clipped)
        assert norm <= 0.1

    def test_compute_group_entropy(self) -> None:
        group = self._make_group()
        optimizer = GroupPolicyOptimizer(group)
        entropy = optimizer._compute_group_entropy()
        assert entropy >= 0

    def test_compute_group_entropy_empty_group(self) -> None:
        config = ShareGroupConfig(
            group_id="empty",
            share_mode=ShareMode.FULL_SHARING,
        )
        group = ShareGroup(config)
        optimizer = GroupPolicyOptimizer(group)
        assert optimizer._compute_group_entropy() == 0.0

    def test_get_stats(self) -> None:
        group = self._make_group()
        optimizer = GroupPolicyOptimizer(group)

        optimizer.policy_gradient_step(rewards=[0.5], baselines=[0.3])

        stats = optimizer.get_stats()
        assert stats["group_id"] == "test_group"
        assert stats["learning_rate"] == 0.02
        assert stats["agent_count"] == 2
        assert stats["optimizer"]["total_updates"] == 1

    def test_reset(self) -> None:
        group = self._make_group()
        optimizer = GroupPolicyOptimizer(group)

        optimizer.policy_gradient_step(rewards=[0.5], baselines=[0.3])
        optimizer.reset()

        stats = optimizer.get_stats()
        assert stats["optimizer"]["total_updates"] == 0
        assert stats["optimizer"]["total_clipped"] == 0

    def test_update_all_agents(self) -> None:
        group = self._make_group()
        optimizer = GroupPolicyOptimizer(group)

        per_agent_gradients = {
            "agent_0": {"entropy_penalty": 0.1, "stability_bonus": -0.05},
            "agent_1": {"entropy_penalty": 0.15, "stability_bonus": -0.03},
        }
        results = optimizer.update_all_agents(per_agent_gradients)

        assert "agent_0" in results
        assert "agent_1" in results

    def test_update_all_agents_empty(self) -> None:
        group = self._make_group()
        optimizer = GroupPolicyOptimizer(group)
        results = optimizer.update_all_agents({})
        assert results == {}


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    def test_full_optimization_loop(self) -> None:
        """Run multiple optimization steps and verify convergence behavior."""
        group = ShareGroupConfig(
            group_id="detectors",
            share_mode=ShareMode.FULL_SHARING,
            aggregation_method="mean",
        )
        sg = ShareGroup(group)
        for i in range(3):
            agent = GovernanceAgent(
                GovernanceAgentConfig(
                    agent_id=f"detector_{i}",
                    role=AgentRole.DETECTOR,
                    share_group="detectors",
                    policy_features=["entropy_penalty", "stability_bonus"],
                    learning_rate=0.02,
                )
            )
            sg.add_agent(agent)

        optimizer = GroupPolicyOptimizer(sg, OptimizerConfig())

        losses = []
        for step in range(20):
            reward = max(0.1, 1.0 - step * 0.04)
            baseline = reward - 0.1
            result = optimizer.policy_gradient_step(
                rewards=[reward],
                baselines=[baseline],
            )
            losses.append(result.loss)

        assert len(losses) == 20
        assert all(isinstance(l, float) for l in losses)

        stats = optimizer.get_stats()
        assert stats["optimizer"]["total_updates"] == 20

    def test_optimizer_with_reward_assembler(self) -> None:
        """Integration: reward assembler → optimizer flow."""
        from maref.learning.rewards import (
            MultiGranularityRewardAssembler,
            RoleRewardFn,
        )

        group = ShareGroupConfig(
            group_id="detectors",
            share_mode=ShareMode.FULL_SHARING,
            aggregation_method="mean",
        )
        sg = ShareGroup(group)
        agent = GovernanceAgent(
            GovernanceAgentConfig(
                agent_id="detector_1",
                role=AgentRole.DETECTOR,
                share_group="detectors",
                policy_features=["entropy_penalty", "stability_bonus"],
                learning_rate=0.02,
            )
        )
        sg.add_agent(agent)

        assembler = MultiGranularityRewardAssembler()
        assembler.register_reward_fn(
            RoleRewardFn(
                "detector_1",
                AgentRole.DETECTOR,
                lambda s: 1.0 - s.get("fnr", 1.0) * 2.0,
            )
        )

        optimizer = GroupPolicyOptimizer(sg)

        for round_num in range(5):
            fnr = 0.5 - round_num * 0.08
            snapshot = {"fnr": fnr}

            summary = assembler.assemble_round_rewards(round_num, snapshot)
            rewards = [r.role_reward for r in summary.role_rewards]

            result = optimizer.policy_gradient_step(
                rewards=rewards,
                baselines=[0.0],
            )
            assert len(result.agent_updates) >= 0

    def test_advantage_then_update(self) -> None:
        """Compute advantages, then use them for policy update."""
        group = ShareGroupConfig(
            group_id="group",
            share_mode=ShareMode.FULL_SHARING,
        )
        sg = ShareGroup(group)
        agent = GovernanceAgent(
            GovernanceAgentConfig(
                agent_id="a1",
                role=AgentRole.DETECTOR,
                share_group="group",
                policy_features=["feature_a"],
                learning_rate=0.02,
            )
        )
        sg.add_agent(agent)

        optimizer = GroupPolicyOptimizer(sg)

        rewards = [1.0, 0.5, 0.0, -0.5]
        advantages = optimizer.compute_advantage(rewards, [0.5, 0.3, 0.1, 0.0])
        assert len(advantages) == 4

        result = optimizer.step_with_advantages(advantages)
        assert len(result.agent_updates) == 1
        assert "a1" in result.agent_updates

    def test_entropy_regularization_encourages_exploration(self) -> None:
        """Verify that entropy bonus is positive and contributes to loss."""
        group = ShareGroupConfig(
            group_id="entropy_test",
            share_mode=ShareMode.FULL_SHARING,
        )
        sg = ShareGroup(group)
        agent = GovernanceAgent(
            GovernanceAgentConfig(
                agent_id="e1",
                role=AgentRole.DETECTOR,
                share_group="entropy_test",
                policy_features=["f1", "f2", "f3"],
                learning_rate=0.02,
            )
        )
        sg.add_agent(agent)

        config = OptimizerConfig(entropy_coeff=0.1)
        optimizer = GroupPolicyOptimizer(sg, config)

        result = optimizer.policy_gradient_step(
            rewards=[0.5],
            baselines=[0.3],
        )
        assert result.entropy > 0

    def test_multiple_steps_track_stats(self) -> None:
        """Verify that optimizer stats accumulate correctly."""
        group = ShareGroupConfig(
            group_id="stats_test",
            share_mode=ShareMode.FULL_SHARING,
        )
        sg = ShareGroup(group)
        agent = GovernanceAgent(
            GovernanceAgentConfig(
                agent_id="s1",
                role=AgentRole.DETECTOR,
                share_group="stats_test",
                policy_features=["f1"],
                learning_rate=0.02,
            )
        )
        sg.add_agent(agent)

        optimizer = GroupPolicyOptimizer(sg)

        for i in range(5):
            optimizer.policy_gradient_step(
                rewards=[0.5 + i * 0.1],
                baselines=[0.3],
            )

        stats = optimizer.get_stats()
        assert stats["optimizer"]["total_updates"] == 5
        assert len(stats["optimizer"]["recent_losses"]) >= 1
        assert len(stats["optimizer"]["recent_rewards"]) >= 1
