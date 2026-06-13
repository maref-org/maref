"""
MAREF Multi-Granularity Reward System

Provides a three-level reward hierarchy for multi-agent governance optimization:
- Role Level: Per-agent rewards based on role-specific metrics
- Round Level: Weighted aggregation of all role rewards within a round
- Cycle Level: Long-term reward reflecting convergence quality across cycles

Key components:
- RoleReward: Per-role reward with multi-level signals
- RoleRewardFn: Pluggable reward function per role
- MultiGranularityRewardAssembler: Assembles and aggregates rewards across levels
- CycleRewardTracker: Tracks and computes cycle-level rewards

Design principles:
- Enables precise credit assignment to individual governance roles
- Backward compatible: supports legacy single-reward mode
- Extensible: custom reward functions per role
"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.evolution.agents import AgentRole


class RewardLevel(Enum):
    """Granularity level of a reward signal."""

    ROLE = "role"
    """Reward specific to a single governance agent role."""

    ROUND = "round"
    """Aggregate reward across all roles in a single evolution round."""

    CYCLE = "cycle"
    """Long-term reward reflecting convergence quality across a full cycle."""


@dataclass
class RoleReward:
    """
    Reward signal for a single governance agent role.

    Contains three levels of reward data:
    - role_reward: Direct reward for this agent's specific performance
    - turn_reward: Reward for this agent's contribution within the current turn
    - context: Additional metadata for debugging and analysis

    Usage:
        reward = RoleReward(
            agent_id="anomaly_detector",
            role=AgentRole.DETECTOR,
            role_reward=0.8,
            turn_reward=0.75,
            context={"fnr": 0.12, "fpr": 0.08},
        )
    """

    agent_id: str
    role: AgentRole
    role_reward: float
    turn_reward: float = 0.0
    cycle_reward: float = 0.0
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def weighted_reward(self) -> float:
        """Composite reward with role > turn > cycle emphasis."""
        return 0.5 * self.role_reward + 0.3 * self.turn_reward + 0.2 * self.cycle_reward

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "role_reward": self.role_reward,
            "turn_reward": self.turn_reward,
            "cycle_reward": self.cycle_reward,
            "weighted_reward": self.weighted_reward,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RoleReward:
        return cls(
            agent_id=d["agent_id"],
            role=AgentRole(d["role"]),
            role_reward=float(d["role_reward"]),
            turn_reward=float(d.get("turn_reward", 0.0)),
            cycle_reward=float(d.get("cycle_reward", 0.0)),
            context=d.get("context", {}),
        )


class RoleRewardFn:
    """
    Pluggable reward function for a specific governance role.

    Each role can define how its reward is computed based on
    round snapshot data. This enables precise credit assignment.

    Usage:
        def detector_reward_fn(round_snapshot: dict) -> float:
            fnr = round_snapshot.get("fnr", 1.0)
            return 1.0 - fnr * 2.0

        reward_fn = RoleRewardFn(
            agent_id="anomaly_detector",
            role=AgentRole.DETECTOR,
            fn=detector_reward_fn,
        )
        reward = reward_fn.compute({"fnr": 0.15, "fpr": 0.08})
    """

    def __init__(
        self,
        agent_id: str,
        role: AgentRole,
        fn: Callable[[dict[str, Any]], float],
        turn_fn: Callable[[dict[str, Any]], float] | None = None,
        weight: float = 1.0,
    ) -> None:
        self._agent_id = agent_id
        self._role = role
        self._fn = fn
        self._turn_fn = turn_fn
        self._weight = weight

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def role(self) -> AgentRole:
        return self._role

    @property
    def weight(self) -> float:
        return self._weight

    def compute(self, round_snapshot: dict[str, Any]) -> RoleReward:
        role_reward = self._fn(round_snapshot)
        role_reward = max(-1.0, min(1.0, role_reward))

        if self._turn_fn:
            turn_reward = self._turn_fn(round_snapshot)
            turn_reward = max(-1.0, min(1.0, turn_reward))
        else:
            turn_reward = role_reward

        return RoleReward(
            agent_id=self._agent_id,
            role=self._role,
            role_reward=role_reward,
            turn_reward=turn_reward,
            context=dict(round_snapshot),
        )

    def compute_with_weight(self, round_snapshot: dict[str, Any]) -> RoleReward:
        reward = self.compute(round_snapshot)
        reward.role_reward *= self._weight
        reward.turn_reward *= self._weight
        return reward


# ============================================================================
# Built-in reward functions for standard governance roles
# ============================================================================

def detector_reward_fn(round_snapshot: dict[str, Any]) -> float:
    """
    Reward for detector roles (anomaly_detector, drift_monitor).

    Rewards:
    - Low FNR (few missed anomalies)
    - Low FPR (few false alarms)
    - Balanced tradeoff between the two
    """
    fnr = round_snapshot.get("fnr", 1.0)
    fpr = round_snapshot.get("fpr", 1.0)
    detection_accuracy = round_snapshot.get("detection_accuracy")

    if detection_accuracy is not None:
        return float(detection_accuracy) * 2.0 - 1.0

    fnr_penalty = min(fnr * 2.0, 1.0)
    fpr_penalty = min(fpr * 1.5, 0.75)

    return 1.0 - fnr_penalty - fpr_penalty


def evaluator_reward_fn(round_snapshot: dict[str, Any]) -> float:
    """
    Reward for evaluator roles (trust_evaluator).

    Rewards:
    - Accurate trust scoring (low scoring error)
    - Timely evaluation (no timeouts)
    """
    scoring_error = round_snapshot.get("scoring_error", 1.0)
    timeout = round_snapshot.get("timeout", False)

    base = 1.0 - scoring_error
    timeout_penalty = 0.3 if timeout else 0.0

    return max(-1.0, base - timeout_penalty)


def optimizer_reward_fn(round_snapshot: dict[str, Any]) -> float:
    """
    Reward for optimizer roles (policy_optimizer).

    Rewards:
    - Policy improvement (lower FNR/FPR after optimization)
    - Stability (no oscillation in policy weights)
    """
    fnr_improvement = round_snapshot.get("fnr_improvement", 0.0)
    stability = round_snapshot.get("stability_score", 0.5)
    oscillation = round_snapshot.get("oscillation", False)

    improvement_reward = fnr_improvement * 2.0
    stability_reward = stability - 0.5
    oscillation_penalty = 0.5 if oscillation else 0.0

    return improvement_reward + stability_reward - oscillation_penalty


def enforcer_reward_fn(round_snapshot: dict[str, Any]) -> float:
    """
    Reward for enforcer roles (circuit_breaker).

    Rewards:
    - Timely circuit breaker activation on genuine anomalies
    - No false circuit breaker triggers
    - System stability maintained
    """
    breaker_triggered = round_snapshot.get("circuit_breaker_triggered", False)
    was_genuine = round_snapshot.get("anomaly_was_genuine", True)
    system_stable = round_snapshot.get("system_stable", True)

    if breaker_triggered:
        if was_genuine:
            return 0.8 if system_stable else 0.3
        else:
            return -0.6
    else:
        if system_stable:
            return 0.5
        else:
            return -0.4


# ============================================================================
# Reward Registry — maps roles to their reward functions
# ============================================================================

BUILTIN_REWARD_FUNCTIONS: dict[AgentRole, Callable[[dict[str, Any]], float]] = {
    AgentRole.DETECTOR: detector_reward_fn,
    AgentRole.EVALUATOR: evaluator_reward_fn,
    AgentRole.OPTIMIZER: optimizer_reward_fn,
    AgentRole.ENFORCER: enforcer_reward_fn,
}


def create_role_reward_fn(
    agent_id: str,
    role: AgentRole,
    custom_fn: Callable[[dict[str, Any]], float] | None = None,
    weight: float = 1.0,
) -> RoleRewardFn:
    """
    Create a RoleRewardFn for a given agent.

    Uses the built-in reward function for the role unless a custom
    function is provided.

    Args:
        agent_id: The agent this reward function is for.
        role: The agent's governance role.
        custom_fn: Optional custom reward function.
        weight: Reward weight multiplier.

    Returns:
        Configured RoleRewardFn instance.
    """
    fn = custom_fn or BUILTIN_REWARD_FUNCTIONS.get(role, detector_reward_fn)
    return RoleRewardFn(
        agent_id=agent_id,
        role=role,
        fn=fn,
        weight=weight,
    )


# ============================================================================
# Multi-Granularity Reward Assembler
# ============================================================================

@dataclass
class RoundRewardSummary:
    """Summary of rewards for a single evolution round."""

    round_num: int
    role_rewards: list[RoleReward] = field(default_factory=list)
    round_reward: float = 0.0
    cycle_reward: float = 0.0

    @property
    def avg_role_reward(self) -> float:
        if not self.role_rewards:
            return 0.0
        return statistics.mean([r.role_reward for r in self.role_rewards])

    @property
    def max_role_reward(self) -> float:
        if not self.role_rewards:
            return 0.0
        return max(r.role_reward for r in self.role_rewards)

    @property
    def min_role_reward(self) -> float:
        if not self.role_rewards:
            return 0.0
        return min(r.role_reward for r in self.role_rewards)

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_num": self.round_num,
            "role_rewards": [r.to_dict() for r in self.role_rewards],
            "round_reward": self.round_reward,
            "cycle_reward": self.cycle_reward,
            "avg_role_reward": self.avg_role_reward,
            "max_role_reward": self.max_role_reward,
            "min_role_reward": self.min_role_reward,
        }


class MultiGranularityRewardAssembler:
    """
    Assembles rewards across three granularity levels.

    Responsibilities:
    1. Compute per-role rewards using RoleRewardFn
    2. Aggregate role rewards into a round-level reward
    3. Track and compute cycle-level rewards based on convergence

    Usage:
        assembler = MultiGranularityRewardAssembler()

        # Register reward functions for each agent
        assembler.register_reward_fn(
            RoleRewardFn("anomaly_detector", AgentRole.DETECTOR, detector_reward_fn)
        )

        # Compute rewards for a round
        summary = assembler.assemble_round_rewards(
            round_num=5,
            round_snapshot={"fnr": 0.12, "fpr": 0.08},
        )
        print(f"Round reward: {summary.round_reward}")
        print(f"Per-role: {summary.role_rewards}")
    """

    def __init__(self) -> None:
        self._reward_fns: dict[str, RoleRewardFn] = {}
        self._round_history: list[RoundRewardSummary] = []
        self._cycle_history: list[float] = []

    def register_reward_fn(self, reward_fn: RoleRewardFn) -> None:
        """Register a reward function for an agent."""
        self._reward_fns[reward_fn.agent_id] = reward_fn

    def unregister_reward_fn(self, agent_id: str) -> RoleRewardFn | None:
        """Remove a reward function."""
        return self._reward_fns.pop(agent_id, None)

    def has_reward_fn(self, agent_id: str) -> bool:
        return agent_id in self._reward_fns

    def assemble_role_reward(
        self,
        agent_id: str,
        round_snapshot: dict[str, Any],
    ) -> RoleReward:
        """
        Compute the role-level reward for a single agent.

        Args:
            agent_id: The agent to compute reward for.
            round_snapshot: Current round metrics snapshot.

        Returns:
            RoleReward for the agent.
        """
        reward_fn = self._reward_fns.get(agent_id)
        if reward_fn is None:
            fallback = round_snapshot.get("reward", 0.0)
            return RoleReward(
                agent_id=agent_id,
                role=AgentRole.DETECTOR,
                role_reward=fallback,
                turn_reward=fallback,
                context={"fallback": True, **round_snapshot},
            )
        return reward_fn.compute(round_snapshot)

    def assemble_round_rewards(
        self,
        round_num: int,
        round_snapshot: dict[str, Any],
        agent_ids: list[str] | None = None,
    ) -> RoundRewardSummary:
        """
        Compute rewards for all registered agents in a round.

        Args:
            round_num: Current round number.
            round_snapshot: Current round metrics snapshot.
            agent_ids: Specific agents to compute rewards for.
                      If None, all registered agents are used.

        Returns:
            RoundRewardSummary with per-role and aggregate rewards.
        """
        target_ids = agent_ids or list(self._reward_fns.keys())
        role_rewards: list[RoleReward] = []

        for agent_id in target_ids:
            reward = self.assemble_role_reward(agent_id, round_snapshot)
            role_rewards.append(reward)

        round_reward = self._aggregate_round_reward(role_rewards)

        summary = RoundRewardSummary(
            round_num=round_num,
            role_rewards=role_rewards,
            round_reward=round_reward,
        )

        self._round_history.append(summary)
        return summary

    def assemble_cycle_reward(
        self,
        cycle_metrics: dict[str, Any],
    ) -> float:
        """
        Compute the cycle-level reward based on convergence quality.

        Args:
            cycle_metrics: Metrics for the completed cycle, including:
                - fnr_series: List of FNR values per round
                - fpr_series: List of FPR values per round
                - convergence: Whether the cycle converged

        Returns:
            Cycle-level reward in [-1.0, 1.0].
        """
        fnr_series = cycle_metrics.get("fnr_series", [])
        converged = cycle_metrics.get("converged", False)

        if not fnr_series:
            return 0.0

        fnr_final = fnr_series[-1]
        fnr_improvement = fnr_series[0] - fnr_final if len(fnr_series) > 1 else 0.0

        fnr_reward = 1.0 - fnr_final * 2.0
        improvement_reward = fnr_improvement * 3.0
        convergence_bonus = 0.5 if converged else 0.0

        reward = fnr_reward * 0.4 + improvement_reward * 0.3 + convergence_bonus * 0.3

        return max(-1.0, min(1.0, reward))

    def apply_cycle_rewards(
        self,
        cycle_metrics: dict[str, Any],
    ) -> list[RoleReward]:
        """
        Compute cycle rewards and apply them to all role rewards in history.

        Updates the cycle_reward field of recent role rewards.

        Returns:
            Updated RoleReward list for the most recent round.
        """
        cycle_reward = self.assemble_cycle_reward(cycle_metrics)
        self._cycle_history.append(cycle_reward)

        if self._round_history:
            latest = self._round_history[-1]
            latest.cycle_reward = cycle_reward
            for role_reward in latest.role_rewards:
                role_reward.cycle_reward = cycle_reward
            return latest.role_rewards
        return []

    def get_round_history(self, last_n: int = 0) -> list[RoundRewardSummary]:
        if last_n > 0:
            return self._round_history[-last_n:]
        return list(self._round_history)

    def get_cycle_history(self) -> list[float]:
        return list(self._cycle_history)

    def get_stats(self) -> dict[str, Any]:
        if not self._round_history:
            return {
                "total_rounds": 0,
                "total_cycles": 0,
                "avg_round_reward": 0.0,
                "avg_role_reward": 0.0,
            }

        all_round_rewards = [s.round_reward for s in self._round_history]
        all_role_rewards = [
            r.role_reward
            for s in self._round_history
            for r in s.role_rewards
        ]

        return {
            "total_rounds": len(self._round_history),
            "total_cycles": len(self._cycle_history),
            "avg_round_reward": statistics.mean(all_round_rewards),
            "avg_role_reward": statistics.mean(all_role_rewards) if all_role_rewards else 0.0,
            "latest_round_reward": all_round_rewards[-1],
            "cycle_rewards": self._cycle_history[-10:],
            "registered_fns": len(self._reward_fns),
        }

    # --- Internal aggregation ---

    def _aggregate_round_reward(self, role_rewards: list[RoleReward]) -> float:
        if not role_rewards:
            return 0.0

        weighted_sum = sum(r.weighted_reward for r in role_rewards)
        total_weight = sum(
            self._reward_fns[r.agent_id].weight
            if r.agent_id in self._reward_fns
            else 1.0
            for r in role_rewards
        )

        if total_weight == 0:
            return 0.0

        return weighted_sum / total_weight
