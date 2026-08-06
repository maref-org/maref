"""
MAREF Group Policy Optimizer

Provides PPO-style policy gradient optimization for governance agent groups.
Enables grouped agents to perform joint parameter updates with gradient
clipping, advantage computation, and entropy regularization.

Key components:
- GroupPolicyOptimizer: PPO-style optimizer for a ShareGroup
- OptimizerConfig: Configuration for the policy optimizer
- AdvantageBuffer: Advantage computation with baselines
- EntropyRegularizer: Entropy penalty for exploration
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any

import structlog

from maref.evolution.agents import ShareGroup
from maref.learning.scheduler import LearningRateScheduler, SchedulerConfig

logger = structlog.get_logger(__name__)


@dataclass
class OptimizerConfig:
    """Configuration for the group policy optimizer."""

    clip_epsilon: float = 0.2
    """PPO clipping parameter. Prevents overly large policy updates."""

    value_loss_coeff: float = 0.5
    """Coefficient for value loss in combined objective."""

    entropy_coeff: float = 0.01
    """Entropy regularization coefficient for exploration."""

    max_grad_norm: float = 1.0
    """Maximum gradient norm for clipping."""

    gae_lambda: float = 0.95
    """Generalized Advantage Estimation lambda parameter."""

    discount_factor: float = 0.99
    """Reward discount factor (gamma)."""

    min_learning_rate: float = 0.0001
    """Minimum learning rate floor."""

    scheduler_patience: int = 3
    """Patience for learning rate reduction on plateau."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "clip_epsilon": self.clip_epsilon,
            "value_loss_coeff": self.value_loss_coeff,
            "entropy_coeff": self.entropy_coeff,
            "max_grad_norm": self.max_grad_norm,
            "gae_lambda": self.gae_lambda,
            "discount_factor": self.discount_factor,
            "min_learning_rate": self.min_learning_rate,
            "scheduler_patience": self.scheduler_patience,
        }


@dataclass
class OptimizerState:
    """Runtime state of the group policy optimizer."""

    total_updates: int = 0
    total_clipped: int = 0
    reward_history: list[float] = field(default_factory=list)
    loss_history: list[float] = field(default_factory=list)
    lr_history: list[float] = field(default_factory=list)
    entropy_history: list[float] = field(default_factory=list)
    clip_fraction: float = 0.0
    avg_grad_norm: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_updates": self.total_updates,
            "total_clipped": self.total_clipped,
            "clip_fraction": (
                self.total_clipped / self.total_updates if self.total_updates > 0 else 0.0
            ),
            "avg_grad_norm": self.avg_grad_norm,
            "recent_losses": self.loss_history[-10:],
            "recent_rewards": self.reward_history[-10:],
            "recent_entropy": self.entropy_history[-10:],
        }


@dataclass
class PolicyUpdateResult:
    """Result of a policy update step."""

    agent_updates: dict[str, dict[str, float]]
    """Per-agent updated weights: {agent_id: {feature: value}}"""

    loss: float
    """Combined loss value for this update."""

    clipped_count: int
    """Number of clipped gradients."""

    entropy: float
    """Policy entropy after update."""

    gradient_norm: float
    """Norm of the aggregated gradient."""


class EntropyRegularizer:
    """
    Entropy-based regularization for exploration.

    Computes the entropy of policy weights and applies
    an entropy bonus to encourage exploration.
    """

    @staticmethod
    def compute_entropy(weights: dict[str, float]) -> float:
        """
        Compute the entropy of a weight distribution.

        Uses a softmax-based entropy computation to handle
        negative weights gracefully.
        """
        if not weights:
            return 0.0

        values = list(weights.values())
        max_val = max(values)
        exp_values = [math.exp(v - max_val) for v in values]
        sum_exp = sum(exp_values)

        if sum_exp == 0:
            return 0.0

        probs = [e / sum_exp for e in exp_values]

        entropy = 0.0
        for p in probs:
            if p > 0:
                entropy -= p * math.log(p)

        return entropy

    @staticmethod
    def entropy_bonus(weights: dict[str, float], coeff: float = 0.01) -> float:
        """Compute entropy bonus for encouraging exploration."""
        return coeff * EntropyRegularizer.compute_entropy(weights)

    @staticmethod
    def entropy_gradient(
        weights: dict[str, float],
    ) -> dict[str, float]:
        """
        Compute the gradient of entropy with respect to weights.

        Returns a gradient that pushes weights toward a more uniform
        distribution (higher entropy).
        """
        if not weights:
            return {}

        values = list(weights.values())
        keys = list(weights.keys())
        max_val = max(values)
        exp_values = [math.exp(v - max_val) for v in values]
        sum_exp = sum(exp_values)

        if sum_exp == 0:
            return dict.fromkeys(keys, 0.0)

        probs = [e / sum_exp for e in exp_values]
        n = len(probs)

        gradient: dict[str, float] = {}
        for i, key in enumerate(keys):
            grad = 0.0
            for j in range(n):
                if i == j:
                    grad += probs[j] * (1 - probs[j])
                else:
                    grad -= probs[i] * probs[j]
            gradient[key] = grad / n

        return gradient


class AdvantageBuffer:
    """
    Advantage computation with Generalized Advantage Estimation (GAE).

    Computes advantages from rewards and baselines using the GAE formula:
        A_t = sum_{l=0}^{T-t-1} (gamma * lambda)^l * delta_{t+l}
        where delta_t = r_t + gamma * V(s_{t+1}) - V(s_t)
    """

    def __init__(
        self,
        discount: float = 0.99,
        gae_lambda: float = 0.95,
    ) -> None:
        self._gamma = discount
        self._lambda = gae_lambda

    def compute_advantages(
        self,
        rewards: list[float],
        values: list[float],
    ) -> list[float]:
        """
        Compute GAE advantages from rewards and value estimates.

        Args:
            rewards: Sequence of rewards per timestep.
            values: Value estimates per state (len = len(rewards) + 1).

        Returns:
            Advantage estimates for each timestep.
        """
        if not rewards:
            return []

        advantages: list[float] = []
        gae = 0.0

        for t in reversed(range(len(rewards))):
            delta = rewards[t]
            next_val = values[t + 1] if t + 1 < len(values) else 0.0
            delta += self._gamma * next_val - values[t]
            gae = delta + self._gamma * self._lambda * gae
            advantages.insert(0, gae)

        return advantages

    def compute_returns(
        self,
        rewards: list[float],
    ) -> list[float]:
        """
        Compute discounted returns from rewards.

        Args:
            rewards: Sequence of rewards.

        Returns:
            Discounted returns for each timestep.
        """
        if not rewards:
            return []

        returns: list[float] = []
        running_return = 0.0

        for r in reversed(rewards):
            running_return = r + self._gamma * running_return
            returns.insert(0, running_return)

        return returns


