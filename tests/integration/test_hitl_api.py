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