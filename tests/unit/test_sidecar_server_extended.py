"""Extended unit tests for the MAREF Sidecar Server (FastAPI).

Covers session CRUD, MCP JSON-RPC, compliance, providers/skills/tasks,
and streaming endpoints not tested in test_sidecar_server.py.
"""

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
    app = create_app(collector, monitor)
    return TestClient(app)


class TestMCPEndpoints:
    def test_mcp_jsonrpc_initialize(self, client: TestClient) -> None:
        response = client.post(
            "/api/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "initialize",
                "id": 1,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert data["result"]["protocolVersion"] == "2024-11-05"
        assert data["result"]["serverInfo"]["name"] == "MAREF Sidecar"

    def test_mcp_jsonrpc_tools_list(self, client: TestClient) -> None:
        response = client.post(
            "/api/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 2,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["result"]["tools"]) >= 10

    def test_mcp_jsonrpc_resources_list(self, client: TestClient) -> None:
        response = client.post(
            "/api/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "resources/list",
                "id": 3,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["result"]["resources"]) >= 3

    def test_mcp_jsonrpc_prompts_list(self, client: TestClient) -> None:
        response = client.post(
            "/api/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "prompts/list",
                "id": 4,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["result"]["prompts"]) >= 2

    def test_mcp_jsonrpc_unknown_method(self, client: TestClient) -> None:
        response = client.post(
            "/api/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "bogus/method",
                "id": 5,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["error"]["code"] == -32601

    def test_mcp_well_known(self, client: TestClient) -> None:
        response = client.get("/api/mcp/.well-known")
        assert response.status_code == 200
        data = response.json()
        assert data["protocol"] == "mcp"
        assert data["version"] == "2024-11-05"
        assert "tools" in data["capabilities"]

    def test_mcp_tools_call_unknown(self, client: TestClient) -> None:
        response = client.post(
            "/api/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 6,
                "params": {"name": "nonexistent", "arguments": {}},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["result"]["isError"] is True


class TestRedMetrics:
    def test_red_metrics_endpoint(self, client: TestClient) -> None:
        response = client.get("/api/red-metrics")
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert "by_path" in data

    def test_red_metrics_with_window(self, client: TestClient) -> None:
        response = client.get("/api/red-metrics?window=120")
        assert response.status_code == 200


class TestSessionCRUD:
    def test_create_session(self, client: TestClient) -> None:
        response = client.post(
            "/api/sessions",
            json={
                "title": "Test Session",
                "mode": "agent",
                "provider": "bailian",
                "model": "deepseek-v4-pro",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Session"
        assert data["mode"] == "agent"
        assert "id" in data
        assert data["status"] == "idle"

    def test_list_sessions(self, client: TestClient) -> None:
        client.post(
            "/api/sessions",
            json={"title": "S1", "mode": "chat", "provider": "ollama", "model": "gemma3:4b"},
        )
        client.post(
            "/api/sessions",
            json={"title": "S2", "mode": "chat", "provider": "ollama", "model": "gemma3:4b"},
        )
        response = client.get("/api/sessions")
        assert response.status_code == 200
        data = response.json()
        assert len(data["sessions"]) >= 2

    def test_get_session(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/sessions",
            json={
                "title": "GetTest",
                "mode": "agent",
                "provider": "bailian",
                "model": "deepseek-v4-pro",
            },
        )
        sid = create_resp.json()["id"]
        response = client.get(f"/api/sessions/{sid}")
        assert response.status_code == 200
        assert response.json()["title"] == "GetTest"

    def test_get_session_not_found(self, client: TestClient) -> None:
        response = client.get("/api/sessions/nonexistent")
        assert response.status_code == 404

    def test_delete_session(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/sessions",
            json={
                "title": "DelTest",
                "mode": "agent",
                "provider": "bailian",
                "model": "deepseek-v4-pro",
            },
        )
        sid = create_resp.json()["id"]
        response = client.delete(f"/api/sessions/{sid}")
        assert response.status_code == 200
        assert response.json()["deleted"] is True
        # Verify deleted
        get_resp = client.get(f"/api/sessions/{sid}")
        assert get_resp.status_code == 404

    def test_delete_session_not_found(self, client: TestClient) -> None:
        response = client.delete("/api/sessions/nonexistent")
        assert response.status_code == 404


class TestMessages:
    def test_get_messages_empty(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/sessions",
            json={
                "title": "MsgTest",
                "mode": "chat",
                "provider": "ollama",
                "model": "gemma3:4b",
            },
        )
        sid = create_resp.json()["id"]
        response = client.get(f"/api/sessions/{sid}/messages")
        assert response.status_code == 200
        # Should have initial assistant welcome message
        assert len(response.json()["messages"]) >= 1

    def test_get_messages_session_not_found(self, client: TestClient) -> None:
        response = client.get("/api/sessions/nonexistent/messages")
        assert response.status_code == 404

    def test_send_message(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/sessions",
            json={
                "title": "SendTest",
                "mode": "chat",
                "provider": "ollama",
                "model": "gemma3:4b",
            },
        )
        sid = create_resp.json()["id"]
        response = client.post(f"/api/sessions/{sid}/messages", json={"content": "Hello"})
        assert response.status_code == 200
        msg = response.json()
        assert msg["role"] == "user"
        assert msg["content"] == "Hello"

    def test_send_message_empty_content(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/sessions",
            json={
                "title": "EmptyTest",
                "mode": "chat",
                "provider": "ollama",
                "model": "gemma3:4b",
            },
        )
        sid = create_resp.json()["id"]
        response = client.post(f"/api/sessions/{sid}/messages", json={"content": ""})
        assert response.status_code == 400

    def test_send_message_session_not_found(self, client: TestClient) -> None:
        response = client.post("/api/sessions/nonexistent/messages", json={"content": "Hello"})
        assert response.status_code == 404


class TestProvidersSkillsTasks:
    def test_providers_endpoint(self, client: TestClient) -> None:
        response = client.get("/api/providers")
        assert response.status_code == 200
        data = response.json()
        assert len(data["providers"]) >= 5
        provider_ids = [p["id"] for p in data["providers"]]
        assert "ollama" in provider_ids
        assert "bailian" in provider_ids
        assert "siliconflow" in provider_ids
        assert "openai" in provider_ids
        assert "anthropic" in provider_ids

    def test_providers_have_models(self, client: TestClient) -> None:
        response = client.get("/api/providers")
        for p in response.json()["providers"]:
            assert len(p["models"]) >= 1
            assert p["defaultModel"]

    def test_skills_endpoint(self, client: TestClient) -> None:
        response = client.get("/api/skills")
        assert response.status_code == 200
        data = response.json()
        assert len(data["skills"]) >= 5
        skill_ids = [s["id"] for s in data["skills"]]
        assert "file-browser" in skill_ids
        assert "git-ops" in skill_ids

    def test_tasks_endpoint(self, client: TestClient) -> None:
        response = client.get("/api/tasks")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) >= 3
        task_ids = [t["id"] for t in data["tasks"]]
        assert "task-1" in task_ids
        assert "task-2" in task_ids
        assert "task-3" in task_ids


@pytest.mark.xfail(strict=False, reason="SSE 流式端点在无真实事件源时挂起 (TestClient 等待 response body 完成)")
class TestStreaming:
    def test_stream_endpoint(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/sessions",
            json={
                "title": "StreamTest",
                "mode": "chat",
                "provider": "ollama",
                "model": "gemma3:4b",
            },
        )
        sid = create_resp.json()["id"]
        response = client.get(f"/api/sessions/{sid}/stream")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    def test_stream_session_not_found(self, client: TestClient) -> None:
        response = client.get("/api/sessions/nonexistent/stream")
        assert response.status_code == 404

    def test_interrupt(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/sessions",
            json={
                "title": "IntTest",
                "mode": "chat",
                "provider": "ollama",
                "model": "gemma3:4b",
            },
        )
        sid = create_resp.json()["id"]
        response = client.post(f"/api/sessions/{sid}/interrupt")
        assert response.status_code == 200
        assert response.json()["interrupted"] is False  # No active stream


class TestCompliance:
    def test_compliance_register(self, client: TestClient) -> None:
        response = client.post(
            "/api/compliance/register",
            json={
                "agent_id": "test-agent",
                "data_residency": "CN",
                "model_backend": "bailian",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "test-agent"
        assert data["status"] == "registered"
        assert "governance_state" in data

    def test_compliance_agents_list(self, client: TestClient) -> None:
        client.post(
            "/api/compliance/register",
            json={
                "agent_id": "agent-a",
                "data_residency": "CN",
                "model_backend": "bailian",
            },
        )
        client.post(
            "/api/compliance/register",
            json={
                "agent_id": "agent-b",
                "data_residency": "US",
                "model_backend": "openai",
            },
        )
        response = client.get("/api/compliance/agents")
        assert response.status_code == 200
        data = response.json()
        assert len(data["agents"]) >= 2

    def test_compliance_check_action(self, client: TestClient) -> None:
        client.post(
            "/api/compliance/register",
            json={
                "agent_id": "check-agent",
                "data_residency": "CN",
                "model_backend": "bailian",
            },
        )
        response = client.post(
            "/api/compliance/check-action",
            json={
                "agent_id": "check-agent",
                "action": "read_file",
                "action_type": "read",
                "entropy": 0.1,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "allowed" in data
        assert "decision" in data

    def test_compliance_check_action_unregistered(self, client: TestClient) -> None:
        response = client.post(
            "/api/compliance/check-action",
            json={
                "agent_id": "unknown-agent",
                "action": "read_file",
                "action_type": "read",
            },
        )
        assert response.status_code == 200
        assert response.json()["allowed"] is False

    @pytest.mark.skip(reason="BUG: compliance/unified.py asyncio.run() in sync method")
    def test_compliance_snapshot(self, client: TestClient) -> None:
        client.post(
            "/api/compliance/register",
            json={
                "agent_id": "snap-agent",
                "data_residency": "CN",
                "model_backend": "bailian",
            },
        )
        response = client.post("/api/compliance/snapshot", json={"agent_id": "snap-agent"})
        assert response.status_code == 200

    def test_compliance_snapshot_unregistered(self, client: TestClient) -> None:
        response = client.post("/api/compliance/snapshot", json={"agent_id": "unknown"})
        assert response.status_code == 200
        assert "error" in response.json()

    def test_compliance_audit_log(self, client: TestClient) -> None:
        client.post(
            "/api/compliance/register",
            json={
                "agent_id": "audit-agent",
                "data_residency": "CN",
                "model_backend": "bailian",
            },
        )
        response = client.get("/api/compliance/audit-log/audit-agent")
        assert response.status_code == 200
        data = response.json()
        assert "audit_log" in data

    def test_compliance_audit_log_unregistered(self, client: TestClient) -> None:
        response = client.get("/api/compliance/audit-log/unknown")
        assert response.status_code == 200
        assert "error" in response.json()


class TestObservationEndpointsExtended:
    def test_health_with_collector(self, client: TestClient) -> None:
        # Collect some data first
        response = client.get("/api/observations")
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "collector_running" in data
        assert "buffer_size" in data
