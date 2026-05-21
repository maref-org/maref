from __future__ import annotations

from maref.integration.mcp_transport import JSONRPCRequest
from maref.integration.mcp_server import MCPServer


class TestMCPServerBasics:
    """P1.1: MCP Server 基础功能测试"""

    def test_server_initialize(self):
        server = MCPServer(name="test-server", version="0.1.0")
        req = JSONRPCRequest(method="initialize", params={
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        }, id=1)
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["serverInfo"]["name"] == "test-server"
        assert resp.result["serverInfo"]["version"] == "0.1.0"

    def test_server_tools_list_empty(self):
        server = MCPServer()
        req = JSONRPCRequest(method="tools/list", id=2)
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["tools"] == []

    def test_server_register_tool(self):
        server = MCPServer()
        def echo_handler(args):
            return {"content": [{"type": "text", "text": args.get("message", "")}]}

        server.register_tool(
            name="echo",
            description="Echo the input message",
            input_schema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
            handler=echo_handler,
        )

        req = JSONRPCRequest(method="tools/list", id=3)
        resp = server.handle_request(req)
        assert not resp.is_error
        assert len(resp.result["tools"]) == 1
        assert resp.result["tools"][0]["name"] == "echo"

    def test_server_call_tool(self):
        server = MCPServer()
        def add_handler(args):
            a = args.get("a", 0)
            b = args.get("b", 0)
            return {"content": [{"type": "text", "text": str(a + b)}]}

        server.register_tool(
            name="add",
            description="Add two numbers",
            input_schema={
                "type": "object",
                "properties": {
                    "a": {"type": "number"},
                    "b": {"type": "number"},
                },
                "required": ["a", "b"],
            },
            handler=add_handler,
        )

        req = JSONRPCRequest(
            method="tools/call",
            params={"name": "add", "arguments": {"a": 2, "b": 3}},
            id=4,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        content = resp.result["content"]
        assert content[0]["text"] == "5"

    def test_server_call_unknown_tool(self):
        server = MCPServer()
        req = JSONRPCRequest(
            method="tools/call",
            params={"name": "unknown", "arguments": {}},
            id=5,
        )
        resp = server.handle_request(req)
        assert resp.is_error
        assert resp.error_code == -32602  # Invalid params

    def test_server_resources_list_empty(self):
        server = MCPServer()
        req = JSONRPCRequest(method="resources/list", id=6)
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["resources"] == []

    def test_server_register_and_read_resource(self):
        server = MCPServer()
        def doc_handler(uri):
            return {"contents": [{"uri": uri, "mimeType": "text/plain", "text": "Hello doc"}]}

        server.register_resource(
            uri="doc://readme",
            name="README",
            mime_type="text/plain",
            handler=doc_handler,
        )

        req = JSONRPCRequest(
            method="resources/read",
            params={"uri": "doc://readme"},
            id=7,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["contents"][0]["text"] == "Hello doc"

    def test_server_prompts_list_empty(self):
        server = MCPServer()
        req = JSONRPCRequest(method="prompts/list", id=8)
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["prompts"] == []

    def test_server_register_and_get_prompt(self):
        server = MCPServer()
        def greeting_handler(args):
            name = args.get("name", "World")
            return {
                "description": "A greeting prompt",
                "messages": [
                    {"role": "user", "content": {"type": "text", "text": f"Hello, {name}!"}}
                ],
            }

        server.register_prompt(
            name="greeting",
            description="Greet someone",
            arguments=[
                {"name": "name", "description": "Name to greet", "required": False},
            ],
            handler=greeting_handler,
        )

        req = JSONRPCRequest(
            method="prompts/get",
            params={"name": "greeting", "arguments": {"name": "MAREF"}},
            id=9,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["messages"][0]["content"]["text"] == "Hello, MAREF!"

    def test_server_inprocess_transport(self):
        server = MCPServer()
        transport = server.get_inprocess_transport()
        transport.connect()

        req = JSONRPCRequest(method="initialize", id=10)
        resp = transport.send(req)
        assert not resp.is_error
        assert "serverInfo" in resp.result

    def test_server_unknown_method(self):
        server = MCPServer()
        req = JSONRPCRequest(method="unknown/method", id=11)
        resp = server.handle_request(req)
        assert resp.is_error
        assert resp.error_code == -32601  # Method not found


class TestMCPServerSecurityIntegration:
    """P1.3: MCP Server 与安全模块集成测试"""

    def test_tool_call_with_security_gate(self):
        from maref.integration.mcp_security import MCPSecurityGate, MCPTrustLevel

        gate = MCPSecurityGate()
        server = MCPServer(security_gate=gate)

        def safe_handler(args):
            return {"content": [{"type": "text", "text": "ok"}]}

        server.register_tool(
            name="safe_tool",
            description="A safe tool",
            input_schema={"type": "object", "properties": {}},
            handler=safe_handler,
        )

        req = JSONRPCRequest(
            method="tools/call",
            params={"name": "safe_tool", "arguments": {}},
            id=12,
        )
        resp = server.handle_request(req, trust_level=MCPTrustLevel.TRUSTED)
        assert not resp.is_error
        assert resp.result["content"][0]["text"] == "ok"

    def test_blocked_tool_denied(self):
        from maref.integration.mcp_security import MCPSecurityGate, MCPTrustLevel

        gate = MCPSecurityGate()
        server = MCPServer(security_gate=gate)

        def bash_handler(args):
            return {"content": [{"type": "text", "text": "executed"}]}

        server.register_tool(
            name="bash",
            description="Run bash commands",
            input_schema={"type": "object", "properties": {}},
            handler=bash_handler,
        )

        req = JSONRPCRequest(
            method="tools/call",
            params={"name": "bash", "arguments": {"command": "ls"}},
            id=13,
        )
        resp = server.handle_request(req, trust_level=MCPTrustLevel.UNTRUSTED)
        assert resp.is_error
        assert "blocked" in resp.error["message"].lower() or "deny" in resp.error["message"].lower()
