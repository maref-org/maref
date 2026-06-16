"""
MAREF Learning Rate Scheduler — ReduceLROnPlateau

M5.2: Replaces fixed 0.999 decay with adaptive scheduling.
If avg_reward shows no improvement for `patience` consecutive epochs,
learning rate is halved.

Features:
- Tracks rolling avg_reward with configurable window
- Patience-based plateau detection
- Cooldown period after rate reduction
- Minimum learning rate floor
- Stats export for observability
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SchedulerConfig:
    patience: int = 3
    factor: float = 0.5
    min_lr: float = 0.0001
    cooldown: int = 2
    threshold: float = 0.01
    window_size: int = 5

    def to_dict(self) -> dict[str, Any]:
        return {
            "patience": self.patience,
            "factor": self.factor,
            "min_lr": self.min_lr,
            "cooldown": self.cooldown,
            "threshold": self.threshold,
            "window_size": self.window_size,
        }


@dataclass
class SchedulerState:
    best_avg_reward: float = float("-inf")
    epochs_no_improvement: int = 0
    cooldown_remaining: int = 0
    epoch_count: int = 0
    lr_history: list[float] = field(default_factory=list)
    reward_history: list[float] = field(default_factory=list)


class LearningRateScheduler:
    """
    ReduceLROnPlateau-style adaptive learning rate scheduler.

    Monitors avg_reward rolling average. When `patience` consecutive
    epochs show no improvement beyond `threshold`, learning rate is
    multiplied by `factor` (typically 0.5).
    """

    def __init__(
        self,
        initial_lr: float = 0.01,
        config: SchedulerConfig | None = None,
    ) -> None:
        self._lr = initial_lr
        self._config = config or SchedulerConfig()
        self._state = SchedulerState()
        self._state.lr_history.append(initial_lr)

    @property
    def learning_rate(self) -> float:
        return self._lr

    def step(self, avg_reward: float) -> float:
        self._state.epoch_count += 1

        if self._state.cooldown_remaining > 0:
            self._state.cooldown_remaining -= 1
            self._state.reward_history.append(avg_reward)
            self._state.lr_history.append(self._lr)
            return self._lr

        rolling_avg = self._compute_rolling_avg(avg_reward)
        self._state.reward_history.append(avg_reward)

        if rolling_avg > self._state.best_avg_reward + self._config.threshold:
            self._state.best_avg_reward = rolling_avg
            self._state.epochs_no_improvement = 0
        else:
            self._state.epochs_no_improvement += 1

        if self._state.epochs_no_improvement >= self._config.patience:
            old_lr = self._lr
            self._lr = max(self._config.min_lr, self._lr * self._config.factor)
            self._state.cooldown_remaining = self._config.cooldown
            self._state.epochs_no_improvement = 0
            self._state.best_avg_reward = rolling_avg

            if self._lr < old_lr:
                self._state.lr_history.append(self._lr)

        return self._lr

    def _compute_rolling_avg(self, new_reward: float) -> float:
        window = self._state.reward_history[-self._config.window_size :]
        window.append(new_reward)
        return sum(window) / len(window)

    def should_reduce(self) -> bool:
        return (
            self._state.epochs_no_improvement >= self._config.patience
            and self._state.cooldown_remaining == 0
        )

    def get_stats(self) -> dict[str, Any]:
        return {
            "current_lr": self._lr,
            "epoch_count": self._state.epoch_count,
            "best_avg_reward": (
                self._state.best_avg_reward if self._state.best_avg_reward != float("-inf") else 0.0
            ),
            "epochs_no_improvement": self._state.epochs_no_improvement,
            "cooldown_remaining": self._state.cooldown_remaining,
            "config": self._config.to_dict(),
            "lr_history": self._state.lr_history[-10:],
            "reward_history": self._state.reward_history[-10:],
        }

    def reset(self) -> None:
        self._state = SchedulerState()
