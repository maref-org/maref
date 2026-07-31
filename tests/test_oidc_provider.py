"""Tests for OIDC/SSO Provider Integration."""

from __future__ import annotations

from maref.gaas.oidc_provider import (
    OIDCProviderConfig,
    OIDCTokenVerifier,
    SSOManager,
    _create_test_id_token,
    _decode_jwt_header,
)


def _make_provider(
    provider_id: str = "okta",
    issuer: str = "https://okta.example.com",
    client_id: str = "maref-client",
) -> OIDCProviderConfig:
    return OIDCProviderConfig(
        provider_id=provider_id,
        issuer_url=issuer,
        client_id=client_id,
    )


class TestOIDCProviderConfig:
    def test_default_config(self) -> None:
        config = OIDCProviderConfig(
            provider_id="okta",
            issuer_url="https://okta.example.com",
            client_id="client-1",
        )
        assert config.provider_id == "okta"
        assert config.client_secret == ""
        assert "openid" in config.scopes
        assert config.claim_mapping["sub"] == "user_id"

    def test_custom_scopes(self) -> None:
        config = OIDCProviderConfig(
            provider_id="keycloak",
            issuer_url="https://kc.example.com",
            client_id="c1",
            scopes=["openid", "groups"],
        )
        assert "groups" in config.scopes


class TestOIDCTokenVerifier:
    def test_verify_valid_token(self) -> None:
        config = _make_provider()
        verifier = OIDCTokenVerifier(config)
        token = _create_test_id_token(
            issuer=config.issuer_url,
            audience=config.client_id,
            sub="user-123",
            email="user@example.com",
            name="Test User",
        )
        user = verifier.verify_token(token)
        assert user is not None
        assert user.user_id == "user-123"
        assert user.email == "user@example.com"
        assert user.display_name == "Test User"
        assert user.provider_id == "okta"

    def test_rejects_wrong_issuer(self) -> None:
        config = _make_provider(issuer="https://okta.example.com")
        verifier = OIDCTokenVerifier(config)
        token = _create_test_id_token(
            issuer="https://evil.example.com",
            audience=config.client_id,
            sub="user-123",
        )
        assert verifier.verify_token(token) is None

    def test_rejects_expired_token(self) -> None:
        config = _make_provider()
        verifier = OIDCTokenVerifier(config)
        token = _create_test_id_token(
            issuer=config.issuer_url,
            audience=config.client_id,
            sub="user-123",
            expires_in=-100,  # Already expired
        )
        assert verifier.verify_token(token) is None

    def test_rejects_wrong_audience(self) -> None:
        config = _make_provider(client_id="maref-client")
        verifier = OIDCTokenVerifier(config)
        token = _create_test_id_token(
            issuer=config.issuer_url,
            audience="wrong-client",
            sub="user-123",
        )
        assert verifier.verify_token(token) is None

    def test_rejects_malformed_token(self) -> None:
        config = _make_provider()
        verifier = OIDCTokenVerifier(config)
        assert verifier.verify_token("not.a.valid") is None
        assert verifier.verify_token("onlyonepart") is None
        assert verifier.verify_token("") is None

    def test_rejects_missing_sub(self) -> None:
        """Token without 'sub' claim is rejected."""
        config = _make_provider()
        verifier = OIDCTokenVerifier(config)
        # Create token with empty sub
        token = _create_test_id_token(
            issuer=config.issuer_url,
            audience=config.client_id,
            sub="",
        )
        assert verifier.verify_token(token) is None

    def test_accepts_aud_as_list(self) -> None:
        """Audience can be a list (RFC 7519 §4.1.3)."""
        import base64
        import json
        import time

        config = _make_provider(client_id="maref-client")
        verifier = OIDCTokenVerifier(config)
        header = {"alg": "RS256", "typ": "JWT", "kid": "test-key"}
        payload = {
            "iss": config.issuer_url,
            "aud": ["other-api", "maref-client"],  # list with matching entry
            "sub": "user-123",
            "exp": int(time.time() + 3600),
        }
        h = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
        p = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        token = f"{h}.{p}."
        user = verifier.verify_token(token)
        assert user is not None
        assert user.user_id == "user-123"

    def test_rejects_aud_as_list_not_matching(self) -> None:
        """Audience list without matching client_id is rejected."""
        import base64
        import json
        import time

        config = _make_provider(client_id="maref-client")
        verifier = OIDCTokenVerifier(config)
        header = {"alg": "RS256", "typ": "JWT", "kid": "test-key"}
        payload = {
            "iss": config.issuer_url,
            "aud": ["other-api", "yet-another"],
            "sub": "user-123",
            "exp": int(time.time() + 3600),
        }
        h = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
        p = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        token = f"{h}.{p}."
        assert verifier.verify_token(token) is None


class TestJWTHeaderValidation:
    """Tests for JWT header parsing and alg validation."""

    def test_decode_valid_header(self) -> None:
        header = _decode_jwt_header("eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig")
        assert header is not None
        assert header["alg"] == "RS256"
        assert header["typ"] == "JWT"

    def test_decode_invalid_header(self) -> None:
        assert _decode_jwt_header("invalid.payload.sig") is None
        assert _decode_jwt_header("") is None
        assert _decode_jwt_header("notenoughparts") is None

    def test_rejects_alg_none_token(self) -> None:
        """alg: none tokens are rejected by _verify_signature."""
        import base64
        import json
        import time

        config = _make_provider()
        verifier = OIDCTokenVerifier(config)
        # Manually create a token with alg: none
        header = {"alg": "none", "typ": "JWT"}
        payload = {
            "iss": config.issuer_url,
            "aud": config.client_id,
            "sub": "attacker",
            "exp": int(time.time() + 3600),
        }
        h = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
        p = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        token = f"{h}.{p}."
        assert verifier.verify_token(token) is None


