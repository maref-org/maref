# Copyright 2026 MAREF Team
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileNotice: Patent disclosures apply to core FSM implementations. See NOTICE file for details.

"""Governance-aware scheduler wrapper.

Wraps a standard Scheduler with additional governance safeguards:
- Automatic AuditBus subscription/unsubscription lifecycle management
- Pre-flight agent health checks before task allocation
- Graceful degradation when governance events are received
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from maref.executor.scheduler import Scheduler
from maref.executor.types import Task

logger = logging.getLogger(__name__)


class GovernanceAwareScheduler:
    """A governance-aware wrapper around the base Scheduler.

    Provides a higher-level interface that ensures:
    1. The scheduler is always connected to the AuditBus when active.
    2. Task allocation can be filtered by agent health.
    3. HALT/circuit-open states are observable by external callers.

    Usage:
        bus = AuditBus()
        base_scheduler = Scheduler(task_queue, bus=bus)
        gov_scheduler = GovernanceAwareScheduler(base_scheduler)
        gov_scheduler.start()
        # ... later ...
        gov_scheduler.stop()
    """

    def __init__(self, scheduler: Scheduler) -> None:
        self._scheduler = scheduler

    # --- Delegated properties ---

    @property
    def halted(self) -> bool:
        """True if the underlying scheduler has been halted."""
        return self._scheduler.halted

    @property
    def faulty_agents(self) -> set[str]:
        """Set of agent IDs currently marked as faulty."""
        return self._scheduler.faulty_agents

    @property
    def running(self) -> bool:
        """True if the underlying scheduler tick loop is running."""
        return self._scheduler._running

    # --- Lifecycle ---

    def start(self) -> None:
        """Start the underlying scheduler tick loop."""
        self._scheduler.start()

    def stop(self) -> None:
        """Stop the underlying scheduler and unsubscribe from governance events."""
        self._scheduler.stop()

    # --- Job management (delegated) ---

    def add_cron_job(self, name: str, cron_expr: str, task_template: Task) -> str:
        """Add a cron job to the underlying scheduler."""
        return self._scheduler.add_cron_job(name, cron_expr, task_template)

    def remove_job(self, job_id: str) -> bool:
        """Remove a cron job from the underlying scheduler."""
        return self._scheduler.remove_job(job_id)

    def list_jobs(self) -> list[Any]:
        """List all cron jobs in the underlying scheduler."""
        return self._scheduler.list_jobs()

    def get_job(self, job_id: str) -> Any | None:
        """Get a specific cron job from the underlying scheduler."""
        return self._scheduler.get_job(job_id)

    # --- Agent health filtering ---

    def is_agent_healthy(self, agent_id: str) -> bool:
        """Return True if the agent is not in the faulty list."""
        return agent_id not in self.faulty_agents

    def filter_tasks_for_healthy_agents(
        self, tasks: list[Task], agent_resolver: Callable[[Task], str | None]
    ) -> list[Task]:
        """Filter a list of tasks, keeping only those bound to healthy agents.

        Args:
            tasks: Candidate tasks to filter.
            agent_resolver: Callable that extracts an agent_id from a Task.
                Should return None if the task is not agent-bound.

        Returns:
            Tasks whose resolved agent is healthy (or not agent-bound).
        """
        healthy: list[Task] = []
        for task in tasks:
            agent_id = agent_resolver(task)
            if agent_id is None or self.is_agent_healthy(agent_id):
                healthy.append(task)
            else:
                logger.debug(
                    "Task %s skipped: agent %s is faulty", task.id, agent_id
                )
        return healthy

    # --- Event handling (forwarded) ---

    def register_event(self, event_type: str, handler: Any) -> str:
        """Register an event handler on the underlying scheduler."""
        return self._scheduler.register_event(event_type, handler)

    def trigger_event(self, event_type: str, data: dict[str, Any]) -> bool:
        """Trigger an event on the underlying scheduler."""
        return self._scheduler.trigger_event(event_type, data)

    # --- Internal access (for advanced use) ---

    @property
    def _underlying(self) -> Scheduler:
        """Direct access to the wrapped Scheduler instance."""
        return self._scheduler
