"""
MAREF Execution Harness

Unified scheduler and executor for LoopBase instances. Wraps loops in
LoopGovernanceBridge for governance integration, manages concurrency,
and provides status tracking.

Usage:
    harness = Harness(max_concurrent=4)
    task_id = await harness.submit(loop, input_data, name="my-task")
    await harness.start()
    status = harness.get_status(task_id)
    await harness.cancel(task_id)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from maref.execution.types import LoopTask, LoopTaskStatus
from maref.governance.audit import AuditLogger
from maref.loop.base import LoopBase
from maref.loop.bridge import LoopGovernanceBridge

logger = logging.getLogger(__name__)


class Harness:
    """Concurrent loop scheduler with governance integration.

    Manages the lifecycle of LoopBase instances: submission, execution
    (wrapped in LoopGovernanceBridge), status tracking, and cancellation.
    """

    def __init__(
        self,
        max_concurrent: int = 4,
        audit_logger: AuditLogger | None = None,
        bridge: LoopGovernanceBridge | None = None,
    ) -> None:
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._bridge = bridge or LoopGovernanceBridge(audit_logger=audit_logger)
        self._tasks: dict[str, LoopTask] = {}
        self._running_tasks: dict[str, asyncio.Task[Any]] = {}
        self._lock = asyncio.Lock()

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    async def submit(
        self,
        loop: LoopBase,
        input_data: Any,
        name: str = "",
    ) -> str:
        """Submit a loop for governance-wrapped execution.

        Returns the task ID immediately; the loop runs asynchronously.
        """
        task_id = _new_id()
        loop_task = LoopTask(
            id=task_id,
            name=name or f"{type(loop).__name__}-{task_id[:8]}",
            loop_type=type(loop).__name__,
            input_preview=str(input_data)[:100],
        )
        async with self._lock:
            self._tasks[task_id] = loop_task

        run_task = asyncio.create_task(self._run_governed(loop, input_data, loop_task))
        async with self._lock:
            self._running_tasks[task_id] = run_task

        logger.info("Harness submitted task=%s type=%s", task_id, loop_task.loop_type)
        return task_id

    async def _run_governed(
        self,
        loop: LoopBase,
        input_data: Any,
        loop_task: LoopTask,
    ) -> None:
        async with self._semaphore:
            loop_task.status = LoopTaskStatus.RUNNING
            loop_task.started_at = time.time()
            try:
                result = await self._bridge.run_governed(
                    loop,
                    input_data,
                    task_id=loop_task.id,
                )
                loop_task.status = LoopTaskStatus.COMPLETED
                loop_task.rounds_completed = result.rounds_completed
                loop_task.stop_reason = result.stop_reason.value
                logger.info(
                    "Harness completed task=%s rounds=%d reason=%s",
                    loop_task.id,
                    result.rounds_completed,
                    result.stop_reason,
                )
            except asyncio.CancelledError:
                loop_task.status = LoopTaskStatus.CANCELLED
                loop_task.error = "cancelled"
                logger.info("Harness cancelled task=%s", loop_task.id)
            except Exception as exc:
                loop_task.status = LoopTaskStatus.FAILED
                loop_task.error = str(exc)
                logger.error("Harness failed task=%s: %s", loop_task.id, exc)
            finally:
                loop_task.completed_at = time.time()
                async with self._lock:
                    self._running_tasks.pop(loop_task.id, None)

    def get_status(self, task_id: str) -> LoopTask | None:
        return self._tasks.get(task_id)

    def list_tasks(self, status: LoopTaskStatus | None = None) -> list[LoopTask]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    async def cancel(self, task_id: str) -> bool:
        async with self._lock:
            run_task = self._running_tasks.get(task_id)
            if run_task is None:
                return False
            run_task.cancel()
            loop_task = self._tasks.get(task_id)
            if loop_task and loop_task.status == LoopTaskStatus.PENDING:
                loop_task.status = LoopTaskStatus.CANCELLED
            return True

    async def cancel_all(self) -> int:
        async with self._lock:
            ids = list(self._running_tasks.keys())
        count = 0
        for tid in ids:
            if await self.cancel(tid):
                count += 1
        return count

    def get_stats(self) -> dict[str, Any]:
        all_tasks = list(self._tasks.values())
        return {
            "max_concurrent": self._max_concurrent,
            "total_submitted": len(all_tasks),
            "running": sum(1 for t in all_tasks if t.status == LoopTaskStatus.RUNNING),
            "completed": sum(1 for t in all_tasks if t.status == LoopTaskStatus.COMPLETED),
            "failed": sum(1 for t in all_tasks if t.status == LoopTaskStatus.FAILED),
            "cancelled": sum(1 for t in all_tasks if t.status == LoopTaskStatus.CANCELLED),
            "pending": sum(1 for t in all_tasks if t.status == LoopTaskStatus.PENDING),
        }

    async def wait_all(self) -> None:
        async with self._lock:
            pending = list(self._running_tasks.values())
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


def _new_id() -> str:
    import uuid

    return uuid.uuid4().hex[:12]
