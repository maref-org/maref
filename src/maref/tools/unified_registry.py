"""Unified Tool Registry v2

Bridges MCP tools, Harnesses, and arbitrary capabilities into a single
discoverable, filterable, auditable registry.

Distilled patterns from production AI agent systems:
- Unified capability interface (all tools/Harnesses share the same contract)
- Permission middleware chain (pre-execution interception)
- Role-based visibility filtering
- Lifecycle management (install/uninstall at runtime)
- Call audit trail with cost tracking hooks

NOT copied from any proprietary source. Original Python implementation
inspired by common patterns in multi-agent orchestration systems.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

from maref.tools.tool_schema import ToolDefinition, ToolRiskLevel

if TYPE_CHECKING:
    from maref.governance.audit import AuditLogger


# ---------------------------------------------------------------------------
# Capability Types
# ---------------------------------------------------------------------------

class CapabilityType(Enum):
    MCP_TOOL = "mcp_tool"
    HARNESS = "harness"
    BUILTIN = "builtin"
    CUSTOM = "custom"


class ExecutionMode(Enum):
    SYNC = "sync"
    ASYNC = "async"


@dataclass
class ToolCallContext:
    """Context passed to every tool execution."""
    caller_id: str = ""
    round_id: str = ""
    role: str = ""
    trust_level: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallRecord:
    """Immutable audit record for a tool invocation."""
    tool_id: str
    capability_type: CapabilityType
    caller_id: str
    method_name: str
    arguments: dict[str, Any]
    timestamp: float
    duration_ms: float = 0.0
    success: bool = True
    error: str = ""
    result_summary: str = ""
    cost_tokens: int = 0


class PermissionVerdict(Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_HITL = "require_hitl"


@dataclass
class PermissionRequest:
    tool_id: str
    method_name: str
    caller_id: str
    role: str
    trust_level: str
    arguments: dict[str, Any]
    risk_level: ToolRiskLevel
    capability_type: CapabilityType = CapabilityType.CUSTOM


class PermissionMiddleware(ABC):
    """Base class for permission middleware in the execution chain."""

    @abstractmethod
    def check(self, request: PermissionRequest) -> PermissionVerdict:
        ...

    @abstractmethod
    def name(self) -> str:
        ...


# ---------------------------------------------------------------------------
# Unified Capability Interface
# ---------------------------------------------------------------------------

class Capability(Protocol):
    """Minimal interface all capabilities must implement.

    Uses Protocol (structural subtyping) so existing classes like
    MCPServer, StressHarness, etc. can be adapted without inheritance.
    """
    capability_id: str
    capability_type: CapabilityType
    definition: ToolDefinition

    def execute(self, method_name: str, arguments: dict[str, Any],
                context: ToolCallContext) -> dict[str, Any]:
        ...

    def list_methods(self) -> list[str]:
        ...


# ---------------------------------------------------------------------------
# Capability Adapters
# ---------------------------------------------------------------------------

@dataclass
class MCPCapabilityAdapter:
    """Adapt an MCPServer to the Capability interface."""
    capability_id: str
    server: Any  # MCPServer
    definition: ToolDefinition
    capability_type: CapabilityType = CapabilityType.MCP_TOOL

    def execute(self, method_name: str, arguments: dict[str, Any],
                context: ToolCallContext) -> dict[str, Any]:
        transport = self.server.get_inprocess_transport()
        request_id = int(time.time() * 1000)
        from maref.integration.mcp_transport import JSONRPCRequest
        response = transport.call(JSONRPCRequest(
            id=request_id,
            method="tools/call",
            params={"name": method_name, "arguments": arguments},
        ))
        if response.error:
            return {"error": response.error["message"], "success": False}
        return {"result": response.result, "success": True}

    def list_methods(self) -> list[str]:
        return list(self.definition.tools)


@dataclass
class HarnessCapabilityAdapter:
    """Adapt a Harness (StressHarness, EmergenceTestHarness) to Capability."""
    capability_id: str
    harness: Any
    definition: ToolDefinition
    capability_type: CapabilityType = CapabilityType.HARNESS

    def execute(self, method_name: str, arguments: dict[str, Any],
                context: ToolCallContext) -> dict[str, Any]:
        method = getattr(self.harness, method_name, None)
        if method is None:
            return {"error": f"Unknown method: {method_name}", "success": False}
        try:
            result = method(**arguments)
            if hasattr(result, "to_dict"):
                result = result.to_dict()
            return {"result": result, "success": True}
        except Exception as e:
            return {"error": str(e), "success": False}

    def list_methods(self) -> list[str]:
        return [m for m in dir(self.harness)
                if not m.startswith("_") and callable(getattr(self.harness, m))]


@dataclass
class FunctionCapabilityAdapter:
    """Adapt a plain Python function to Capability."""
    capability_id: str
    func: Any
    definition: ToolDefinition
    capability_type: CapabilityType = CapabilityType.BUILTIN

    def execute(self, method_name: str, arguments: dict[str, Any],
                context: ToolCallContext) -> dict[str, Any]:
        if method_name != self.definition.name:
            return {"error": f"Unknown method: {method_name}", "success": False}
        try:
            result = self.func(**arguments)
            return {"result": result, "success": True}
        except Exception as e:
            return {"error": str(e), "success": False}

    def list_methods(self) -> list[str]:
        return [self.definition.name]


# ---------------------------------------------------------------------------
# Role Definitions
# ---------------------------------------------------------------------------

class AgentRole(Enum):
    ARCHITECT = "architect"
    DEVELOPER = "developer"
    TESTER = "tester"
    AUDITOR = "auditor"
    OPERATOR = "operator"
    ADMIN = "admin"


# Default role → allowed capability types mapping
ROLE_CAPABILITY_ALLOWLIST: dict[AgentRole, set[CapabilityType]] = {
    AgentRole.ARCHITECT: {CapabilityType.MCP_TOOL, CapabilityType.HARNESS, CapabilityType.BUILTIN, CapabilityType.CUSTOM},
    AgentRole.DEVELOPER: {CapabilityType.MCP_TOOL, CapabilityType.BUILTIN},
    AgentRole.TESTER: {CapabilityType.HARNESS, CapabilityType.MCP_TOOL},
    AgentRole.AUDITOR: {CapabilityType.MCP_TOOL, CapabilityType.HARNESS},
    AgentRole.OPERATOR: {CapabilityType.MCP_TOOL, CapabilityType.BUILTIN},
    AgentRole.ADMIN: {CapabilityType.MCP_TOOL, CapabilityType.HARNESS, CapabilityType.BUILTIN, CapabilityType.CUSTOM},
}

# Default role → risk level ceiling
ROLE_RISK_CEILING: dict[AgentRole, set[ToolRiskLevel]] = {
    AgentRole.ARCHITECT: {ToolRiskLevel.LOW, ToolRiskLevel.MEDIUM, ToolRiskLevel.HIGH},
    AgentRole.DEVELOPER: {ToolRiskLevel.LOW, ToolRiskLevel.MEDIUM},
    AgentRole.TESTER: {ToolRiskLevel.LOW, ToolRiskLevel.MEDIUM},
    AgentRole.AUDITOR: {ToolRiskLevel.LOW, ToolRiskLevel.MEDIUM},
    AgentRole.OPERATOR: {ToolRiskLevel.LOW},
    AgentRole.ADMIN: {ToolRiskLevel.LOW, ToolRiskLevel.MEDIUM, ToolRiskLevel.HIGH, ToolRiskLevel.CRITICAL},
}


# ---------------------------------------------------------------------------
# Built-in Permission Middlewares
# ---------------------------------------------------------------------------

class RoleCapabilityFilter(PermissionMiddleware):
    """Block tool types not allowed for the caller's role."""

    def __init__(self, role_allowlist: dict[AgentRole, set[CapabilityType]] | None = None) -> None:
        self._allowlist = role_allowlist or ROLE_CAPABILITY_ALLOWLIST

    def check(self, request: PermissionRequest) -> PermissionVerdict:
        try:
            role = AgentRole(request.role)
        except ValueError:
            return PermissionVerdict.DENY
        allowed = self._allowlist.get(role, set())
        if not allowed:
            return PermissionVerdict.DENY
        if request.capability_type not in allowed:
            return PermissionVerdict.DENY
        return PermissionVerdict.ALLOW

    def name(self) -> str:
        return "role_capability_filter"


