"""Integration test: MCP → Governance/Audit call chain via Sidecar server."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

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


class TestMCPIntegration:
    def test_full_mcp_initialize_chain(self, client: TestClient) -> None:
        """MCP initialize → SidecarMCPBridge.get_server_info → JSON-RPC response."""
        response = client.post(
            "/api/mcp",
            json={"jsonrpc": "2.0", "method": "initialize", "id": 1},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert data["result"]["protocolVersion"] == "2024-11-05"
        assert data["result"]["serverInfo"]["name"] == "MAREF Sidecar"

    def test_full_mcp_tools_list_chain(self, client: TestClient) -> None:
        """MCP tools/list → SidecarMCPBridge.list_tools → response."""
        response = client.post(
            "/api/mcp",
            json={"jsonrpc": "2.0", "method": "tools/list", "id": 2},
        )
        assert response.status_code == 200
        data = response.json()
        tools = data["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        assert "maref_health_check" in tool_names
        assert "maref_list_agents" in tool_names
        assert "maref_compliance_check" in tool_names
        assert all("description" in t for t in tools)
        assert all("inputSchema" in t for t in tools)

    def test_tool_call_real_tool(self, client: TestClient) -> None:
        """tools/call → handle_tool_call → tool result response."""
        response = client.post(
            "/api/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 3,
                "params": {
                    "name": "maref_health_check",
                    "arguments": {"detail": True},
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert "content" in data["result"]
        assert data["result"]["content"][0]["type"] == "text"

    def test_tool_call_with_args(self, client: TestClient) -> None:
        """tools/call for maref_list_agents (no args)."""
        response = client.post(
            "/api/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 4,
                "params": {
                    "name": "maref_list_agents",
                    "arguments": {},
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "result" in data

    def test_tool_call_unknown(self, client: TestClient) -> None:
        """tools/call for nonexistent tool → isError response."""
        response = client.post(
            "/api/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 5,
                "params": {
                    "name": "nonexistent_tool",
                    "arguments": {},
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["result"]["isError"] is True
        assert "No backend registered" in data["result"]["content"][0]["text"]

    def test_tool_call_compliance_check(self, client: TestClient) -> None:
        """tools/call for maref_compliance_check."""
        response = client.post(
            "/api/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 6,
                "params": {
                    "name": "maref_compliance_check",
                    "arguments": {
                        "agent_id": "agent-1",
                        "action": "read_file",
                    },
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "result" in data

    def test_health_endpoint_chain(self, client: TestClient) -> None:
        """GET /api/health → collector status."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_version_endpoint_aligned(self, client: TestClient) -> None:
        """GET /api/version → version string."""
        response = client.get("/api/version")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data

    def test_mcp_well_known_structure(self, client: TestClient) -> None:
        """GET /api/mcp/.well-known → capabilities listing."""
        response = client.get("/api/mcp/.well-known")
        assert response.status_code == 200
        data = response.json()
        assert data["protocol"] == "mcp"
        assert data["version"] == "2024-11-05"
        assert "tools" in data["capabilities"]
        assert len(data["capabilities"]["tools"]) > 0

    def test_full_governance_state_availability(self, client: TestClient) -> None:
        """GET /api/v1/governance/state returns governance data."""
        response = client.get("/api/v1/governance/state")
        assert response.status_code == 200
        data = response.json()
        assert "state" in data
        assert "entropy" in data
        assert "circuit_breaker" in data
        assert data["state"] in ("OBSERVE", "ANALYZE", "EVALUATE", "DECIDE", "ACT", "VERIFY", "STABILIZE", "REPORT", "INIT")
