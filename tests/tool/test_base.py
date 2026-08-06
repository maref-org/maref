from __future__ import annotations

from typing import Any

import pytest

from maref.tool.base import Tool, ToolResult


class EchoTool(Tool[str]):
    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echoes input"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"message": {"type": "string"}}}

    async def execute(self, input: dict[str, Any], context: Any) -> ToolResult[str]:
        msg = input.get("message", "")
        return ToolResult(data=msg)

    def is_read_only(self) -> bool:
        return True

    def is_enabled(self) -> bool:
        return True


class TestTool:
    @pytest.mark.asyncio
    async def test_tool_execute_returns_result(self) -> None:
        tool = EchoTool()
        result = await tool.execute({"message": "hello"}, None)
        assert result.success
        assert result.data == "hello"

    @pytest.mark.asyncio
    async def test_tool_result_error_property(self) -> None:
        result = ToolResult(data=None, error="something went wrong")
        assert not result.success
        assert result.error == "something went wrong"

    def test_tool_name(self) -> None:
        tool = EchoTool()
        assert tool.name == "echo"

    def test_tool_read_only(self) -> None:
        tool = EchoTool()
        assert tool.is_read_only()

    def test_tool_enabled(self) -> None:
        tool = EchoTool()
        assert tool.is_enabled()
