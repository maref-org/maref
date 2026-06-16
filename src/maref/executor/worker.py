from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from maref.executor.queue import TaskQueue
from maref.executor.types import Task, TaskStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


HandlerType = Callable[[Task], None]


class WorkerPool:
    def __init__(self, task_queue: TaskQueue, num_workers: int = 4) -> None:
        self._queue = task_queue
        self._num_workers = num_workers
        self._workers: list[threading.Thread] = []
        self._handlers: dict[str, HandlerType] = {}
        self._default_handler: HandlerType = lambda t: None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._tasks_processed: int = 0
        self._tasks_failed: int = 0
        self._lock = threading.Lock()

    def register_handler(self, name: str, handler: HandlerType) -> None:
        self._handlers[name] = handler

    def start(self) -> None:
        self._stop_event.clear()
        self._pause_event.clear()
        self._workers = []
        for i in range(self._num_workers):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"worker-{i}",
                daemon=True,
            )
            t.start()
            self._workers.append(t)

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        for w in self._workers:
            w.join(timeout=timeout)

    def submit(self, task: Task) -> str:
        return self._queue.enqueue(task)

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            active = sum(1 for w in self._workers if w.is_alive())
        stats = self._queue.stats()
        return {
            "running": not self._stop_event.is_set(),
            "paused": self._pause_event.is_set(),
            "active_workers": active,
            "total_workers": self._num_workers,
            "tasks_processed": self._tasks_processed,
            "tasks_failed": self._tasks_failed,
            "queue": stats,
        }

    def pause(self) -> None:
        self._pause_event.set()

    def resume(self) -> None:
        self._pause_event.clear()

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._pause_event.is_set():
                time.sleep(0.05)
                continue
            tasks = self._queue.dequeue(limit=1)
            if not tasks:
                time.sleep(0.05)
                continue
            if self._pause_event.is_set():
                self._queue.update_status(tasks[0].id, TaskStatus.QUEUED, started_at=None)
                time.sleep(0.05)
                continue
            task = tasks[0]
            self._execute_task(task)

    def _find_handler(self, task: Task) -> HandlerType:
        handler = self._handlers.get(task.name)
        if handler is not None:
            return handler
        return self._default_handler

    def _execute_task(self, task: Task) -> None:
        handler = self._find_handler(task)
        timeout = task.timeout_seconds
        if timeout is not None and timeout > 0:
            result: list[bool | None] = [None]
            exc_info: list[BaseException | None] = [None]

            def run_with_capture() -> None:
                try:
                    handler(task)
                    result[0] = True
                except BaseException as e:
                    exc_info[0] = e
                    result[0] = False

            runner = threading.Thread(target=run_with_capture, daemon=True)
            runner.start()
            runner.join(timeout=timeout)
            if runner.is_alive():
                with self._lock:
                    self._tasks_processed += 1
                self._queue.update_status(
                    task.id,
                    TaskStatus.TIMEOUT,
                    error_message=f"Task timed out after {timeout}s",
                    completed_at=_now(),
                )
                return
            if result[0] is True:
                with self._lock:
                    self._tasks_processed += 1
                self._queue.update_status(
                    task.id,
                    TaskStatus.COMPLETED,
                    completed_at=_now(),
                )
                return
            if result[0] is False and exc_info[0] is not None:
                self._handle_failure(task, exc_info[0])
                return
        else:
            try:
                handler(task)
                with self._lock:
                    self._tasks_processed += 1
                self._queue.update_status(
                    task.id,
                    TaskStatus.COMPLETED,
                    completed_at=_now(),
                )
            except BaseException as e:
                self._handle_failure(task, e)

    def _handle_failure(self, task: Task, error: BaseException) -> None:
        task.retry_count += 1
        if task.retry_count < task.max_retries:
            task.error_message = str(error)
            self._queue.update_status(
                task.id,
                TaskStatus.QUEUED,
                error_message=str(error),
                retry_count=task.retry_count,
                started_at=None,
            )
        else:
            with self._lock:
                self._tasks_processed += 1
                self._tasks_failed += 1
            self._queue.update_status(
                task.id,
                TaskStatus.FAILED,
                error_message=str(error),
                retry_count=task.retry_count,
                completed_at=_now(),
            )
            self._queue.move_to_dlq(
                task.id,
                reason=f"Max retries ({task.max_retries}) exceeded: {error}",
            )
