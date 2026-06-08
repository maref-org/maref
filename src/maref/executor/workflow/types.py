from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"


class WorkflowStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIALLY_COMPLETED = "partially_completed"
    CANCELLED = "cancelled"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class WorkflowStep:
    """单个工作流步骤。

    - 顺序步骤: depends_on 为空列表, 在上一步之后执行
    - 并行步骤: 相同 parallel_group 的步骤同时执行
    - 条件回退: fallback_step 在主步骤失败时执行
    """
    name: str
    description: str = ""
    agent_role: str = ""  # 对应 WorkerPool 注册的 handler 名称
    input_template: str = ""  # 输入模板, 支持 {placeholder} 替换
    validator_prompt: str = ""  # 验证 prompt, 为空则跳过验证
    timeout_seconds: float | None = None
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
            "depends_on": self.depends_on,
            "fallback_step": self.fallback_step,
            "parallel_group": self.parallel_group,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowStep:
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            agent_role=data.get("agent_role", ""),
            input_template=data.get("input_template", ""),
            validator_prompt=data.get("validator_prompt", ""),
            timeout_seconds=data.get("timeout_seconds"),
            max_retries=data.get("max_retries", 0),
            depends_on=data.get("depends_on", []),
            fallback_step=data.get("fallback_step", ""),
            parallel_group=data.get("parallel_group", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class WorkflowScript:
    """编排脚本 — 一组有序/并行步骤的有向无环图。"""
    id: str = field(default_factory=_new_id)
    name: str = ""
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    max_concurrency: int = 4
    checkpoint_interval: int = 5  # 每 N 个步骤创建一次检查点
    created_at: str = field(default_factory=_now)
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
            if s.parallel_group:
                groups.setdefault(s.parallel_group, []).append(s)
        return groups

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "max_concurrency": self.max_concurrency,
            "checkpoint_interval": self.checkpoint_interval,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowScript:
        return cls(
            id=data.get("id", _new_id()),
            name=data.get("name", ""),
            description=data.get("description", ""),
            steps=[WorkflowStep.from_dict(s) for s in data.get("steps", [])],
            max_concurrency=data.get("max_concurrency", 4),
            checkpoint_interval=data.get("checkpoint_interval", 5),
            created_at=data.get("created_at", _now()),
            metadata=data.get("metadata", {}),
        )


@dataclass
class StepResult:
    """单个步骤的执行结果。"""
    step_name: str
    status: StepStatus = StepStatus.PENDING
    started_at: str = ""
    completed_at: str = ""
    output: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowResult:
    """整个编排脚本的执行结果。"""
    script_id: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    started_at: str = field(default_factory=_now)
    completed_at: str = ""
    step_results: list[StepResult] = field(default_factory=list)
    final_output: dict[str, Any] = field(default_factory=dict)
    total_duration_ms: float = 0.0
    error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_step_result(self, name: str) -> StepResult | None:
        for sr in self.step_results:
            if sr.step_name == name:
                return sr
        return None

    def failed_steps(self) -> list[StepResult]:
        return [sr for sr in self.step_results if sr.status in (StepStatus.FAILED, StepStatus.TIMEOUT)]

    def summary(self) -> dict[str, Any]:
        total = len(self.step_results)
        completed = sum(1 for sr in self.step_results if sr.status == StepStatus.COMPLETED)
        failed = len(self.failed_steps())
        return {
            "script_id": self.script_id,
            "status": self.status.value,
            "steps": {"total": total, "completed": completed, "failed": failed},
            "total_duration_ms": self.total_duration_ms,
            "error": self.error_message if self.error_message else None,
        }


# 检查点快照
@dataclass
class WorkflowCheckpoint:
    id: str = field(default_factory=_new_id)
    script: WorkflowScript = field(default_factory=WorkflowScript)
    last_completed_step: int = -1  # 最后成功完成的步骤索引
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
