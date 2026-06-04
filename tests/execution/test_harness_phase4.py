"""Phase 4 测试：工具标准化 — ToolOrchestrator + Harness 集成。"""

from __future__ import annotations

from typing import Any

from maref import HarnessAbortedError, HarnessConfig, HarnessHookRegistry, PermissionHook, ToolOrchestrator, ToolResult, ToolSpec, UnifiedHarness
from maref.integration.mcp_client import MCPClient
from maref.recursive.hook_registry import HookResult, HookVerdict


# ── ToolOrchestrator ────────────────────────────────────────────────────────

class TestToolOrchestrator:
    def test_register_and_list(self) -> None:
        o = ToolOrchestrator()
        o.register("echo", lambda p: p, ToolSpec(name="echo", description="echoes input"))
        tools = o.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "echo"

    def test_execute_success(self) -> None:
        o = ToolOrchestrator()

        def double(args: dict[str, Any]) -> int:
            return args["x"] * 2

        o.register("double", double, ToolSpec(name="double"))
        result = o.execute("double", {"x": 21})
        assert result.success
        assert result.output == 42

    def test_execute_unknown_tool(self) -> None:
        o = ToolOrchestrator()
        result = o.execute("nonexistent", {})
        assert not result.success
        assert "unknown" in result.error

    def test_execute_handler_error(self) -> None:
        o = ToolOrchestrator()

        def crash(args: dict[str, Any]) -> None:
            raise RuntimeError("boom")

        o.register("crash", crash, ToolSpec(name="crash"))
        result = o.execute("crash", {})
        assert not result.success
        assert "boom" in result.error

    def test_get_spec(self) -> None:
        o = ToolOrchestrator()
        spec = ToolSpec(name="test", description="a test tool")
        o.register("test", lambda p: p, spec)
        assert o.get_spec("test") is spec
        assert o.get_spec("nope") is None

    def test_execute_duration_ms_set(self) -> None:
        o = ToolOrchestrator()

        def slow(args: dict[str, Any]) -> str:
            import time
            time.sleep(0.01)
            return "done"

        o.register("slow", slow, ToolSpec(name="slow"))
        result = o.execute("slow", {})
        assert result.duration_ms >= 5

    def test_register_duplicate_overwrites(self) -> None:
        o = ToolOrchestrator()
        o.register("x", lambda p: "first", ToolSpec(name="x"))
        o.register("x", lambda p: "second", ToolSpec(name="x"))
        result = o.execute("x", {})
        assert result.output == "second"


# ── Permission Hook 集成 ────────────────────────────────────────────────────

class TestToolOrchestratorWithHooks:
    def test_permission_hook_blocks_destructive(self) -> None:
        reg = HarnessHookRegistry()
        PermissionHook(reg)
        o = ToolOrchestrator(hook_registry=reg)
        o.register("rm", lambda p: "deleted", ToolSpec(name="rm"))
        result = o.execute("rm", {"args": "rm -rf /"})
        assert not result.success
        assert "permission denied" in result.error

    def test_permission_hook_allows_safe(self) -> None:
        reg = HarnessHookRegistry()
        PermissionHook(reg)
        o = ToolOrchestrator(hook_registry=reg)
        o.register("read", lambda p: "content", ToolSpec(name="read"))
        result = o.execute("read", {"path": "/safe/file"})
        assert result.success

    def test_no_hook_registry_passes_through(self) -> None:
        o = ToolOrchestrator()
        o.register("anything", lambda p: "ok", ToolSpec(name="anything"))
        result = o.execute("anything", {"danger": "rm -rf /"})
        assert result.success


# ── UnifiedHarness 集成 ─────────────────────────────────────────────────────

class TestUnifiedHarnessToolIntegration:
    def test_tool_orchestrator_in_constructor(self) -> None:
        o = ToolOrchestrator()
        h = UnifiedHarness(tool_orchestrator=o)
        assert h._tool_orchestrator is o

    def test_tool_orchestrator_accessible(self) -> None:
        o = ToolOrchestrator()
        h = UnifiedHarness(tool_orchestrator=o)
        h.configure(HarnessConfig())
        h.preflight()
        h.run()
