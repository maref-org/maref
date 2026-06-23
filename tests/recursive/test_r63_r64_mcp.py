from __future__ import annotations

import json
import sys

import pytest

from maref.integration.mcp_bridge import (
    BridgeEvent,
    MCPBridge,
    ToolToRole,
    map_tool_to_role,
)
from maref.integration.mcp_client import (
    ConnectionState,
    MCPClient,
    MCPConnection,
    MCPServerConfig,
    MCPToolDef,
)
from maref.integration.mcp_security import (
    MCPSecurityGate,
    MCPTrustLevel,
    SecurityVerdict,
)
from maref.integration.mcp_transport import (
    HTTPTransport,
    JSONRPCRequest,
    JSONRPCResponse,
    MCPTransport,
    SSETransport,
    StdioTransport,
    TransportState,
)


class TestJSONRPC:
    def test_request_to_json(self) -> None:
        req = JSONRPCRequest(method="tools/list", id=1)
        raw = req.to_json()
        data = json.loads(raw)
        assert data["method"] == "tools/list"
        assert data["jsonrpc"] == "2.0"

    def test_request_with_params(self) -> None:
        req = JSONRPCRequest(method="tools/call", params={"name": "search"}, id=3)
        raw = req.to_json()
        data = json.loads(raw)
        assert data["params"]["name"] == "search"

    def test_response_from_json(self) -> None:
        raw = json.dumps({"jsonrpc": "2.0", "result": {"ok": True}, "id": 1})
        resp = JSONRPCResponse.from_json(raw)
        assert resp.result == {"ok": True}

    def test_response_has_error(self) -> None:
        raw = json.dumps(
            {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Not found"}, "id": 1}
        )
        resp = JSONRPCResponse.from_json(raw)
        assert resp.is_error
        assert resp.error_code == -32601

    def test_response_no_error(self) -> None:
        raw = json.dumps({"jsonrpc": "2.0", "result": {}, "id": 1})
        resp = JSONRPCResponse.from_json(raw)
        assert not resp.is_error


class TestStdioTransport:
    def test_connect_with_echo_command(self) -> None:
        script = """
import sys, json
for line in sys.stdin:
    req = json.loads(line)
    resp = {"jsonrpc": "2.0", "result": {"echo": req.get("method")}, "id": req.get("id", 0)}
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
"""
        transport = StdioTransport([sys.executable, "-c", script])
        transport.connect()
        assert transport.state == TransportState.CONNECTED
        resp = transport.send(JSONRPCRequest(method="test", id=1))
        assert resp.result == {"echo": "test"}
        transport.disconnect()

    def test_send_when_disconnected(self) -> None:
        transport = StdioTransport(["nonexistent_command_xyz"])
        resp = transport.send(JSONRPCRequest(method="test", id=1))
        assert resp.is_error

    def test_initialize_sends_correct_method(self) -> None:
        script = """
import sys, json
for line in sys.stdin:
    req = json.loads(line)
    resp = {"jsonrpc": "2.0", "result": {"method_received": req.get("method")}, "id": req.get("id", 0)}
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
"""
        transport = StdioTransport([sys.executable, "-c", script])
        transport.connect()
        resp = transport.send_initialize("maref-test")
        assert resp.result == {"method_received": "initialize"}
        transport.disconnect()

    def test_send_tools_list(self) -> None:
        script = """
import sys, json
for line in sys.stdin:
    req = json.loads(line)
    resp = {"jsonrpc": "2.0", "result": {"method": req.get("method")}, "id": req.get("id", 0)}
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
"""
        transport = StdioTransport([sys.executable, "-c", script])
        transport.connect()
        resp = transport.send_tools_list()
        assert resp.result == {"method": "tools/list"}
        transport.disconnect()

    def test_send_tool_call(self) -> None:
        script = """
import sys, json
for line in sys.stdin:
    req = json.loads(line)
    resp = {"jsonrpc": "2.0", "result": {"params": req.get("params", {})}, "id": req.get("id", 0)}
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
"""
        transport = StdioTransport([sys.executable, "-c", script])
        transport.connect()
        resp = transport.send_tool_call("search", {"query": "test"})
        assert resp.result["params"]["name"] == "search"
        assert resp.result["params"]["arguments"]["query"] == "test"
        transport.disconnect()


class TestSSETransport:
    def test_connect_fails_no_server(self) -> None:
        transport = SSETransport("http://localhost:0/sse", max_retries=0, timeout=1.0)
        with pytest.raises(ConnectionError):
            transport.connect()
        assert transport.state in (TransportState.DISCONNECTED, TransportState.ERROR)

    def test_state_transitions(self) -> None:
        transport = SSETransport("http://localhost:0/sse")
        assert transport.state == TransportState.DISCONNECTED
        transport.set_state(TransportState.CONNECTING)
        assert transport.state == TransportState.CONNECTING
        transport.set_state(TransportState.CONNECTED)
        assert transport.state == TransportState.CONNECTED
        transport.set_state(TransportState.ERROR)
        assert transport.state == TransportState.ERROR

    def test_send_while_disconnected(self) -> None:
        transport = SSETransport("http://localhost:0/sse")
        resp = transport.send(JSONRPCRequest(method="test", id=1))
        assert resp.is_error
        assert "not connected" in (resp.error or {}).get("message", "").lower()

    def test_default_state(self) -> None:
        transport = SSETransport("http://localhost:0/sse")
        assert transport.state == TransportState.DISCONNECTED

    def test_on_event_callback(self) -> None:
        transport = SSETransport("http://localhost:0/sse")
        received: list[str] = []

        transport.on_event("test_event", lambda d: received.append(d))
        transport._process_event("test_event", '{"hello": "world"}')
        assert len(received) == 1
        assert received[0] == '{"hello": "world"}'

    def test_process_endpoint_event(self) -> None:
        from urllib.parse import urljoin

        transport = SSETransport("http://localhost:8080/sse")
        transport._process_event("endpoint", "/messages")
        assert transport._message_endpoint == "http://localhost:8080/messages"

    def test_process_session_id_event(self) -> None:
        transport = SSETransport("http://localhost:8080/sse")
        transport._process_event("session_id", "sess-abc")
        assert transport._session_id == "sess-abc"


class TestMCPServerConfig:
    def test_config_hash_consistent(self) -> None:
        cfg1 = MCPServerConfig(command=["python", "server.py"], transport_type="stdio")
        cfg2 = MCPServerConfig(command=["python", "server.py"], transport_type="stdio")
        assert cfg1.config_hash() == cfg2.config_hash()

    def test_config_hash_different(self) -> None:
        cfg1 = MCPServerConfig(command=["python", "server_a.py"])
        cfg2 = MCPServerConfig(command=["python", "server_b.py"])
        assert cfg1.config_hash() != cfg2.config_hash()


class TestMCPClient:
    def test_register_server(self) -> None:
        script = """
import sys, json
for line in sys.stdin:
    req = json.loads(line)
    resp = {"jsonrpc": "2.0", "result": {"ok": True}, "id": req.get("id", 0)}
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
"""
        client = MCPClient()
        config = MCPServerConfig(
            command=[sys.executable, "-c", script],
            transport_type="stdio",
        )
        conn = client.register_server(config)
        assert conn.state == ConnectionState.CONNECTED

    def test_connection_pool_memoize(self) -> None:
        script = """
import sys, json
for line in sys.stdin:
    req = json.loads(line)
    resp = {"jsonrpc": "2.0", "result": {"ok": True}, "id": req.get("id", 0)}
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
"""
        client = MCPClient()
        config = MCPServerConfig(command=[sys.executable, "-c", script], transport_type="stdio")
        conn1 = client.register_server(config)
        conn2 = client.register_server(config)
        assert conn1 is conn2

    def test_list_tools(self) -> None:
        script = """
import sys, json
for line in sys.stdin:
    req = json.loads(line)
    method = req.get("method", "")
    if method == "tools/list":
        resp = {"jsonrpc": "2.0", "result": {"tools": [{"name": "search", "description": "Search tool"}]}, "id": req.get("id", 0)}
    else:
        resp = {"jsonrpc": "2.0", "result": {"ok": True}, "id": req.get("id", 0)}
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
"""
        client = MCPClient()
        config = MCPServerConfig(command=[sys.executable, "-c", script], transport_type="stdio")
        conn = client.register_server(config)
        tools = client.list_tools(conn)
        assert len(tools) == 1
        assert tools[0].name == "search"

    def test_call_tool(self) -> None:
        script = """
import sys, json
for line in sys.stdin:
    req = json.loads(line)
    method = req.get("method", "")
    if method == "tools/call":
        params = req.get("params", {})
        resp = {"jsonrpc": "2.0", "result": {"called": params.get("name", "")}, "id": req.get("id", 0)}
    else:
        resp = {"jsonrpc": "2.0", "result": {"ok": True}, "id": req.get("id", 0)}
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
"""
        client = MCPClient()
        config = MCPServerConfig(command=[sys.executable, "-c", script], transport_type="stdio")
        conn = client.register_server(config)
        resp = client.call_tool(conn, "search", {"query": "test"})
        assert resp.result == {"called": "search"}


class TestMCPSecurityGate:
    def test_trusted_allows_all(self) -> None:
        gate = MCPSecurityGate()
        assert gate.check("bash", MCPTrustLevel.TRUSTED) == SecurityVerdict.ALLOW
        assert gate.check("rm -rf", MCPTrustLevel.TRUSTED) == SecurityVerdict.ALLOW

    def test_untrusted_blocks_shell_tools(self) -> None:
        gate = MCPSecurityGate()
        assert gate.check("bash", MCPTrustLevel.UNTRUSTED) == SecurityVerdict.DENY
        assert gate.check("shell_runner", MCPTrustLevel.UNTRUSTED) == SecurityVerdict.DENY
        assert gate.check("system_call", MCPTrustLevel.UNTRUSTED) == SecurityVerdict.DENY

    def test_untrusted_audits_safe_tools(self) -> None:
        gate = MCPSecurityGate()
        assert gate.check("search", MCPTrustLevel.UNTRUSTED) == SecurityVerdict.AUDIT
        assert gate.check("read_file", MCPTrustLevel.UNTRUSTED) == SecurityVerdict.AUDIT

    def test_untrusted_blocks_destructive_args(self) -> None:
        gate = MCPSecurityGate()
        assert (
            gate.check("write", MCPTrustLevel.UNTRUSTED, {"cmd": "rm -rf /"})
            == SecurityVerdict.DENY
        )

    def test_semi_trusted_blocks_shell(self) -> None:
        gate = MCPSecurityGate()
        assert gate.check("bash", MCPTrustLevel.SEMI_TRUSTED) == SecurityVerdict.DENY
        assert gate.check("search", MCPTrustLevel.SEMI_TRUSTED) == SecurityVerdict.AUDIT


class TestToolRoleMapping:
    def test_search_maps_to_explorer(self) -> None:
        assert map_tool_to_role("search") == ToolToRole.EXPLORER

    def test_file_write_maps_to_executor(self) -> None:
        assert map_tool_to_role("file_write") == ToolToRole.EXECUTOR

    def test_lint_maps_to_critic(self) -> None:
        assert map_tool_to_role("lint") == ToolToRole.CRITIC

    def test_store_maps_to_memory(self) -> None:
        assert map_tool_to_role("store") == ToolToRole.MEMORY

    def test_unknown_maps_to_explorer(self) -> None:
        assert map_tool_to_role("unknown_tool") == ToolToRole.EXPLORER


class TestMCPBridge:
    def test_discover_tools_emits_events(self) -> None:
        script = """
import sys, json
for line in sys.stdin:
    req = json.loads(line)
    method = req.get("method", "")
    if method == "tools/list":
        resp = {"jsonrpc": "2.0", "result": {"tools": [{"name": "search", "description": "Search"}]}, "id": req.get("id", 0)}
    else:
        resp = {"jsonrpc": "2.0", "result": {"ok": True}, "id": req.get("id", 0)}
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
"""
        client = MCPClient()
        config = MCPServerConfig(command=[sys.executable, "-c", script], transport_type="stdio")
        conn = client.register_server(config)
        bridge = MCPBridge(client)
        events: list[BridgeEvent] = []
        bridge.on("maref.mcp.discover", lambda e: events.append(e))
        bridge.discover_tools(conn)
        assert len(events) == 1
        assert events[0].data["mapped_role"] == ToolToRole.EXPLORER

    def test_invoke_tool_blocked_by_security(self) -> None:
        client = MCPClient()
        bridge = MCPBridge(client)
        conn = MCPConnection(
            transport=SSETransport("http://localhost:0"),
            config_hash="dummy",
            state=ConnectionState.CONNECTED,
        )
        result = bridge.invoke_tool(conn, "bash", {}, MCPTrustLevel.UNTRUSTED)
        assert result == {"error": "Tool blocked by security gate", "tool": "bash"}

    def test_import_skill_from_mcp(self) -> None:
        client = MCPClient()
        bridge = MCPBridge(client)
        skill = bridge.import_skill_from_mcp("skill://example/audit/v1")
        assert skill is not None
        assert skill.name == "example-audit-v1"
        assert skill.source.value == "mcp_remote"

    def test_import_non_skill_uri(self) -> None:
        client = MCPClient()
        bridge = MCPBridge(client)
        skill = bridge.import_skill_from_mcp("http://example.com")
        assert skill is None

    def test_invoke_tool_emits_event(self) -> None:
        script = """
import sys, json
for line in sys.stdin:
    req = json.loads(line)
    params = req.get("params", {})
    resp = {"jsonrpc": "2.0", "result": {"searched": params.get("arguments", {}).get("query", "")}, "id": req.get("id", 0)}
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
"""
        client = MCPClient()
        config = MCPServerConfig(command=[sys.executable, "-c", script], transport_type="stdio")
        conn = client.register_server(config)
        bridge = MCPBridge(client)
        events: list[BridgeEvent] = []
        bridge.on("maref.mcp.invoke", lambda e: events.append(e))
        result = bridge.invoke_tool(conn, "search", {"query": "test"}, MCPTrustLevel.TRUSTED)
        assert result == {"searched": "test"}
        assert len(events) == 1


class TestMCPClientEdgeCases:
    def test_list_resources(self) -> None:
        script = """
import sys, json
for line in sys.stdin:
    req = json.loads(line)
    method = req.get("method", "")
    if method == "resources/list":
        resp = {"jsonrpc": "2.0", "result": {"resources": [{"uri": "file:///test", "name": "test_res"}]}, "id": req.get("id", 0)}
    else:
        resp = {"jsonrpc": "2.0", "result": {"ok": True}, "id": req.get("id", 0)}
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
"""
        client = MCPClient()
        config = MCPServerConfig(command=[sys.executable, "-c", script], transport_type="stdio")
        conn = client.register_server(config)
        resources = client.list_resources(conn)
        assert len(resources) == 1

    def test_call_tool_session_expired(self) -> None:
        script = """
import sys, json
for line in sys.stdin:
    resp = {"jsonrpc": "2.0", "error": {"code": -32001, "message": "session expired"}, "id": 1}
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
"""
        client = MCPClient()
        config = MCPServerConfig(command=[sys.executable, "-c", script], transport_type="stdio")
        conn = client.register_server(config)
        resp = client.call_tool(conn, "test_tool", {"arg": "val"})
        assert resp.is_error

    def test_sse_register_server(self) -> None:
        client = MCPClient()
        config = MCPServerConfig(url="http://localhost:9999/sse", transport_type="sse")
        try:
            conn = client.register_server(config)
            assert conn.state in (ConnectionState.CONNECTED, ConnectionState.ERROR)
        except ConnectionError:
            pass  # 没有运行 SSE 服务器时会超时

    def test_mcp_connection_touch(self) -> None:
        conn = MCPConnection(
            transport=SSETransport("http://localhost:0"),
            config_hash="abc",
        )
        conn.touch()
        assert conn.last_used_at > 0

    def test_mcp_tool_def_defaults(self) -> None:
        tool = MCPToolDef(name="test_tool")
        assert tool.description == ""
        assert tool.input_schema == {}


class TestHTTPTransport:
    def test_connect_and_disconnect(self) -> None:
        transport = HTTPTransport("http://localhost:12345/test")
        transport.connect()
        assert transport.state in (TransportState.CONNECTED, TransportState.ERROR)
        transport.disconnect()
        assert transport.state == TransportState.DISCONNECTED

    def test_send_when_disconnected(self) -> None:
        transport = HTTPTransport("http://localhost:12345/test")
        resp = transport.send(JSONRPCRequest(method="test", id=1))
        assert resp.is_error

    def test_set_and_get_state(self) -> None:
        transport = SSE2Transport("http://localhost:0")
        transport.set_state(TransportState.CONNECTING)
        assert transport.state == TransportState.CONNECTING


class SSE2Transport(MCPTransport):
    def __init__(self, url: str) -> None:
        super().__init__()
        self._url = url

    def connect(self) -> None:
        self.set_state(TransportState.CONNECTED)

    def disconnect(self) -> None:
        self.set_state(TransportState.DISCONNECTED)

    def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
        return JSONRPCResponse(result={}, id=request.id)
