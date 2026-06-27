from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

TInput = TypeVar("TInput", bound=BaseModel)
TOutput = TypeVar("TOutput", bound=BaseModel)


class ToolResultStatus(Enum):
    SUCCESS = "success"
    ERROR = "error"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"


@dataclass
class ToolContext:
    agent_id: str = ""
    session_id: str = ""
    permission_mode: str = "governed"
    workspace_root: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    is_valid: bool = True
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class PermissionResult:
    granted: bool = True
    mode: str = "allow"
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult(Generic[TOutput]):
    status: ToolResultStatus = ToolResultStatus.SUCCESS
    data: TOutput | None = None
    error: str = ""
    duration_ms: float = 0.0
    truncated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.status == ToolResultStatus.SUCCESS

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "truncated": self.truncated,
            "metadata": self.metadata,
        }


class Tool(ABC, Generic[TInput, TOutput]):
    name: str = ""
    description: str = ""
    input_schema: type[TInput] | None = None
    output_schema: type[TOutput] | None = None
    max_result_chars: int = 30_000
    requires_user_interaction: bool = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.name:
            cls.name = cls.__name__.lower()

    @abstractmethod
    async def validate(self, input: TInput) -> ValidationResult:
        ...

    async def check_permissions(self, input: TInput, ctx: ToolContext) -> PermissionResult:
        return PermissionResult(granted=True)

    @abstractmethod
    async def call(self, input: TInput, ctx: ToolContext) -> ToolResult[TOutput]:
        ...

    def is_read_only(self, input: TInput) -> bool:
        return False

    def is_concurrency_safe(self, input: TInput) -> bool:
        return False

    def result_for_llm(self, output: TOutput) -> str:
        return str(output)

    def result_for_user(self, output: TOutput) -> str:
        return str(output)

    async def execute(self, input: TInput, ctx: ToolContext) -> ToolResult[TOutput]:
        start = time.monotonic()
        try:
            validation = await self.validate(input)
            if not validation.is_valid:
                return ToolResult(
                    status=ToolResultStatus.BLOCKED,
                    error=f"Validation failed: {validation.message}",
                    metadata={"validation": validation.details},
                )
            permission = await self.check_permissions(input, ctx)
            if not permission.granted:
                return ToolResult(
                    status=ToolResultStatus.BLOCKED,
                    error=f"Permission denied: {permission.reason}",
                    metadata={"permission": permission.details},
                )
            result = await self.call(input, ctx)
            result.duration_ms = (time.monotonic() - start) * 1000
            return result
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=str(e),
                duration_ms=(time.monotonic() - start) * 1000,
            )
