"""Tests for governance, audit, immunity, and HITL endpoints in the Sidecar server."""

from __future__ import annotations

import sys

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


class TestGovernanceEndpoints:
    def test_governance_state(self, client: TestClient) -> None:
        response = client.get("/api/v1/governance/state")
        assert response.status_code == 200
        data = response.json()
        assert "state" in data
        assert "entropy" in data

    def test_governance_transitions(self, client: TestClient) -> None:
        response = client.get("/api/v1/governance/transitions")
        assert response.status_code == 200
        data = response.json()
        assert "transitions" in data

    def test_governance_circuit_breaker(self, client: TestClient) -> None:
        response = client.get("/api/v1/governance/circuit-breaker")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data

    def test_governance_oscillation(self, client: TestClient) -> None:
        response = client.get("/api/v1/governance/oscillation")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data


class TestAuditEndpoints:
    def test_audit_logs_default(self, client: TestClient) -> None:
        response = client.get("/api/v1/audit/logs")
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert "total" in data

    def test_audit_logs_with_params(self, client: TestClient) -> None:
        response = client.get("/api/v1/audit/logs?type=governance&limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data

    def test_audit_logs_with_search(self, client: TestClient) -> None:
        response = client.get("/api/v1/audit/logs?search=test&limit=5")
        assert response.status_code == 200

    def test_audit_stats(self, client: TestClient) -> None:
        response = client.get("/api/v1/audit/stats")
        assert response.status_code == 200
        data = response.json()
        assert "counts" in data


class TestImmunityEndpoints:
    def test_list_cooldown_entries(self, client: TestClient) -> None:
        response = client.get("/api/immunity/cooldown")
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert "total" in data

    def test_cooldown_summary(self, client: TestClient) -> None:
        response = client.get("/api/immunity/cooldown/summary")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_list_genes(self, client: TestClient) -> None:
        response = client.get("/api/immunity/genes")
        assert response.status_code == 200
        data = response.json()
        assert "genes" in data
        assert "total" in data


class TestHITLEndpoints:
    def test_hitl_pending_default(self, client: TestClient) -> None:
        response = client.get("/api/v1/hitl/pending")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "count" in data

    def test_hitl_pending_with_tier(self, client: TestClient) -> None:
        response = client.get("/api/v1/hitl/pending?tier=1")
        assert response.status_code == 200

    def test_hitl_history(self, client: TestClient) -> None:
        response = client.get("/api/v1/hitl/history?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "count" in data

    def test_hitl_stats(self, client: TestClient) -> None:
        response = client.get("/api/v1/hitl/stats")
        assert response.status_code == 200
        data = response.json()
        assert "stats" in data

    def test_hitl_request_and_approve(self, client: TestClient) -> None:
        request_resp = client.post(
            "/api/v1/hitl/request",
            json={
                "agent_id": "agent-1",
                "action": "test_action",
                "reason": "test",
                "tier": 1,
            },
        )
        assert request_resp.status_code == 200
        event = request_resp.json()
        event_id = event.get("event_id", "")
        assert event_id, f"Expected event_id, got: {event}"

        approve_resp = client.post(f"/api/v1/hitl/{event_id}/approve")
        assert approve_resp.status_code == 200
        result = approve_resp.json()
        assert "status" in result

    def test_hitl_approve_nonexistent(self, client: TestClient) -> None:
        response = client.post("/api/v1/hitl/nonexistent-id/approve")
        assert response.status_code == 404

    def test_hitl_deny(self, client: TestClient) -> None:
        request_resp = client.post(
            "/api/v1/hitl/request",
            json={
                "agent_id": "agent-2",
                "action": "delete_file",
                "reason": "cleanup",
                "tier": 2,
            },
        )
        assert request_resp.status_code == 200
        event_id = request_resp.json().get("event_id", "")

        deny_resp = client.post(f"/api/v1/hitl/{event_id}/deny")
        assert deny_resp.status_code == 200
        result = deny_resp.json()
        assert "status" in result


class TestObservabilityEndpoints:
    @pytest.mark.xfail(
        sys.platform == "darwin",
        reason="SQLite threading issue on macOS with FastAPI TestClient",
    )
    def test_error_budget(self, client: TestClient) -> None:
        response = client.get("/api/v1/observability/error-budget")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_cost_report(self, client: TestClient) -> None:
        response = client.get("/api/v1/observability/cost-report")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_cost_report_with_params(self, client: TestClient) -> None:
        response = client.get("/api/v1/observability/cost-report?agent_id=agent-1&since=2026-01-01")
        assert response.status_code == 200

    def test_cost_by_team(self, client: TestClient) -> None:
        response = client.get("/api/v1/observability/cost-by-team")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
