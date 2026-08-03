"""v0.47 S7 — /api/mcp routed through MCPGateway three-layer governance.

The main MCP JSON-RPC entrypoint must go through the same
SecurityGate → PolicyEngine → CircuitBreaker governance as
``/api/mcp/gateway/tools/call`` (previously it bypassed straight to
``SidecarMCPBridge.handle_tool_call``).

These tests verify the routing path directly: ``/api/mcp`` ``tools/call``
must invoke ``MCPGateway.route_tool_call`` (not the raw bridge handler).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from sidecar.collector import MockAgentAdapter, ObservationCollector
from sidecar.monitor import CompositeMonitor
from sidecar.server import create_app


@pytest.fixture
def client() -> TestClient:
    adapter = MockAgentAdapter(num_agents=2)
    collector = ObservationCollector(adapter)
    monitor = CompositeMonitor()
    app = create_app(collector, monitor, allow_unauthenticated=True)
    return TestClient(app)


class TestMCPMainEntrypointGoverned:
    @patch("sidecar.server.MCPGateway.route_tool_call")
    def test_tools_call_routes_through_gateway(self, mock_route: object, client: TestClient) -> None:
        """tools/call goes through MCPGateway.route_tool_call."""
        mock_route.return_value = {
            "content": [{"type": "text", "text": "governed"}],
        }
        response = client.post(
            "/api/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 1,
                "params": {"name": "maref_list_agents", "arguments": {}},
            },
        )
        assert response.status_code == 200
        assert mock_route.called
        name_arg = mock_route.call_args[0][0] if mock_route.call_args else None
        assert name_arg == "maref_list_agents"

    @patch("sidecar.server.MCPGateway.route_tool_call")
    def test_tools_call_gateway_result_wrapped_jsonrpc(self, mock_route: object, client: TestClient) -> None:
        """The gateway result is wrapped in a JSON-RPC response."""
        mock_route.return_value = {
            "content": [{"type": "text", "text": "done"}],
        }
        response = client.post(
            "/api/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 7,
                "params": {"name": "maref_health_check", "arguments": {}},
            },
        )
        data = response.json()
        assert data["id"] == 7
        assert data["result"]["content"][0]["text"] == "done"

    @patch("sidecar.server.MCPGateway.route_tool_call")
    def test_tools_call_gateway_denial_is_error(self, mock_route: object, client: TestClient) -> None:
        """A governance denial from the gateway surfaces as an isError result."""
        mock_route.return_value = {
            "isError": True,
            "content": [{"type": "text", "text": "Security gate denied"}],
        }
        response = client.post(
            "/api/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 8,
                "params": {"name": "maref_bash", "arguments": {}},
            },
        )
        data = response.json()
        assert data["result"]["isError"] is True

    def test_initialize_still_served_by_bridge(self, client: TestClient) -> None:
        """Non-call methods (initialize/list) keep using the bridge."""
        response = client.post(
            "/api/mcp",
            json={"jsonrpc": "2.0", "method": "initialize", "id": 1},
        )
        assert response.status_code == 200
        assert response.json()["result"]["serverInfo"]["name"] == "MAREF Sidecar"

    def test_real_security_gate_blocks_dangerous_tool(self, client: TestClient) -> None:
        """The wired MCPSecurityGate genuinely blocks a dangerous tool via
        the main /api/mcp entrypoint (end-to-end, no mocks)."""
        response = client.post(
            "/api/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 4,
                "params": {
                    "name": "maref_exec",
                    "arguments": {"command": "rm -rf /"},
                },
            },
        )
        assert response.status_code == 200
        result = response.json()["result"]
        assert result["isError"] is True
        assert "denied" in result["content"][0]["text"].lower()
