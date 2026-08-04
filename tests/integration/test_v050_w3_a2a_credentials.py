"""
v0.50 W3-S1 — A2A 发送层携带凭证测试（I7）

覆盖：
- A2AClient 配置 signing_key 后请求携带 Ed25519 签名头
- 未配置 signing_key 时不附加签名头（向后兼容）
- a2a_server 配置 peer_public_keys 后验签，伪造请求被拒绝
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import MagicMock, patch

from maref.integration.a2a_client import AGENT_ID, A2AClient
from maref.signing.signing_key import ReportSigningKey


def _make_key() -> ReportSigningKey:
    return ReportSigningKey.generate()


class TestW3S1ClientSigning:
    def test_headers_include_signature_when_key_configured(self) -> None:
        key = _make_key()
        client = A2AClient(timeout=5.0, signing_key=key)
        headers = client._headers(payload=b'{"a":1}')
        assert "X-A2A-Signature" in headers
        assert "X-A2A-Timestamp" in headers
        assert headers["X-A2A-Agent-Id"] == AGENT_ID

    def test_signature_verifies_against_public_key(self) -> None:
        key = _make_key()
        client = A2AClient(timeout=5.0, signing_key=key)
        payload = b'{"jsonrpc":"2.0"}'
        headers = client._headers(payload=payload)
        sig = headers["X-A2A-Signature"]
        timestamp = headers["X-A2A-Timestamp"]
        signed_bytes = f"{timestamp}.{payload.decode()}".encode()
        assert ReportSigningKey.verify_signature(key.public_key_pem, sig, signed_bytes)

    def test_no_signature_headers_without_key(self) -> None:
        client = A2AClient(timeout=5.0)
        headers = client._headers(payload=b'{"a":1}')
        assert "X-A2A-Signature" not in headers

    def test_send_task_attaches_signed_headers(self) -> None:
        key = _make_key()
        client = A2AClient(timeout=5.0, signing_key=key)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "result": {"id": "task-1", "status": {"state": "submitted"}},
        }
        mock_response.raise_for_status = MagicMock()

        captured: dict[str, Any] = {}

        async def fake_post(*args, **kwargs):
            captured["headers"] = kwargs.get("headers", {})
            captured["json"] = kwargs.get("json")
            return mock_response

        with patch("maref.integration.a2a_client.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = fake_post
            asyncio.run(client.send_task("http://peer.local", "skill-1", "hello"))

        assert "X-A2A-Signature" in captured["headers"]
        assert "X-A2A-Timestamp" in captured["headers"]


class TestW3S1ServerVerification:
    @staticmethod
    def _make_app():
        from fastapi import FastAPI

        from maref.governance.audit import AuditLogger
        from maref.governance.state_machine import GovernanceStateMachine
        from maref.integration.a2a_bridge import A2ABridge
        from maref.integration.a2a_server import create_a2a_router

        sm = GovernanceStateMachine()
        al = AuditLogger.__new__(AuditLogger)
        al._entries = []
        al._hmac_key = b"test-hmac-key-for-a2a-test"
        bridge = A2ABridge(state_machine=sm, audit_logger=al)
        app = FastAPI()
        app.include_router(create_a2a_router(bridge, peer_public_keys=_PUBLIC_KEYS))
        return app

    def test_signed_request_accepted(self) -> None:
        from fastapi.testclient import TestClient

        client = TestClient(self._make_app())

        payload = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "tasks/send",
            "params": {
                "id": "req-1",
                "message": {"parts": [{"text": "hello"}]},
                "metadata": {"skills": []},
            },
        }
        body_bytes = json.dumps(payload, separators=(",", ":")).encode()
        timestamp = "1700000000"
        signed = f"{timestamp}.{body_bytes.decode()}".encode()
        sig = _CLIENT_KEY.sign_report(signed)
        headers = {
            "Content-Type": "application/json",
            "X-A2A-Agent-Id": "urn:agent:maref:peer",
            "X-A2A-Signature": sig,
            "X-A2A-Timestamp": timestamp,
        }
        resp = client.post("/api/a2a/task/send", content=body_bytes, headers=headers)
        assert resp.status_code in (200, 503)

    def test_unsigned_request_rejected_when_verification_enabled(self) -> None:
        from fastapi.testclient import TestClient

        client = TestClient(self._make_app())

        payload = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "tasks/send",
            "params": {
                "id": "req-1",
                "message": {"parts": [{"text": "hello"}]},
                "metadata": {"skills": []},
            },
        }
        headers = {
            "Content-Type": "application/json",
            "X-A2A-Agent-Id": "urn:agent:maref:peer",
        }
        resp = client.post("/api/a2a/task/send", json=payload, headers=headers)
        assert resp.status_code == 401


_CLIENT_KEY = _make_key()
_PUBLIC_KEYS = {"urn:agent:maref:peer": _CLIENT_KEY.public_key_pem}
