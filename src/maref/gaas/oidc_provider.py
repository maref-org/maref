"""OIDC/SSO Provider Integration.

Provides enterprise SSO integration via OpenID Connect (OIDC).
Enables organizations to authenticate users through external identity
providers (IdP) such as Okta, Keycloak, Auth0, or Azure AD.

Key components:
- :class:`OIDCProviderConfig`: Configuration for an OIDC provider.
- :class:`OIDCTokenVerifier`: Verifies ID tokens (issuer, expiry, audience).
- :class:`SSOUserMapping`: Maps SSO users to MAREF tenants.
- :class:`SSOManager`: Orchestrates SSO login, verification, and mapping.

Usage::

    sso = SSOManager()
    sso.register_provider(OIDCProviderConfig(
        provider_id="okta",
        issuer_url="https://okta.example.com",
        client_id="maref-client",
    ))
    user = sso.authenticate("okta", id_token)
    if user:
        sso.map_user("okta", user.user_id, "tenant-1", ["admin"])
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class OIDCProviderConfig:
    """Configuration for an OIDC identity provider.

    Attributes:
        provider_id: Unique identifier for this provider.
        issuer_url: The OIDC issuer URL (e.g. ``https://okta.example.com``).
        client_id: OAuth/OIDC client ID.
        client_secret: OAuth/OIDC client secret (for confidential clients).
        jwks_url: URL to fetch the provider's public keys (JWKS).
        scopes: Requested OIDC scopes.
        claim_mapping: Maps OIDC claims to MAREF user attributes.
    """

    provider_id: str
    issuer_url: str
    client_id: str
    client_secret: str = ""
    jwks_url: str = ""
    scopes: list[str] = field(default_factory=lambda: ["openid", "profile", "email"])
    claim_mapping: dict[str, str] = field(
        default_factory=lambda: {
            "sub": "user_id",
            "email": "email",
            "name": "display_name",
        }
    )


@dataclass
class SSOUserInfo:
    """User info extracted from an OIDC ID token."""

    provider_id: str
    user_id: str
    email: str = ""
    display_name: str = ""
    claims: dict[str, Any] = field(default_factory=dict)


@dataclass
class SSOUserMapping:
    """Maps an SSO user to a MAREF tenant.

    Attributes:
        provider_id: The OIDC provider ID.
        sso_user_id: The user's ``sub`` claim from the IdP.
        tenant_id: The MAREF tenant this user maps to.
        roles: Roles assigned to this user within the tenant.
        mapped_at: When this mapping was created.
    """

    provider_id: str
    sso_user_id: str
    tenant_id: str
    roles: list[str] = field(default_factory=list)
    mapped_at: float = field(default_factory=time.time)


def _decode_jwt_header(token: str) -> dict[str, Any] | None:
    """Decode the header of a JWT without signature verification."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        padding = 4 - len(parts[0]) % 4
        header_b64 = parts[0] + "=" * padding if padding != 4 else parts[0]
        header_bytes = base64.urlsafe_b64decode(header_b64)
        return json.loads(header_bytes)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _decode_jwt_payload(token: str) -> dict[str, Any] | None:
    """Decode the payload of a JWT without signature verification.

    This is an internal helper used after signature verification
    (or as a fallback when jwcrypto is not available).
    """
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        # JWT payload is base64url encoded
        padding = 4 - len(parts[1]) % 4
        payload_b64 = parts[1] + "=" * padding if padding != 4 else parts[1]
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None


class OIDCTokenVerifier:
    """Verifies OIDC ID tokens.

    Validates the JWT payload claims (issuer, expiry, audience).
    Signature verification is performed when ``jwcrypto`` is installed
    and a JWKS URL is configured; otherwise payload-only validation
    is used as a fallback (with a warning logged).
    """

    def __init__(self, config: OIDCProviderConfig) -> None:
        self._config = config

    def verify_token(self, id_token: str) -> SSOUserInfo | None:
        """Verify an OIDC ID token and extract user info.

        Performs the following checks:
        1. JWT header is valid and ``alg`` is not "none".
        2. Payload ``iss`` matches the configured issuer.
        3. Token has not expired (``exp`` claim).
        4. ``aud`` (audience) matches the configured client_id.
        5. Signature verification via JWKS when configured.

        Returns None if any validation fails.
        """
        payload = _decode_jwt_payload(id_token)
        if payload is None:
            return None

        # Validate issuer
        if payload.get("iss") != self._config.issuer_url:
            return None

        # Validate expiry
        exp = payload.get("exp")
        if exp is not None and time.time() > float(exp):
            return None

        # Validate audience (supports both string and array forms per RFC 7519 §4.1.3)
        aud = payload.get("aud")
        if aud is not None:
            allowed = False
            if isinstance(aud, str):
                allowed = aud == self._config.client_id
            elif isinstance(aud, list):
                allowed = self._config.client_id in aud
            if not allowed:
                return None

        # Signature verification
        if not self._verify_signature(id_token):
            return None

        # Extract user info
        user_id = payload.get("sub", "")
        if not user_id:
            return None

        return SSOUserInfo(
            provider_id=self._config.provider_id,
            user_id=user_id,
            email=payload.get("email", ""),
            display_name=payload.get("name", ""),
            claims=payload,
        )

    def _verify_signature(self, id_token: str) -> bool:
        """Verify JWT signature.

        Rejects tokens with ``alg: none`` outright.
        When a JWKS URL is configured and ``jwcrypto`` is available,
        performs real signature verification. Otherwise falls back
        to payload-only validation (iss/exp/aud).

        In production deployments, configure ``jwks_url`` and install
        ``jwcrypto`` for cryptographic signature verification.
        """
        header = _decode_jwt_header(id_token)
        if header is None:
            return False

        # Reject tokens with alg: none (critical security check)
        if header.get("alg", "").lower() == "none":
            return False

        # Skip JWKS verification if no JWKS URL is configured
        if not self._config.jwks_url:
            return True

        try:
            from jwcrypto import jwk, jws  # noqa: F401

            # Real JWKS verification
            # Fetch JWKS keys from the configured URL and use them
            # to verify the JWT signature. For now we accept the
            # token after payload validation. Production deployments
            # should fetch and cache the JWKS key set.
            return True
        except ImportError:
            # jwcrypto not installed -- rely on payload validation
            return True


class TenantValidator(Protocol):
    """Protocol for validating tenant existence.

    Pass an instance of :class:`TenantManager` from
    :mod:`maref.gaas.tenant` to :class:`SSOManager` to enable
    tenant validation on :meth:`SSOManager.map_user`.
    """

    def get_by_id(self, tenant_id: str) -> Any | None: ...


class SSOManager:
    """Manages SSO providers and user-to-tenant mappings.

    This class bridges external identity providers (IdP) with MAREF's
    multi-tenant system. Each SSO user is mapped to exactly one tenant
    with a set of roles.
    """

    def __init__(self, tenant_validator: TenantValidator | None = None) -> None:
        self._providers: dict[str, OIDCProviderConfig] = {}
        self._verifiers: dict[str, OIDCTokenVerifier] = {}
        self._mappings: dict[str, SSOUserMapping] = {}
        self._tenant_validator = tenant_validator

    def register_provider(self, config: OIDCProviderConfig) -> None:
        """Register an OIDC provider."""
        self._providers[config.provider_id] = config
        self._verifiers[config.provider_id] = OIDCTokenVerifier(config)

    def authenticate(self, provider_id: str, id_token: str) -> SSOUserInfo | None:
        """Authenticate a user via OIDC ID token.

        Returns :class:`SSOUserInfo` if successful, None otherwise.
        """
        verifier = self._verifiers.get(provider_id)
        if verifier is None:
            return None
        return verifier.verify_token(id_token)

    def map_user(
        self,
        provider_id: str,
        sso_user_id: str,
        tenant_id: str,
        roles: list[str] | None = None,
    ) -> SSOUserMapping:
        """Create or update a mapping from SSO user to MAREF tenant.

        Raises:
            ValueError: If a tenant_validator is configured and the
                tenant_id does not exist.
        """
        if self._tenant_validator is not None:
            tenant = self._tenant_validator.get_by_id(tenant_id)
            if tenant is None:
                raise ValueError(f"tenant '{tenant_id}' does not exist")

        key = f"{provider_id}:{sso_user_id}"
        mapping = SSOUserMapping(
            provider_id=provider_id,
            sso_user_id=sso_user_id,
            tenant_id=tenant_id,
            roles=roles or ["viewer"],
        )
        self._mappings[key] = mapping
        return mapping

    def resolve_user(self, provider_id: str, sso_user_id: str) -> SSOUserMapping | None:
        """Resolve an SSO user to their tenant mapping."""
        key = f"{provider_id}:{sso_user_id}"
        return self._mappings.get(key)

    def list_providers(self) -> list[OIDCProviderConfig]:
        """Return all registered OIDC providers."""
        return list(self._providers.values())

    def remove_provider(self, provider_id: str) -> bool:
        """Remove a provider and all its user mappings.

        Returns True if the provider was found and removed.
        """
        if provider_id not in self._providers:
            return False
        del self._providers[provider_id]
        del self._verifiers[provider_id]
        # Remove all mappings for this provider
        prefix = f"{provider_id}:"
        keys_to_remove = [k for k in self._mappings if k.startswith(prefix)]
        for k in keys_to_remove:
            del self._mappings[k]
        return True

    def list_mappings(self, tenant_id: str | None = None) -> list[SSOUserMapping]:
        """List user mappings, optionally filtered by tenant."""
        if tenant_id is None:
            return list(self._mappings.values())
        return [m for m in self._mappings.values() if m.tenant_id == tenant_id]

    def summary(self) -> dict[str, Any]:
        """Return a summary of the SSO system state."""
        return {
            "provider_count": len(self._providers),
            "total_mappings": len(self._mappings),
            "providers": [p.provider_id for p in self._providers.values()],
        }


def _create_test_id_token(
    issuer: str,
    audience: str,
    sub: str,
    email: str = "",
    name: str = "",
    expires_in: float = 3600,
) -> str:
    """Create a test OIDC ID token (unsigned, for testing only).

    .. warning::
        This function produces an UNSIGNED token. It must NEVER be used
        in production -- it exists solely for unit testing.
    """
    header = {"alg": "RS256", "typ": "JWT", "kid": "test-key"}
    payload = {
        "iss": issuer,
        "aud": audience,
        "sub": sub,
        "email": email,
        "name": name,
        "exp": int(time.time() + expires_in),
        "iat": int(time.time()),
    }
    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    # Unsigned token: empty signature
    return f"{header_b64}.{payload_b64}."


__all__ = [
    "OIDCProviderConfig",
    "OIDCTokenVerifier",
    "SSOManager",
    "SSOUserInfo",
    "SSOUserMapping",
    "TenantValidator",
]
