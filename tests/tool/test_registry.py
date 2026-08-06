from __future__ import annotations

from typing import Any

from maref.tool.base import Tool, ToolResult
from maref.tool.registry import ToolRegistry


class MockTool(Tool[str]):
    @property
    def name(self) -> str:
        return "mock"

    @property
    def description(self) -> str:
        return "mock tool"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {}

    async def execute(self, input: dict[str, Any], context: Any) -> ToolResult[str]:
        return ToolResult(data="ok")

    def is_read_only(self) -> bool:
        return True

    def is_enabled(self) -> bool:
        return True


class TestToolRegistry:
    def test_register_and_get(self) -> None:
        registry = ToolRegistry()
        tool = MockTool()
        registry.register(tool)
        assert registry.get("mock") is tool

    def test_list_tools(self) -> None:
        registry = ToolRegistry()
        registry.register(MockTool())
        assert len(registry.list_tools()) == 1
        assert registry.list_tools()[0].name == "mock"

    def test_get_nonexistent_returns_none(self) -> None:
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None

    def test_remove(self) -> None:
        registry = ToolRegistry()
        registry.register(MockTool())
        registry.remove("mock")
        assert registry.get("mock") is None

    def test_clear(self) -> None:
        registry = ToolRegistry()
        registry.register(MockTool())
        registry.clear()
        assert registry.count == 0

    def test_count(self) -> None:
        registry = ToolRegistry()
        assert registry.count == 0
        registry.register(MockTool())
        assert registry.count == 1
