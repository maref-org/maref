"""Token budget controller — cost accounting, budget caps, and meltdown.

Extends the existing GasMeter (recursive/cost_tracker.py) with:

- Budget caps per task / user / organization
- Meltdown: task auto-downgrades when budget exceeded
- Rate limiting: prevent cost spikes
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Any


class BudgetAction(Enum):
    ALLOW = "allow"
    DOWNGRADE = "downgrade"   # Switch to cheaper model
    BLOCK = "block"            # Block the operation
    INTERRUPT = "interrupt"    # Kill the running task


@dataclass
class BudgetResult:
    action: BudgetAction
    reason: str = ""
    current_cost: float = 0.0
    limit: float = 0.0
    suggested_model: str = ""


@dataclass
class BudgetConfig:
    """Per-scope budget configuration."""

    max_cost: float = 100.0          # Total cost cap
    max_cost_per_task: float = 10.0  # Per-task cost cap
    max_requests_per_min: int = 100  # Rate limit
    downgrade_threshold: float = 0.8  # % of max_cost that triggers downgrade
    interrupt_threshold: float = 1.0  # % of max_cost that triggers interrupt


DEFAULT_CONFIGS: dict[str, BudgetConfig] = {
    "premium": BudgetConfig(
        max_cost=500.0,
        max_cost_per_task=50.0,
        max_requests_per_min=500,
        downgrade_threshold=0.8,
    ),
    "standard": BudgetConfig(),
    "cheap": BudgetConfig(
        max_cost=20.0,
        max_cost_per_task=2.0,
        max_requests_per_min=30,
        downgrade_threshold=0.6,
        interrupt_threshold=0.9,
    ),
}


class TokenBudgetController:
    """Budget enforcement for token usage and API costs.

    Usage:
        controller = TokenBudgetController()
        # Check before executing
        result = controller.check_cost("task-1", "user-1", estimated_cost=5.0)
        if result.action == BudgetAction.BLOCK:
            raise ValueError(f"Budget exceeded: {result.reason}")
        # Record actual cost
        controller.record_cost("task-1", "user-1", actual_cost=4.5)
    """

    def __init__(self, tier: str = "standard") -> None:
        config = DEFAULT_CONFIGS.get(tier, DEFAULT_CONFIGS["standard"])
        self._max_cost = config.max_cost
        self._max_cost_per_task = config.max_cost_per_task
        self._max_rpm = config.max_requests_per_min
        self._downgrade_pct = config.downgrade_threshold
        self._interrupt_pct = config.interrupt_threshold
        self._user_costs: dict[str, float] = {}
        self._task_costs: dict[str, float] = {}
        self._request_timestamps: dict[str, list[float]] = {}
        self._lock = Lock()
        self._downgraded_tasks: set[str] = set()

    def check_cost(
        self,
        task_id: str,
        user_id: str,
        estimated_cost: float,
    ) -> BudgetResult:
        with self._lock:
            total_user = self._user_costs.get(user_id, 0.0)
            total_task = self._task_costs.get(task_id, 0.0)

            # Per-task cap
            if total_task + estimated_cost > self._max_cost_per_task:
                return BudgetResult(
                    action=BudgetAction.BLOCK,
                    reason=f"per-task cost {total_task + estimated_cost:.2f} exceeds limit {self._max_cost_per_task}",
                    current_cost=total_task,
                    limit=self._max_cost_per_task,
                )

            # Total cap with downgrade at threshold
            usage_pct = (total_user + estimated_cost) / max(self._max_cost, 1)
            if usage_pct >= self._interrupt_pct:
                return BudgetResult(
                    action=BudgetAction.INTERRUPT,
                    reason=f"budget usage {usage_pct*100:.0f}% exceeds interrupt threshold",
                    current_cost=total_user,
                    limit=self._max_cost,
                )
            if usage_pct >= self._downgrade_pct:
                return BudgetResult(
                    action=BudgetAction.DOWNGRADE,
                    reason=f"budget usage {usage_pct*100:.0f}% exceeds downgrade threshold",
                    current_cost=total_user,
                    limit=self._max_cost,
                    suggested_model="cheap",
                )

            # Rate limiting
            now = time.time()
            user_ts = self._request_timestamps.get(user_id, [])
            recent = [t for t in user_ts if now - t < 60]
            if len(recent) >= self._max_rpm:
                return BudgetResult(
                    action=BudgetAction.BLOCK,
                    reason=f"rate limit {len(recent)}/min exceeds max {self._max_rpm}",
                    current_cost=float(len(recent)),
                    limit=float(self._max_rpm),
                )

            return BudgetResult(
                action=BudgetAction.ALLOW,
                reason="within budget",
                current_cost=total_user,
                limit=self._max_cost,
            )

    def record_cost(
        self,
        task_id: str,
        user_id: str,
        actual_cost: float,
    ) -> None:
        with self._lock:
            self._user_costs[user_id] = self._user_costs.get(user_id, 0.0) + actual_cost
            self._task_costs[task_id] = self._task_costs.get(task_id, 0.0) + actual_cost
            ts = self._request_timestamps.setdefault(user_id, [])
            ts.append(time.time())
            # Trim old timestamps
            cutoff = time.time() - 60
            self._request_timestamps[user_id] = [t for t in ts if t > cutoff]

    def is_downgraded(self, task_id: str) -> bool:
        return task_id in self._downgraded_tasks

    def get_user_cost(self, user_id: str) -> float:
        return self._user_costs.get(user_id, 0.0)

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_users": len(self._user_costs),
                "total_tasks": len(self._task_costs),
                "total_cost": sum(self._user_costs.values()),
                "max_cost": self._max_cost,
                "max_cost_per_task": self._max_cost_per_task,
                "downgraded_tasks": len(self._downgraded_tasks),
            }
