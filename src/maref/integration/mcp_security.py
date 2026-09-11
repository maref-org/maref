from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx


class MCPTrustLevel(str, Enum):
    TRUSTED = "trusted"
    SEMI_TRUSTED = "semi_trusted"
    UNTRUSTED = "untrusted"


class SecurityVerdict(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    AUDIT = "AUDIT"


FORBIDDEN_UNTRUSTED_PATTERNS = [
    "rm ",
    "DROP",
    "DELETE",
    "sudo",
    "chmod",
    "chown",
    "format",
    "mkfs",
]

FORBIDDEN_UNTRUSTED_TOOLS = [
    "bash",
    "shell",
    "exec",
    "system",
    "spawn",
    "eval",
]


@dataclass
class AuditLogEntry:
    timestamp: datetime
    agent_id: str
    tool_name: str
    trust_level: str
    verdict: str
    args_hash: str
    chain_id: str | None = None
    delegation_depth: int = 0
    risk_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RateLimiter:
    max_requests: int = 100
    window_seconds: int = 60
    _requests: deque[float] = field(default_factory=deque, repr=False)

    def check_rate(self) -> bool:
        now = time.time()
        # Remove old requests outside the window
        while self._requests and self._requests[0] < now - self.window_seconds:
            self._requests.popleft()

        if len(self._requests) >= self.max_requests:
            return False

        self._requests.append(now)
        return True

    def get_current_rate(self) -> int:
        now = time.time()
        while self._requests and self._requests[0] < now - self.window_seconds:
            self._requests.popleft()
        return len(self._requests)


@dataclass
class ZeroTrustContext:
    agent_id: str = ""
    chain_id: str | None = None
    delegation_depth: int = 0
    max_delegation_depth: int = 5
    session_id: str = ""
    request_id: str = ""
    token_claims: dict[str, Any] = field(default_factory=dict)


@dataclass
class OAuthTokenData:
    access_token: str = ""
    refresh_token: str = ""
    expires_at: float = 0.0
    scopes: list[str] = field(default_factory=list)
    token_type: str = "Bearer"
    issuer: str = ""
    subject: str = ""
    code_verifier: str = ""  # PKCE verifier retained for refresh/re-auth


class OAuthTokenProvider:
    def __init__(
        self,
        token_url: str = "",
        client_id: str = "",
        client_secret: str = "",
        scopes: list[str] | None = None,
        flow: str = "client_credentials",
    ) -> None:
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.scopes = scopes or ["maref:mcp"]
        self.flow = flow
        self._tokens: dict[str, OAuthTokenData] = {}
        self._pending_auth_codes: dict[str, tuple[str, str, str]] = {}

    def get_token(self, server_url: str) -> str:
        token_data = self._tokens.get(server_url)
        if token_data and token_data.access_token:
            if token_data.expires_at > time.time() + 30:
                return token_data.access_token
            try:
                return self.refresh_token(server_url)
            except Exception:
                pass
        return self._acquire_token(server_url)

    def refresh_token(self, server_url: str) -> str:
        token_data = self._tokens.get(server_url)
        if token_data and token_data.refresh_token:
            return self._do_refresh(server_url, token_data.refresh_token)
        return self._acquire_token(server_url)

    def store_token(self, server_url: str, token_data: OAuthTokenData) -> None:
        self._tokens[server_url] = token_data

    @staticmethod
    def generate_pkce_pair() -> tuple[str, str]:
        """Generate a PKCE code_verifier and S256 code_challenge (RFC 7636)."""
        code_verifier = secrets.token_urlsafe(64)[:128]
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return code_verifier, code_challenge

    def build_authorization_url(
        self,
        authorization_endpoint: str,
        redirect_uri: str,
        code_challenge: str,
        state: str | None = None,
        code_challenge_method: str = "S256",
    ) -> str:
        """Build an authorization request URL carrying the PKCE challenge."""
        from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

        params: dict[str, str] = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "scope": " ".join(self.scopes),
        }
        if state:
            params["state"] = state
        parsed = urlparse(authorization_endpoint)
        existing = dict(parse_qsl(parsed.query))
        existing.update(params)
        return urlunparse(parsed._replace(query=urlencode(existing)))

    def store_authorization_code(
        self,
        server_url: str,
        code: str,
        code_verifier: str,
        redirect_uri: str = "",
    ) -> None:
        """Store an authorization code + PKCE verifier for later exchange."""
        self._pending_auth_codes[server_url] = (code, code_verifier, redirect_uri)

    def _acquire_token(self, server_url: str) -> str:
        if self.flow == "client_credentials":
            return self._client_credentials_grant(server_url)
        if self.flow == "authorization_code":
            return self._authorization_code_grant(server_url)
        raise ValueError(f"Unsupported OAuth flow: {self.flow}")

    def _authorization_code_grant(self, server_url: str) -> str:
        """Exchange a stored authorization code + PKCE verifier for a token."""
        pending = self._pending_auth_codes.get(server_url)
        if pending is None:
            raise RuntimeError(
                "authorization_code flow requires a code: call store_authorization_code() first"
            )
        code, code_verifier, redirect_uri = pending
        token_endpoint = self.token_url or f"{server_url.rstrip('/')}/oauth/token"
        payload: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code_verifier": code_verifier,
        }
        if redirect_uri:
            payload["redirect_uri"] = redirect_uri
        try:
            response = httpx.post(token_endpoint, data=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            token_data = OAuthTokenData(
                access_token=data.get("access_token", ""),
                refresh_token=data.get("refresh_token", ""),
                expires_at=time.time() + data.get("expires_in", 3600),
                scopes=data.get("scope", " ".join(self.scopes)).split(),
                token_type=data.get("token_type", "Bearer"),
                issuer=server_url,
                subject=self.client_id,
                code_verifier="",
            )
            self._tokens[server_url] = token_data
            self._pending_auth_codes.pop(server_url, None)
            return token_data.access_token
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"OAuth authorization_code exchange failed: {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"OAuth authorization_code request failed: {exc}") from exc

    def _client_credentials_grant(self, server_url: str) -> str:
        token_endpoint = self.token_url or f"{server_url.rstrip('/')}/oauth/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": " ".join(self.scopes),
        }
        try:
            response = httpx.post(token_endpoint, data=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            token_data = OAuthTokenData(
                access_token=data.get("access_token", ""),
                refresh_token=data.get("refresh_token", ""),
                expires_at=time.time() + data.get("expires_in", 3600),
                scopes=data.get("scope", " ".join(self.scopes)).split(),
                token_type=data.get("token_type", "Bearer"),
                issuer=server_url,
                subject=self.client_id,
            )
            self._tokens[server_url] = token_data
            return token_data.access_token
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"OAuth token acquisition failed: {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"OAuth token request failed: {exc}") from exc

    def _do_refresh(self, server_url: str, refresh_token: str) -> str:
        token_endpoint = self.token_url or f"{server_url.rstrip('/')}/oauth/token"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        try:
            response = httpx.post(token_endpoint, data=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            token_data = OAuthTokenData(
                access_token=data.get("access_token", ""),
                refresh_token=data.get("refresh_token", refresh_token),
                expires_at=time.time() + data.get("expires_in", 3600),
                scopes=data.get("scope", " ".join(self.scopes)).split(),
                token_type=data.get("token_type", "Bearer"),
                issuer=server_url,
                subject=self.client_id,
            )
            self._tokens[server_url] = token_data
            return token_data.access_token
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"OAuth token refresh failed: {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"OAuth token refresh request failed: {exc}") from exc


class OAuthMiddleware:
    def __init__(
        self,
        token_provider: OAuthTokenProvider | None = None,
        verification_key: bytes | None = None,
        allow_unverified_tokens: bool = False,
    ) -> None:
        if verification_key is None and not allow_unverified_tokens:
            raise ValueError(
                "OAuthMiddleware requires a verification_key; pass "
                "allow_unverified_tokens=True only for non-production use"
            )
        self._provider = token_provider
        self._verification_key = verification_key

    async def authenticate(self, headers: dict[str, str]) -> ZeroTrustContext:
        auth_header = headers.get("authorization", headers.get("Authorization", ""))
        if not auth_header:
            raise PermissionError("Missing Authorization header")

        parts = auth_header.strip().split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise PermissionError("Invalid Authorization header format")

        token = parts[1]
        if not token:
            raise PermissionError("Empty Bearer token")

        claims = self._validate_token(token)
        return ZeroTrustContext(
            agent_id=claims.get("sub", "oauth-user"),
            session_id=claims.get("session_id", ""),
            request_id=claims.get("jti", ""),
            token_claims=claims,
        )

    def _validate_token(self, token: str) -> dict[str, Any]:
        try:
            import base64

            parts = token.split(".")
            if len(parts) != 3:
                raise PermissionError("Invalid token format or signature")
            header_b64, payload_b64, sig_b64 = parts
            # Verify the signature when a verification key is configured
            # (v0.47 S8 — previously the payload was decoded with no
            # signature check, so a forged token was accepted).
            if self._verification_key is None:
                raise PermissionError(
                    "Token signature verification required but no verification_key configured"
                )
            signing_input = f"{header_b64}.{payload_b64}".encode()
            expected = hmac.new(
                self._verification_key,
                signing_input,
                hashlib.sha256,
            ).digest()
            try:
                actual = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
            except (ValueError, TypeError):
                raise PermissionError("Invalid token signature") from None
            if not hmac.compare_digest(expected, actual):
                raise PermissionError("Token signature verification failed")

            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding
            try:
                payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                exp = payload.get("exp", 0)
                if exp and exp < time.time():
                    raise PermissionError("Token has expired")
                return payload
            except (json.JSONDecodeError, ValueError):
                raise PermissionError("Invalid token format or signature") from None
        except PermissionError:
            raise
        except Exception as exc:
            raise PermissionError(f"Token validation failed: {exc}") from exc


@dataclass
class MCPSecurityGate:
    allow_untrusted_shell: bool = False
    blocked_patterns: list[str] = field(default_factory=lambda: list(FORBIDDEN_UNTRUSTED_PATTERNS))
    blocked_tools: list[str] = field(default_factory=lambda: list(FORBIDDEN_UNTRUSTED_TOOLS))
    enable_rate_limiting: bool = True
    enable_audit_logging: bool = True
    enable_delegation_check: bool = True
    max_delegation_depth: int = 5
    rate_limiter: RateLimiter = field(default_factory=lambda: RateLimiter())
    oauth_provider: OAuthTokenProvider | None = None
    verification_key: bytes | None = None
    allow_unverified_tokens: bool = False
    _audit_log: list[AuditLogEntry] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if self.verification_key is None and not self.allow_unverified_tokens:
            raise ValueError(
                "MCPSecurityGate requires a verification_key; pass "
                "allow_unverified_tokens=True only for non-production use"
            )

    def authenticate_request(self, headers: dict[str, str]) -> ZeroTrustContext:
        auth_header = headers.get("authorization", headers.get("Authorization", ""))
        if not auth_header:
            return ZeroTrustContext(agent_id="anonymous")

        parts = auth_header.strip().split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return ZeroTrustContext(agent_id="anonymous")

        token = parts[1]
        if not token:
            return ZeroTrustContext(agent_id="anonymous")

        try:
            import base64

            segments = token.split(".")
            if len(segments) == 3:
                header_b64, payload_b64, sig_b64 = segments
                # Verify the JWT signature when a key is configured
                # (v0.47 S8 — previously only the payload was decoded).
                if self.verification_key is not None:
                    signing_input = f"{header_b64}.{payload_b64}".encode()
                    expected = hmac.new(
                        self.verification_key, signing_input, hashlib.sha256
                    ).digest()
                    try:
                        actual = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
                    except (ValueError, TypeError):
                        return ZeroTrustContext(
                            agent_id="anonymous", token_claims={"error": "bad_signature"}
                        )
                    if not hmac.compare_digest(expected, actual):
                        return ZeroTrustContext(
                            agent_id="anonymous",
                            token_claims={"error": "invalid_signature"},
                        )
                padding = 4 - len(segments[1]) % 4
                if padding != 4:
                    segments[1] += "=" * padding
                try:
                    payload = json.loads(base64.urlsafe_b64decode(segments[1]))
                    exp = payload.get("exp", 0)
                    if exp and exp < time.time():
                        return ZeroTrustContext(
                            agent_id="anonymous", token_claims={"error": "expired"}
                        )
                    return ZeroTrustContext(
                        agent_id=payload.get("sub", "oauth-user"),
                        session_id=payload.get("session_id", ""),
                        request_id=payload.get("jti", ""),
                        token_claims=payload,
                    )
                except (json.JSONDecodeError, ValueError):
                    pass
        except Exception:
            pass

        return ZeroTrustContext(agent_id="anonymous")

    def check(
        self,
        tool_name: str,
        trust_level: MCPTrustLevel,
        args: dict[str, Any] | None = None,
        context: ZeroTrustContext | None = None,
        relaxed: bool = False,
    ) -> str:
        context = context or ZeroTrustContext()
        args = args or {}

        # Check rate limiting
        if self.enable_rate_limiting and not self.rate_limiter.check_rate():
            self._log_audit(tool_name, trust_level, "DENY", args, context, risk_score=1.0)
            return SecurityVerdict.DENY

        # Check delegation depth
        if self.enable_delegation_check:
            if context.delegation_depth > self.max_delegation_depth:
                self._log_audit(tool_name, trust_level, "DENY", args, context, risk_score=1.0)
                return SecurityVerdict.DENY

        # Base trust level check (session-aware)
        verdict = self._check_trust_level(tool_name, trust_level, args, relaxed=relaxed)

        # Calculate risk score
        risk_score = self._calculate_risk(tool_name, trust_level, args, context)

        # Log audit
        if self.enable_audit_logging:
            self._log_audit(tool_name, trust_level, verdict, args, context, risk_score)

        return verdict

    def _check_trust_level(
        self,
        tool_name: str,
        trust_level: MCPTrustLevel,
        args: dict[str, Any],
        relaxed: bool = False,
    ) -> str:
        if trust_level == MCPTrustLevel.TRUSTED:
            return SecurityVerdict.ALLOW

        args_str = str(args).lower()

        if trust_level == MCPTrustLevel.UNTRUSTED:
            if not self.allow_untrusted_shell:
                lowered = tool_name.lower()
                for blocked in self.blocked_tools:
                    if blocked in lowered:
                        return SecurityVerdict.DENY

                for pattern in self.blocked_patterns:
                    if pattern.lower() in args_str:
                        return SecurityVerdict.DENY

            return SecurityVerdict.AUDIT

        if trust_level == MCPTrustLevel.SEMI_TRUSTED:
            for blocked in self.blocked_tools:
                if blocked in tool_name.lower():
                    if relaxed:
                        # Within an execution session, shell/exec tools are
                        # AUDIT'd (recorded) rather than DENY'd, enabling
                        # autonomous task loops (e.g. run tests after edit).
                        # But P0 dangerous args still get DENY.
                        for pattern in self.blocked_patterns:
                            if pattern.lower() in args_str:
                                return SecurityVerdict.DENY
                        return SecurityVerdict.AUDIT
                    return SecurityVerdict.DENY
            return SecurityVerdict.AUDIT

        return SecurityVerdict.DENY

    def _calculate_risk(
        self,
        tool_name: str,
        trust_level: MCPTrustLevel,
        args: dict[str, Any],
        context: ZeroTrustContext,
    ) -> float:
        risk = 0.0

        # Trust level risk
        if trust_level == MCPTrustLevel.UNTRUSTED:
            risk += 0.3
        elif trust_level == MCPTrustLevel.SEMI_TRUSTED:
            risk += 0.1

        # Delegation depth risk
        if context.delegation_depth > 2:
            risk += 0.2
        if context.delegation_depth > 4:
            risk += 0.3

        # Tool risk
        lowered = tool_name.lower()
        for blocked in self.blocked_tools:
            if blocked in lowered:
                risk += 0.2
                break

        # Args risk
        args_str = str(args).lower()
        for pattern in self.blocked_patterns:
            if pattern.lower() in args_str:
                risk += 0.2
                break

        return min(risk, 1.0)

    def _log_audit(
        self,
        tool_name: str,
        trust_level: MCPTrustLevel,
        verdict: str,
        args: dict[str, Any],
        context: ZeroTrustContext,
        risk_score: float,
    ) -> None:
        import hashlib

        args_hash = hashlib.sha256(str(args).encode()).hexdigest()[:16]

        entry = AuditLogEntry(
            timestamp=datetime.now(timezone.utc),
            agent_id=context.agent_id,
            tool_name=tool_name,
            trust_level=trust_level.value,
            verdict=verdict,
            args_hash=args_hash,
            chain_id=context.chain_id,
            delegation_depth=context.delegation_depth,
            risk_score=risk_score,
        )
        self._audit_log.append(entry)

    def get_audit_log(self) -> list[AuditLogEntry]:
        return list(self._audit_log)

    def get_audit_summary(self) -> dict[str, Any]:
        total = len(self._audit_log)
        allowed = sum(1 for e in self._audit_log if e.verdict == "ALLOW")
        denied = sum(1 for e in self._audit_log if e.verdict == "DENY")
        audited = sum(1 for e in self._audit_log if e.verdict == "AUDIT")

        return {
            "total_requests": total,
            "allowed": allowed,
            "denied": denied,
            "audited": audited,
            "current_rate": self.rate_limiter.get_current_rate(),
            "max_rate": self.rate_limiter.max_requests,
        }

    def export_audit_log(self, format: str = "json") -> str:
        import json

        if format == "json":
            return json.dumps(
                [
                    {
                        "timestamp": e.timestamp.isoformat(),
                        "agent_id": e.agent_id,
                        "tool_name": e.tool_name,
                        "trust_level": e.trust_level,
                        "verdict": e.verdict,
                        "args_hash": e.args_hash,
                        "chain_id": e.chain_id,
                        "delegation_depth": e.delegation_depth,
                        "risk_score": e.risk_score,
                    }
                    for e in self._audit_log
                ],
                indent=2,
            )
        elif format == "syslog":
            lines = []
            for e in self._audit_log:
                lines.append(
                    f"{e.timestamp.isoformat()} MAREF-SECURITY "
                    f"agent={e.agent_id} tool={e.tool_name} "
                    f"trust={e.trust_level} verdict={e.verdict} "
                    f"risk={e.risk_score:.2f} depth={e.delegation_depth}"
                )
            return "\n".join(lines)
        else:
            raise ValueError(f"Unsupported format: {format}")


def _require_hmac_key() -> bytes:
    """Lazy-load HMAC key from environment, raising on missing.

    Module-level raise was too aggressive: importing ``mcp_security``
    (transitively via ``browser_controller`` → ``browser_server`` → ``mcp_server``)
    should not crash when the env var is unset.  Only callers that actually
    *sign* audit entries need the key.
    """
    key = os.environb.get(b"MAREF_HMAC_SECRET_KEY")
    if key is None:
        raise RuntimeError(
            "MAREF_HMAC_SECRET_KEY environment variable must be set. "
            "This is required for audit log integrity. "
            'Generate a key with: python -c "import secrets; print(secrets.token_hex(32))"'
        )
    return key


DEFAULT_HMAC_SECRET_KEY: bytes | None = os.environb.get(b"MAREF_HMAC_SECRET_KEY")


def _resolve_key(secret_key: bytes | None) -> bytes:
    if secret_key is not None:
        return secret_key
    return _require_hmac_key()


def sign_audit_entry(
    entry: AuditLogEntry, secret_key: bytes | None = DEFAULT_HMAC_SECRET_KEY
) -> str:
    """Create HMAC-SHA256 signature for an audit log entry.

    The signature covers all immutable fields of the entry, providing
    tamper-evident audit logging. Store alongside the entry for verification.
    """
    secret_key = _resolve_key(secret_key)
    payload = json.dumps(
        {
            "timestamp": entry.timestamp.isoformat(),
            "agent_id": entry.agent_id,
            "tool_name": entry.tool_name,
            "trust_level": entry.trust_level,
            "verdict": entry.verdict,
            "args_hash": entry.args_hash,
            "chain_id": entry.chain_id,
            "delegation_depth": entry.delegation_depth,
            "risk_score": entry.risk_score,
        },
        sort_keys=True,
    )
    return hmac.new(secret_key, payload.encode(), hashlib.sha256).hexdigest()


def verify_audit_signature(
    entry: AuditLogEntry, signature: str, secret_key: bytes | None = DEFAULT_HMAC_SECRET_KEY
) -> bool:
    """Verify HMAC-SHA256 signature of an audit log entry."""
    secret_key_bytes = _resolve_key(secret_key)
    try:
        expected = sign_audit_entry(entry, secret_key=secret_key_bytes)
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False
