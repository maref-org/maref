"""Smoke tests for maref.tools.unified_registry."""
from __future__ import annotations

import pytest

from maref.tools.tool_schema import ToolDefinition, ToolRiskLevel
from maref.tools.unified_registry import (
    AgentRole,
    CapabilityType,
    ExecutionMode,
    FunctionCapabilityAdapter,
    HarnessCapabilityAdapter,
    HitlGate,
    MCPCapabilityAdapter,
    PermissionRequest,
    PermissionVerdict,
    RegisteredCapability,
    RiskLevelCeiling,
    RoleCapabilityFilter,
    ROLE_CAPABILITY_ALLOWLIST,
    ROLE_RISK_CEILING,
    ToolCallContext,
    ToolCallRecord,
    TrustLevelOverride,
    UnifiedToolRegistry,
)


class TestEnums:
    def test_capability_type_values(self) -> None:
        assert CapabilityType.MCP_TOOL.value == "mcp_tool"
        assert CapabilityType.HARNESS.value == "harness"
        assert CapabilityType.BUILTIN.value == "builtin"
        assert CapabilityType.CUSTOM.value == "custom"

    def test_execution_mode_values(self) -> None:
        assert ExecutionMode.SYNC.value == "sync"
        assert ExecutionMode.ASYNC.value == "async"

    def test_permission_verdict_values(self) -> None:
        assert PermissionVerdict.ALLOW.value == "allow"
        assert PermissionVerdict.DENY.value == "deny"
        assert PermissionVerdict.REQUIRE_HITL.value == "require_hitl"

    def test_agent_role_values(self) -> None:
        assert AgentRole.ARCHITECT.value == "architect"
        assert AgentRole.DEVELOPER.value == "developer"
        assert AgentRole.TESTER.value == "tester"
        assert AgentRole.AUDITOR.value == "auditor"
        assert AgentRole.OPERATOR.value == "operator"
        assert AgentRole.ADMIN.value == "admin"


class TestToolCallContext:
    def test_init_default(self) -> None:
        ctx = ToolCallContext()
        assert ctx.caller_id == ""
        assert ctx.round_id == ""
        assert ctx.role == ""
        assert ctx.trust_level == "default"

    def test_init_custom(self) -> None:
        ctx = ToolCallContext(caller_id="agent1", round_id="r1", role="developer", trust_level="high")
        assert ctx.caller_id == "agent1"
        assert ctx.round_id == "r1"


class TestToolCallRecord:
    def test_init_minimal(self) -> None:
        rec = ToolCallRecord(
            tool_id="t1", capability_type=CapabilityType.BUILTIN,
            caller_id="c1", method_name="m1", arguments={}, timestamp=100.0,
        )
        assert rec.tool_id == "t1"
        assert rec.success is True

    def test_init_full(self) -> None:
        rec = ToolCallRecord(
            tool_id="t1", capability_type=CapabilityType.MCP_TOOL,
            caller_id="c1", method_name="m1", arguments={"key": "val"},
            timestamp=200.0, duration_ms=50.0, success=False,
            error="fail", result_summary="n/a", cost_tokens=100,
        )
        assert rec.success is False
        assert rec.error == "fail"


class TestPermissionRequest:
    def test_init_minimal(self) -> None:
        req = PermissionRequest(
            tool_id="t1", method_name="m1", caller_id="c1",
            role="developer", trust_level="default", arguments={},
            risk_level=ToolRiskLevel.LOW,
        )
        assert req.tool_id == "t1"
        assert req.risk_level == ToolRiskLevel.LOW


class TestRoleCapabilityFilter:
    def test_init_default(self) -> None:
        instance = RoleCapabilityFilter()
        assert instance is not None

    def test_check_allow(self) -> None:
        instance = RoleCapabilityFilter()
        req = PermissionRequest(
            tool_id="t1", method_name="m1", caller_id="c1",
            role="developer", trust_level="default", arguments={},
            risk_level=ToolRiskLevel.LOW, capability_type=CapabilityType.MCP_TOOL,
        )
        assert instance.check(req) == PermissionVerdict.ALLOW

    def test_check_deny_wrong_role(self) -> None:
        instance = RoleCapabilityFilter()
        req = PermissionRequest(
            tool_id="t1", method_name="m1", caller_id="c1",
            role="nonexistent", trust_level="default", arguments={},
            risk_level=ToolRiskLevel.LOW, capability_type=CapabilityType.MCP_TOOL,
        )
        assert instance.check(req) == PermissionVerdict.DENY

    def test_name(self) -> None:
        instance = RoleCapabilityFilter()
        assert instance.name() == "role_capability_filter"


