from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from maref.tool.context import ToolUseContext

T = TypeVar("T")


@dataclass
class ToolResult(Generic[T]):
    data: T
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.error is None


class Tool(ABC, Generic[T]):
    """Unified tool interface for all MAREF capabilities."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]: ...

    @abstractmethod
    async def execute(self, input: dict[str, Any], context: ToolUseContext) -> ToolResult[T]: ...

    @abstractmethod
    def is_read_only(self) -> bool: ...

    @abstractmethod
    def is_enabled(self) -> bool: ...
