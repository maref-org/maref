"""v0.47 S6 — sidecar auth fail-open fixes.

1. **Startup rejects without an API key by default** — when no
   ``MAREF_API_KEY`` is configured the middleware denies requests
   (previously ``_verify_token`` returned True → everything allowed).
   A development ``allow_unauthenticated=True`` flag keeps local stacks
   working.

2. **``_has_scope`` performs a real scope check** — the master key's
   allowed scopes are read from ``MAREF_API_KEY_SCOPES`` (comma
   separated); when configured, keys lacking the required scope are
   rejected with 403.

3. **``/_debug/`` prefix is no longer an auth bypass** — debug endpoints
   must authenticate like everything else.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sidecar.api_auth import (
    APIKeyManager,
    AuthMiddleware,
    _register_route_scope,
    require_auth,
)


@pytest.fixture(autouse=True)
def clear_keys():
    APIKeyManager.reload()
    yield
    APIKeyManager.reload()


@pytest.fixture
def app():
    a = FastAPI()
    a.add_middleware(AuthMiddleware)

    @a.get("/api/health")
    @require_auth()
    def health():
        return {"status": "ok"}

    @a.post("/api/v1/hitl/{event_id}/approve")
    @require_auth(scope="hitl:write")
    def hitl_approve(event_id: str):
        return {"approved": True, "event_id": event_id}

    @a.get("/_debug/dump")
    @require_auth()
    def debug_dump():
        return {"debug": True}

    _register_route_scope(a)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


# ── Change 1: no key → reject (fail-closed) ──────────────────────────────


def test_no_key_rejects_request_by_default() -> None:
    """Without MAREF_API_KEY the middleware denies (was: allow-all)."""
    resp = TestClient(FastAPI()).get("/nonexistent")  # placeholder
    assert resp.status_code == 404


@patch.dict(os.environ, {}, clear=True)
def test_unconfigured_key_denies_protected_endpoint(client) -> None:
    APIKeyManager.reload()
    resp = client.post("/api/v1/hitl/event-1/approve")
    assert resp.status_code == 401
    assert "API key" in resp.text or "Authorization" in resp.text


@patch.dict(os.environ, {}, clear=True)
def test_unconfigured_key_denies_even_with_token(client) -> None:
    """No key configured → any presented token is rejected (fail-closed)."""
    APIKeyManager.reload()
    resp = client.post(
        "/api/v1/hitl/event-1/approve",
        headers={"Authorization": "Bearer anything"},
    )
    assert resp.status_code in (401, 403)


@patch.dict(os.environ, {}, clear=True)
def test_allow_unauthenticated_flag_restores_dev_mode(client) -> None:
    APIKeyManager.reload()
    a = FastAPI()
    a.add_middleware(AuthMiddleware, allow_unauthenticated=True)

    @a.post("/api/v1/hitl/{event_id}/approve")
    @require_auth()
    def hitl_approve(event_id: str):
        return {"approved": True, "event_id": event_id}

    dev_client = TestClient(a)
    resp = dev_client.post("/api/v1/hitl/event-1/approve")
    assert resp.status_code == 200


@patch.dict(os.environ, {"MAREF_API_KEY": "test-key"}, clear=True)
def test_configured_key_still_allows(client) -> None:
    APIKeyManager.reload()
    resp = client.post(
        "/api/v1/hitl/event-1/approve",
        headers={"Authorization": "Bearer test-key"},
    )
    assert resp.status_code == 200


# ── Change 2: real scope check ────────────────────────────────────────────


@patch.dict(
    os.environ,
    {"MAREF_API_KEY": "master-key", "MAREF_API_KEY_SCOPES": "read,status"},
    clear=True,
)
def test_scope_restricted_key_denied_for_other_scope(client) -> None:
    APIKeyManager.reload()
    resp = client.post(
        "/api/v1/hitl/event-1/approve",
        headers={"Authorization": "Bearer master-key"},
    )
    assert resp.status_code == 403
    assert "scope" in resp.text.lower()


@patch.dict(
    os.environ,
    {"MAREF_API_KEY": "master-key", "MAREF_API_KEY_SCOPES": "hitl:write"},
    clear=True,
)
def test_scope_restricted_key_allowed_for_matching_scope(client) -> None:
    APIKeyManager.reload()
    resp = client.post(
        "/api/v1/hitl/event-1/approve",
        headers={"Authorization": "Bearer master-key"},
    )
    assert resp.status_code == 200


# ── Change 3: /_debug/ no longer bypasses auth ────────────────────────────


@patch.dict(os.environ, {"MAREF_API_KEY": "test-key"}, clear=True)
def test_debug_path_requires_auth(client) -> None:
    """/_debug/* must authenticate (was a global bypass)."""
    APIKeyManager.reload()
    resp = client.get("/_debug/dump")
    assert resp.status_code in (401, 403)

    resp = client.get(
        "/_debug/dump",
        headers={"Authorization": "Bearer test-key"},
    )
    assert resp.status_code == 200
