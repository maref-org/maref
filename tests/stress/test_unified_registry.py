"""Tests for the Unified Tool Registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from maref.tools.tool_schema import ToolCategory, ToolDefinition, ToolRiskLevel
from maref.tools.unified_registry import (
    AgentRole,
    CapabilityType,
    FunctionCapabilityAdapter,
    HarnessCapabilityAdapter,
    HitlGate,
    PermissionMiddleware,
    PermissionRequest,
    PermissionVerdict,
    RegisteredCapability,
    RiskLevelCeiling,
    RoleCapabilityFilter,
    ToolCallContext,
    UnifiedToolRegistry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_definition(
    name: str = "test_tool",
    category: ToolCategory = ToolCategory.CUSTOM,
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW,
    tools: list[str] | None = None,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"Test tool: {name}",
        category=category,
        risk_level=risk_level,
        tools=tools or [name],
    )


def _make_function():
    """Return a test function."""
    def greet(name: str = "World") -> str:
        return f"Hello, {name}!"
    return greet


def _make_harness():
    """Return a mock harness."""
    @dataclass
    class MockHarness:
        def run(self, scenario: str = "default") -> dict[str, Any]:
            return {"scenario": scenario, "passed": True, "errors": []}

        def diagnose(self, tool_id: str) -> dict[str, Any]:
            return {"tool_id": tool_id, "status": "healthy"}
    return MockHarness()


# ---------------------------------------------------------------------------
# Tests: Registration
# ---------------------------------------------------------------------------

class TestRegistration:

    def test_register_function(self) -> None:
        registry = UnifiedToolRegistry()
        func = _make_function()
        definition = _make_definition(name="greet", risk_level=ToolRiskLevel.LOW)
        adapter = FunctionCapabilityAdapter(
            capability_id="greet",
            func=func,
            definition=definition,
        )
        cap_id = registry.register(adapter)
        assert cap_id == "greet"
        assert registry.get("greet") is not None

    def test_register_harness(self) -> None:
        registry = UnifiedToolRegistry()
        harness = _make_harness()
        definition = _make_definition(name="stress_test", category=ToolCategory.CUSTOM,
                                       risk_level=ToolRiskLevel.MEDIUM,
                                       tools=["run", "diagnose"])
        adapter = HarnessCapabilityAdapter(
            capability_id="stress_test",
            harness=harness,
            definition=definition,
        )
        cap_id = registry.register(adapter, tags=["testing", "harness"])
        assert cap_id == "stress_test"
        all_caps = registry.list_all()
        assert len(all_caps) == 1
        assert all_caps[0]["tags"] == ["testing", "harness"]

    def test_register_duplicate_raises(self) -> None:
        registry = UnifiedToolRegistry()
        func = _make_function()
        definition = _make_definition(name="dup")
        adapter = FunctionCapabilityAdapter(capability_id="dup", func=func, definition=definition)
        registry.register(adapter)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(adapter)

    def test_unregister(self) -> None:
        registry = UnifiedToolRegistry()
        func = _make_function()
        definition = _make_definition()
        adapter = FunctionCapabilityAdapter(capability_id="temp", func=func, definition=definition)
        registry.register(adapter)
        assert registry.unregister("temp") is True
        assert registry.get("temp") is None
        assert registry.unregister("nonexistent") is False

    def test_enable_disable(self) -> None:
        registry = UnifiedToolRegistry()
        func = _make_function()
        definition = _make_definition()
        adapter = FunctionCapabilityAdapter(capability_id="toggle", func=func, definition=definition)
        registry.register(adapter)
        assert registry.disable("toggle") is True
        assert registry.get("toggle") is None
        assert registry.enable("toggle") is True
        assert registry.get("toggle") is not None


# ---------------------------------------------------------------------------
# Tests: Execution
# ---------------------------------------------------------------------------

class TestExecution:

    def test_execute_function(self) -> None:
        registry = UnifiedToolRegistry()
        func = _make_function()
        definition = _make_definition(name="greet", risk_level=ToolRiskLevel.LOW)
        adapter = FunctionCapabilityAdapter(capability_id="greet", func=func, definition=definition)
        registry.register(adapter)

        ctx = ToolCallContext(caller_id="test_agent", role="admin", trust_level="bypass")
        result = registry.execute("greet", "greet", {"name": "World"}, context=ctx)
        assert result["success"] is True
        assert result["result"] == "Hello, World!"

    def test_execute_harness_method(self) -> None:
        registry = UnifiedToolRegistry()
        harness = _make_harness()
        definition = _make_definition(name="harness", risk_level=ToolRiskLevel.MEDIUM,
                                       tools=["run", "diagnose"])
        adapter = HarnessCapabilityAdapter(capability_id="harness", harness=harness, definition=definition)
        registry.register(adapter)

        ctx = ToolCallContext(caller_id="tester", role="admin", trust_level="bypass")
        result = registry.execute("harness", "run", {"scenario": "load_test"}, context=ctx)
        assert result["success"] is True
        assert result["result"]["scenario"] == "load_test"

    def test_execute_unknown_capability(self) -> None:
        registry = UnifiedToolRegistry()
        result = registry.execute("nonexistent", "foo", {}, context=ToolCallContext())
        assert result["success"] is False
        assert "Unknown capability" in result["error"]

    def test_execute_disabled_capability(self) -> None:
        registry = UnifiedToolRegistry()
        func = _make_function()
        definition = _make_definition(risk_level=ToolRiskLevel.LOW)
        adapter = FunctionCapabilityAdapter(capability_id="disabled", func=func, definition=definition)
        registry.register(adapter)
        registry.disable("disabled")

        result = registry.execute("disabled", "test_tool", {}, context=ToolCallContext())
        assert result["success"] is False
        assert "disabled" in result["error"]

    def test_execute_unknown_method(self) -> None:
        registry = UnifiedToolRegistry()
        func = _make_function()
        definition = _make_definition(risk_level=ToolRiskLevel.LOW)
        adapter = FunctionCapabilityAdapter(capability_id="fn", func=func, definition=definition)
        registry.register(adapter)

        ctx = ToolCallContext(role="admin", trust_level="bypass")
        result = registry.execute("fn", "wrong_method", {}, context=ctx)
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Tests: Permission Middleware
# ---------------------------------------------------------------------------

class TestPermissionMiddleware:

    def test_role_capability_filter_allows(self) -> None:
        middleware = RoleCapabilityFilter()
        # Developer can use MCP_TOOL and BUILTIN
        request = PermissionRequest(
            tool_id="test", method_name="run", caller_id="dev",
            role="developer", trust_level="default", arguments={},
            risk_level=ToolRiskLevel.LOW,
            capability_type=CapabilityType.BUILTIN,
        )
        request2 = PermissionRequest(
            tool_id="test", method_name="run", caller_id="dev",
            role="developer", trust_level="default", arguments={},
            risk_level=ToolRiskLevel.MEDIUM,
            capability_type=CapabilityType.MCP_TOOL,
        )
        assert middleware.check(request).value == "allow"
        assert middleware.check(request2).value == "allow"

    def test_role_capability_filter_denies(self) -> None:
        middleware = RoleCapabilityFilter()
        # Operator cannot use HARNESS type
        request_harness = PermissionRequest(
            tool_id="test", method_name="run", caller_id="ops",
            role="operator", trust_level="default", arguments={},
            risk_level=ToolRiskLevel.LOW,
            capability_type=CapabilityType.HARNESS,
        )
        assert middleware.check(request_harness).value == "deny"

        # Unknown role
        request_unknown = PermissionRequest(
            tool_id="test", method_name="run", caller_id="unknown",
            role="unknown_role", trust_level="default", arguments={},
            risk_level=ToolRiskLevel.LOW,
            capability_type=CapabilityType.BUILTIN,
        )
        assert middleware.check(request_unknown).value == "deny"

    def test_risk_level_ceiling(self) -> None:
        middleware = RiskLevelCeiling()

        # Operator can only use LOW
        request_low = PermissionRequest(
            tool_id="test", method_name="run", caller_id="ops",
            role="operator", trust_level="default", arguments={},
            risk_level=ToolRiskLevel.LOW,
        )
        assert middleware.check(request_low).value == "allow"

        request_high = PermissionRequest(
            tool_id="test", method_name="run", caller_id="ops",
            role="operator", trust_level="default", arguments={},
            risk_level=ToolRiskLevel.HIGH,
        )
        assert middleware.check(request_high).value == "deny"

    def test_hitl_gate(self) -> None:
        middleware = HitlGate()

        request_critical = PermissionRequest(
            tool_id="test", method_name="run", caller_id="admin",
            role="admin", trust_level="default", arguments={},
            risk_level=ToolRiskLevel.CRITICAL,
        )
        assert middleware.check(request_critical).value == "require_hitl"

        request_medium = PermissionRequest(
            tool_id="test", method_name="run", caller_id="admin",
            role="admin", trust_level="default", arguments={},
            risk_level=ToolRiskLevel.MEDIUM,
        )
        assert middleware.check(request_medium).value == "allow"

    def test_middleware_chain_blocks(self) -> None:
        registry = UnifiedToolRegistry()
        func = _make_function()
        # CRITICAL risk -> HitlGate should require HITL
        definition = _make_definition(name="test_tool", risk_level=ToolRiskLevel.CRITICAL)
        adapter = FunctionCapabilityAdapter(
            capability_id="critical_fn", func=func, definition=definition,
            capability_type=CapabilityType.BUILTIN,
        )
        registry.register(adapter)

        ctx = ToolCallContext(caller_id="test", role="admin", trust_level="default")
        result = registry.execute("critical_fn", "test_tool", {}, context=ctx)
        assert result["success"] is False
        assert "human approval" in result["error"]

    def test_bypass_trust_level(self) -> None:
        registry = UnifiedToolRegistry()
        func = _make_function()
        definition = _make_definition(name="test_tool", risk_level=ToolRiskLevel.CRITICAL)
        adapter = FunctionCapabilityAdapter(
            capability_id="critical_fn2", func=func, definition=definition,
            capability_type=CapabilityType.BUILTIN,
        )
        registry.register(adapter)

        # Without bypass -> denied by HitlGate
        ctx_normal = ToolCallContext(caller_id="test", role="admin", trust_level="default")
        result = registry.execute("critical_fn2", "test_tool", {}, context=ctx_normal)
        assert result["success"] is False

        # With bypass trust level, HitlGate still triggers because it doesn't check trust_level
        # This is correct - HitlGate should require HITL regardless of trust
        ctx_bypass = ToolCallContext(caller_id="test", role="admin", trust_level="bypass")
        result2 = registry.execute("critical_fn2", "test_tool", {}, context=ctx_bypass)
        assert result2["success"] is False  # HitlGate still blocks


# ---------------------------------------------------------------------------
# Tests: Role-Based Discovery
# ---------------------------------------------------------------------------

class TestRoleBasedDiscovery:

    def setup_method(self) -> None:
        self.registry = UnifiedToolRegistry()
        # Register capabilities of different types and risks
        low_def = _make_definition(name="test_tool", category=ToolCategory.FILE,
                                    risk_level=ToolRiskLevel.LOW)
        high_def = _make_definition(name="test_tool", category=ToolCategory.SHELL,
                                     risk_level=ToolRiskLevel.HIGH)
        harness_def = _make_definition(name="stress", category=ToolCategory.CUSTOM,
                                        risk_level=ToolRiskLevel.MEDIUM,
                                        tools=["run", "diagnose"])

        func = _make_function()
        harness = _make_harness()

        self.registry.register(FunctionCapabilityAdapter(
            capability_id="low_file", func=func, definition=low_def,
            capability_type=CapabilityType.BUILTIN,
        ))
        self.registry.register(FunctionCapabilityAdapter(
            capability_id="high_shell", func=func, definition=high_def,
            capability_type=CapabilityType.MCP_TOOL,
        ))
        self.registry.register(HarnessCapabilityAdapter(
            capability_id="stress", harness=harness, definition=harness_def,
        ))

    def test_admin_sees_all(self) -> None:
        visible = self.registry.list_for_role("admin")
        # Admin can see LOW, MEDIUM, HIGH, CRITICAL risks and all types
        ids = {v["id"] for v in visible}
        assert "low_file" in ids
        assert "high_shell" in ids
        assert "stress" in ids

    def test_operator_sees_only_low(self) -> None:
        visible = self.registry.list_for_role("operator")
        ids = {v["id"] for v in visible}
        assert "low_file" in ids  # LOW risk
        assert "high_shell" not in ids  # HIGH risk, above ceiling
        assert "stress" not in ids  # MEDIUM risk, above ceiling

    def test_developer_no_harness(self) -> None:
        visible = self.registry.list_for_role("developer")
        ids = {v["id"] for v in visible}
        assert "low_file" in ids  # BUILTIN, LOW
        assert "stress" not in ids  # HARNESS not in DEVELOPER allowlist

    def test_unknown_role_empty(self) -> None:
        visible = self.registry.list_for_role("nonexistent")
        assert visible == []

    def test_disabled_not_visible(self) -> None:
        self.registry.disable("low_file")
        visible = self.registry.list_for_role("admin")
        ids = {v["id"] for v in visible}
        assert "low_file" not in ids


# ---------------------------------------------------------------------------
# Tests: Statistics & Audit
# ---------------------------------------------------------------------------

class TestStatsAndAudit:

    def test_call_stats(self) -> None:
        registry = UnifiedToolRegistry()
        func = _make_function()
        definition = _make_definition(name="test_tool", risk_level=ToolRiskLevel.LOW)
        adapter = FunctionCapabilityAdapter(capability_id="fn", func=func, definition=definition)
        registry.register(adapter)

        ctx = ToolCallContext(role="admin", trust_level="bypass")
        result = registry.execute("fn", "test_tool", {}, context=ctx)
        assert result["success"] is True
        result2 = registry.execute("fn", "test_tool", {}, context=ctx)
        assert result2["success"] is True

        stats = registry.get_stats("fn")
        assert stats["call_count"] == 2
        assert stats["error_count"] == 0

    def test_error_stats(self) -> None:
        registry = UnifiedToolRegistry()
        func = _make_function()
        definition = _make_definition(name="test_tool", risk_level=ToolRiskLevel.LOW)
        adapter = FunctionCapabilityAdapter(capability_id="fn", func=func, definition=definition)
        registry.register(adapter)

        ctx = ToolCallContext(role="admin", trust_level="bypass")
        result = registry.execute("fn", "wrong_method", {}, context=ctx)
        assert result["success"] is False

        stats = registry.get_stats("fn")
        assert stats["error_count"] == 1
        assert stats["call_count"] == 1

    def test_global_stats(self) -> None:
        registry = UnifiedToolRegistry()
        func = _make_function()
        definition = _make_definition(name="test_tool", risk_level=ToolRiskLevel.LOW)
        adapter1 = FunctionCapabilityAdapter(capability_id="fn1", func=func, definition=definition)
        adapter2 = FunctionCapabilityAdapter(capability_id="fn2", func=func, definition=definition)
        registry.register(adapter1)
        registry.register(adapter2)

        ctx = ToolCallContext(role="admin", trust_level="bypass")
        registry.execute("fn1", "test_tool", {}, context=ctx)

        stats = registry.get_stats()
        assert stats["registered_capabilities"] == 2
        assert stats["enabled_capabilities"] == 2
        assert stats["total_calls"] == 1

    def test_call_log(self) -> None:
        registry = UnifiedToolRegistry()
        func = _make_function()
        definition = _make_definition(name="test_tool", risk_level=ToolRiskLevel.LOW)
        adapter = FunctionCapabilityAdapter(capability_id="fn", func=func, definition=definition)
        registry.register(adapter)

        ctx = ToolCallContext(caller_id="agent_x", role="admin", trust_level="bypass")
        result = registry.execute("fn", "test_tool", {}, context=ctx)
        assert result["success"] is True

        log = registry.get_call_log()
        assert len(log) == 1
        assert log[0].tool_id == "fn"
        assert log[0].caller_id == "agent_x"
        assert log[0].method_name == "test_tool"
        assert log[0].success is True
        assert log[0].duration_ms >= 0


# ---------------------------------------------------------------------------
# Tests: Middleware Management
# ---------------------------------------------------------------------------

class TestMiddlewareManagement:

    def test_add_remove_middleware(self) -> None:
        registry = UnifiedToolRegistry()
        # Remove all default middlewares
        registry.remove_middleware("role_capability_filter")
        registry.remove_middleware("risk_level_ceiling")
        registry.remove_middleware("hitl_gate")

        # Add custom middleware
        class AllowAll(PermissionMiddleware):
            def check(self, request: PermissionRequest) -> PermissionVerdict:
                return PermissionVerdict.ALLOW
            def name(self) -> str:
                return "allow_all"

        registry.add_middleware(AllowAll())
        func = _make_function()
        definition = _make_definition(name="test_tool", risk_level=ToolRiskLevel.CRITICAL)
        adapter = FunctionCapabilityAdapter(
            capability_id="fn", func=func, definition=definition,
            capability_type=CapabilityType.BUILTIN,
        )
        registry.register(adapter)

        ctx = ToolCallContext(role="operator", trust_level="default")
        result = registry.execute("fn", "test_tool", {}, context=ctx)
        assert result["success"] is True  # Custom middleware allows all

    def test_default_middlewares(self) -> None:
        registry = UnifiedToolRegistry()
        # By default, should have 3 middlewares
        assert len(registry._middlewares) == 3
        names = [m.name() for m in registry._middlewares]
        assert "role_capability_filter" in names
        assert "risk_level_ceiling" in names
        assert "hitl_gate" in names


# ---------------------------------------------------------------------------
# Tests: List All
# ---------------------------------------------------------------------------

class TestListAll:

    def test_list_all_returns_full_info(self) -> None:
        registry = UnifiedToolRegistry()
        func = _make_function()
        definition = _make_definition(name="my_tool", risk_level=ToolRiskLevel.LOW)
        adapter = FunctionCapabilityAdapter(capability_id="my_tool", func=func, definition=definition)
        registry.register(adapter, tags=["demo"])

        all_caps = registry.list_all()
        assert len(all_caps) == 1
        cap = all_caps[0]
        assert cap["id"] == "my_tool"
        assert cap["type"] == "builtin"
        assert cap["enabled"] is True
        assert cap["tags"] == ["demo"]
        assert cap["call_count"] == 0
        assert cap["error_count"] == 0
        assert "definition" in cap
