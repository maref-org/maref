"""Multi-Agent 协作框架基础数据结构与配置。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentRole(str, Enum):
    MANAGER = "manager"
    WORKER = "worker"
    REFLECTOR = "reflector"
    NOTETAKER = "notetaker"


class SubTaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class AgentMessage:
    sender: AgentRole
    recipient: AgentRole
    content: str = ""
    timestamp: float = field(default_factory=time.time)
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_agent: str = ""


@dataclass
class AgentContext:
    start_time: float = field(default_factory=time.time)
    notes: list[str] = field(default_factory=list)
    current_step: int = 0

    def add_note(self, note: str) -> None:
        self.notes.append(f"[step {self.current_step}] {note}")

    def get_context_summary(self) -> dict[str, Any]:
        return {"total_notes": len(self.notes), "current_step": self.current_step}


@dataclass
class SubTask:
    step_index: int = 0
    instruction: str = ""
    action_type: str = ""
    target_text: str = ""
    status: SubTaskStatus = SubTaskStatus.PENDING
    worker_result: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "instruction": self.instruction,
            "action_type": self.action_type,
            "target_text": self.target_text,
            "status": self.status.value if isinstance(self.status, SubTaskStatus) else self.status,
            "worker_result": self.worker_result,
            "error": self.error,
        }


@dataclass
class TaskPlan:
    original_instruction: str = ""
    sub_tasks: list[SubTask] = field(default_factory=list)
    complexity_score: float = 0.0

    @property
    def total_steps(self) -> int:
        return len(self.sub_tasks)

    @property
    def completed_steps(self) -> int:
        return sum(1 for t in self.sub_tasks if t.status == SubTaskStatus.SUCCESS)

    @property
    def success_rate(self) -> float:
        if self.total_steps == 0:
            return 0.0
        return self.completed_steps / self.total_steps

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_instruction": self.original_instruction,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "success_rate": self.success_rate,
            "complexity_score": self.complexity_score,
            "sub_tasks": [t.to_dict() for t in self.sub_tasks],
        }


@dataclass
class MultiAgentConfig:
    enabled: bool = True
    max_steps: int = 10
    max_reflection_rounds: int = 2
    worker_mode: str = "vlm_fallback"
    verbose: bool = True
