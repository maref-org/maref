from __future__ import annotations

from typing import Any

from maref.tool.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool[Any]] = {}

    def register(self, tool: Tool[Any]) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool[Any] | None:
        return self._tools.get(name)

    def list_tools(self) -> list[Tool[Any]]:
        return list(self._tools.values())

    def remove(self, name: str) -> None:
        self._tools.pop(name, None)

    def clear(self) -> None:
        self._tools.clear()

    @property
    def count(self) -> int:
        return len(self._tools)
