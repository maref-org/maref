from __future__ import annotations

import pytest

from maref.mcp.router import MCPServerAdapter, tool_to_mcp_definition
from maref.tool.base import Tool, ToolResult
from maref.tool.context import ToolUseContext
from maref.tool.registry import ToolRegistry


class FakeTool(Tool[str]):
    @property
    def name(self) -> str:
        return "test_tool"

    @property
    def description(self) -> str:
        return "test"

    @property
    def input_schema(self) -> dict[str, object]:
        return {"type": "object", "properties": {}}

    async def execute(self, input: dict, context: ToolUseContext) -> ToolResult[str]:
        return ToolResult(data="ok")

    def is_read_only(self) -> bool:
        return True

    def is_enabled(self) -> bool:
        return True


class TestMCPServerAdapter:
    def setup_method(self) -> None:
        registry = ToolRegistry()
        registry.register(FakeTool())
        self.adapter = MCPServerAdapter(registry)

    def test_list_tools(self) -> None:
        tools = self.adapter.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "test_tool"

    def test_handle_tool_call_known(self) -> None:
        result = self.adapter.handle_tool_call("test_tool", {})
        assert not result.get("isError")
        assert result["content"][0]["text"] == "ok"

    def test_handle_tool_call_unknown(self) -> None:
        result = self.adapter.handle_tool_call("nonexistent", {})
        assert result["isError"]

    def test_tool_to_mcp_definition(self) -> None:
        tool = FakeTool()
        definition = tool_to_mcp_definition(tool)
        assert definition["name"] == "test_tool"
        assert "inputSchema" in definition
