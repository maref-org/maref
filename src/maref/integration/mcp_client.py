from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.integration.mcp_governance import MCPDecisionVerdict, MCPGovernance
from maref.integration.mcp_security import MCPTrustLevel
from maref.integration.mcp_transport import (
    JSONRPCResponse,
    MCPTransport,
    SSETransport,
    StdioTransport,
)

MAX_RETRIES = 1


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CAPABILITY_NEGOTIATE = "capability_negotiate"
    TRUST_ESTABLISH = "trust_establish"
    CONNECTED = "connected"
    EXPIRED = "expired"
    ERROR = "error"


@dataclass
class MCPToolDef:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPResourceDef:
    uri: str
    name: str = ""
    mime_type: str = ""


@dataclass
class MCPServerConfig:
    command: list[str] | None = None
    url: str | None = None
    transport_type: str = "stdio"
    server_name: str = ""
    env: dict[str, str] | None = None

    def config_hash(self) -> str:
        raw = json.dumps({
            "command": self.command,
            "url": self.url,
            "transport_type": self.transport_type,
        }, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class MCPConnection:
    transport: MCPTransport
    config_hash: str
    state: ConnectionState = ConnectionState.DISCONNECTED
    session_id: str = ""
    tools: list[MCPToolDef] = field(default_factory=list)
    resources: list[MCPResourceDef] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    retry_count: int = 0

    def touch(self) -> None:
        self.last_used_at = time.time()


class MCPClient:
    def __init__(self) -> None:
        self._connections: dict[str, MCPConnection] = {}
        self._governance: MCPGovernance | None = None

    def register_governance(self, governance: MCPGovernance) -> None:
        self._governance = governance

    def register_server(self, config: MCPServerConfig) -> MCPConnection:
        ch = config.config_hash()
        if ch in self._connections:
            existing = self._connections[ch]
            existing.touch()
            return existing

        transport: MCPTransport
        if config.transport_type == "stdio" and config.command:
            transport = StdioTransport(config.command)
        elif config.transport_type == "sse" and config.url:
            transport = SSETransport(config.url)
        else:
            raise ValueError(f"Unsupported transport: {config.transport_type}")

        transport.connect()
        conn = MCPConnection(
            transport=transport,
            config_hash=ch,
            state=ConnectionState.CAPABILITY_NEGOTIATE,
            session_id=f"mcp-{ch}",
        )

        resp = transport.send_initialize()
        if resp.is_error:
            conn.state = ConnectionState.ERROR
        else:
            conn.state = ConnectionState.CONNECTED

        self._connections[ch] = conn
        return conn

    def list_tools(self, conn: MCPConnection) -> list[MCPToolDef]:
        resp = conn.transport.send_tools_list()
        if resp.is_error or not resp.result:
            return []
        tools_data = resp.result.get("tools", [])
        conn.tools = [
            MCPToolDef(
                name=t.get("name", ""),
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
            )
            for t in tools_data
        ]
        conn.touch()
        return conn.tools

    def call_tool(
        self,
        conn: MCPConnection,
        tool_name: str,
        args: dict[str, Any],
        trust_level: MCPTrustLevel = MCPTrustLevel.UNTRUSTED,
        agent_id: str = "",
        session_id: str = "",
        chain_id: str | None = None,
        delegation_depth: int = 0,
        request_id: str = "",
    ) -> JSONRPCResponse:
        if self._governance is not None:
            # E1.2: Check CB state before calling
            if self._governance.circuit_breaker.is_open:
                return JSONRPCResponse(
                    jsonrpc="2.0",
                    result=None,
                    error={"code": -32002, "message": "Circuit breaker is open — tool calls blocked until recovery"},
                    id=request_id or "",
                )

            gov_result = self._governance.evaluate(
                tool_name=tool_name,
                args=args,
                trust_level=trust_level,
                agent_id=agent_id,
                session_id=session_id,
                chain_id=chain_id,
                delegation_depth=delegation_depth,
                request_id=request_id,
            )

            if gov_result.verdict == MCPDecisionVerdict.DENY:
                return JSONRPCResponse(
                    jsonrpc="2.0",
                    result=None,
                    error={"code": -32000, "message": f"Governance denied: {gov_result.reason}"},
                    id=request_id or "",
                )

            if gov_result.verdict == MCPDecisionVerdict.ASK_USER:
                return JSONRPCResponse(
                    jsonrpc="2.0",
                    result={
                        "hitl_event_id": gov_result.hitl_event_id,
                        "reason": gov_result.reason,
                        "risk_score": gov_result.risk_score,
                    },
                    error={"code": -32001, "message": f"Governance requires user approval: {gov_result.reason}"},
                    id=request_id or "",
                )

        # E1.2: Track latency and CB monitor for actual transport call
        import time as _time
        _start = _time.time()
        resp = conn.transport.send_tool_call(tool_name, args)
        _elapsed = _time.time() - _start

        if self._governance is not None:
            _success = not resp.is_error
            self._governance.cb_monitor.record_call(tool_name, _elapsed, _success)

        conn.touch()
        if resp.is_error and resp.error_code == -32001:
            self._handle_session_expired(conn)
        return resp

    def list_resources(self, conn: MCPConnection) -> list[MCPResourceDef]:
        resp = conn.transport.send_resources_list()
        if resp.is_error or not resp.result:
            return []
        resources_data = resp.result.get("resources", [])
        conn.resources = [
            MCPResourceDef(
                uri=r.get("uri", ""),
                name=r.get("name", ""),
                mime_type=r.get("mimeType", ""),
            )
            for r in resources_data
        ]
        conn.touch()
        return conn.resources

    def _handle_session_expired(self, conn: MCPConnection) -> None:
        if conn.retry_count >= MAX_RETRIES:
            conn.state = ConnectionState.EXPIRED
            return
        conn.retry_count += 1
        conn.transport.disconnect()
        conn.transport.connect()
        resp = conn.transport.send_initialize()
        if resp.is_error:
            conn.state = ConnectionState.ERROR
        else:
            conn.state = ConnectionState.CONNECTED
            conn.retry_count = 0
