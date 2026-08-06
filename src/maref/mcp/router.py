from __future__ import annotations

from typing import Any

from maref.tool.base import Tool
from maref.tool.context import ToolUseContext
from maref.tool.registry import ToolRegistry


def tool_to_mcp_definition(tool: Tool[Any]) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "inputSchema": tool.input_schema,
    }


def _run_async_from_sync(coro: Any) -> Any:
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor():
                future = asyncio.run_coroutine_threadsafe(coro, loop)
                return future.result()
    except RuntimeError:
        pass
    return asyncio.run(coro)


class MCPServerAdapter:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self._context = ToolUseContext.default()

    def list_tools(self) -> list[dict[str, Any]]:
        return [tool_to_mcp_definition(t) for t in self._registry.list_tools()]

    def handle_tool_call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = self._registry.get(name)
        if tool is None:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
            }
        try:
            result = _run_async_from_sync(tool.execute(arguments, self._context))
            if result.error:
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": result.error}],
                }
            return {
                "content": [{"type": "text", "text": str(result.data)}],
            }
        except Exception as e:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Tool execution failed: {e}"}],
            }
