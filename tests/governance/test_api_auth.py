"""Tests for API auth middleware (sidecar/api_auth.py)."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from sidecar.api_auth import APIKeyManager, AuthMiddleware, require_auth


@pytest.fixture(autouse=True)
def clear_keys():
    APIKeyManager.reload()
    yield
    APIKeyManager.reload()


@pytest.fixture
def app():
    a = FastAPI()
    a.add_middleware(AuthMiddleware, bypass_paths={"/api/public"})

    @a.get("/api/health")
    @require_auth()
    def health():
        return {"status": "ok"}

    @a.post("/api/v1/hitl/{event_id}/approve")
    @require_auth(scope="hitl:write")
    def hitl_approve(event_id: str):
        return {"approved": True, "event_id": event_id}

    @a.post("/api/v1/evolution/dry-run")
    @require_auth(scope="evolution:execute")
    def evolution_dry_run():
        return {"dry_run": True}

    @a.get("/api/version")
    @require_auth()
    def version():
        return {"version": "0.38.0"}

    @a.get("/api/status")
    @require_auth()
    def status():
        return {"status": "running"}

    @a.get("/_debug/health")
    @require_auth()
    def debug_health():
        return {"debug": True}

    @a.get("/api/public")
    @require_auth(bypass_paths={"/api/public"})
    def public():
        return {"public": True}

    return a


@pytest.fixture
def client(app):
    return TestClient(app)


class TestRequireAuth:
    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123"}, clear=True)
    def test_no_token_returns_401(self, client):
        APIKeyManager.reload()
        resp = client.post("/api/v1/hitl/event-1/approve")
        assert resp.status_code == 401
        assert "Missing Authorization" in resp.text

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123"}, clear=True)
    def test_invalid_token_returns_403(self, client):
        APIKeyManager.reload()
        resp = client.post(
            "/api/v1/hitl/event-1/approve",
            headers={"Authorization": "Bearer invalid-key"},
        )
        assert resp.status_code == 403
        assert "Invalid API key" in resp.text

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123"}, clear=True)
    def test_valid_token_allows(self, client):
        APIKeyManager.reload()
        resp = client.post(
            "/api/v1/hitl/event-1/approve",
            headers={"Authorization": "Bearer test-key-123"},
        )
        assert resp.status_code == 200
        assert resp.json()["approved"] is True

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123"}, clear=True)
    def test_evolution_endpoint_protected(self, client):
        APIKeyManager.reload()
        resp = client.post("/api/v1/evolution/dry-run")
        assert resp.status_code == 401

        resp = client.post(
            "/api/v1/evolution/dry-run",
            headers={"Authorization": "Bearer test-key-123"},
        )
        assert resp.status_code == 200
        assert resp.json()["dry_run"] is True

    def test_bypass_paths_work_without_token(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_version_bypass(self, client):
        resp = client.get("/api/version")
        assert resp.status_code == 200
        assert resp.json()["version"] == "0.38.0"

    def test_status_bypass(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_debug_prefix_bypass(self, client):
        resp = client.get("/_debug/health")
        assert resp.status_code == 200

    def test_custom_bypass_path(self, client):
        resp = client.get("/api/public")
        assert resp.status_code == 200

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123", "MAREF_API_KEY_2": "backup-key"}, clear=True)
    def test_multiple_keys_accepted(self, client):
        APIKeyManager.reload()
        resp = client.post(
            "/api/v1/hitl/event-1/approve",
            headers={"Authorization": "Bearer backup-key"},
        )
        assert resp.status_code == 200

    def test_no_env_key_fallback_allows(self, client):
        resp = client.post(
            "/api/v1/hitl/event-1/approve",
            headers={"Authorization": "Bearer any-token"},
        )
        assert resp.status_code == 200


class TestAPIKeyManager:
    def test_auth_disabled_when_no_keys(self):
        APIKeyManager.reload()
        assert APIKeyManager.is_auth_enabled() is False

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key"}, clear=True)
    def test_auth_enabled_with_key(self):
        APIKeyManager.reload()
        assert APIKeyManager.is_auth_enabled() is True

    def test_health_report(self):
        result = APIKeyManager.health()
        assert "auth_enabled" in result
        assert "key_count" in result

    @patch.dict(os.environ, {"MAREF_API_KEY": "reloaded-key"}, clear=True)
    def test_reload_picks_up_env_change(self):
        APIKeyManager.reload()
        assert APIKeyManager.is_auth_enabled() is True

    def test_reload_clears_cache(self):
        APIKeyManager.reload()
        keys_before = APIKeyManager.is_auth_enabled()
        with patch.dict(os.environ, {"MAREF_API_KEY": "new-key"}, clear=True):
            APIKeyManager.reload()
            assert APIKeyManager.is_auth_enabled() is True


class TestTokenExtraction:
    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123"}, clear=True)
    def test_query_param_token(self, client):
        APIKeyManager.reload()
        resp = client.get("/api/health?token=test-key-123")
        assert resp.status_code == 200

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123"}, clear=True)
    def test_bearer_token_preferred(self, client):
        APIKeyManager.reload()
        resp = client.get(
            "/api/health",
            headers={"Authorization": "Bearer test-key-123"},
        )
        assert resp.status_code == 200


class TestEdgeCases:
    def test_malformed_auth_header(self, client):
        resp = client.get(
            "/api/health",
            headers={"Authorization": "Basic dGVzdDpwYXNz"},
        )
        assert resp.status_code == 200  # falls back to bypass

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key"}, clear=True)
    def test_empty_bearer_token(self, client):
        APIKeyManager.reload()
        resp = client.get(
            "/api/health",
            headers={"Authorization": "Bearer "},
        )
        assert resp.status_code == 200  # bypass kicks in

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key"}, clear=True)
    def test_token_with_extra_whitespace(self, client):
        APIKeyManager.reload()
        resp = client.get(
            "/api/health",
            headers={"Authorization": "Bearer  test-key  "},
        )
        assert resp.status_code == 200
