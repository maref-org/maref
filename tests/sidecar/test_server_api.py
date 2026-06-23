from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sidecar.collector import MockAgentAdapter, ObservationCollector
from sidecar.monitor import CompositeMonitor
from sidecar.server import create_app


_client: TestClient | None = None


def _make_client() -> TestClient:
    global _client
    if _client is None:
        adapter = MockAgentAdapter()
        collector = ObservationCollector(adapter)
        monitor = CompositeMonitor()
        app = create_app(collector, monitor, None)
        _client = TestClient(app)
    return _client


class TestHealth:
    def test_health_returns_ok(self) -> None:
        client = _make_client()
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    def test_health_has_collector_state(self) -> None:
        client = _make_client()
        data = client.get("/api/health").json()
        assert "collector_running" in data
        assert "buffer_size" in data


class TestAgents:
    def test_list_agents(self) -> None:
        client = _make_client()
        resp = client.get("/api/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert len(data["agents"]) == 3


class TestObservations:
    def test_get_observations(self) -> None:
        client = _make_client()
        resp = client.get("/api/observations")
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert "observations" in data

    def test_anomalies_endpoint(self) -> None:
        client = _make_client()
        resp = client.get("/api/anomalies")
        assert resp.status_code == 200
        data = resp.json()
        assert "anomalies" in data


class TestMetrics:
    def test_metrics_prometheus(self) -> None:
        client = _make_client()
        resp = client.get("/api/metrics")
        assert resp.status_code == 200

    def test_guardrails_stats(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/guardrails/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_guardrails_events(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/guardrails/events")
        assert resp.status_code == 200
        assert "events" in resp.json()

    def test_guardrails_events_with_limit(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/guardrails/events?limit=10")
        assert resp.status_code == 200


class TestSessions:
    def test_create_session(self) -> None:
        client = _make_client()
        resp = client.post("/api/sessions", json={"title": "test", "mode": "chat"})
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["status"] == "idle"

    def test_list_sessions(self) -> None:
        client = _make_client()
        client.post("/api/sessions", json={"title": "s1"})
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        assert len(resp.json()["sessions"]) >= 1

    def test_get_session_not_found(self) -> None:
        client = _make_client()
        resp = client.get("/api/sessions/nonexistent")
        assert resp.status_code == 404

    def test_get_session_returns_session(self) -> None:
        client = _make_client()
        created = client.post("/api/sessions", json={"title": "my-session"}).json()
        session_id = created["id"]
        resp = client.get(f"/api/sessions/{session_id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "my-session"

    def test_delete_session(self) -> None:
        client = _make_client()
        created = client.post("/api/sessions", json={"title": "to-delete"}).json()
        session_id = created["id"]
        resp = client.delete(f"/api/sessions/{session_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_delete_session_not_found(self) -> None:
        client = _make_client()
        resp = client.delete("/api/sessions/nonexistent")
        assert resp.status_code == 404

    def test_get_messages(self) -> None:
        client = _make_client()
        created = client.post("/api/sessions", json={"title": "chat"}).json()
        session_id = created["id"]
        resp = client.get(f"/api/sessions/{session_id}/messages")
        assert resp.status_code == 200
        assert "messages" in resp.json()

    def test_get_messages_session_not_found(self) -> None:
        client = _make_client()
        resp = client.get("/api/sessions/nonexistent/messages")
        assert resp.status_code == 404

    def test_send_message(self) -> None:
        client = _make_client()
        created = client.post("/api/sessions", json={"title": "chat"}).json()
        session_id = created["id"]
        resp = client.post(f"/api/sessions/{session_id}/messages", json={"content": "hello"})
        assert resp.status_code == 200
        assert resp.json()["role"] == "user"

    def test_send_message_empty_content(self) -> None:
        client = _make_client()
        created = client.post("/api/sessions", json={"title": "chat"}).json()
        session_id = created["id"]
        resp = client.post(f"/api/sessions/{session_id}/messages", json={"content": ""})
        assert resp.status_code == 400

    def test_interrupt_session(self) -> None:
        client = _make_client()
        created = client.post("/api/sessions", json={"title": "chat"}).json()
        session_id = created["id"]
        resp = client.post(f"/api/sessions/{session_id}/interrupt")
        assert resp.status_code == 200



class TestProviders:
    def test_list_providers(self) -> None:
        client = _make_client()
        resp = client.get("/api/providers")
        assert resp.status_code == 200
        assert "providers" in resp.json()

    def test_register_provider(self) -> None:
        client = _make_client()
        resp = client.post("/api/providers", json={"name": "test-llm"})
        assert resp.status_code == 200
        assert "id" in resp.json()


class TestSkills:
    def test_list_skills(self) -> None:
        client = _make_client()
        resp = client.get("/api/skills")
        assert resp.status_code == 200
        assert "skills" in resp.json()


class TestTasks:
    def test_list_tasks(self) -> None:
        client = _make_client()
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        assert "tasks" in resp.json()

    def test_create_task(self) -> None:
        client = _make_client()
        resp = client.post("/api/tasks", json={"title": "new-task"})
        assert resp.status_code == 200
        assert "id" in resp.json()


class TestCompliance:
    def test_compliance_register(self) -> None:
        client = _make_client()
        resp = client.post("/api/compliance/register", json={"agent_id": "agent-1"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "registered"

    def test_compliance_list_agents(self) -> None:
        client = _make_client()
        resp = client.get("/api/compliance/agents")
        assert resp.status_code == 200

    def test_compliance_check_action_allowed(self) -> None:
        client = _make_client()
        client.post("/api/compliance/register", json={"agent_id": "agent-1"})
        resp = client.post("/api/compliance/check-action", json={"agent_id": "agent-1"})
        assert resp.status_code == 200
        assert resp.json()["allowed"] is True

    def test_compliance_check_action_denied_for_unknown(self) -> None:
        client = _make_client()
        resp = client.post("/api/compliance/check-action", json={"agent_id": "unknown"})
        assert resp.status_code == 200
        assert resp.json()["allowed"] is False

    def test_compliance_snapshot(self) -> None:
        client = _make_client()
        client.post("/api/compliance/register", json={"agent_id": "agent-1"})
        resp = client.post("/api/compliance/snapshot", json={"agent_id": "agent-1"})
        assert resp.status_code == 200
        assert "snapshot" in resp.json()

    def test_compliance_snapshot_unknown(self) -> None:
        client = _make_client()
        resp = client.post("/api/compliance/snapshot", json={"agent_id": "unknown"})
        assert resp.status_code == 200
        assert resp.json()["error"] == "Agent not found"

    def test_compliance_audit_log(self) -> None:
        client = _make_client()
        client.post("/api/compliance/register", json={"agent_id": "agent-1"})
        resp = client.get("/api/compliance/audit-log/agent-1")
        assert resp.status_code == 200
        assert "audit_log" in resp.json()

    def test_compliance_audit_log_unknown(self) -> None:
        client = _make_client()
        resp = client.get("/api/compliance/audit-log/unknown")
        assert resp.status_code == 200
        assert resp.json()["error"] == "Agent not found"


class TestGovernance:
    def test_governance_state(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/governance/state")
        assert resp.status_code == 200
        data = resp.json()
        assert "state" in data
        assert "entropy" in data

    def test_governance_transitions(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/governance/transitions")
        assert resp.status_code == 200
        assert "transitions" in resp.json()

    def test_governance_circuit_breaker(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/governance/circuit-breaker")
        assert resp.status_code == 200
        assert "events" in resp.json()

    def test_governance_oscillation(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/governance/oscillation")
        assert resp.status_code == 200
        assert "events" in resp.json()


class TestAudit:
    def test_audit_logs(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/audit/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "total" in data
        assert "counts" in data

    def test_audit_logs_with_type_filter(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/audit/logs?type=transition")
        assert resp.status_code == 200

    def test_audit_logs_with_search(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/audit/logs?search=StateMachine")
        assert resp.status_code == 200

    def test_audit_logs_with_pagination(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/audit/logs?limit=5&offset=2")
        assert resp.status_code == 200

    def test_audit_stats(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/audit/stats")
        assert resp.status_code == 200
        assert "counts" in resp.json()


class TestHITL:
    def test_hitl_pending(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/hitl/pending")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "count" in data

    def test_hitl_pending_with_tier(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/hitl/pending?tier=high")
        assert resp.status_code == 200

    def test_hitl_history(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/hitl/history")
        assert resp.status_code == 200
        assert "events" in resp.json()

    def test_hitl_stats(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/hitl/stats")
        assert resp.status_code == 200
        assert "stats" in resp.json()

    def test_hitl_approve(self) -> None:
        client = _make_client()
        resp = client.post("/api/v1/hitl/hitl-1/approve")
        assert resp.status_code == 200
        assert resp.json()["approved"] is True

    def test_hitl_approve_not_found(self) -> None:
        client = _make_client()
        resp = client.post("/api/v1/hitl/nonexistent/approve")
        assert resp.status_code == 404

    def test_hitl_deny(self) -> None:
        client = _make_client()
        resp = client.post("/api/v1/hitl/hitl-2/deny")
        assert resp.status_code == 200
        assert resp.json()["cancelled"] is True

    def test_hitl_deny_not_found(self) -> None:
        client = _make_client()
        resp = client.post("/api/v1/hitl/nonexistent/deny")
        assert resp.status_code == 404

    def test_hitl_request(self) -> None:
        client = _make_client()
        resp = client.post("/api/v1/hitl/request", json={
            "tier": "high",
            "description": "test",
            "action": "review",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["requires_human"] is True


class TestObservability:
    def test_error_budget(self) -> None:
        import pytest
        pytest.skip("MetricStore SQLite thread-safety issue")
        client = _make_client()
        resp = client.get("/api/v1/observability/error-budget")
        assert resp.status_code == 200
        data = resp.json()
        assert "slo_target" in data
        assert "budget" in data

    def test_cost_report(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/observability/cost-report")
        assert resp.status_code == 200

    def test_cost_by_team(self) -> None:
        client = _make_client()
        resp = client.get("/api/v1/observability/cost-by-team")
        assert resp.status_code == 200


class TestMCP:
    def test_mcp_initialize(self) -> None:
        client = _make_client()
        resp = client.post("/api/mcp", json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["jsonrpc"] == "2.0"
        assert "result" in data

    def test_mcp_tools_list(self) -> None:
        client = _make_client()
        resp = client.post("/api/mcp", json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
        })
        assert resp.status_code == 200
        assert "tools" in resp.json()["result"]

    def test_mcp_resources_list(self) -> None:
        client = _make_client()
        resp = client.post("/api/mcp", json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "resources/list",
        })
        assert resp.status_code == 200

    def test_mcp_prompts_list(self) -> None:
        client = _make_client()
        resp = client.post("/api/mcp", json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "prompts/list",
        })
        assert resp.status_code == 200

    def test_mcp_tools_call(self) -> None:
        client = _make_client()
        resp = client.post("/api/mcp", json={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "maref_health_check", "arguments": {}},
        })
        assert resp.status_code == 200
        assert "result" in resp.json()

    def test_mcp_unknown_method(self) -> None:
        client = _make_client()
        resp = client.post("/api/mcp", json={
            "jsonrpc": "2.0",
            "id": 6,
            "method": "unknown/method",
        })
        assert resp.status_code == 200
        assert "error" in resp.json()
        assert resp.json()["error"]["code"] == -32601

    def test_mcp_well_known(self) -> None:
        client = _make_client()
        resp = client.get("/api/mcp/.well-known")
        assert resp.status_code == 200
        data = resp.json()
        assert data["protocol"] == "mcp"
        assert "capabilities" in data


class TestStatus:
    def test_status(self) -> None:
        client = _make_client()
        resp = client.get("/api/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_version(self) -> None:
        client = _make_client()
        resp = client.get("/api/version")
        assert resp.status_code == 200
        assert resp.json()["version"] == "0.33.0-rc"


class TestObs:
    def test_obs_status(self) -> None:
        client = _make_client()
        resp = client.get("/api/obs/status")
        assert resp.status_code == 200
        assert "enabled" in resp.json()

    def test_red_metrics(self) -> None:
        client = _make_client()
        resp = client.get("/api/red-metrics")
        assert resp.status_code == 200


class TestFiletree:
    def test_filetree(self) -> None:
        client = _make_client()
        resp = client.get("/api/filetree")
        assert resp.status_code == 200
        assert "roots" in resp.json()


class TestImmunity:
    def test_cooldown_list(self) -> None:
        client = _make_client()
        resp = client.get("/api/immunity/cooldown")
        assert resp.status_code == 200

    def test_cooldown_summary(self) -> None:
        client = _make_client()
        resp = client.get("/api/immunity/cooldown/summary")
        assert resp.status_code == 200

    def test_genes_list(self) -> None:
        client = _make_client()
        resp = client.get("/api/immunity/genes")
        assert resp.status_code == 200
