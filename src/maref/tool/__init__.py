"""MAREF Tool interface — unified capability abstraction for Self-* modules."""

from maref.tool.base import Tool, ToolResult
from maref.tool.context import ToolUseContext
from maref.tool.registry import ToolRegistry

__all__ = [
    "Tool",
    "ToolResult",
    "ToolUseContext",
    "ToolRegistry",
]
