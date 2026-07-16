"""
MAREF Budget Circuit Breaker

Hard limit enforcement for token/time budgets. Trips when an agent or
task exceeds its allocated budget, preventing runaway cost accumulation.

States: CLOSED -> OPEN -> HALF_OPEN -> CLOSED

Integrates with:
- BudgetGuard (allocation consumption)
- TokenBudget / TimeBudget (loop-level budgets)
- AgentEconomy (agent wallet balance)
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class BudgetBreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class BudgetBreakerTrip:
    timestamp: float
    reason: str
    agent_id: str
    budget_type: str
    limit: float
    actual: float
    action_taken: str = "force_halt"


class BudgetBreaker:
    """Hard circuit breaker for agent/task budget limits.

    Trips on:
    - Agent-wide budget exceeded (total cost > max_per_agent)
    - Single-task budget exceeded (task cost > max_per_task)
    - Burn rate exceeded (cost/hour > max_burn_rate)

    Recovery:
    - HALF_OPEN: allow 1 probe allocation
    - If probe succeeds -> CLOSED (reset)
    - If probe fails -> OPEN (extend cooldown)
    """

    def __init__(
        self,
        max_per_agent: float = 1000.0,
        max_per_task: float = 200.0,
        max_burn_rate: float = 100.0,
        cooldown_seconds: float = 60.0,
    ) -> None:
        self._max_per_agent = max_per_agent
        self._max_per_task = max_per_task
        self._max_burn_rate = max_burn_rate
        self._cooldown = cooldown_seconds
        self._lock = threading.RLock()
        self._state: dict[str, BudgetBreakerState] = {}
        self._trips: dict[str, list[BudgetBreakerTrip]] = {}
        self._last_trip_time: dict[str, float] = {}
        self._agent_spend: dict[str, float] = {}
        self._task_spend: dict[str, float] = {}
        self._agent_window: dict[str, list[tuple[float, float]]] = {}

    def _get_state(self, agent_id: str) -> BudgetBreakerState:
        return self._state.get(agent_id, BudgetBreakerState.CLOSED)

    def _set_state(self, agent_id: str, state: BudgetBreakerState) -> None:
        self._state[agent_id] = state

    def is_open(self, agent_id: str) -> bool:
        with self._lock:
            return self._get_state(agent_id) == BudgetBreakerState.OPEN

    def check_agent_budget(self, agent_id: str, total_cost: float) -> bool:
        with self._lock:
            state = self._get_state(agent_id)
            if state == BudgetBreakerState.OPEN:
                if self._should_try_half_open(agent_id):
                    self._set_state(agent_id, BudgetBreakerState.HALF_OPEN)
                    return True
                return False
            if total_cost > self._max_per_agent:
                self._trip(
                    agent_id, "agent_budget",
                    self._max_per_agent, total_cost,
                    f"Agent {agent_id} cost {total_cost:.1f} exceeds limit {self._max_per_agent}",
                )
                return False
            return True

    def check_task_budget(self, agent_id: str, task_id: str, task_cost: float) -> bool:
        with self._lock:
            state = self._get_state(agent_id)
            if state == BudgetBreakerState.OPEN:
                return False
            if task_cost > self._max_per_task:
                self._trip(
                    agent_id, "task_budget",
                    self._max_per_task, task_cost,
                    f"Task {task_id} cost {task_cost:.1f} exceeds limit {self._max_per_task}",
                )
                return False
            return True

    def check_burn_rate(self, agent_id: str, window_hours: float = 1.0) -> bool:
        with self._lock:
            state = self._get_state(agent_id)
            if state == BudgetBreakerState.OPEN:
                return False
            now = time.time()
            window = self._agent_window.get(agent_id, [])
            cutoff = now - window_hours * 3600
            recent = [(t, c) for t, c in window if t >= cutoff]
            if not recent:
                return True
            total = sum(c for _, c in recent)
            rate = total / window_hours
            if rate > self._max_burn_rate:
                self._trip(
                    agent_id, "burn_rate",
                    self._max_burn_rate, rate,
                    f"Agent {agent_id} burn rate {rate:.1f}/hr exceeds limit {self._max_burn_rate}",
                )
                return False
            return True

    def record_spend(self, agent_id: str, task_id: str, amount: float) -> None:
        with self._lock:
            self._agent_spend[agent_id] = self._agent_spend.get(agent_id, 0.0) + amount
            self._task_spend[task_id] = self._task_spend.get(task_id, 0.0) + amount
            if agent_id not in self._agent_window:
                self._agent_window[agent_id] = []
            self._agent_window[agent_id].append((time.time(), amount))
            max_window = 1000
            if len(self._agent_window[agent_id]) > max_window:
                self._agent_window[agent_id] = self._agent_window[agent_id][-max_window:]

    def get_agent_spend(self, agent_id: str) -> float:
        with self._lock:
            return self._agent_spend.get(agent_id, 0.0)

    def get_task_spend(self, task_id: str) -> float:
        with self._lock:
            return self._task_spend.get(task_id, 0.0)

    def record_success(self, agent_id: str) -> None:
        with self._lock:
            if self._get_state(agent_id) == BudgetBreakerState.HALF_OPEN:
                self._set_state(agent_id, BudgetBreakerState.CLOSED)
                logger.info("BudgetBreaker recovered agent=%s", agent_id)

    def _trip(
        self, agent_id: str, budget_type: str,
        limit: float, actual: float, reason: str,
    ) -> None:
        self._set_state(agent_id, BudgetBreakerState.OPEN)
        self._last_trip_time[agent_id] = time.time()
        trip = BudgetBreakerTrip(
            timestamp=time.time(),
            reason=reason,
            agent_id=agent_id,
            budget_type=budget_type,
            limit=limit,
            actual=actual,
        )
        if agent_id not in self._trips:
            self._trips[agent_id] = []
        self._trips[agent_id].append(trip)
        max_trips = 100
        if len(self._trips[agent_id]) > max_trips:
            self._trips[agent_id] = self._trips[agent_id][-max_trips:]
        logger.warning("BudgetBreaker tripped agent=%s type=%s limit=%.1f actual=%.1f",
                       agent_id, budget_type, limit, actual)

    def _should_try_half_open(self, agent_id: str) -> bool:
        import random
        last = self._last_trip_time.get(agent_id, 0.0)
        jitter = random.uniform(0, self._cooldown * 0.2)
        return (time.time() - last) > (self._cooldown + jitter)

    def reset(self, agent_id: str | None = None) -> None:
        with self._lock:
            if agent_id:
                self._state.pop(agent_id, None)
                self._last_trip_time.pop(agent_id, None)
                self._agent_spend.pop(agent_id, None)
            else:
                self._state.clear()
                self._last_trip_time.clear()
                self._agent_spend.clear()
                self._task_spend.clear()
                self._agent_window.clear()

    def get_stats(self, agent_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            if agent_id:
                trips = self._trips.get(agent_id, [])
                return {
                    "agent_id": agent_id,
                    "state": self._get_state(agent_id).value,
                    "total_spend": self._agent_spend.get(agent_id, 0.0),
                    "trip_count": len(trips),
                    "last_trip": trips[-1].reason if trips else None,
                    "max_per_agent": self._max_per_agent,
                    "max_burn_rate": self._max_burn_rate,
                }
            return {
                "agents": len(self._state),
                "open_count": sum(
                    1 for s in self._state.values()
                    if s == BudgetBreakerState.OPEN
                ),
                "total_trips": sum(len(t) for t in self._trips.values()),
                "max_per_agent": self._max_per_agent,
                "max_per_task": self._max_per_task,
                "max_burn_rate": self._max_burn_rate,
            }
