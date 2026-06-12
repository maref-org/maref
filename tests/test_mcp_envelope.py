"""Tests for MCP message envelope (Article 15-A)."""

import pytest
from maref.integration.mcp_transport import JSONRPCRequest
from maref.integration.mcp_server import MCPServer


def test_request_auto_generates_envelope():
    req = JSONRPCRequest(method="tools/list", id=1)
    assert req.trace_id and len(req.trace_id.split("-")) == 5, "Not a UUID v4"
    assert req.timestamp, "Timestamp missing"
    assert "T" in req.timestamp, "Not ISO-8601 format"


def test_request_without_trace_id_is_rejected():
    server = MCPServer()
    req = JSONRPCRequest(method="tools/list", id=1)
    # Bypass __post_init__ auto-generation to test server-side validation
    object.__setattr__(req, "trace_id", "")
    resp = server.handle_request(req)
    assert resp.is_error
    assert "trace_id" in resp.error["message"].lower()


def test_tools_list_includes_api_version():
    server = MCPServer()
    server.register_tool("test_tool", "A test tool", {"type": "object"}, lambda x: {})
    resp = server._handle_tools_list(1)
    tools = resp.result["tools"]
    for tool in tools:
        assert "api_version" in tool["inputSchema"], f"Tool {tool['name']} missing api_version"


def test_envelope_serialized_in_json():
    req = JSONRPCRequest(method="test", id=1, source_agent="test@runner")
    j = req.to_json()
    import json
    parsed = json.loads(j)
    assert "trace_id" in parsed
    assert "timestamp" in parsed
    assert "source_agent" in parsed
    assert parsed["source_agent"] == "test@runner"
