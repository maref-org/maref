"""
MAREF Meta-Learning Engine (M5 Enhanced)

Phase 10: Implements lightweight reinforcement learning for policy optimization.
The meta-learner observes the outcomes of governance decisions and adjusts
future strategies to maximize long-term stability and performance.

M5 enhancements:
- ExperienceStore: SQLite-persisted replay buffer (>1000 samples target)
- LearningRateScheduler: ReduceLROnPlateau adaptive scheduling
- Stratified sampling: balanced positive/negative experience batches
- Recency-weighted sampling: prioritizes recent 24h data
- Backward compatible: all existing API methods preserved

Key concepts:
- Decision effect feedback loop
- Policy gradient optimization
- Experience replay for sample efficiency
- Stability constraints to prevent runaway optimization
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from drift_guard.policy_sandbox import PolicySandbox
from drift_guard.types import PipelineConfig
from maref.learning.replay import DecisionOutcome, ExperienceStore
from maref.learning.scheduler import LearningRateScheduler
from maref_lite.state_machine import GovernanceState


@dataclass
class MetaLearningState:
    """Internal state of the meta-learner."""

    policy_weights: dict[str, float] = field(default_factory=dict)
    experience_buffer: list[DecisionOutcome] = field(default_factory=list)
    total_reward: float = 0.0
    episode_count: int = 0
    learning_rate: float = 0.02
    discount_factor: float = 0.90

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_weights": self.policy_weights,
            "buffer_size": len(self.experience_buffer),
            "total_reward": self.total_reward,
            "episode_count": self.episode_count,
            "learning_rate": self.learning_rate,
            "discount_factor": self.discount_factor,
        }


class MetaLearner:
    """
    Lightweight meta-learning optimizer for governance policies (M5 enhanced).

    M5 improvements over prototype:
    - ExperienceStore: cross-session persistent replay buffer
    - LearningRateScheduler: adaptive ReduceLROnPlateau (replaces fixed 0.999 decay)
    - Stratified sampling: prevents positive-only bias in gradient estimation
    - Recency weighting: prioritizes recent experience for faster adaptation

    Uses policy gradient methods to learn which state transitions
    and threshold configurations lead to better long-term outcomes.
    """

    def __init__(
        self,
        sandbox: PolicySandbox | None = None,
        buffer_size: int = 2000,
        learning_rate: float = 0.02,
        experience_db_path: str = ":memory:",
    ) -> None:
        self._sandbox = sandbox or PolicySandbox()
        self._buffer_size = buffer_size

        self._store = ExperienceStore(
            db_path=experience_db_path,
            max_size=max(buffer_size, 10000),
        )
        self._lr_scheduler = LearningRateScheduler(initial_lr=learning_rate)

        self._state = MetaLearningState(
            learning_rate=self._lr_scheduler.learning_rate,
            policy_weights={
                "entropy_penalty": -0.1,
                "stability_bonus": 0.2,
                "transition_efficiency": 0.05,
            },
        )

        self._stability_epochs: list[float] = []
        self._max_weight_magnitude = 1.0
        self._min_learning_rate = 0.0005

    def record_decision(self, outcome: DecisionOutcome) -> None:
        """
        Record the outcome of a governance decision.

        M5: Persists to SQLite ExperienceStore in addition to in-memory buffer.
        """
        self._store.insert(outcome)
        self._state.experience_buffer.append(outcome)
        self._state.total_reward += outcome.reward

        if len(self._state.experience_buffer) > self._buffer_size:
            self._state.experience_buffer.pop(0)

    def compute_reward(
        self,
        state_before: GovernanceState,
        state_after: GovernanceState,
        entropy_before: int,
        entropy_after: int,
        anomaly_resolved: bool = False,
        time_in_state: float = 0.0,
    ) -> float:
        """
        Compute reward for a state transition.

        Rewards:
        - Reducing entropy: positive
        - Resolving anomalies: strongly positive
        - Staying in high-entropy states: negative
        - Efficient transitions (few steps): positive
        """
        reward = 0.0

        entropy_delta = entropy_before - entropy_after
        reward += entropy_delta * 0.5

        if anomaly_resolved:
            reward += 2.0

        if entropy_after <= 2 and time_in_state > 5.0:
            reward += 0.1 * min(time_in_state, 60.0)

        if time_in_state < 1.0:
            reward -= 0.2

        if state_after == GovernanceState.HALT:
            reward -= 8.0
        elif state_after == GovernanceState.STABILIZE:
            reward += 1.0

        return reward

    def optimize_policy(self) -> PipelineConfig | None:
        """
        Run one optimization step using collected experience.

        M5: Uses stratified sampling from ExperienceStore for gradient estimation.
        Learning rate is updated via adaptive ReduceLROnPlateau scheduler.

        Returns:
            A new proposed policy configuration, or None if not enough data
        """
        if self._store.count() < 50:
            return None

        gradient = self._estimate_gradient()

        for key in self._state.policy_weights:
            if key in gradient:
                self._state.policy_weights[key] += self._state.learning_rate * gradient[key]

        self._clip_weights()
        self._decay_learning_rate()
        self._state.episode_count += 1

        return self._generate_policy()

    def _estimate_gradient(self) -> dict[str, float]:
        """Estimate policy gradient from experience buffer.

        M5: Uses stratified sampling from ExperienceStore for balanced
        positive/negative experience representation."""
        gradient = {"entropy_penalty": 0.0, "stability_bonus": 0.0, "transition_efficiency": 0.0}

        recent = self._store.sample(batch_size=200, stratified=True, recency_weight=0.7)

        if not recent:
            recent = self._state.experience_buffer[-100:]

        for outcome in recent:
            reward = outcome.reward
            weight = 1.0

            entropy_delta = outcome.entropy_before - outcome.entropy_after
            gradient["entropy_penalty"] += weight * reward * entropy_delta

            if outcome.entropy_after <= 2:
                gradient["stability_bonus"] += weight * reward

            if outcome.state_before != outcome.state_after:
                gradient["transition_efficiency"] += weight * reward

        n = len(recent)
        if n > 0:
            for key in gradient:
                gradient[key] /= n

        return gradient

    def _clip_weights(self) -> None:
        """Clip policy weights to prevent runaway values."""
        for key in self._state.policy_weights:
            self._state.policy_weights[key] = max(
                -self._max_weight_magnitude,
                min(self._max_weight_magnitude, self._state.policy_weights[key]),
            )

    def _decay_learning_rate(self) -> None:
        """M5: Adaptive ReduceLROnPlateau learning rate scheduling.

        Replaces the prototype's fixed 0.999 decay factor.
        If avg_reward shows no improvement for 3 consecutive epochs,
        learning rate is halved (subject to min_lr floor)."""
        avg_reward = self._store.avg_reward(last_n=100)

        self._state.learning_rate = self._lr_scheduler.step(avg_reward)

        self._state.learning_rate = max(
            self._min_learning_rate,
            self._state.learning_rate,
        )

    def _generate_policy(self) -> PipelineConfig:
        """Generate a new policy configuration from current weights."""
        baseline = self._sandbox.get_active_config()

        entropy_weight = self._state.policy_weights["entropy_penalty"]
        stability_weight = self._state.policy_weights["stability_bonus"]

        adjustment = (entropy_weight + stability_weight) * 0.1

        new_config = PipelineConfig(
            kl_warning=max(0.01, baseline.kl_warning + adjustment),
            kl_critical=max(0.1, baseline.kl_critical + adjustment * 2),
            kl_max=max(0.5, baseline.kl_max + adjustment * 3),
            hellinger_warning=baseline.hellinger_warning,
            hellinger_critical=baseline.hellinger_critical,
            check_interval_seconds=baseline.check_interval_seconds,
            review_timeout_seconds=baseline.review_timeout_seconds,
            reset_cooldown_seconds=baseline.reset_cooldown_seconds,
            reset_on_critical=baseline.reset_on_critical,
        )

        return new_config

    def get_stats(self) -> dict[str, Any]:
        """Get meta-learner statistics (M5: includes store and scheduler stats)."""
        store_stats = self._store.get_stats()
        return {
            "state": self._state.to_dict(),
            "buffer_utilization": len(self._state.experience_buffer) / self._buffer_size,
            "avg_reward": (self._state.total_reward / max(self._state.episode_count, 1)),
            "store": store_stats,
            "scheduler": self._lr_scheduler.get_stats(),
            "persisted_samples": self._store.count(),
        }

    def save(self, path: Path) -> None:
        """Save meta-learner state to disk (JSON for backward compat)."""
        with open(path, "w") as f:
            json.dump(self._state.to_dict(), f, indent=2, default=str)

    def load(self, path: Path) -> None:
        """Load meta-learner state from disk."""
        with open(path) as f:
            data = json.load(f)
            self._state.policy_weights = data.get("policy_weights", {})
            self._state.learning_rate = data.get("learning_rate", 0.02)
            self._state.total_reward = data.get("total_reward", 0.0)
            self._state.episode_count = data.get("episode_count", 0)
