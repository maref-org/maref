from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

os.environ.setdefault("MAREF_HMAC_SECRET_KEY", "test-hmac-secret-for-testing")

from maref.gaas import api

_app = FastAPI()
_app.include_router(api.router)


@pytest.fixture
def client():
    return TestClient(_app)


class TestHealthEndpoint:
    def test_health_returns_healthy(self, client):
        resp = client.get("/api/v1/gaas/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "gaas"

    def test_health_no_auth_required(self, client):
        resp = client.get("/api/v1/gaas/health", headers={})
        assert resp.status_code == 200


class TestRouteRegistration:
    def test_router_prefix(self):
        assert api.router.prefix == "/api/v1/gaas"

    def test_routes_defined(self):
        paths = {r.path for r in api.router.routes}
        assert "/api/v1/gaas/health" in paths
        assert "/api/v1/gaas/govern" in paths
        assert "/api/v1/gaas/hitl/request" in paths
        assert "/api/v1/gaas/hitl/{event_id}/approve" in paths
        assert "/api/v1/gaas/hitl/{event_id}/deny" in paths
        assert "/api/v1/gaas/hitl/pending" in paths
        assert "/api/v1/gaas/trust/score" in paths
        assert "/api/v1/gaas/audit/query" in paths
        assert "/api/v1/gaas/cb/status" in paths
        assert "/api/v1/gaas/session/declare" in paths
        assert "/api/v1/gaas/session/active" in paths
        assert "/api/v1/gaas/session/{session_id}" in paths
        assert "/api/v1/gaas/session/{session_id}/complete" in paths
        assert "/api/v1/gaas/session/{session_id}/step" in paths

    def test_route_methods(self):
        route_map = {}
        for r in api.router.routes:
            for method in r.methods:
                route_map[(r.path, method)] = r
        assert ("/api/v1/gaas/govern", "POST") in route_map
        assert ("/api/v1/gaas/hitl/request", "POST") in route_map
        assert ("/api/v1/gaas/hitl/{event_id}/approve", "POST") in route_map
        assert ("/api/v1/gaas/hitl/{event_id}/deny", "POST") in route_map
        assert ("/api/v1/gaas/hitl/pending", "GET") in route_map
        assert ("/api/v1/gaas/trust/score", "GET") in route_map
        assert ("/api/v1/gaas/audit/query", "POST") in route_map
        assert ("/api/v1/gaas/cb/status", "GET") in route_map
        assert ("/api/v1/gaas/health", "GET") in route_map


class TestServiceSingletons:
    def test_get_tenant_manager_returns_instance(self):
        tm = api.get_tenant_manager()
        assert tm is not None
        assert api.get_tenant_manager() is tm

    def test_get_governance_router_returns_instance(self):
        gr = api.get_governance_router()
        assert gr is not None
        assert api.get_governance_router() is gr

    def test_get_hitl_service_returns_instance(self):
        hs = api.get_hitl_service()
        assert hs is not None
        assert api.get_hitl_service() is hs

    def test_get_audit_service_returns_instance(self):
        audit = api.get_audit_service()
        assert audit is not None
        assert api.get_audit_service() is audit

    def test_get_trust_service_returns_instance(self):
        ts = api.get_trust_service()
        assert ts is not None
        assert api.get_trust_service() is ts

    def test_get_cb_pool_returns_instance(self):
        cb = api.get_cb_pool()
        assert cb is not None
        assert api.get_cb_pool() is cb

    def test_singletons_are_stable(self):
        for getter in [
            api.get_tenant_manager,
            api.get_governance_router,
            api.get_hitl_service,
            api.get_audit_service,
            api.get_trust_service,
            api.get_cb_pool,
        ]:
            assert getter() is getter()


class TestRequireApiKey:
    @pytest.mark.asyncio
    async def test_valid_key_returns_tenant_id(self):
        mock_tm = MagicMock()
        mock_tenant = MagicMock()
        mock_tenant.tenant_id = "tenant-001"
        mock_tm.get_by_api_key.return_value = mock_tenant
        with patch.object(api, "get_tenant_manager", return_value=mock_tm):
            result = await api.require_api_key(x_api_key="valid-key-123")
        assert result == "tenant-001"

    @pytest.mark.asyncio
    async def test_invalid_key_raises_401(self):
        mock_tm = MagicMock()
        mock_tm.get_by_api_key.return_value = None
        with patch.object(api, "get_tenant_manager", return_value=mock_tm):
            with pytest.raises(HTTPException) as exc:
                await api.require_api_key(x_api_key="bad-key")
            assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Invalid API key" in exc.value.detail

    def test_govern_endpoint_requires_auth(self, client):
        resp = client.post(
            "/api/v1/gaas/govern",
            json={"action": "test", "agent_id": "agent-1", "tenant_id": "t"},
            headers={},
        )
        assert resp.status_code == 422


class TestHITLEndpoints:
    def test_hitl_request(self, client):
        with patch.object(api, "get_tenant_manager") as mock_tm:
            mock_tm.return_value.get_by_api_key.return_value = MagicMock(tenant_id="tenant-001")
            with patch.object(api, "get_hitl_service") as mock_hitl:
                mock_event = MagicMock()
                mock_event.event_id = "evt-001"
                mock_event.status.value = "pending"
                mock_hitl.return_value.request.return_value = mock_event
                resp = client.post(
                    "/api/v1/gaas/hitl/request",
                    json={
                        "agent_id": "agent-1", "action": "deploy",
                        "description": "Deploy", "tenant_id": "t",
                    },
                    headers={"X-API-Key": "test-key"},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["event_id"] == "evt-001"
        assert data["status"] == "pending"

    def test_hitl_approve(self, client):
        with patch.object(api, "get_tenant_manager") as mock_tm:
            mock_tm.return_value.get_by_api_key.return_value = MagicMock(tenant_id="tenant-001")
            with patch.object(api, "get_hitl_service") as mock_hitl:
                mock_hitl.return_value.gaas_approve.return_value = MagicMock(value="approved")
                resp = client.post(
                    "/api/v1/gaas/hitl/evt-001/approve",
                    headers={"X-API-Key": "test-key"},
                )
        assert resp.status_code == 200
        assert resp.json()["approved"] is True

    def test_hitl_deny(self, client):
        with patch.object(api, "get_tenant_manager") as mock_tm:
            mock_tm.return_value.get_by_api_key.return_value = MagicMock(tenant_id="tenant-001")
            with patch.object(api, "get_hitl_service") as mock_hitl:
                mock_hitl.return_value.gaas_reject.return_value = MagicMock(value="denied")
                resp = client.post(
                    "/api/v1/gaas/hitl/evt-001/deny",
                    headers={"X-API-Key": "test-key"},
                )
        assert resp.status_code == 200
        assert resp.json()["approved"] is False

    def test_hitl_pending(self, client):
        with patch.object(api, "get_tenant_manager") as mock_tm:
            mock_tm.return_value.get_by_api_key.return_value = MagicMock(tenant_id="tenant-001")
            with patch.object(api, "get_hitl_service") as mock_hitl:
                mock_event = MagicMock()
                mock_event.event_id = "evt-001"
                mock_event.agent_id = "agent-1"
                mock_event.action = "deploy"
                mock_event.description = "Deploy"
                mock_event.tier.value = "critical"
                mock_event.timestamp = 1000.0
                mock_hitl.return_value.get_tenant_pending.return_value = [mock_event]
                resp = client.get(
                    "/api/v1/gaas/hitl/pending",
                    headers={"X-API-Key": "test-key"},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["events"][0]["event_id"] == "evt-001"


class TestTrustScoreEndpoint:
    def test_trust_score_valid(self, client):
        with patch.object(api, "get_tenant_manager") as mock_tm:
            mock_tm.return_value.get_by_api_key.return_value = MagicMock(tenant_id="tenant-001")
            with patch.object(api, "get_trust_service") as mock_ts:
                mock_ts.return_value.get_score.return_value = 75.0
                mock_ts.return_value.get_report.return_value = {
                    "trust_tier": "silver",
                    "history_count": 12,
                    "last_updated": 1767225600.0,
                }
                resp = client.get(
                    "/api/v1/gaas/trust/score?agent_id=agent-1",
                    headers={"X-API-Key": "test-key"},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["trust_score"] == 75.0
        assert data["trust_tier"] == "silver"
        assert data["agent_id"] == "agent-1"

    def test_trust_score_no_report(self, client):
        with patch.object(api, "get_tenant_manager") as mock_tm:
            mock_tm.return_value.get_by_api_key.return_value = MagicMock(tenant_id="tenant-001")
            with patch.object(api, "get_trust_service") as mock_ts:
                mock_ts.return_value.get_score.return_value = None
                resp = client.get(
                    "/api/v1/gaas/trust/score?agent_id=agent-1",
                    headers={"X-API-Key": "test-key"},
                )
        assert resp.status_code == 200
        assert resp.json()["trust_score"] is None


class TestCBStatusEndpoint:
    def test_cb_status_valid(self, client):
        with patch.object(api, "get_tenant_manager") as mock_tm:
            mock_tm.return_value.get_by_api_key.return_value = MagicMock(tenant_id="tenant-001")
            with patch.object(api, "get_cb_pool") as mock_cb:
                mock_cb.return_value.get_status.return_value = {
                    "state": "CLOSED",
                    "failure_count": 0,
                    "last_trip_time": None,
                }
                resp = client.get(
                    "/api/v1/gaas/cb/status?agent_id=agent-1&action=test",
                    headers={"X-API-Key": "test-key"},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "CLOSED"
        assert data["failure_count"] == 0


class TestGovernEndpoint:
    def _make_gov_response(self, **kw):
        from maref.gaas.models import CircuitBreakerState, GovernResponse, Verdict
        return GovernResponse(
            verdict=Verdict.ALLOW,
            circuit_breaker_state=CircuitBreakerState.CLOSED,
            audit_log_id="log-001",
            **kw,
        )

    def test_govern_valid(self, client):
        with patch.object(api, "get_tenant_manager") as mock_tm:
            mock_tm.return_value.get_by_api_key.return_value = MagicMock(tenant_id="tenant-001")
            with patch.object(api, "get_governance_router") as mock_gr:
                mock_gr.return_value.govern.return_value = self._make_gov_response()
                resp = client.post(
                    "/api/v1/gaas/govern",
                    json={"action": "query", "agent_id": "agent-1", "tenant_id": "t"},
                    headers={"X-API-Key": "test-key"},
                )
        assert resp.status_code == 200

    def test_govern_overrides_tenant_id(self, client):
        captured = {}
        with patch.object(api, "get_tenant_manager") as mock_tm:
            mock_tm.return_value.get_by_api_key.return_value = MagicMock(tenant_id="tenant-001")
            with patch.object(api, "get_governance_router") as mock_gr:
                def capture(req):
                    captured["tenant_id"] = req.tenant_id
                    return self._make_gov_response()
                mock_gr.return_value.govern.side_effect = capture
                resp = client.post(
                    "/api/v1/gaas/govern",
                    json={
                        "agent_id": "agent-1", "action": "query",
                        "resource": "db", "tenant_id": "user-supplied",
                    },
                    headers={"X-API-Key": "test-key"},
                )
        assert resp.status_code == 200
        assert captured["tenant_id"] == "tenant-001"


class TestAuditQueryEndpoint:
    def test_audit_query_valid(self, client):
        from maref.gaas.models import AuditEntry
        with patch.object(api, "get_tenant_manager") as mock_tm:
            mock_tm.return_value.get_by_api_key.return_value = MagicMock(tenant_id="tenant-001")
            with patch.object(api, "get_audit_service") as mock_audit:
                mock_entry = AuditEntry(
                    log_id="log-001", timestamp=1000.0, tenant_id="tenant-001",
                    agent_id="agent-1", action="deploy", verdict="approved",
                    hmac_signature="abc123",
                )
                mock_audit.return_value.query.return_value = ([mock_entry], 1)
                resp = client.post(
                    "/api/v1/gaas/audit/query",
                    json={"limit": 10, "offset": 0, "tenant_id": "t"},
                    headers={"X-API-Key": "test-key"},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["entries"]) == 1
        assert data["entries"][0]["log_id"] == "log-001"


class TestSessionEndpoints:
    def test_session_not_found_returns_404(self, client):
        from maref.gaas import session_manager
        with patch.object(api, "get_tenant_manager") as mock_tm:
            mock_tm.return_value.get_by_api_key.return_value = MagicMock(tenant_id="tenant-001")
            with patch.object(session_manager, "get_session", return_value=None):
                resp = client.get(
                    "/api/v1/gaas/session/nonexistent",
                    headers={"X-API-Key": "test-key"},
                )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Session not found"

    def test_session_complete_not_found(self, client):
        from maref.gaas import session_manager
        with patch.object(api, "get_tenant_manager") as mock_tm:
            mock_tm.return_value.get_by_api_key.return_value = MagicMock(tenant_id="tenant-001")
            with patch.object(session_manager, "complete_session", return_value=None):
                resp = client.post(
                    "/api/v1/gaas/session/nonexistent/complete",
                    json={"success": True},
                    headers={"X-API-Key": "test-key"},
                )
        assert resp.status_code == 404

    def test_session_step_not_found(self, client):
        from maref.gaas import session_manager
        with patch.object(api, "get_tenant_manager") as mock_tm:
            mock_tm.return_value.get_by_api_key.return_value = MagicMock(tenant_id="tenant-001")
            with patch.object(session_manager, "increment_step", return_value=None):
                resp = client.post(
                    "/api/v1/gaas/session/nonexistent/step",
                    headers={"X-API-Key": "test-key"},
                )
        assert resp.status_code == 404
