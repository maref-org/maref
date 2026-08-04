"""
v0.50 W4-S1 — MCP JWT 验签默认开启（I4/I13）

覆盖：
- MCPSecurityGate 无 verification_key 构造抛错（fail-closed）
- 显式 allow_unverified_tokens=True 才放行
- 有 key 时伪造 token 被拒绝、合法 token 通过
- OAuthMiddleware 无 key 默认 fail-closed
- sidecar _wire_mcp_governance 从 MAREF_MCP_SECRET_KEY 注入 key
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

import pytest

from maref.integration.mcp_security import (
    MCPSecurityGate,
    OAuthMiddleware,
    OAuthTokenProvider,
)


def _run(coro: Any) -> Any:
    import asyncio

    return asyncio.run(coro)


def _make_token(secret: bytes, sub: str = "agent-x", expire: float | None = None) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
    payload_dict = {"sub": sub, "session_id": "s1", "jti": "j1"}
    if expire is not None:
        payload_dict["exp"] = expire
    payload = base64.urlsafe_b64encode(
        json.dumps(payload_dict).encode()
    ).rstrip(b"=").decode()
    signing_input = f"{header}.{payload}".encode()
    sig = base64.urlsafe_b64encode(
        hmac.new(secret, signing_input, hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.{sig}"


class TestGateFailClosed:
    def test_no_verification_key_raises(self) -> None:
        with pytest.raises(ValueError):
            MCPSecurityGate()

    def test_no_verification_key_raises_even_with_other_options(self) -> None:
        with pytest.raises(ValueError):
            MCPSecurityGate(max_delegation_depth=3)

    def test_allow_unverified_explicitly_ok(self) -> None:
        gate = MCPSecurityGate(allow_unverified_tokens=True)
        assert gate.verification_key is None

    def test_with_key_ok(self) -> None:
        gate = MCPSecurityGate(verification_key=b"secret")
        assert gate.verification_key == b"secret"


class TestGateSignatureEnforcement:
    def test_valid_token_accepted(self) -> None:
        secret = b"secret"
        gate = MCPSecurityGate(verification_key=secret)
        token = _make_token(secret)
        ctx = gate.authenticate_request({"authorization": f"Bearer {token}"})
        assert ctx.agent_id == "agent-x"

    def test_forged_token_rejected(self) -> None:
        gate = MCPSecurityGate(verification_key=b"real-secret")
        forged = _make_token(b"attacker-secret")
        ctx = gate.authenticate_request({"authorization": f"Bearer {forged}"})
        assert ctx.agent_id == "anonymous"
        assert ctx.token_claims.get("error") == "invalid_signature"

    def test_expired_token_rejected(self) -> None:
        secret = b"secret"
        gate = MCPSecurityGate(verification_key=secret)
        token = _make_token(secret, expire=time.time() - 100)
        ctx = gate.authenticate_request({"authorization": f"Bearer {token}"})
        assert ctx.agent_id == "anonymous"
        assert ctx.token_claims.get("error") == "expired"


class TestOAuthFailClosed:
    def test_oauth_middleware_no_key_raises(self) -> None:
        with pytest.raises(ValueError):
            OAuthMiddleware(token_provider=OAuthTokenProvider())

    def test_oauth_middleware_allow_unverified_ok(self) -> None:
        mw = OAuthMiddleware(
            token_provider=OAuthTokenProvider(), allow_unverified_tokens=True
        )
        assert mw._verification_key is None

    def test_oauth_valid_token_accepted(self) -> None:
        secret = b"secret"
        mw = OAuthMiddleware(
            token_provider=OAuthTokenProvider(), verification_key=secret
        )
        token = _make_token(secret)
        ctx = _run(mw.authenticate({"authorization": f"Bearer {token}"}))
        assert ctx.agent_id == "agent-x"

    def test_oauth_forged_token_rejected(self) -> None:
        mw = OAuthMiddleware(
            token_provider=OAuthTokenProvider(), verification_key=b"real-secret"
        )
        forged = _make_token(b"attacker-secret")
        with pytest.raises(PermissionError):
            _run(mw.authenticate({"authorization": f"Bearer {forged}"}))


class TestSidecarInjection:
    def test_wire_mcp_governance_injects_env_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.sidecar import server as sidecar_server

        monkeypatch.setenv("MAREF_MCP_SECRET_KEY", "sidecar-secret")
        gateway = _FakeGateway()
        sidecar_server._wire_mcp_governance(gateway)
        assert gateway._gate.verification_key == os.environb.get(b"MAREF_MCP_SECRET_KEY")

    def test_wire_mcp_governance_fails_closed_without_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.sidecar import server as sidecar_server

        monkeypatch.delenv("MAREF_MCP_SECRET_KEY", raising=False)
        with pytest.raises(ValueError, match="MAREF_MCP_SECRET_KEY"):
            sidecar_server._wire_mcp_governance(_FakeGateway())


class _FakeGateway:
    def __init__(self) -> None:
        self._gate = None
        self._policy_engine = None
        self._governance = None
