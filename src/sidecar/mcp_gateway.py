from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from maref.integration.mcp_governance import (
    MCPGovernance,
    MCPPolicyContext,
    MCPPolicyEngine,
)
from maref.integration.mcp_security import (
    MCPTrustLevel,
    SecurityVerdict,
    ZeroTrustContext,
)


@dataclass
class BackendRegistration:
    prefix: str = ""
    server_url: str = ""
    transport_type: str = "http"
    tools: list[dict[str, Any]] = field(default_factory=list)
    handler: Callable[..., Any] | None = None
    healthy: bool = True


def _create_audit_signature(
    tool_name: str,
    verdict: str,
    risk_score: float,
    args_hash: str,
    secret_key: bytes,
) -> str:
    payload = json.dumps(
        {
            "tool_name": tool_name,
            "verdict": verdict,
            "risk_score": risk_score,
            "args_hash": args_hash,
            "timestamp": time.time(),
        },
        sort_keys=True,
    )
    import hmac
    return hmac.new(secret_key, payload.encode(), hashlib.sha256).hexdigest()


class MCPGateway:
    def __init__(
        self,
        security_gate: Any | None = None,
        policy_engine: MCPPolicyEngine | None = None,
        governance: MCPGovernance | None = None,
        default_backend: BackendRegistration | None = None,
        secret_key: bytes | None = None,
        boundary: Any | None = None,
    ) -> None:
        self._backends: dict[str, BackendRegistration] = {}
        self._default_backend = default_backend
        env_key = os.environb.get(b"MAREF_MCP_SECRET_KEY")
        if secret_key is not None:
            self._secret_key = secret_key
        elif env_key is not None:
            self._secret_key = env_key
        else:
            raise RuntimeError(
                "MCPGateway requires a secret_key. "
                "Set MAREF_MCP_SECRET_KEY environment variable "
                "or pass secret_key to MCPGateway()."
            )
        self._audit_log: list[dict[str, Any]] = []
        self._gate = security_gate
        self._policy_engine = policy_engine
        self._governance = governance
        # TrustBoundaryManager (P0-1 wiring): risk-classified boundary gate.
        # Default fail-closed so HIGH/IRREVERSIBLE tool calls are blocked
        # without an explicit AuthorizationScope.
        if boundary is not None:
            self._boundary = boundary
        else:
            from maref.governance.trust_boundary import TrustBoundaryManager

            self._boundary = TrustBoundaryManager()

    def register_backend(
        self,
        prefix: str,
        server_url: str = "",
        transport_type: str = "http",
        handler: Callable[..., Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> None:
        reg = BackendRegistration(
            prefix=prefix,
            server_url=server_url,
            transport_type=transport_type,
            handler=handler,
            tools=tools or [],
        )
        self._backends[prefix] = reg

    def _find_backend(self, tool_name: str) -> BackendRegistration | None:
        matches = [(p, b) for p, b in self._backends.items() if tool_name.startswith(p)]
        if not matches:
            return self._default_backend
        matches.sort(key=lambda x: len(x[0]), reverse=True)
        return matches[0][1]

    def route_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        context: ZeroTrustContext | None = None,
        trust_level: MCPTrustLevel = MCPTrustLevel.SEMI_TRUSTED,
    ) -> dict[str, Any]:
        arguments = arguments or {}
        context = context or ZeroTrustContext()

        backend = self._find_backend(tool_name)
        if backend is None:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"No backend registered for tool: {tool_name}"}],
            }

        if self._gate is not None:
            verdict = self._gate.check(
                tool_name=tool_name,
                trust_level=trust_level,
                args=arguments,
                context=context,
            )
            if verdict == SecurityVerdict.DENY:
                self._log_gateway_call(tool_name, "DENY", 1.0, arguments, context)
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": f"Security gate denied: {tool_name}"}],
                }

        if self._boundary is not None:
            boundary_decision = self._boundary.check_no_raise(
                action=tool_name,
                agent_id=context.agent_id or "unknown",
                metadata=arguments,
            )
            if boundary_decision is not None and not boundary_decision.allowed:
                self._log_gateway_call(tool_name, "DENY", 1.0, arguments, context)
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": f"TrustBoundary denied: {boundary_decision.reason}"}],
                }

        if self._policy_engine is not None:
            policy_context = MCPPolicyContext(
                tool_name=tool_name,
                args=arguments,
                trust_level=trust_level,
                agent_id=context.agent_id,
                session_id=context.session_id,
                chain_id=context.chain_id,
                delegation_depth=context.delegation_depth,
                request_id=context.request_id,
            )
            policy_result = self._policy_engine.evaluate(policy_context)
            if policy_result.verdict.value == "deny":
                self._log_gateway_call(tool_name, "DENY", policy_result.risk_score, arguments, context)
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": f"Policy denied: {policy_result.reason}"}],
                }

        if self._governance is not None:
            should_trip, trip_reason = self._governance.cb_monitor.should_trip(tool_name)
            if should_trip:
                self._governance.circuit_breaker.record_failure()
                self._log_gateway_call(tool_name, "DENY", 1.0, arguments, context)
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": f"Circuit breaker monitor tripped for '{tool_name}': {trip_reason}"}],
                }
            cb = self._governance.circuit_breaker
            if cb.is_open:
                self._log_gateway_call(tool_name, "DENY", 1.0, arguments, context)
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": f"Circuit breaker open — tool call blocked: {tool_name}"}],
                }

        try:
            result = self._forward_call(backend, tool_name, arguments, context)
            if self._governance is not None:
                self._governance.circuit_breaker.record_success()
                self._governance.cb_monitor.record_call(tool_name, 0.0, success=True)
            self._log_gateway_call(tool_name, "ALLOW", 0.0, arguments, context)
            return result
        except Exception as exc:
            if self._governance is not None:
                self._governance.circuit_breaker.record_failure()
                self._governance.cb_monitor.record_call(tool_name, 0.0, success=False)
            self._log_gateway_call(tool_name, "ERROR", 1.0, arguments, context)
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Gateway error: {exc}"}],
            }

    def _forward_call(
        self,
        backend: BackendRegistration,
        tool_name: str,
        arguments: dict[str, Any],
        context: ZeroTrustContext,
    ) -> dict[str, Any]:
        if backend.transport_type == "in-process":
            if backend.handler is not None:
                raw = backend.handler(tool_name, arguments)
                if isinstance(raw, dict):
                    return raw
                return {
                    "content": [{"type": "text", "text": str(raw)}],
                }
            return {
                "isError": True,
                "content": [{"type": "text", "text": "In-process handler not available"}],
            }

        if backend.transport_type == "http":
            url = f"{backend.server_url.rstrip('/')}/api/mcp"
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
                "id": int(time.time() * 1000),
            }
            try:
                response = httpx.post(url, json=payload, timeout=30.0)
                response.raise_for_status()
                data = response.json()
                if "result" in data:
                    return data["result"]
                if "error" in data:
                    return {
                        "isError": True,
                        "content": [{"type": "text", "text": data["error"].get("message", "Unknown error")}],
                    }
                return {
                    "content": [{"type": "text", "text": str(data)}],
                }
            except httpx.HTTPStatusError as exc:
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": f"HTTP {exc.response.status_code} from backend"}],
                }
            except httpx.RequestError as exc:
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": f"Backend unreachable: {exc}"}],
                }

        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Unsupported transport: {backend.transport_type}"}],
        }

    def list_all_tools(self) -> list[dict[str, Any]]:
        all_tools: list[dict[str, Any]] = []
        seen: set[str] = set()

        for _prefix, backend in self._backends.items():
            if backend.transport_type == "in-process" and backend.tools:
                for tool in backend.tools:
                    name = tool.get("name", "")
                    if name and name not in seen:
                        all_tools.append(tool)
                        seen.add(name)
            elif backend.transport_type == "http" and backend.server_url:
                remote_tools = self._fetch_remote_tools(backend)
                for tool in remote_tools:
                    name = tool.get("name", "")
                    if name and name not in seen:
                        all_tools.append(tool)
                        seen.add(name)

        if self._default_backend and self._default_backend.tools:
            for tool in self._default_backend.tools:
                name = tool.get("name", "")
                if name and name not in seen:
                    all_tools.append(tool)
                    seen.add(name)

        return all_tools

    def _fetch_remote_tools(self, backend: BackendRegistration) -> list[dict[str, Any]]:
        url = f"{backend.server_url.rstrip('/')}/api/mcp"
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": 1,
        }
        try:
            response = httpx.post(url, json=payload, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            if "result" in data and "tools" in data["result"]:
                return data["result"]["tools"]
        except Exception:
            pass
        return []

    def get_backends(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for prefix, reg in self._backends.items():
            result[prefix] = {
                "server_url": reg.server_url,
                "transport_type": reg.transport_type,
                "healthy": reg.healthy,
                "tool_count": len(reg.tools),
            }
        if self._default_backend:
            result["__default__"] = {
                "server_url": self._default_backend.server_url,
                "transport_type": self._default_backend.transport_type,
                "healthy": self._default_backend.healthy,
                "tool_count": len(self._default_backend.tools),
            }
        return result

    def get_audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit_log)

    def _log_gateway_call(
        self,
        tool_name: str,
        verdict: str,
        risk_score: float,
        args: dict[str, Any],
        context: ZeroTrustContext,
    ) -> None:
        args_hash = hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()[:16]
        entry = {
            "timestamp": time.time(),
            "tool_name": tool_name,
            "verdict": verdict,
            "risk_score": risk_score,
            "args_hash": args_hash,
            "agent_id": context.agent_id,
            "chain_id": context.chain_id,
            "delegation_depth": context.delegation_depth,
        }
        entry["audit_signature"] = _create_audit_signature(
            tool_name, verdict, risk_score, args_hash, self._secret_key
        )
        self._audit_log.append(entry)


def create_mcp_gateway_router(gateway: MCPGateway) -> Any:
    from fastapi import APIRouter, HTTPException

    router = APIRouter(tags=["mcp-gateway"])

    @router.get("/api/mcp/gateway/health")
    def gateway_health() -> dict[str, Any]:
        return {
            "status": "healthy",
            "backends": gateway.get_backends(),
            "total_backends": len(gateway.get_backends()),
            "audit_log_size": len(gateway.get_audit_log()),
        }

    @router.post("/api/mcp/gateway/tools/call")
    def gateway_tool_call(body: dict[str, Any]) -> dict[str, Any]:
        tool_name = body.get("name", "")
        if not tool_name:
            raise HTTPException(status_code=400, detail="Missing 'name' in request body")
        arguments = body.get("arguments", {})
        result = gateway.route_tool_call(tool_name, arguments)
        return result

    @router.get("/api/mcp/gateway/tools")
    def gateway_list_tools() -> dict[str, Any]:
        tools = gateway.list_all_tools()
        return {"tools": tools, "total": len(tools)}

    return router