class RiskLevelCeiling(PermissionMiddleware):
    """Block tools above the caller role's risk ceiling."""

    def __init__(self, risk_ceiling: dict[AgentRole, set[ToolRiskLevel]] | None = None) -> None:
        self._ceiling = risk_ceiling or ROLE_RISK_CEILING

    def check(self, request: PermissionRequest) -> PermissionVerdict:
        try:
            role = AgentRole(request.role)
        except ValueError:
            return PermissionVerdict.DENY
        allowed = self._ceiling.get(role, set())
        if request.risk_level not in allowed:
            return PermissionVerdict.DENY
        return PermissionVerdict.ALLOW

    def name(self) -> str:
        return "risk_level_ceiling"


class HitlGate(PermissionMiddleware):
    """Require human-in-the-loop for CRITICAL risk tools."""

    def __init__(self, hitl_required_for: set[ToolRiskLevel] | None = None) -> None:
        self._hitl_levels = hitl_required_for or {ToolRiskLevel.CRITICAL}

    def check(self, request: PermissionRequest) -> PermissionVerdict:
        if request.risk_level in self._hitl_levels:
            return PermissionVerdict.REQUIRE_HITL
        return PermissionVerdict.ALLOW

    def name(self) -> str:
        return "hitl_gate"


class TrustLevelOverride(PermissionMiddleware):
    """High trust level bypasses other checks for specific tool/method combos."""

    def __init__(self, bypass_tools: dict[str, list[str]] | None = None) -> None:
        self._bypass_map = bypass_tools or {}

    def check(self, request: PermissionRequest) -> PermissionVerdict:
        if request.trust_level == "bypass":
            bypass_list = self._bypass_map.get(request.tool_id, [])
            if not bypass_list or request.method_name in bypass_list:
                return PermissionVerdict.ALLOW
        return PermissionVerdict.ALLOW  # pass-through, let other middleware decide

    def name(self) -> str:
        return "trust_level_override"


