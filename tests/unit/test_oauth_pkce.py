"""OAuth 2.1 PKCE + authorization_code flow tests.

Validates that OAuthTokenProvider supports the authorization_code grant with
PKCE (RFC 7636), required by OAuth 2.1.  The client_credentials flow remains
unchanged (backward compatibility).
"""

from __future__ import annotations

import base64
import hashlib
from unittest.mock import MagicMock, patch

import pytest

from maref.integration.mcp_security import OAuthTokenProvider


class TestPKCE:
    def test_generate_pkce_pair_format(self) -> None:
        verifier, challenge = OAuthTokenProvider.generate_pkce_pair()
        # Verifier length within RFC 7636 range (43-128 chars).
        assert 43 <= len(verifier) <= 128
        # Challenge must equal BASE64URL(SHA256(verifier)) without padding.
        expected = (
            base64.urlsafe_b64encode(
                hashlib.sha256(verifier.encode("ascii")).digest()
            )
            .rstrip(b"=")
            .decode("ascii")
        )
        assert challenge == expected

    def test_generate_pkce_pair_uniqueness(self) -> None:
        verifiers = {OAuthTokenProvider.generate_pkce_pair()[0] for _ in range(20)}
        assert len(verifiers) == 20

    def test_challenge_no_padding(self) -> None:
        _, challenge = OAuthTokenProvider.generate_pkce_pair()
        assert "=" not in challenge


class TestAuthorizationCodeFlow:
    def test_build_authorization_url(self) -> None:
        provider = OAuthTokenProvider(
            client_id="cid",
            flow="authorization_code",
            scopes=["maref:mcp"],
        )
        url = provider.build_authorization_url(
            "https://auth.example.com/authorize",
            redirect_uri="https://app.example.com/callback",
            code_challenge="challenge123",
            state="xyz",
        )
        assert "response_type=code" in url
        assert "client_id=cid" in url
        assert "code_challenge=challenge123" in url
        assert "code_challenge_method=S256" in url
        assert "state=xyz" in url

    def test_exchange_requires_stored_code(self) -> None:
        provider = OAuthTokenProvider(
            client_id="cid",
            client_secret="secret",
            flow="authorization_code",
        )
        with pytest.raises(RuntimeError, match="store_authorization_code"):
            provider.get_token("https://server.example.com")

    @patch("maref.integration.mcp_security.httpx.post")
    def test_exchange_success(self, mock_post: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "access_token": "atk123",
            "refresh_token": "rtk456",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "maref:mcp",
        }
        mock_post.return_value = mock_resp

        provider = OAuthTokenProvider(
            token_url="https://auth.example.com/oauth/token",
            client_id="cid",
            client_secret="secret",
            flow="authorization_code",
        )
        verifier, _challenge = provider.generate_pkce_pair()
        provider.store_authorization_code(
            "https://server.example.com",
            code="authcode789",
            code_verifier=verifier,
            redirect_uri="https://app.example.com/callback",
        )
        token = provider.get_token("https://server.example.com")
        assert token == "atk123"

        # Verify the token request carried the PKCE verifier + code.
        call_args = mock_post.call_args
        payload = call_args.kwargs.get("data") or {}
        assert payload["grant_type"] == "authorization_code"
        assert payload["code"] == "authcode789"
        assert payload["code_verifier"] == verifier
        assert payload["redirect_uri"] == "https://app.example.com/callback"

        # Stored token must NOT retain the verifier (sensitive credential
        # cleared after token exchange per PKCE hygiene).
        stored = provider._tokens["https://server.example.com"]
        assert stored.code_verifier == ""

    @patch("maref.integration.mcp_security.httpx.post")
    def test_exchange_without_redirect_uri(self, mock_post: MagicMock) -> None:
        """redirect_uri is optional in the token exchange payload."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"access_token": "atk", "expires_in": 60}
        mock_post.return_value = mock_resp

        provider = OAuthTokenProvider(
            token_url="https://auth.example.com/oauth/token",
            client_id="cid",
            client_secret="secret",
            flow="authorization_code",
        )
        verifier, _ = provider.generate_pkce_pair()
        provider.store_authorization_code(
            "https://srv.example.com",
            code="c1",
            code_verifier=verifier,
        )
        provider.get_token("https://srv.example.com")
        payload = mock_post.call_args.kwargs.get("data") or {}
        assert "redirect_uri" not in payload
        assert payload["code_verifier"] == verifier

    def test_client_credentials_flow_unchanged(self) -> None:
        """client_credentials flow still works without PKCE (backward compat)."""
        provider = OAuthTokenProvider(
            token_url="https://auth.example.com/oauth/token",
            client_id="cid",
            client_secret="secret",
            flow="client_credentials",
        )
        assert provider.flow == "client_credentials"
        assert provider._pending_auth_codes == {}
