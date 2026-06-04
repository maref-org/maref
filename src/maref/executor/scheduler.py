"""Cron-based and event-driven task scheduler."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from maref.executor.queue import TaskQueue
from maref.executor.types import Task


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CronExpression:
    def __init__(self, expression: str) -> None:
        self._raw = expression
        fields = expression.strip().split()
        if len(fields) != 5:
            raise ValueError(f"Invalid cron expression: {expression!r}")
        self._minutes = self._parse_field(fields[0], 0, 59)
        self._hours = self._parse_field(fields[1], 0, 23)
        self._days_of_month = self._parse_field(fields[2], 1, 31)
        self._months = self._parse_field(fields[3], 1, 12)
        self._days_of_week = self._parse_field(fields[4], 0, 7)
        self._normalize_dow()

    @staticmethod
    def _parse_field(field: str, min_val: int, max_val: int) -> list[tuple[Any, ...]]:
        parts = field.split(",")
        matchers: list[tuple[Any, ...]] = []
        for part in parts:
            part = part.strip()
            if part == "*":
                matchers.append(("any",))
            elif part.startswith("*/"):
                n = int(part[2:])
                if n <= 0:
                    raise ValueError(f"Invalid step value in cron field: {part!r}")
                matchers.append(("every", n))
            elif "-" in part:
                a_str, b_str = part.split("-", 1)
                a, b = int(a_str), int(b_str)
                if a < min_val or b > max_val or a > b:
                    raise ValueError(
                        f"Invalid range {part!r} in cron field (min={min_val}, max={max_val})"
                    )
                matchers.append(("range", a, b))
            else:
                v = int(part)
                if v < min_val or v > max_val:
                    raise ValueError(
                        f"Value {v} out of range [{min_val}, {max_val}] in cron field"
                    )
                matchers.append(("exact", v))
        return matchers

    @staticmethod
    def _matches_field(value: int, matchers: list[tuple[Any, ...]]) -> bool:
        for matcher in matchers:
            kind = matcher[0]
            if kind == "any":
                return True
            if kind == "every":
                if value % matcher[1] == 0:
                    return True
            elif kind == "range":
                if matcher[1] <= value <= matcher[2]:
                    return True
            elif kind == "exact":
                if value == matcher[1]:
                    return True
        return False

    def _normalize_dow(self) -> None:
        normalized: list[tuple[Any, ...]] = []
        for matcher in self._days_of_week:
            kind = matcher[0]
            if kind == "exact" and matcher[1] == 7:
                normalized.append(("exact", 0))
            elif kind == "range":
                a, b = matcher[1], matcher[2]
                if a <= 7 and b >= 7:
                    if a == 0:
                        normalized.append(("range", 0, 6))
                    else:
                        normalized.append(("range", a, 6))
                else:
                    normalized.append(matcher)
            else:
                normalized.append(matcher)
        self._days_of_week = normalized

    @staticmethod
    def _py_to_cron_dow(py_dow: int) -> int:
        return (py_dow + 1) % 7

    def matches(self, dt: datetime) -> bool:
        cron_dow = self._py_to_cron_dow(dt.weekday())
        return (
            self._matches_field(dt.minute, self._minutes)
            and self._matches_field(dt.hour, self._hours)
            and self._matches_field(dt.day, self._days_of_month)
            and self._matches_field(dt.month, self._months)
            and self._matches_field(cron_dow, self._days_of_week)
        )

    def next_after(self, dt: datetime) -> datetime:
        current = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(525600):
            if self.matches(current):
                return current
            current += timedelta(minutes=1)
        raise ValueError(f"No matching time found within 1 year after {dt}")

    def __repr__(self) -> str:
        return f"CronExpression({self._raw!r})"


@dataclass
class CronJob:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    cron_expression: str = ""
    task_template: Task = field(default_factory=Task)
    enabled: bool = True
    last_run: str | None = None
    next_run: str | None = None
    run_count: int = 0
    created_at: str = field(default_factory=lambda: _now().isoformat())


class Scheduler:
    def __init__(self, task_queue: TaskQueue, tick_interval: float = 60.0) -> None:
        self._queue = task_queue
        self._tick_interval = tick_interval
        self._jobs: dict[str, CronJob] = {}
        self._event_handlers: dict[str, Callable[[dict[str, Any]], None]] = {}
        self._event_ids: dict[str, str] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self.halted: bool = False
        self.faulty_agents: set[str] = set()

    def add_cron_job(self, name: str, cron_expr: str, task_template: Task) -> str:
        CronExpression(cron_expr)
        job = CronJob(
            name=name,
            cron_expression=cron_expr,
            task_template=task_template,
        )
        with self._lock:
            self._jobs[job.id] = job
        return job.id

    def remove_job(self, job_id: str) -> bool:
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                return True
            return False

    def list_jobs(self) -> list[CronJob]:
        with self._lock:
            return list(self._jobs.values())

    def get_job(self, job_id: str) -> CronJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def register_event(self, event_type: str, handler: Callable[[dict[str, Any]], None]) -> str:
        event_id = str(uuid.uuid4())
        with self._lock:
            self._event_handlers[event_type] = handler
            self._event_ids[event_id] = event_type
        return event_id

    def trigger_event(self, event_type: str, data: dict[str, Any]) -> bool:
        with self._lock:
            handler = self._event_handlers.get(event_type)
        if handler is None:
            return False
        handler(data)
        return True

    def get_next_run(self, job_id: str) -> str | None:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return None
        cron = CronExpression(job.cron_expression)
        next_dt = cron.next_after(_now())
        return next_dt.isoformat()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._tick_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _tick_loop(self) -> None:
        while self._running:
            self._tick()
            time.sleep(self._tick_interval)

    def _tick(self) -> None:
        now = _now()
        job_snapshots: list[tuple[str, CronJob]] = []
        with self._lock:
            for job_id, job in self._jobs.items():
                if job.enabled:
                    job_snapshots.append((job_id, job))
        for job_id, job in job_snapshots:
            cron = CronExpression(job.cron_expression)
            if cron.matches(now):
                new_task = self._create_task_from_template(job.task_template)
                self._queue.enqueue(new_task)
                with self._lock:
                    stored_job = self._jobs.get(job_id)
                    if stored_job is not None:
                        stored_job.last_run = now.isoformat()
                        stored_job.run_count += 1
                        try:
                            next_dt = cron.next_after(now)
                            stored_job.next_run = next_dt.isoformat()
                        except ValueError:
                            stored_job.next_run = None

    @staticmethod
    def _create_task_from_template(template: Task) -> Task:
        return Task(
            name=template.name,
            description=template.description,
            priority=template.priority,
            payload=dict(template.payload),
            metadata=dict(template.metadata),
            timeout_seconds=template.timeout_seconds,
            max_retries=template.max_retries,
            session_id=template.session_id,
            tags=list(template.tags),
        )