# ---------------------------------------------------------------------------
# Unified Registry
# ---------------------------------------------------------------------------

@dataclass
class RegisteredCapability:
    capability: Capability
    enabled: bool = True
    tags: list[str] = field(default_factory=list)
    installed_at: float = 0.0
    call_count: int = 0
    total_duration_ms: float = 0.0
    error_count: int = 0


class UnifiedToolRegistry:
    """Central registry for all MAREF capabilities.

    Features:
    - Unified interface for MCP tools, Harnesses, and custom functions
    - Dynamic install/uninstall at runtime
    - Role-based capability filtering
    - Middleware chain for permission checking
    - Call audit trail integration
    - Per-capability statistics tracking
    """

    def __init__(self, audit_logger: AuditLogger | None = None) -> None:
        self._capabilities: dict[str, RegisteredCapability] = {}
        self._middlewares: list[PermissionMiddleware] = []
        self._audit_logger = audit_logger
        self._call_log: list[ToolCallRecord] = []
        self._max_call_log = 10_000

        # Register default middlewares
        self.add_middleware(RoleCapabilityFilter())
        self.add_middleware(RiskLevelCeiling())
        self.add_middleware(HitlGate())

    # ---- Registration ----

    def register(self, capability: Capability, tags: list[str] | None = None,
                 enabled: bool = True) -> str:
        """Register a capability. Returns capability_id."""
        cap_id = capability.capability_id
        if cap_id in self._capabilities:
            raise ValueError(f"Capability already registered: {cap_id}")
        self._capabilities[cap_id] = RegisteredCapability(
            capability=capability,
            enabled=enabled,
            tags=tags or [],
            installed_at=time.time(),
        )
        return cap_id

    def register_mcp_server(self, name: str, server: Any,
                            definition: ToolDefinition,
                            tags: list[str] | None = None) -> str:
        """Register an MCPServer as a capability."""
        adapter = MCPCapabilityAdapter(
            capability_id=name,
            server=server,
            definition=definition,
        )
        return self.register(adapter, tags=tags)

    def register_harness(self, name: str, harness: Any,
                         definition: ToolDefinition,
                         tags: list[str] | None = None) -> str:
        """Register a Harness (StressHarness, etc.) as a capability."""
        adapter = HarnessCapabilityAdapter(
            capability_id=name,
            harness=harness,
            definition=definition,
        )
        return self.register(adapter, tags=tags)

    def register_function(self, name: str, func: Any,
                          definition: ToolDefinition) -> str:
        """Register a plain function as a capability."""
        adapter = FunctionCapabilityAdapter(
            capability_id=name,
            func=func,
            definition=definition,
        )
        return self.register(adapter)

    def unregister(self, capability_id: str) -> bool:
        """Unregister a capability. Returns True if it existed."""
        if capability_id in self._capabilities:
            del self._capabilities[capability_id]
            return True
        return False

    def enable(self, capability_id: str) -> bool:
        if capability_id in self._capabilities:
            self._capabilities[capability_id].enabled = True
            return True
        return False

    def disable(self, capability_id: str) -> bool:
        if capability_id in self._capabilities:
            self._capabilities[capability_id].enabled = False
            return True
        return False

    # ---- Middleware ----

    def add_middleware(self, middleware: PermissionMiddleware) -> None:
        self._middlewares.append(middleware)

    def remove_middleware(self, name: str) -> bool:
        before = len(self._middlewares)
        self._middlewares = [m for m in self._middlewares if m.name() != name]
        return len(self._middlewares) < before

    # ---- Discovery ----

    def list_all(self) -> list[dict[str, Any]]:
        """List all registered capabilities (admin view)."""
        return [
            {
                "id": cap_id,
                "type": rc.capability.capability_type.value,
                "definition": rc.capability.definition.to_dict(),
                "enabled": rc.enabled,
                "tags": rc.tags,
                "call_count": rc.call_count,
                "error_count": rc.error_count,
                "installed_at": rc.installed_at,
            }
            for cap_id, rc in self._capabilities.items()
        ]

    def list_for_role(self, role: str) -> list[dict[str, Any]]:
        """List capabilities visible to a given role."""
        try:
            agent_role = AgentRole(role)
        except ValueError:
            return []

        allowed_types = ROLE_CAPABILITY_ALLOWLIST.get(agent_role, set())
        allowed_risks = ROLE_RISK_CEILING.get(agent_role, set())

        visible = []
        for cap_id, rc in self._capabilities.items():
            if not rc.enabled:
                continue
            cap_type = rc.capability.capability_type
            risk = rc.capability.definition.risk_level
            if cap_type not in allowed_types:
                continue
            if risk not in allowed_risks:
                continue
            visible.append({
                "id": cap_id,
                "type": cap_type.value,
                "definition": rc.capability.definition.to_dict(),
                "tags": rc.tags,
            })
        return visible

    def get(self, capability_id: str) -> Capability | None:
        rc = self._capabilities.get(capability_id)
        if rc is None or not rc.enabled:
            return None
        return rc.capability

    def get_definition(self, capability_id: str) -> ToolDefinition | None:
        rc = self._capabilities.get(capability_id)
        if rc is None:
            return None
        return rc.capability.definition

    # ---- Execution ----

    def execute(self, capability_id: str, method_name: str,
                arguments: dict[str, Any],
                context: ToolCallContext | None = None) -> dict[str, Any]:
        """Execute a capability method with full permission chain and audit."""
        rc = self._capabilities.get(capability_id)
        if rc is None:
            return {"error": f"Unknown capability: {capability_id}", "success": False}
        if not rc.enabled:
            return {"error": f"Capability disabled: {capability_id}", "success": False}

        capability = rc.capability
        definition = capability.definition

        # Build permission request
        ctx = context or ToolCallContext()
        perm_request = PermissionRequest(
            tool_id=capability_id,
            method_name=method_name,
            caller_id=ctx.caller_id,
            role=ctx.role,
            trust_level=ctx.trust_level,
            arguments=arguments,
            risk_level=definition.risk_level,
            capability_type=capability.capability_type,
        )

        # Run middleware chain
        for middleware in self._middlewares:
            verdict = middleware.check(perm_request)
            if verdict == PermissionVerdict.DENY:
                return {
                    "error": f"Permission denied by {middleware.name()}",
                    "success": False,
                    "verdict": verdict.value,
                }
            if verdict == PermissionVerdict.REQUIRE_HITL:
                return {
                    "error": f"Requires human approval (blocked by {middleware.name()})",
                    "success": False,
                    "verdict": verdict.value,
                }

        # Execute with timing
        t0 = time.perf_counter()
        try:
            result = capability.execute(method_name, arguments, ctx)
            duration_ms = (time.perf_counter() - t0) * 1000
            success = result.get("success", True)
            error = result.get("error", "")

            # Update stats
            rc.call_count += 1
            rc.total_duration_ms += duration_ms
            if not success:
                rc.error_count += 1

            # Audit
            self._record_call(ToolCallRecord(
                tool_id=capability_id,
                capability_type=capability.capability_type,
                caller_id=ctx.caller_id,
                method_name=method_name,
                arguments=arguments,
                timestamp=time.time(),
                duration_ms=duration_ms,
                success=success,
                error=error,
            ))

            return result

        except Exception as e:
            duration_ms = (time.perf_counter() - t0) * 1000
            rc.call_count += 1
            rc.error_count += 1

            self._record_call(ToolCallRecord(
                tool_id=capability_id,
                capability_type=capability.capability_type,
                caller_id=ctx.caller_id,
                method_name=method_name,
                arguments=arguments,
                timestamp=time.time(),
                duration_ms=duration_ms,
                success=False,
                error=str(e),
            ))

            return {"error": str(e), "success": False}

    # ---- Audit ----

    def _record_call(self, record: ToolCallRecord) -> None:
        self._call_log.append(record)
        if len(self._call_log) > self._max_call_log:
            self._call_log = self._call_log[-self._max_call_log:]

        if self._audit_logger:
            self._audit_logger.log(
                event_type="tool_call",
                actor=record.caller_id,
                action=f"{record.tool_id}.{record.method_name}",
                details=f"success={record.success} duration={record.duration_ms:.1f}ms",
                metadata={
                    "capability_type": record.capability_type.value,
                    "error": record.error,
                },
            )

    def get_call_log(self, limit: int = 100) -> list[ToolCallRecord]:
        return self._call_log[-limit:]

    def get_stats(self, capability_id: str | None = None) -> dict[str, Any]:
        if capability_id:
            rc = self._capabilities.get(capability_id)
            if rc is None:
                return {}
            return {
                "call_count": rc.call_count,
                "error_count": rc.error_count,
                "total_duration_ms": rc.total_duration_ms,
                "avg_duration_ms": (
                    rc.total_duration_ms / rc.call_count if rc.call_count > 0 else 0.0
                ),
            }

        # Global stats
        total_calls = sum(rc.call_count for rc in self._capabilities.values())
        total_errors = sum(rc.error_count for rc in self._capabilities.values())
        return {
            "registered_capabilities": len(self._capabilities),
            "enabled_capabilities": sum(1 for rc in self._capabilities.values() if rc.enabled),
            "total_calls": total_calls,
            "total_errors": total_errors,
            "error_rate": total_errors / total_calls if total_calls > 0 else 0.0,
        }
