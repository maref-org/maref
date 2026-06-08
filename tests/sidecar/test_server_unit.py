"""
Comprehensive unit tests for MAREF Sidecar Server (FastAPI).

Covers:
  - Factory function create_app()
  - Health, agents, observations, anomalies, metrics endpoints
  - Providers, skills, tasks endpoints
  - Session CRUD (create, list, get, delete)
  - Messages (get, send)
  - Streaming (SSE) and interrupt
  - Terminal WebSocket
  - MCP JSON-RPC endpoints
  - Compliance endpoints
  - RED metrics endpoint
  - SidecarServer backward compatibility class

All external dependencies are mocked.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from sidecar.server import PROVIDERS, SKILLS, MOCK_TASKS, SidecarServer, create_app


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def mock_collector():
    """Mock ObservationCollector."""
    collector = MagicMock()
    collector._running = True
    collector.get_buffer_size.return_value = 42
    collector.get_recent.return_value = []
    return collector


@pytest.fixture
def mock_monitor():
    """Mock CompositeMonitor."""
    monitor = MagicMock()
    monitor.get_recent_anomalies.return_value = []
    monitor.get_critical_count.return_value = 0
    monitor.get_anomaly_count.return_value = 0
    return monitor


@pytest.fixture
def client(mock_collector, mock_monitor):
    """TestClient with mocked collector and monitor."""
    app = create_app(collector=mock_collector, monitor=mock_monitor)
    return TestClient(app)


@pytest.fixture
def client_no_deps():
    """TestClient without collector/monitor."""
    app = create_app()
    return TestClient(app)


# ── Health & Observation Endpoints ───────────────────────────────────


class TestHealthEndpoint:
    def test_health_with_collector(self, client, mock_collector):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["collector_running"] is True
        assert data["buffer_size"] == 42

    def test_health_without_collector(self, client_no_deps):
        response = client_no_deps.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestAgentsEndpoint:
    def test_agents_with_collector(self, client, mock_collector):
        mock_collector.get_recent.return_value = []
        response = client.get("/api/agents")
        assert response.status_code == 200
        assert response.json() == {"agents": []}

    def test_agents_without_collector(self, client_no_deps):
        response = client_no_deps.get("/api/agents")
        assert response.status_code == 200
        assert response.json() == {"agents": []}


class TestObservationsEndpoint:
    def test_observations_with_collector(self, client, mock_collector):
        mock_collector.get_recent.return_value = []
        response = client.get("/api/observations")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["observations"] == []

    def test_observations_without_collector(self, client_no_deps):
        response = client_no_deps.get("/api/observations")
        assert response.status_code == 200
        assert response.json() == {"count": 0, "observations": []}


class TestAnomaliesEndpoint:
    def test_anomalies_with_monitor(self, client, mock_monitor):
        response = client.get("/api/anomalies")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["critical_count"] == 0
        assert data["anomalies"] == []

    def test_anomalies_without_monitor(self, client_no_deps):
        response = client_no_deps.get("/api/anomalies")
        assert response.status_code == 200
        assert response.json() == {"count": 0, "critical_count": 0, "anomalies": []}


class TestMetricsEndpoint:
    def test_metrics_with_deps(self, client, mock_collector, mock_monitor):
        mock_collector.get_buffer_size.return_value = 10
        mock_monitor.get_anomaly_count.return_value = 2
        mock_monitor.get_critical_count.return_value = 1
        response = client.get("/api/metrics")
        assert response.status_code == 200
        text = response.text
        assert "maref_observations_total 10" in text
        assert "maref_anomalies_total 2" in text
        assert "maref_anomalies_critical 1" in text

    def test_metrics_without_deps(self, client_no_deps):
        response = client_no_deps.get("/api/metrics")
        assert response.status_code == 200
        text = response.text
        assert "maref_observations_total 0" in text
        assert "maref_anomalies_total 0" in text
        assert "maref_anomalies_critical 0" in text


class TestRedMetricsEndpoint:
    def test_red_metrics(self, client):
        with patch(
            "sidecar.server._global_red_collector"
        ) as mock_red:
            mock_red.get_red_summary.return_value = {"rate": 1.0}
            mock_red.get_path_metrics.return_value = {}
            response = client.get("/api/red-metrics?window=60")
            assert response.status_code == 200
            data = response.json()
            assert data["summary"] == {"rate": 1.0}
            assert data["by_path"] == {}
            mock_red.get_red_summary.assert_called_once_with(60)


# ── Provider, Skill, Task Endpoints ──────────────────────────────────


class TestProvidersEndpoint:
    def test_providers(self, client):
        response = client.get("/api/providers")
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert len(data["providers"]) == len(PROVIDERS)
        assert data["providers"][0]["id"] == "ollama"


class TestSkillsEndpoint:
    def test_skills(self, client):
        response = client.get("/api/skills")
        assert response.status_code == 200
        data = response.json()
        assert "skills" in data
        assert len(data["skills"]) == len(SKILLS)
        assert data["skills"][0]["id"] == "file-browser"


class TestTasksEndpoint:
    def test_tasks_empty_sessions(self, client):
        response = client.get("/api/tasks")
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert len(data["tasks"]) == len(MOCK_TASKS)

    def test_tasks_with_session(self, client):
        # Create a session first so tasks attach sessionId
        client.post("/api/sessions", json={"title": "Test"})
        response = client.get("/api/tasks")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == len(MOCK_TASKS)
        # When sessions exist, first task gets the first session id
        assert data["tasks"][0]["sessionId"] != ""


# ── Session CRUD ─────────────────────────────────────────────────────


class TestSessionCRUD:
    def test_create_session(self, client):
        response = client.post(
            "/api/sessions",
            json={
                "title": "Test Session",
                "mode": "agent",
                "provider": "openai",
                "model": "gpt-4o",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Session"
        assert data["mode"] == "agent"
        assert data["provider"] == "openai"
        assert data["model"] == "gpt-4o"
        assert data["status"] == "idle"
        assert "id" in data

    def test_create_session_defaults(self, client):
        response = client.post("/api/sessions", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "新 Agent"
        assert data["mode"] == "agent"
        assert data["provider"] == "bailian"
        assert data["model"] == "deepseek-v4-pro"

    def test_list_sessions(self, client):
        client.post("/api/sessions", json={"title": "S1"})
        client.post("/api/sessions", json={"title": "S2"})
        response = client.get("/api/sessions")
        assert response.status_code == 200
        data = response.json()
        assert len(data["sessions"]) >= 2

    def test_get_session(self, client):
        create_resp = client.post("/api/sessions", json={"title": "Get Me"})
        sid = create_resp.json()["id"]
        response = client.get(f"/api/sessions/{sid}")
        assert response.status_code == 200
        assert response.json()["id"] == sid

    def test_get_session_not_found(self, client):
        response = client.get("/api/sessions/nonexistent")
        assert response.status_code == 404
        assert response.json()["detail"] == "Session not found"

    def test_delete_session(self, client):
        create_resp = client.post("/api/sessions", json={"title": "Delete Me"})
        sid = create_resp.json()["id"]
        response = client.delete(f"/api/sessions/{sid}")
        assert response.status_code == 200
        assert response.json() == {"deleted": True}
        assert client.get(f"/api/sessions/{sid}").status_code == 404

    def test_delete_session_not_found(self, client):
        response = client.delete("/api/sessions/nonexistent")
        assert response.status_code == 404
        assert response.json()["detail"] == "Session not found"


# ── Messages ─────────────────────────────────────────────────────────


class TestMessagesEndpoint:
    def test_get_messages(self, client):
        create_resp = client.post("/api/sessions", json={"title": "Msg Test"})
        sid = create_resp.json()["id"]
        response = client.get(f"/api/sessions/{sid}/messages")
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        # Welcome message is auto-added
        assert len(data["messages"]) == 1
        assert data["messages"][0]["role"] == "assistant"

    def test_get_messages_session_not_found(self, client):
        response = client.get("/api/sessions/nonexistent/messages")
        assert response.status_code == 404

    def test_send_message(self, client):
        create_resp = client.post("/api/sessions", json={"title": "Send Test"})
        sid = create_resp.json()["id"]
        response = client.post(
            f"/api/sessions/{sid}/messages",
            json={"content": "Hello"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "user"
        assert data["content"] == "Hello"
        assert data["sessionId"] == sid

    def test_send_message_empty_content(self, client):
        create_resp = client.post("/api/sessions", json={"title": "Empty Test"})
        sid = create_resp.json()["id"]
        response = client.post(
            f"/api/sessions/{sid}/messages",
            json={"content": "   "},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Content required"

    def test_send_message_session_not_found(self, client):
        response = client.post(
            "/api/sessions/nonexistent/messages",
            json={"content": "Hello"},
        )
        assert response.status_code == 404


# ── Streaming & Interrupt ────────────────────────────────────────────


class TestStreamingEndpoint:
    def test_stream_session_not_found(self, client):
        response = client.get("/api/sessions/nonexistent/stream")
        assert response.status_code == 404

    def test_stream_success(self, client):
        create_resp = client.post("/api/sessions", json={"title": "Stream Test"})
        sid = create_resp.json()["id"]
        # Add a user message so stream has content to respond to
        client.post(f"/api/sessions/{sid}/messages", json={"content": "capabilities"})

        with patch(
            "sidecar.server.StreamEngine.generate_stream"
        ) as mock_gen:

            async def _fake_gen(*_a, **_k):
                from sidecar.stream_engine import StreamEvent

                yield StreamEvent(type="thinking")
                yield StreamEvent(type="response", content="H")
                yield StreamEvent(type="done")

            mock_gen.return_value = _fake_gen()
            response = client.get(f"/api/sessions/{sid}/stream")
            assert response.status_code == 200
            # SSE response
            assert "text/event-stream" in response.headers.get("content-type", "")
            text = response.text
            assert "event: thinking" in text
            assert "event: response" in text
            assert "event: done" in text


class TestInterruptEndpoint:
    def test_interrupt(self, client):
        create_resp = client.post("/api/sessions", json={"title": "Interrupt Test"})
        sid = create_resp.json()["id"]
        with patch(
            "sidecar.server.StreamEngine.interrupt"
        ) as mock_interrupt:
            mock_interrupt.return_value = True
            response = client.post(f"/api/sessions/{sid}/interrupt")
            assert response.status_code == 200
            assert response.json() == {"interrupted": True}
            mock_interrupt.assert_called_once_with(sid)


# ── Terminal WebSocket ───────────────────────────────────────────────


class TestTerminalWebSocket:
    def test_terminal_ws(self, client):
        create_resp = client.post("/api/sessions", json={"title": "Terminal Test"})
        sid = create_resp.json()["id"]

        async def _fake_handle(ws, session_id):
            await ws.accept()
            await ws.close()

        with patch(
            "sidecar.server.TerminalBridge.handle_websocket",
            side_effect=_fake_handle,
        ) as mock_handle:
            with client.websocket_connect(f"/api/sessions/{sid}/terminal"):
                pass
            mock_handle.assert_called_once()
            call_args = mock_handle.call_args
            assert call_args[0][1] == sid


# ── MCP Endpoints ────────────────────────────────────────────────────


class TestMCPEndpoints:
    def test_mcp_initialize(self, client):
        response = client.post(
            "/api/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert "result" in data
        assert data["result"]["protocolVersion"] == "2024-11-05"

    def test_mcp_tools_list(self, client):
        response = client.post(
            "/api/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "tools" in data["result"]

    def test_mcp_resources_list(self, client):
        response = client.post(
            "/api/mcp",
            json={"jsonrpc": "2.0", "id": 3, "method": "resources/list"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "resources" in data["result"]

    def test_mcp_prompts_list(self, client):
        response = client.post(
            "/api/mcp",
            json={"jsonrpc": "2.0", "id": 4, "method": "prompts/list"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "prompts" in data["result"]

    def test_mcp_tools_call(self, client, mock_collector):
        with patch(
            "sidecar.server.SidecarMCPBridge.handle_tool_call"
        ) as mock_handle, patch(
            "sidecar.server.get_current_trace_id", create=True, return_value="trace-123"
        ):
            mock_handle.return_value = {"content": [{"type": "text", "text": "ok"}]}
            response = client.post(
                "/api/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {"name": "maref_observe_agent", "arguments": {}},
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["result"] == {"content": [{"type": "text", "text": "ok"}]}

    def test_mcp_method_not_found(self, client):
        response = client.post(
            "/api/mcp",
            json={"jsonrpc": "2.0", "id": 6, "method": "unknown/method"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32601

    def test_mcp_well_known(self, client):
        response = client.get("/api/mcp/.well-known")
        assert response.status_code == 200
        data = response.json()
        assert data["protocol"] == "mcp"
        assert data["endpoint"] == "/api/mcp"
        assert "capabilities" in data


# ── Compliance Endpoints ─────────────────────────────────────────────


class TestComplianceEndpoints:
    def test_compliance_register(self, client):
        response = client.post(
            "/api/compliance/register",
            json={
                "agent_id": "agent-1",
                "data_residency": "US",
                "model_backend": "EU",
                "cross_border": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "agent-1"
        assert data["status"] == "registered"
        assert "governance_state" in data

    def test_compliance_agents(self, client):
        client.post(
            "/api/compliance/register",
            json={"agent_id": "agent-1"},
        )
        response = client.get("/api/compliance/agents")
        assert response.status_code == 200
        data = response.json()
        assert len(data["agents"]) == 1
        assert data["agents"][0]["agent_id"] == "agent-1"

    def test_compliance_check_action_allowed(self, client):
        client.post(
            "/api/compliance/register",
            json={"agent_id": "agent-1", "phase": "OLD_YANG"},
        )
        response = client.post(
            "/api/compliance/check-action",
            json={
                "agent_id": "agent-1",
                "action": "read_file",
                "action_type": "tool_execution",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is True
        assert "decision" in data

    def test_compliance_check_action_not_registered(self, client):
        response = client.post(
            "/api/compliance/check-action",
            json={
                "agent_id": "agent-missing",
                "action": "read_file",
                "action_type": "tool_execution",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is False
        assert "error" in data

    def test_compliance_snapshot(self, client):
        client.post(
            "/api/compliance/register",
            json={"agent_id": "agent-1"},
        )
        with patch(
            "sidecar.compliance.unified.UnifiedSidecar.run_compliance_snapshot"
        ) as mock_snap:
            from sidecar.compliance.policy import ComplianceCheckResult, ComplianceRuleSeverity
            mock_snap.return_value = [
                ComplianceCheckResult(
                    rule_id="r1",
                    passed=True,
                    severity=ComplianceRuleSeverity.INFO,
                    message="ok",
                )
            ]
            response = client.post(
                "/api/compliance/snapshot",
                json={"agent_id": "agent-1"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["agent_id"] == "agent-1"
            assert "results" in data
            assert "has_critical" in data

    def test_compliance_snapshot_not_registered(self, client):
        response = client.post(
            "/api/compliance/snapshot",
            json={"agent_id": "agent-missing"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "error" in data

    def test_compliance_audit_log(self, client):
        client.post(
            "/api/compliance/register",
            json={"agent_id": "agent-1", "phase": "OLD_YANG"},
        )
        client.post(
            "/api/compliance/check-action",
            json={
                "agent_id": "agent-1",
                "action": "read_file",
                "action_type": "tool_execution",
            },
        )
        response = client.get("/api/compliance/audit-log/agent-1")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "agent-1"
        assert len(data["audit_log"]) >= 1

    def test_compliance_audit_log_not_registered(self, client):
        response = client.get("/api/compliance/audit-log/agent-missing")
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert data["audit_log"] == []


# ── SidecarServer Backward Compatibility ─────────────────────────────


class TestSidecarServerBackwardCompat:
    def test_init(self):
        server = SidecarServer()
        assert server._running is True

    def test_handle_request_health(self):
        server = SidecarServer()
        response = server._handle_request("GET /health HTTP/1.1")
        assert b"200 OK" in response
        assert b"healthy" in response

    def test_handle_request_agents(self):
        server = SidecarServer()
        response = server._handle_request("GET /agents HTTP/1.1")
        assert b"200 OK" in response
        assert b"agents" in response

    def test_handle_request_observations(self):
        server = SidecarServer()
        response = server._handle_request("GET /observations HTTP/1.1")
        assert b"200 OK" in response
        assert b"count" in response

    def test_handle_request_anomalies(self):
        server = SidecarServer()
        response = server._handle_request("GET /anomalies HTTP/1.1")
        assert b"200 OK" in response
        assert b"anomalies" in response

    def test_handle_request_metrics(self):
        server = SidecarServer()
        response = server._handle_request("GET /metrics HTTP/1.1")
        assert b"200 OK" in response
        assert b"maref_observations_total" in response

    def test_handle_request_nonexistent(self):
        server = SidecarServer()
        response = server._handle_request("GET /nonexistent HTTP/1.1")
        assert b"404 Not Found" in response

    def test_handle_request_bad_request(self):
        server = SidecarServer()
        response = server._handle_request("BADREQUEST")
        assert b"400 Bad Request" in response

    def test_stop(self):
        server = SidecarServer()
        server.stop()
        assert server._running is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
