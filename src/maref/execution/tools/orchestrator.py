"""ToolOrchestrator — 统一工具调用入口。

作为 UnifiedHarness 的工具调用中枢，将工具执行与 Hook 权限检查连接。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolSpec:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    source: str = "local"  # "local" | "mcp"


@dataclass
class ToolResult:
    success: bool = True
    output: Any = None
    error: str | None = None
    duration_ms: float = 0.0


class ToolOrchestrator:
    """统一工具调度：注册 → 权限检查 → 执行 → 结果返回。"""

    def __init__(self, hook_registry: Any = None) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, Callable[[dict[str, Any]], Any]] = {}
        self._hook_registry = hook_registry

    def register(self, name: str, handler: Callable[[dict[str, Any]], Any], spec: ToolSpec) -> None:
        self._specs[name] = spec
        self._handlers[name] = handler

    def register_mcp(self, client: Any, conn: Any) -> int:
        """注册 MCP 连接中的所有工具。返回注册的工具数。"""
        try:
            tools = client.list_tools(conn)
        except Exception:
            return 0
        count = 0
        for t in tools:
            spec = ToolSpec(name=t.name, description=t.description, input_schema=t.input_schema, source="mcp")

            def make_handler(tool_name: str) -> Callable[[dict[str, Any]], Any]:
                def handler(args: dict[str, Any]) -> Any:
                    resp = client.call_tool(conn, tool_name, args)
                    if resp.is_error:
                        raise RuntimeError(resp.error.get("message", str(resp.error)))
                    return resp.result
                return handler

            if spec.name not in self._specs:
                self._specs[spec.name] = spec
                self._handlers[spec.name] = make_handler(spec.name)
                count += 1
        return count

    def execute(self, name: str, params: dict[str, Any] | None = None) -> ToolResult:
        if name not in self._handlers:
            return ToolResult(success=False, error=f"unknown tool: {name}")

        if self._hook_registry:
            result = self._hook_registry.fire("harness.tool_call", {"tool": name, "args": str(params or {})})
            if not result.passed:
                return ToolResult(success=False, error=f"permission denied: {result.error or 'blocked by hook'}")

        start = time.time()
        try:
            output = self._handlers[name](params or {})
            elapsed = (time.time() - start) * 1000
            return ToolResult(success=True, output=output, duration_ms=elapsed)
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return ToolResult(success=False, error=str(e), duration_ms=elapsed)

    def list_tools(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def get_spec(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)