class TestSSOManager:
    def test_register_provider(self) -> None:
        sso = SSOManager()
        sso.register_provider(_make_provider())
        assert len(sso.list_providers()) == 1

    def test_authenticate_success(self) -> None:
        sso = SSOManager()
        config = _make_provider()
        sso.register_provider(config)
        token = _create_test_id_token(
            issuer=config.issuer_url,
            audience=config.client_id,
            sub="user-456",
        )
        user = sso.authenticate("okta", token)
        assert user is not None
        assert user.user_id == "user-456"

    def test_authenticate_unknown_provider(self) -> None:
        sso = SSOManager()
        assert sso.authenticate("unknown", "token") is None

    def test_map_user(self) -> None:
        sso = SSOManager()
        mapping = sso.map_user("okta", "user-1", "tenant-1", ["admin"])
        assert mapping.tenant_id == "tenant-1"
        assert "admin" in mapping.roles

    def test_resolve_user(self) -> None:
        sso = SSOManager()
        sso.map_user("okta", "user-1", "tenant-1")
        mapping = sso.resolve_user("okta", "user-1")
        assert mapping is not None
        assert mapping.tenant_id == "tenant-1"

    def test_resolve_unknown_user(self) -> None:
        sso = SSOManager()
        assert sso.resolve_user("okta", "unknown") is None

    def test_map_user_updates_existing(self) -> None:
        sso = SSOManager()
        sso.map_user("okta", "user-1", "tenant-1", ["viewer"])
        sso.map_user("okta", "user-1", "tenant-2", ["admin"])
        mapping = sso.resolve_user("okta", "user-1")
        assert mapping is not None
        assert mapping.tenant_id == "tenant-2"
        assert "admin" in mapping.roles

    def test_remove_provider(self) -> None:
        sso = SSOManager()
        sso.register_provider(_make_provider())
        sso.map_user("okta", "user-1", "tenant-1")
        assert sso.remove_provider("okta") is True
        assert len(sso.list_providers()) == 0
        assert sso.resolve_user("okta", "user-1") is None

    def test_remove_unknown_provider(self) -> None:
        sso = SSOManager()
        assert sso.remove_provider("unknown") is False

    def test_list_mappings_by_tenant(self) -> None:
        sso = SSOManager()
        sso.map_user("okta", "user-1", "tenant-a")
        sso.map_user("okta", "user-2", "tenant-a")
        sso.map_user("okta", "user-3", "tenant-b")
        tenant_a = sso.list_mappings("tenant-a")
        assert len(tenant_a) == 2
        tenant_b = sso.list_mappings("tenant-b")
        assert len(tenant_b) == 1

    def test_summary(self) -> None:
        sso = SSOManager()
        sso.register_provider(_make_provider("okta"))
        sso.register_provider(_make_provider("keycloak"))
        sso.map_user("okta", "u1", "t1")
        s = sso.summary()
        assert s["provider_count"] == 2
        assert s["total_mappings"] == 1
        assert "okta" in s["providers"]

    def test_default_roles(self) -> None:
        sso = SSOManager()
        mapping = sso.map_user("okta", "u1", "t1")
        assert "viewer" in mapping.roles

    def test_multiple_providers_same_user(self) -> None:
        """Same user ID from different providers are distinct."""
        sso = SSOManager()
        sso.register_provider(_make_provider("okta"))
        sso.register_provider(_make_provider("azuread"))
        sso.map_user("okta", "user-1", "tenant-1")
        sso.map_user("azuread", "user-1", "tenant-2")
        okta_mapping = sso.resolve_user("okta", "user-1")
        azure_mapping = sso.resolve_user("azuread", "user-1")
        assert okta_mapping is not None
        assert azure_mapping is not None
        assert okta_mapping.tenant_id == "tenant-1"
        assert azure_mapping.tenant_id == "tenant-2"

    def test_map_user_with_tenant_validator_passes(self) -> None:
        """map_user succeeds when tenant exists."""
        existing_tenants = {"tenant-1": "ok"}

        class FakeTenantValidator:
            def get_by_id(self, tenant_id: str) -> str | None:
                return existing_tenants.get(tenant_id)

        sso = SSOManager(tenant_validator=FakeTenantValidator())
        mapping = sso.map_user("okta", "u1", "tenant-1", ["admin"])
        assert mapping.tenant_id == "tenant-1"

    def test_map_user_with_tenant_validator_raises(self) -> None:
        """map_user raises ValueError when tenant does not exist."""
        import pytest

        class FakeTenantValidator:
            def get_by_id(self, tenant_id: str) -> None:
                return None

        sso = SSOManager(tenant_validator=FakeTenantValidator())
        with pytest.raises(ValueError, match="does not exist"):
            sso.map_user("okta", "u1", "nonexistent-tenant")

    def test_map_user_without_validator_does_not_validate(self) -> None:
        """Without tenant_validator, map_user does not validate tenant."""
        sso = SSOManager()
        mapping = sso.map_user("okta", "u1", "any-tenant")
        assert mapping.tenant_id == "any-tenant"
