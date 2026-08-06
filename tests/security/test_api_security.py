"""Comprehensive API security tests for MAREF sidecar server.

Covers authentication bypass, injection attacks, scope escalation,
and auth middleware edge cases.
"""

from __future__ import annotations

import concurrent.futures
import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sidecar.api_auth import (
    _SCOPE_MAP,
    APIKeyManager,
    AuthMiddleware,
    _register_route_scope,
    clear_audit_log,
    require_auth,
)
from sidecar.mcp_gateway import _create_audit_signature


@pytest.fixture(autouse=True)
def reset_state():
    clear_audit_log()
    _SCOPE_MAP.clear()
    APIKeyManager.reload()
    yield
    clear_audit_log()
    _SCOPE_MAP.clear()
    APIKeyManager.reload()


@pytest.fixture
def app():
    a = FastAPI()
    a.add_middleware(AuthMiddleware, bypass_paths={"/api/public", "/_debug/"})

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

    @a.post("/api/v1/compliance/register")
    @require_auth(scope="compliance:admin")
    def compliance_register(body: dict):
        return {"status": "registered"}

    @a.get("/api/version")
    @require_auth()
    def version():
        return {"version": "0.38.0"}

    @a.get("/api/public/info")
    def public_info():
        return {"public": True}

    @a.get("/_debug/health")
    @require_auth()
    def debug_health():
        return {"debug": True}

    @a.get("/_debug_x/health")
    @require_auth()
    def debug_x_health():
        return {"debug_x": True}

    @a.post("/api/v1/hitl/{event_id}/deny")
    @require_auth(scope="hitl:write")
    def hitl_deny(event_id: str):
        return {"denied": True, "event_id": event_id}

    @a.post("/api/sessions")
    @require_auth()
    def create_session(body: dict):
        return {"session_id": "test-session"}

    @a.post("/api/v1/admin/actions")
    @require_auth(scope="admin:write")
    def admin_actions():
        return {"action": "executed"}

    @a.get("/api/v1/user/profile")
    @require_auth(scope="user:read")
    def user_profile():
        return {"user": "test"}

    @a.get("/api/unrestricted/stats")
    def unrestricted_stats():
        return {"stats": {}}

    _register_route_scope(a)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


class TestAuthenticationBypass:
    """Verify token extraction and validation cannot be bypassed."""

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123"}, clear=True)
    def test_token_in_query_param(self, client):
        APIKeyManager.reload()
        resp = client.get(
            "/_debug_x/health",
            params={"token": "test-key-123"},
        )
        assert resp.status_code == 200
        assert resp.json()["debug_x"] is True

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123"}, clear=True)
    def test_token_in_header_preferred_over_query(self, client):
        APIKeyManager.reload()
        resp = client.get(
            "/_debug_x/health",
            params={"token": "wrong-key"},
            headers={"Authorization": "Bearer test-key-123"},
        )
        assert resp.status_code == 200

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123"}, clear=True)
    def test_empty_token_header_returns_401(self, client):
        APIKeyManager.reload()
        resp = client.get(
            "/_debug_x/health",
            headers={"Authorization": "Bearer "},
        )
        assert resp.status_code == 401
        assert "Missing" in resp.text or "Authorization" in resp.text

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123"}, clear=True)
    def test_whitespace_token_rejected(self, client):
        APIKeyManager.reload()
        resp = client.get(
            "/_debug_x/health",
            headers={"Authorization": "Bearer   "},
        )
        assert resp.status_code == 403

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123"}, clear=True)
    def test_multiple_auth_headers(self, client):
        APIKeyManager.reload()
        resp = client.get(
            "/_debug_x/health",
            headers=[
                ("Authorization", "Bearer test-key-123"),
                ("Authorization", "Bearer test-key-123"),
            ],
        )
        assert resp.status_code == 200

    @patch.dict(os.environ, {"MAREF_API_KEY": "test key with spaces"}, clear=True)
    def test_url_encoded_token_decoded(self, client):
        APIKeyManager.reload()
        resp = client.get(
            "/_debug_x/health",
            params={"token": "test key with spaces"},
        )
        assert resp.status_code == 200

    @patch.dict(os.environ, {"MAREF_API_KEY": "replayable-key"}, clear=True)
    def test_token_replay_no_protection(self, client):
        APIKeyManager.reload()
        for _ in range(3):
            resp = client.get(
                "/_debug_x/health",
                params={"token": "replayable-key"},
            )
            assert resp.status_code == 200

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123"}, clear=True)
    def test_bypass_path_prefix_mismatch(self, client):
        APIKeyManager.reload()
        resp = client.get("/_debug_x/health")
        assert resp.status_code == 401

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123"}, clear=True)
    def test_token_from_cookie_not_supported(self, client):
        APIKeyManager.reload()
        resp = client.get(
            "/_debug_x/health",
            cookies={"token": "test-key-123"},
        )
        assert resp.status_code == 401

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123"}, clear=True)
    def test_case_insensitive_auth_header(self, client):
        APIKeyManager.reload()
        resp = client.get(
            "/_debug_x/health",
            headers={"authorization": "Bearer test-key-123"},
        )
        assert resp.status_code == 200


