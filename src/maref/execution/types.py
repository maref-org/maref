from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LoopTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class ScheduleType(str, Enum):
    IMMEDIATE = "immediate"
    DELAYED = "delayed"
    CRON = "cron"
    INTERVAL = "interval"


@dataclass
class ScheduleSpec:
    type: ScheduleType = ScheduleType.IMMEDIATE
    delay_seconds: float = 0.0
    cron_expression: str = ""
    interval_seconds: float = 0.0
    max_runs: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "delay_seconds": self.delay_seconds,
            "cron_expression": self.cron_expression,
            "interval_seconds": self.interval_seconds,
            "max_runs": self.max_runs,
        }


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class LoopTask:
    id: str = field(default_factory=_new_id)
    name: str = ""
    loop_type: str = ""
    status: LoopTaskStatus = LoopTaskStatus.PENDING
    input_preview: str = ""
    schedule: str = "immediate"
    error: str | None = None
    rounds_completed: int = 0
    stop_reason: str = ""
    created_at: float = field(default_factory=__import__("time").time)
    started_at: float | None = None
    completed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "loop_type": self.loop_type,
            "status": self.status.value,
            "input_preview": self.input_preview[:100],
            "schedule": self.schedule,
            "error": self.error,
            "rounds_completed": self.rounds_completed,
            "stop_reason": self.stop_reason,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }
