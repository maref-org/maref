from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass
class ATPConfig:
    """Configuration for ATP (Agent Trust Protocol) adapter."""
    endpoint: str = "https://api.lyrie.ai/atp/v1"
    api_key: str | None = None
    timeout_seconds: int = 30
    retry_attempts: int = 3
    enable_local_fallback: bool = True
    cache_duration_seconds: int = 300


@dataclass
class ATPIdentity:
    """Represents an Agent's identity in the ATP system."""
    agent_id: str
    public_key: str
    registered_at: datetime
    certificate: str | None = None
    is_verified: bool = False
    trust_score: float = 0.0
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "public_key": self.public_key[:50] + "..." if len(self.public_key) > 50 else self.public_key,
            "registered_at": self.registered_at.isoformat(),
            "is_verified": self.is_verified,
            "trust_score": self.trust_score,
            "capabilities": self.capabilities,
        }


@dataclass
class ATPHandshakeRequest:
    """Request for ATP handshake/authentication."""
    agent_did: str
    session_id: str
    timestamp: int
    capabilities: list[str] = field(default_factory=list)
    nonce: str = field(default_factory=lambda: secrets.token_hex(16))
    signature: bytes | None = None

    def sign(self, key_pair: ATPKeyPair) -> None:
        """Sign the handshake request with the private key."""
        message = f"{self.agent_did}:{self.session_id}:{self.timestamp}:{self.nonce}".encode()
        self.signature = hashlib.sha256(key_pair.private_key + message).digest()

    def is_fresh(self, max_age_seconds: int = 60) -> bool:
        """Check if the request is within the valid time window."""
        import time
        return abs(time.time() - self.timestamp) <= max_age_seconds


@dataclass
class ATPKeyPair:
    """ATP key pair for agent identity."""
    public_key: bytes
    private_key: bytes
    algorithm: str = "hmac-sha256"
    key_id: str = ""


@dataclass
class ATPChallenge:
    """Challenge-response mechanism for identity verification."""
    agent_id: str
    nonce: str
    timestamp: datetime
    expires_at: datetime
    algorithm: str = "SHA-256"

    @classmethod
    def create(cls, agent_id: str, ttl_seconds: int = 300) -> ATPChallenge:
        now = datetime.now(timezone.utc)
        nonce = secrets.token_hex(32)
        return cls(
            agent_id=agent_id,
            nonce=nonce,
            timestamp=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "nonce": self.nonce,
            "timestamp": self.timestamp.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "algorithm": self.algorithm,
        }


@dataclass
class ATPVerificationResult:
    """Result of an identity verification attempt."""
    is_valid: bool
    agent_id: str
    trust_score: float = 0.0
    reason: str | None = None
    capabilities: list[str] = field(default_factory=list)
    verified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "agent_id": self.agent_id,
            "trust_score": self.trust_score,
            "reason": self.reason,
            "capabilities": self.capabilities,
            "verified_at": self.verified_at.isoformat(),
        }


class ATPAdapter:
    """Adapter for Lyrie.ai Agent Trust Protocol (ATP).

    Provides:
    - Identity registration
    - Challenge-response verification
    - Trust score retrieval
    - Certificate management
    """

    def __init__(self, config: ATPConfig | None = None) -> None:
        self.config = config or ATPConfig()
        self._identity_cache: dict[str, ATPIdentity] = {}
        self._verification_cache: dict[str, ATPVerificationResult] = {}

    def register_identity(self, agent_id: str, public_key: str, metadata: dict[str, Any] | None = None) -> bool:
        """Register a new agent identity with the ATP service."""
        if not self.config.endpoint:
            # Local fallback mode
            self._identity_cache[agent_id] = ATPIdentity(
                agent_id=agent_id,
                public_key=public_key,
                registered_at=datetime.now(timezone.utc),
                metadata=metadata or {},
            )
            return True

        try:
            response = self._make_request("POST", "/identities/register", {
                "agent_id": agent_id,
                "public_key": public_key,
                "metadata": metadata or {},
            })

            if response.get("status") == "registered":
                identity = ATPIdentity(
                    agent_id=agent_id,
                    public_key=public_key,
                    registered_at=datetime.now(timezone.utc),
                    certificate=response.get("certificate"),
                )
                self._identity_cache[agent_id] = identity
                return True
            return False
        except Exception:
            if self.config.enable_local_fallback:
                return self.register_identity(agent_id, public_key, metadata)
            raise

    def verify_identity(self, agent_id: str) -> ATPVerificationResult:
        """Verify an agent's identity and retrieve trust score."""
        # Check cache first
        if agent_id in self._verification_cache:
            cached = self._verification_cache[agent_id]
            if (datetime.now(timezone.utc) - cached.verified_at).seconds < self.config.cache_duration_seconds:
                return cached

        if not self.config.endpoint:
            # Local fallback mode
            result = ATPVerificationResult(
                is_valid=False,
                agent_id=agent_id,
                reason="local_mode",
            )
            self._verification_cache[agent_id] = result
            return result

        try:
            response = self._make_request("GET", f"/identities/{agent_id}/verify")

            if response.get("status") == "verified":
                result = ATPVerificationResult(
                    is_valid=True,
                    agent_id=agent_id,
                    trust_score=response.get("trust_score", 0.0),
                    capabilities=response.get("capabilities", []),
                )
            else:
                result = ATPVerificationResult(
                    is_valid=False,
                    agent_id=agent_id,
                    reason=response.get("reason", "unknown"),
                )

            self._verification_cache[agent_id] = result
            return result
        except Exception as e:
            if self.config.enable_local_fallback:
                return ATPVerificationResult(
                    is_valid=False,
                    agent_id=agent_id,
                    reason=f"verification_error: {str(e)}",
                )
            raise

    def create_challenge(self, agent_id: str) -> ATPChallenge:
        """Create a challenge for identity verification."""
        if not self.config.endpoint:
            # Local mode: generate challenge locally
            return ATPChallenge.create(agent_id)

        try:
            response = self._make_request("POST", f"/identities/{agent_id}/challenge")
            return ATPChallenge(
                agent_id=agent_id,
                nonce=response["nonce"],
                timestamp=datetime.fromisoformat(response["timestamp"]),
                expires_at=datetime.fromisoformat(response["expires_at"]),
            )
        except Exception:
            # Fallback to local challenge generation
            return ATPChallenge.create(agent_id)

    def verify_challenge_response(
        self,
        agent_id: str,
        challenge: ATPChallenge,
        response: dict[str, Any],
    ) -> ATPVerificationResult:
        """Verify a challenge response from an agent."""
        # Verify nonce matches
        if response.get("nonce") != challenge.nonce:
            return ATPVerificationResult(
                is_valid=False,
                agent_id=agent_id,
                reason="nonce_mismatch",
            )

        # Verify challenge hasn't expired
        if challenge.is_expired():
            return ATPVerificationResult(
                is_valid=False,
                agent_id=agent_id,
                reason="challenge_expired",
            )

        if not self.config.endpoint:
            # Local mode: basic verification
            return ATPVerificationResult(
                is_valid=True,
                agent_id=agent_id,
                trust_score=0.5,  # Neutral score in local mode
                reason="locally_verified",
            )

        try:
            verify_response = self._make_request(
                "POST",
                f"/identities/{agent_id}/verify-challenge",
                {
                    "challenge": challenge.to_dict(),
                    "response": response,
                },
            )

            if verify_response.get("status") == "verified":
                return ATPVerificationResult(
                    is_valid=True,
                    agent_id=agent_id,
                    trust_score=verify_response.get("trust_score", 0.0),
                    capabilities=verify_response.get("capabilities", []),
                )
            else:
                return ATPVerificationResult(
                    is_valid=False,
                    agent_id=agent_id,
                    reason=verify_response.get("reason", "verification_failed"),
                )
        except Exception as e:
            if self.config.enable_local_fallback:
                return ATPVerificationResult(
                    is_valid=False,
                    agent_id=agent_id,
                    reason=f"challenge_verification_error: {str(e)}",
                )
            raise

    def get_identity(self, agent_id: str) -> ATPIdentity | None:
        """Retrieve cached identity information."""
        return self._identity_cache.get(agent_id)

    def revoke_identity(self, agent_id: str, reason: str = "unspecified") -> bool:
        """Revoke an agent's identity."""
        if agent_id in self._identity_cache:
            identity = self._identity_cache[agent_id]
            identity.is_verified = False
            identity.trust_score = 0.0
            identity.metadata["revoked_reason"] = reason
            identity.metadata["revoked_at"] = datetime.now(timezone.utc).isoformat()

        if not self.config.endpoint:
            return True

        try:
            response = self._make_request(
                "POST",
                f"/identities/{agent_id}/revoke",
                {"reason": reason},
            )
            return response.get("status") == "revoked"
        except Exception:
            return False

    def _make_request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make HTTP request to ATP service.

        This is a placeholder that would use httpx/requests in production.
        For now, it raises to trigger fallback behavior.
        """
        # In production, this would make actual HTTP requests
        # For now, we simulate network failure to test fallback
        raise ConnectionError("ATP endpoint not configured or unreachable")

    def _generate_agent_fingerprint(self, agent_id: str, public_key: str) -> str:
        """Generate a unique fingerprint for an agent."""
        content = f"{agent_id}:{public_key}".encode()
        return hashlib.sha256(content).hexdigest()[:16]