class TestInjectionAttacks:
    """Verify the server handles malicious inputs without exposing vulnerabilities."""

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123"}, clear=True)
    def test_sql_injection_in_body(self, client):
        APIKeyManager.reload()
        resp = client.post(
            "/api/v1/compliance/register",
            json={
                "agent_id": "1; DROP TABLE users--",
                "data_residency": "us",
            },
            headers={"Authorization": "Bearer test-key-123"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "registered"

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123"}, clear=True)
    def test_command_injection_in_params(self, client):
        APIKeyManager.reload()
        resp = client.post(
            "/api/v1/evolution/dry-run",
            json={
                "command": "$(id)",
                "argument": "; rm -rf /",
                "payload": "`cat /etc/passwd`",
            },
            headers={"Authorization": "Bearer test-key-123"},
        )
        assert resp.status_code in (200, 422)

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123"}, clear=True)
    def test_json_prototype_pollution(self, client):
        APIKeyManager.reload()
        resp = client.post(
            "/api/v1/compliance/register",
            json={
                "__proto__": {"admin": True},
                "constructor": {"prototype": {"admin": True}},
                "agent_id": "test-agent",
            },
            headers={"Authorization": "Bearer test-key-123"},
        )
        assert resp.status_code == 200

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123"}, clear=True)
    def test_path_traversal_in_route_param(self, client):
        APIKeyManager.reload()
        resp = client.post(
            "/api/v1/hitl/../../../etc/passwd/approve",
            headers={"Authorization": "Bearer test-key-123"},
        )
        assert resp.status_code == 404

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123"}, clear=True)
    def test_xss_via_error_response(self, client):
        APIKeyManager.reload()
        resp = client.post(
            "/api/v1/hitl/<script>alert(1)</script>/approve",
            headers={"Authorization": "Bearer test-key-123"},
        )
        assert resp.status_code == 404
        content_type = resp.headers.get("content-type", "")
        assert "text/html" not in content_type

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key-123"}, clear=True)
    def test_large_payload_dos(self, client):
        APIKeyManager.reload()
        large_body = {"data": "A" * 500_000}
        resp = client.post(
            "/api/sessions",
            json=large_body,
            headers={"Authorization": "Bearer test-key-123"},
        )
        assert resp.status_code in (200, 413, 422)


class TestScopeEscalation:
    """Verify scope-based access control is enforced correctly."""

    @patch("sidecar.api_auth._has_scope")
    def test_low_privilege_scope_blocked_high_privilege(self, mock_has_scope, client):
        def _check(token: str, required: str) -> bool:
            mapping = {
                "user-token": {"user:read"},
                "admin-token": {"admin:write", "user:read"},
            }
            return required in mapping.get(token, set())

        mock_has_scope.side_effect = _check

        with patch.dict(
            os.environ,
            {"MAREF_API_KEY": "user-token", "MAREF_API_KEY_2": "admin-token"},
            clear=True,
        ):
            APIKeyManager.reload()

            resp = client.post(
                "/api/v1/admin/actions",
                headers={"Authorization": "Bearer user-token"},
            )
            assert resp.status_code == 403
            assert "scope" in resp.text.lower() or "Insufficient" in resp.text

            resp = client.post(
                "/api/v1/admin/actions",
                headers={"Authorization": "Bearer admin-token"},
            )
            assert resp.status_code == 200
            assert resp.json()["action"] == "executed"

    @patch("sidecar.api_auth._has_scope", return_value=False)
    def test_missing_scope_blocked(self, mock_has_scope, client):
        with patch.dict(os.environ, {"MAREF_API_KEY": "test-key"}, clear=True):
            APIKeyManager.reload()
            resp = client.post(
                "/api/v1/admin/actions",
                headers={"Authorization": "Bearer test-key"},
            )
            assert resp.status_code == 403
            assert "scope" in resp.text.lower() or "Insufficient" in resp.text

    @patch("sidecar.api_auth._has_scope")
    def test_wildcard_scope_matching_rejected(self, mock_has_scope, client):
        mock_has_scope.return_value = False
        resp = client.post(
            "/api/v1/admin/actions",
            headers={"Authorization": "Bearer *:write"},
        )
        assert resp.status_code == 403

    def test_scope_map_populated_correctly(self, client):
        expected = {
            "/api/health": "default",
            "/api/v1/hitl/{event_id}/approve": "hitl:write",
            "/api/v1/evolution/dry-run": "evolution:execute",
            "/api/v1/compliance/register": "compliance:admin",
            "/api/version": "default",
            "/_debug/health": "default",
            "/_debug_x/health": "default",
            "/api/v1/hitl/{event_id}/deny": "hitl:write",
            "/api/sessions": "default",
            "/api/v1/admin/actions": "admin:write",
            "/api/v1/user/profile": "user:read",
        }
        for path, scope in expected.items():
            registered = _SCOPE_MAP.get(path)
            assert registered == scope, f"{path}: expected scope={scope}, got {registered}"

    def test_route_without_scope_unrestricted(self, client):
        with patch.dict(os.environ, {"MAREF_API_KEY": "any-token"}, clear=True):
            APIKeyManager.reload()
            resp = client.get(
                "/api/unrestricted/stats",
                headers={"Authorization": "Bearer any-token"},
            )
            assert resp.status_code == 200
            assert resp.json()["stats"] == {}

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key"}, clear=True)
    @patch("sidecar.api_auth._has_scope", return_value=False)
    def test_valid_token_insufficient_scope_rejected(self, mock_has_scope, client):
        APIKeyManager.reload()
        resp = client.post(
            "/api/v1/admin/actions",
            headers={"Authorization": "Bearer test-key"},
        )
        assert resp.status_code == 403

    @patch.dict(os.environ, {"MAREF_API_KEY": "master-key"}, clear=True)
    @patch("sidecar.api_auth._has_scope")
    def test_multiple_scopes_needed_one_provided(self, mock_has_scope, client):
        APIKeyManager.reload()

        def _check(_token: str, required: str) -> bool:
            return required in {"admin:write"}

        mock_has_scope.side_effect = _check

        resp = client.post(
            "/api/v1/admin/actions",
            headers={"Authorization": "Bearer master-key"},
        )
        assert resp.status_code == 200

        resp = client.get(
            "/api/v1/user/profile",
            headers={"Authorization": "Bearer master-key"},
        )
        assert resp.status_code == 403


class TestAuthMiddlewareEdgeCases:
    """Verify auth middleware behavior under edge conditions."""

    def test_auth_disabled_when_no_key_set(self, client):
        """No key configured → fail-closed: requests are denied (v0.47 S6)."""
        assert APIKeyManager.is_auth_enabled() is False
        with patch.dict(os.environ, {}, clear=True):
            APIKeyManager.reload()
            resp = client.post(
                "/api/v1/hitl/event-1/approve",
                headers={"Authorization": "Bearer any-token"},
            )
            assert resp.status_code in (401, 403)

    @patch.dict(os.environ, {"MAREF_API_KEY": "new-key-after-rotation"}, clear=True)
    def test_key_rotation_reload_picks_up(self, client):
        APIKeyManager.reload()
        assert APIKeyManager.is_auth_enabled() is True

        resp = client.post(
            "/api/v1/hitl/event-1/approve",
            headers={"Authorization": "Bearer new-key-after-rotation"},
        )
        assert resp.status_code == 200

        resp = client.post(
            "/api/v1/hitl/event-1/approve",
            headers={"Authorization": "Bearer old-stale-key"},
        )
        assert resp.status_code == 403

    @patch.dict(os.environ, {"MAREF_API_KEY": "key-A", "MAREF_API_KEY_2": "key-B"}, clear=True)
    def test_concurrent_requests_different_keys(self, app):
        APIKeyManager.reload()

        def _request(token: str) -> int:
            c = TestClient(app)
            resp = c.get(
                "/_debug_x/health",
                headers={"Authorization": f"Bearer {token}"},
            )
            return resp.status_code

        tokens = ["key-A", "key-B"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            futures = [ex.submit(_request, t) for t in tokens]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        for status in results:
            assert status == 200

    @patch("sidecar.mcp_gateway.time.time", return_value=1234567890.0)
    def test_audit_signature_non_forgeable(self, mock_time):
        secret = b"test-secret-key"
        tampered = b"tampered-secret-key"

        sig = _create_audit_signature("bash", "ALLOW", 0.0, "abc123", secret)
        forged = _create_audit_signature("bash", "ALLOW", 0.0, "abc123", tampered)
        assert sig != forged

        sig_same = _create_audit_signature("bash", "ALLOW", 0.0, "abc123", secret)
        assert sig == sig_same

        sig_diff = _create_audit_signature("bash", "DENY", 0.0, "abc123", secret)
        assert sig != sig_diff

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key"}, clear=True)
    def test_rate_limiting_headers_not_present(self, client):
        APIKeyManager.reload()
        resp = client.get(
            "/_debug_x/health",
            headers={"Authorization": "Bearer test-key"},
        )
        for h in resp.headers:
            assert not h.lower().startswith("x-ratelimit-"), (
                f"Rate limit header {h} should not be present"
            )

    @patch.dict(os.environ, {"MAREF_API_KEY": "test-key"}, clear=True)
    def test_audit_log_not_exposed_via_api(self, client):
        APIKeyManager.reload()
        from sidecar.api_auth import get_audit_log

        client.get(
            "/_debug_x/health",
            headers={"Authorization": "Bearer test-key"},
        )
        assert len(get_audit_log()) > 0

        auth = {"Authorization": "Bearer test-key"}
        for path in ["/api/auth/log", "/api/v1/auth/audit", "/api/internal/auth-audit"]:
            resp = client.get(path, headers=auth)
            assert resp.status_code == 404, f"{path} should not expose audit log"
