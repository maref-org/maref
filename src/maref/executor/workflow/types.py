from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class StepStatus(Enum):
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStatus(Enum):
    COMPLETED = "completed"
    FAILED = "failed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class WorkflowStep:
    name: str = ""
    description: str = ""
    agent_role: str = ""
    input_template: str = ""
    validator_prompt: str = ""
    timeout_seconds: float = 0.0
    max_retries: int = 0
    depends_on: list[str] = field(default_factory=list)
    fallback_step: str = ""
    parallel_group: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "agent_role": self.agent_role,
            "input_template": self.input_template,
            "validator_prompt": self.validator_prompt,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "depends_on": list(self.depends_on),
            "fallback_step": self.fallback_step,
            "parallel_group": self.parallel_group,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowStep:
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            agent_role=data.get("agent_role", ""),
            input_template=data.get("input_template", ""),
            validator_prompt=data.get("validator_prompt", ""),
            timeout_seconds=data.get("timeout_seconds", 0.0),
            max_retries=data.get("max_retries", 0),
            depends_on=list(data.get("depends_on", [])),
            fallback_step=data.get("fallback_step", ""),
            parallel_group=data.get("parallel_group", ""),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class WorkflowScript:
    id: str = field(default_factory=_new_id)
    name: str = ""
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    max_concurrency: int = 4
    checkpoint_interval: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def step_names(self) -> list[str]:
        return [s.name for s in self.steps]

    def get_step(self, name: str) -> WorkflowStep | None:
        for s in self.steps:
            if s.name == name:
                return s
        return None

    def parallel_groups(self) -> dict[str, list[WorkflowStep]]:
        groups: dict[str, list[WorkflowStep]] = {}
        for s in self.steps:
            pg = s.parallel_group or f"__seq_{s.name}"
            groups.setdefault(pg, []).append(s)
        return groups

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "max_concurrency": self.max_concurrency,
            "checkpoint_interval": self.checkpoint_interval,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowScript:
        return cls(
            id=data.get("id", _new_id()),
            name=data.get("name", ""),
            description=data.get("description", ""),
            steps=[WorkflowStep.from_dict(s) for s in data.get("steps", [])],
            max_concurrency=data.get("max_concurrency", 4),
            checkpoint_interval=data.get("checkpoint_interval", 0),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class StepResult:
    step_name: str = ""
    status: StepStatus = StepStatus.COMPLETED
    started_at: str = ""
    completed_at: str = ""
    output: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowResult:
    script_id: str = ""
    status: WorkflowStatus = WorkflowStatus.COMPLETED
    started_at: str = ""
    completed_at: str = ""
    step_results: list[StepResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    final_output: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        total = len(self.step_results)
        completed = sum(1 for s in self.step_results if s.status == StepStatus.COMPLETED)
        failed = sum(1 for s in self.step_results if s.status == StepStatus.FAILED)
        return {
            "status": self.status.value,
            "steps": {"total": total, "completed": completed, "failed": failed},
            "total_duration_ms": self.total_duration_ms,
        }

    def failed_steps(self) -> list[StepResult]:
        return [s for s in self.step_results if s.status == StepStatus.FAILED]

    def get_step_result(self, name: str) -> StepResult | None:
        for s in self.step_results:
            if s.step_name == name:
                return s
        return None


@dataclass
class WorkflowCheckpoint:
    id: str = field(default_factory=_new_id)
    script: WorkflowScript = field(default_factory=WorkflowScript)
    last_completed_step: int = 0
    step_results: list[StepResult] = field(default_factory=list)
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "script": self.script.to_dict(),
            "last_completed_step": self.last_completed_step,
            "step_results": [
                {
                    "step_name": sr.step_name,
                    "status": sr.status.value,
                    "started_at": sr.started_at,
                    "completed_at": sr.completed_at,
                    "output": sr.output,
                    "error_message": sr.error_message,
                    "duration_ms": sr.duration_ms,
                }
                for sr in self.step_results
            ],
            "created_at": self.created_at,
        }
