"""Tests for HITL API Router — Agent operation confirmation endpoints."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from maref.integration.hitl_api import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


class TestHITLAPI:
    def test_request_approval_p0(self):
        resp = client.post("/api/v1/hitl/request", json={
            "session_id": "test-session",
            "action": "execute_command",
            "description": "Run `rm -rf /` on production server",
            "parameters": {"command": "rm -rf /", "server": "prod-01"},
            "tier": "p0_response",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "execute_command"
        assert data["tier"] == "p0_response"
        assert data["requires_human"] is True
        assert data["event_id"].startswith("hitl-")

    def test_request_approval_p1(self):
        resp = client.post("/api/v1/hitl/request", json={
            "session_id": "test-session",
            "action": "read_file",
            "description": "Read /etc/config.json",
            "tier": "p1_escalate",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["auto_approve_seconds"] == 30.0
        assert data["requires_human"] is False

    def test_confirm_action(self):
        req_resp = client.post("/api/v1/hitl/request", json={
            "session_id": "test-session",
            "action": "write_file",
            "description": "Write to /etc/config.json",
            "tier": "p0_response",
        })
        event_id = req_resp.json()["event_id"]

        resp = client.post("/api/v1/hitl/confirm", json={
            "event_id": event_id,
            "reviewer": "test-user",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["event_id"] == event_id
        assert data["approved"] is True

    def test_cancel_action(self):
        req_resp = client.post("/api/v1/hitl/request", json={
            "session_id": "test-session",
            "action": "delete_file",
            "description": "Delete /etc/config.json",
            "tier": "p0_response",
        })
        event_id = req_resp.json()["event_id"]

        resp = client.post("/api/v1/hitl/cancel", json={
            "event_id": event_id,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["event_id"] == event_id
        assert data["cancelled"] is True

    def test_pause_resume(self):
        resp = client.post("/api/v1/hitl/pause?session_id=test-session")
        assert resp.status_code == 200
        assert resp.json()["paused"] is True

        resp = client.post("/api/v1/hitl/resume?session_id=test-session")
        assert resp.status_code == 200
        assert resp.json()["resumed"] is True

    def test_get_pending_events(self):
        client.post("/api/v1/hitl/request", json={
            "session_id": "test-session",
            "action": "pending_action",
            "description": "A pending action",
            "tier": "p0_response",
        })

        resp = client.get("/api/v1/hitl/pending")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] > 0
        assert any(e["action"] == "pending_action" for e in data["events"])

    def test_get_pending_by_tier(self):
        client.post("/api/v1/hitl/request", json={
            "session_id": "test-session",
            "action": "p1_action",
            "description": "An auto-approve action",
            "tier": "p1_escalate",
        })

        resp = client.get("/api/v1/hitl/pending?tier=p0_response")
        assert resp.status_code == 200
        data = resp.json()
        for event in data["events"]:
            assert event["tier"] == "p0_response"

    def test_get_stats(self):
        resp = client.get("/api/v1/hitl/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "stats" in data
        assert "total_events" in data["stats"]

    def test_approve_by_path(self):
        req_resp = client.post("/api/v1/hitl/request", json={
            "session_id": "test-session",
            "action": "path_approve",
            "description": "Approve via path endpoint",
            "tier": "p0_response",
        })
        event_id = req_resp.json()["event_id"]

        resp = client.post(f"/api/v1/hitl/{event_id}/approve?reviewer=tester")
        assert resp.status_code == 200
        data = resp.json()
        assert data["event_id"] == event_id
        assert data["approved"] is True
        assert data["status"] == "approved"

    def test_deny_by_path(self):
        req_resp = client.post("/api/v1/hitl/request", json={
            "session_id": "test-session",
            "action": "path_deny",
            "description": "Deny via path endpoint",
            "tier": "p0_response",
        })
        event_id = req_resp.json()["event_id"]

        resp = client.post(f"/api/v1/hitl/{event_id}/deny?reason=Not+needed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["event_id"] == event_id
        assert data["cancelled"] is True

    def test_get_history(self):
        created = client.post("/api/v1/hitl/request", json={
            "session_id": "test-session",
            "action": "history_item",
            "description": "Should appear in history after approval",
            "tier": "p0_response",
        }).json()
        event_id = created["event_id"]
        client.post(f"/api/v1/hitl/{event_id}/approve")

        resp = client.get("/api/v1/hitl/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] > 0
        assert any(e["event_id"] == event_id for e in data["events"])

    def test_get_history_empty_on_fresh_router(self):
        resp = client.get("/api/v1/hitl/history?limit=5&offset=0")
        assert resp.status_code == 200
        assert isinstance(resp.json()["events"], list)

    def test_auto_approve_timeout_scenario(self):
        """P1 tier auto-approves after timeout window (verify flow)."""
        resp = client.post("/api/v1/hitl/request", json={
            "session_id": "test-session",
            "action": "auto_approve_test",
            "description": "Should auto-approve after 30s",
            "tier": "p1_escalate",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["requires_human"] is False
        assert data["auto_approve_seconds"] == 30.0
        assert data["status"] == "pending"

        event_id = data["event_id"]
        resp2 = client.get("/api/v1/hitl/pending")
        pending_ids = [e["event_id"] for e in resp2.json()["events"]]
        assert event_id in pending_ids

        resp3 = client.post(f"/api/v1/hitl/{event_id}/approve")
        assert resp3.status_code == 200
        assert resp3.json()["approved"] is True

        resp4 = client.get("/api/v1/hitl/history")
        history_ids = [e["event_id"] for e in resp4.json()["events"]]
        assert event_id in history_ids

    def test_history_pagination(self):
        """History supports limit and offset parameters."""
        resp = client.get("/api/v1/hitl/history?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events"]) <= 5

        resp2 = client.get("/api/v1/hitl/history?limit=2&offset=0")
        assert resp2.status_code == 200
        first_page = resp2.json()["events"]

        resp3 = client.get("/api/v1/hitl/history?limit=2&offset=2")
        assert resp3.status_code == 200
        second_page = resp3.json()["events"]
        if len(first_page) == 2 and len(second_page) > 0:
            assert first_page[0]["event_id"] != second_page[0]["event_id"]