class TestRiskLevelCeiling:
    def test_init_default(self) -> None:
        instance = RiskLevelCeiling()
        assert instance is not None

    def test_check_allow(self) -> None:
        instance = RiskLevelCeiling()
        req = PermissionRequest(
            tool_id="t1", method_name="m1", caller_id="c1",
            role="developer", trust_level="default", arguments={},
            risk_level=ToolRiskLevel.LOW, capability_type=CapabilityType.MCP_TOOL,
        )
        assert instance.check(req) == PermissionVerdict.ALLOW

    def test_name(self) -> None:
        instance = RiskLevelCeiling()
        assert instance.name() == "risk_level_ceiling"


class TestHitlGate:
    def test_init_default(self) -> None:
        instance = HitlGate()
        assert instance is not None

    def test_check_low(self) -> None:
        instance = HitlGate()
        req = PermissionRequest(
            tool_id="t1", method_name="m1", caller_id="c1",
            role="developer", trust_level="default", arguments={},
            risk_level=ToolRiskLevel.LOW, capability_type=CapabilityType.MCP_TOOL,
        )
        assert instance.check(req) == PermissionVerdict.ALLOW

    def test_check_critical(self) -> None:
        instance = HitlGate()
        req = PermissionRequest(
            tool_id="t1", method_name="m1", caller_id="c1",
            role="developer", trust_level="default", arguments={},
            risk_level=ToolRiskLevel.CRITICAL, capability_type=CapabilityType.MCP_TOOL,
        )
        assert instance.check(req) == PermissionVerdict.REQUIRE_HITL

    def test_name(self) -> None:
        instance = HitlGate()
        assert instance.name() == "hitl_gate"


class TestTrustLevelOverride:
    def test_init_default(self) -> None:
        instance = TrustLevelOverride()
        assert instance is not None

    def test_check_pass_through(self) -> None:
        instance = TrustLevelOverride()
        req = PermissionRequest(
            tool_id="t1", method_name="m1", caller_id="c1",
            role="developer", trust_level="default", arguments={},
            risk_level=ToolRiskLevel.LOW, capability_type=CapabilityType.MCP_TOOL,
        )
        assert instance.check(req) == PermissionVerdict.ALLOW

    def test_name(self) -> None:
        instance = TrustLevelOverride()
        assert instance.name() == "trust_level_override"


class TestUnifiedToolRegistry:
    def test_init_default(self) -> None:
        registry = UnifiedToolRegistry()
        assert registry is not None
        assert len(registry._capabilities) == 0

    def test_register_and_list_all(self) -> None:
        registry = UnifiedToolRegistry()
        definition = ToolDefinition(
            name="test_func", description="A test function",
            risk_level=ToolRiskLevel.LOW, tools={"test": "test"},
        )
        def _test_fn(**kwargs): return {"result": "ok"}
        cap_id = registry.register_function("test_func", _test_fn, definition)
        assert cap_id == "test_func"
        all_items = registry.list_all()
        assert len(all_items) == 1
        assert all_items[0]["id"] == "test_func"

    def test_unregister(self) -> None:
        registry = UnifiedToolRegistry()
        definition = ToolDefinition(
            name="test_func", description="A test function",
            risk_level=ToolRiskLevel.LOW, tools={"test": "test"},
        )
        def _test_fn(**kwargs): return {"result": "ok"}
        registry.register_function("test_func", _test_fn, definition)
        assert registry.unregister("test_func") is True
        assert registry.unregister("nonexistent") is False

    def test_enable_disable(self) -> None:
        registry = UnifiedToolRegistry()
        definition = ToolDefinition(
            name="test_func", description="A test function",
            risk_level=ToolRiskLevel.LOW, tools={"test": "test"},
        )
        def _test_fn(**kwargs): return {"result": "ok"}
        registry.register_function("test_func", _test_fn, definition)
        assert registry.disable("test_func") is True
        assert registry.enable("test_func") is True
        assert registry.disable("nonexistent") is False

    def test_get_nonexistent(self) -> None:
        registry = UnifiedToolRegistry()
        assert registry.get("nonexistent") is None

    def test_list_for_role(self) -> None:
        registry = UnifiedToolRegistry()
        assert registry.list_for_role("nonexistent") == []

    def test_add_remove_middleware(self) -> None:
        registry = UnifiedToolRegistry()
        middleware = HitlGate()
        registry.add_middleware(middleware)
        assert registry.remove_middleware("hitl_gate") is True
        assert registry.remove_middleware("nonexistent") is False


class TestRegisteredCapability:
    def test_init_default(self) -> None:
        definition = ToolDefinition(
            name="test", description="test",
            risk_level=ToolRiskLevel.LOW, tools={"x": "y"},
        )
        adapter = FunctionCapabilityAdapter(
            capability_id="test", func=lambda: None, definition=definition,
        )
        rc = RegisteredCapability(capability=adapter)
        assert rc.enabled is True
        assert rc.call_count == 0
        assert rc.error_count == 0