class GroupPolicyOptimizer:
    """
    PPO-style policy gradient optimizer for governance agent groups.

    Responsibilities:
    1. Compute advantages from per-agent rewards and baselines
    2. Perform PPO-style clipped policy gradient updates
    3. Apply entropy regularization for exploration
    4. Track optimization statistics for observability

    Usage:
        optimizer = GroupPolicyOptimizer(group, OptimizerConfig())
        result = optimizer.policy_gradient_step(
            rewards=[0.8, 0.6],
            values=[0.7, 0.5, 0.0],
        )
        logger.debug("Loss: %s, Updates: %s", result.loss, result.agent_updates)
    """

    def __init__(
        self,
        group: ShareGroup,
        config: OptimizerConfig | None = None,
    ) -> None:
        self._group = group
        self._config = config or OptimizerConfig()
        self._state = OptimizerState()
        self._advantage_buffer = AdvantageBuffer(
            discount=self._config.discount_factor,
            gae_lambda=self._config.gae_lambda,
        )
        self._lr_scheduler = LearningRateScheduler(
            initial_lr=0.02,
            config=SchedulerConfig(
                patience=self._config.scheduler_patience,
                factor=0.5,
                min_lr=self._config.min_learning_rate,
            ),
        )

    @property
    def group(self) -> ShareGroup:
        return self._group

    @property
    def config(self) -> OptimizerConfig:
        return self._config

    @property
    def learning_rate(self) -> float:
        return self._lr_scheduler.learning_rate

    def compute_advantage(
        self,
        rewards: list[float],
        baselines: list[float],
    ) -> list[float]:
        """
        Compute advantages using GAE.

        Args:
            rewards: Sequence of rewards.
            baselines: Value baseline estimates (same length as rewards).

        Returns:
            Advantage estimates.
        """
        if not rewards:
            return []

        values = list(baselines) if len(baselines) == len(rewards) + 1 else [*baselines, 0.0]

        return self._advantage_buffer.compute_advantages(rewards, values)

    def policy_gradient_step(
        self,
        rewards: list[float],
        baselines: list[float] | None = None,
    ) -> PolicyUpdateResult:
        """
        Perform one PPO-style policy gradient step for the group.

        Args:
            rewards: Sequence of rewards for this step.
            baselines: Optional value baselines. Defaults to rolling mean.

        Returns:
            PolicyUpdateResult with updated weights and stats.
        """
        if not rewards:
            return PolicyUpdateResult(
                agent_updates={},
                loss=0.0,
                clipped_count=0,
                entropy=0.0,
                gradient_norm=0.0,
            )

        if baselines is None:
            baseline_val = statistics.mean(rewards) if rewards else 0.0
            baselines = [baseline_val] * len(rewards)

        advantages = self.compute_advantage(rewards, baselines)

        if not advantages:
            return PolicyUpdateResult(
                agent_updates={},
                loss=0.0,
                clipped_count=0,
                entropy=0.0,
                gradient_norm=0.0,
            )

        gradient_per_feature = self._compute_gradient(advantages)
        clipped_gradient, clipped_count = self._clip_gradient(gradient_per_feature)
        gradient_norm = self._compute_grad_norm(clipped_gradient)

        agent_results = self._group.apply_update(
            clipped_gradient,
            learning_rate=self._lr_scheduler.learning_rate,
        )

        total_loss = self._compute_loss(clipped_gradient, advantages)
        entropy = self._compute_group_entropy()

        self._lr_scheduler.step(statistics.mean(rewards))

        self._state.total_updates += 1
        self._state.total_clipped += clipped_count
        self._state.reward_history.append(statistics.mean(rewards))
        self._state.loss_history.append(total_loss)
        self._state.lr_history.append(self._lr_scheduler.learning_rate)
        self._state.entropy_history.append(entropy)
        self._state.clip_fraction = self._state.total_clipped / self._state.total_updates
        self._state.avg_grad_norm = gradient_norm

        return PolicyUpdateResult(
            agent_updates=agent_results,
            loss=total_loss,
            clipped_count=clipped_count,
            entropy=entropy,
            gradient_norm=gradient_norm,
        )

    def step_with_advantages(
        self,
        advantages: list[float],
    ) -> PolicyUpdateResult:
        """
        Perform a policy update with pre-computed advantages.

        Args:
            advantages: Pre-computed advantage values.

        Returns:
            PolicyUpdateResult.
        """
        if not advantages:
            return PolicyUpdateResult(
                agent_updates={},
                loss=0.0,
                clipped_count=0,
                entropy=0.0,
                gradient_norm=0.0,
            )

        gradient_per_feature = self._compute_gradient(advantages)
        clipped_gradient, clipped_count = self._clip_gradient(gradient_per_feature)
        gradient_norm = self._compute_grad_norm(clipped_gradient)

        agent_results = self._group.apply_update(
            clipped_gradient,
            learning_rate=self._lr_scheduler.learning_rate,
        )

        total_loss = self._compute_loss(clipped_gradient, advantages)
        entropy = self._compute_group_entropy()

        avg_advantage = statistics.mean(advantages)
        self._lr_scheduler.step(avg_advantage)

        self._state.total_updates += 1
        self._state.total_clipped += clipped_count
        self._state.loss_history.append(total_loss)
        self._state.lr_history.append(self._lr_scheduler.learning_rate)
        self._state.entropy_history.append(entropy)
        self._state.clip_fraction = self._state.total_clipped / self._state.total_updates
        self._state.avg_grad_norm = gradient_norm

        return PolicyUpdateResult(
            agent_updates=agent_results,
            loss=total_loss,
            clipped_count=clipped_count,
            entropy=entropy,
            gradient_norm=gradient_norm,
        )

    def compute_returns(self, rewards: list[float]) -> list[float]:
        """Compute discounted returns from rewards."""
        return self._advantage_buffer.compute_returns(rewards)

    def update_all_agents(
        self,
        per_agent_gradients: dict[str, dict[str, float]],
    ) -> dict[str, dict[str, float]]:
        """
        Compute aggregated gradient and update all agents in the group.

        Args:
            per_agent_gradients: {agent_id: {feature: gradient}}

        Returns:
            Updated weights for each agent.
        """
        if not per_agent_gradients:
            return {}

        aggregated = self._group.aggregate_gradients(per_agent_gradients)
        clipped, _ = self._clip_gradient(aggregated)

        return self._group.apply_update(
            clipped,
            learning_rate=self._lr_scheduler.learning_rate,
        )

    def reset(self) -> None:
        """Reset optimizer state (preserves learned policy weights)."""
        self._state = OptimizerState()
        self._lr_scheduler = LearningRateScheduler(
            initial_lr=0.02,
            config=SchedulerConfig(
                patience=self._config.scheduler_patience,
                factor=0.5,
                min_lr=self._config.min_learning_rate,
            ),
        )

    def get_stats(self) -> dict[str, Any]:
        return {
            "group_id": self._group.group_id,
            "learning_rate": self._lr_scheduler.learning_rate,
            "optimizer": self._state.to_dict(),
            "lr_scheduler": self._lr_scheduler.get_stats(),
            "agent_count": self._group.agent_count,
        }

    # --- Internal computation ---

    def _compute_gradient(self, advantages: list[float]) -> dict[str, float]:
        """Compute per-feature gradient from advantages."""
        agents = self._group.agents
        if not agents:
            return {}

        all_features: set[str] = set()
        for agent in agents.values():
            all_features.update(agent.policy_features)

        if not all_features:
            return {}

        avg_advantage = statistics.mean(advantages) if advantages else 0.0

        gradient: dict[str, float] = {}
        for feature in all_features:
            grad_sum = 0.0
            agent_count = 0
            for agent in agents.values():
                if feature in agent.policy_features:
                    weight = agent.policy_weights.get(feature, 0.0)
                    grad_sum += avg_advantage * weight
                    agent_count += 1

            gradient[feature] = grad_sum / max(agent_count, 1)

        return gradient

    def _clip_gradient(self, gradient: dict[str, float]) -> tuple[dict[str, float], int]:
        """
        Clip gradient by PPO clipping and gradient norm.

        Returns:
            (clipped_gradient, clipped_count)
        """
        clipped: dict[str, float] = {}
        clipped_count = 0

        for feature, grad in gradient.items():
            if abs(grad) > self._config.clip_epsilon:
                clipped[feature] = (
                    self._config.clip_epsilon if grad > 0 else -self._config.clip_epsilon
                )
                clipped_count += 1
            else:
                clipped[feature] = grad

        norm = self._compute_grad_norm(clipped)
        if norm > self._config.max_grad_norm:
            scale = self._config.max_grad_norm / norm
            clipped = {k: v * scale for k, v in clipped.items()}
            clipped_count += len(clipped)

        return clipped, clipped_count

    def _compute_grad_norm(self, gradient: dict[str, float]) -> float:
        return sum(v * v for v in gradient.values()) ** 0.5

    def _compute_loss(self, gradient: dict[str, float], advantages: list[float]) -> float:
        """Compute combined PPO loss."""
        surrogate_loss = sum(gradient.values()) * statistics.mean(advantages) if advantages else 0.0

        entropy_bonus = 0.0
        for agent in self._group.agents.values():
            entropy_bonus += EntropyRegularizer.entropy_bonus(
                agent.policy_weights,
                self._config.entropy_coeff,
            )

        return -surrogate_loss - entropy_bonus

    def _compute_group_entropy(self) -> float:
        """Compute average entropy across all agents in the group."""
        agents = self._group.agents
        if not agents:
            return 0.0

        total_entropy = sum(
            EntropyRegularizer.compute_entropy(agent.policy_weights) for agent in agents.values()
        )
        return total_entropy / len(agents)
