from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from maref.identity.did_registry import AgentDID


@dataclass
class AuthorizationScope:
    """授权范围证书 — 方案 D M2。

    声明主体（subject_did）在某时限内被授权执行不超过 ``max_risk_level``
    风险等级的动作子集。每个动作执行前校验
    ``action.risk_level <= scope.max_risk_level``，越界即阻断并记审计。
    """

    subject_did: str
    max_risk_level: str
    allowed_actions: list[str] = field(default_factory=list)
    valid_until: float | None = None
    jurisdiction: str = "local"
    issuer: str = ""
    signature: str = ""

    def canonical_payload(self) -> bytes:
        """Canonical bytes the issuer signs over (v0.47 S12)."""
        return (
            f"{self.subject_did}\n"
            f"{self.max_risk_level}\n"
            f"{','.join(sorted(self.allowed_actions))}\n"
            f"{self.valid_until!r}\n"
            f"{self.jurisdiction}\n"
            f"{self.issuer}"
        ).encode()

    def sign(self, signing_key: Any) -> None:
        """Sign the scope with the issuer's Ed25519 key (v0.47 S12)."""
        self.signature = signing_key.sign_report(self.canonical_payload())

    def verify_signature(self, public_key_pem: str) -> bool:
        """Verify the issuer's Ed25519 signature against a public key."""
        if not self.signature or not public_key_pem:
            return False
        from maref.signing.signing_key import ReportSigningKey

        return ReportSigningKey.verify_signature(
            public_key_pem, self.signature, self.canonical_payload()
        )

    def allows_action(self, action: str, risk_level: str) -> bool:
        """校验动作是否在授权范围内。

        Args:
            action: 动作标识。
            risk_level: 动作的风险等级（RiskLevel.value）。

        Returns:
            True 表示允许；False 表示越界（风险超限或动作未授权）。

        Note:
            前缀授权 ``file:`` 只匹配 ``file:<...>`` / ``file.<...>`` 域内动作，
            不匹配 ``filesystem:...`` 等含相同词根的跨域动作（防跨域超授权）。
        """
        if self.allowed_actions:
            allowed = any(
                action == a or self._prefix_allows(a, action)
                for a in self.allowed_actions
                if a.endswith(":")
            ) or (action in self.allowed_actions)
            if not allowed:
                return False
        order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "IRREVERSIBLE": 3}
        return order.get(risk_level, 99) <= order.get(self.max_risk_level, -1)

    @staticmethod
    def _prefix_allows(scope_action: str, action: str) -> bool:
        """前缀授权判定：前缀词根后必须紧跟路径分隔符（``:`` / ``.``）或结束。

        防止 ``file:`` 匹配 ``filesystem:format`` 等含相同词根的跨域动作。
        """
        prefix = scope_action.rstrip(":")
        if not action.startswith(prefix):
            return False
        rest = action[len(prefix):]
        # 前缀后必须为分隔符或已结束；空 rest 表示完全相等（由 action==a 覆盖）。
        return rest.startswith(":") or rest.startswith(".")

    def is_expired(self, now: float | None = None) -> bool:
        if self.valid_until is None:
            return False
        now = now if now is not None else time.time()
        # valid_until 可能来自外部 dict（字符串时间戳），类型安全地解析，
        # 无法解析时按 fail-closed 处理（视为过期）。
        try:
            valid_until = float(self.valid_until)
        except (TypeError, ValueError):
            return True
        return now > valid_until

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_did": self.subject_did,
            "max_risk_level": self.max_risk_level,
            "allowed_actions": list(self.allowed_actions),
            "valid_until": self.valid_until,
            "jurisdiction": self.jurisdiction,
            "issuer": self.issuer,
            "signature": self.signature,
        }

    @classmethod
    def issue(
        cls,
        subject_did: str,
        max_risk_level: str,
        allowed_actions: list[str] | None = None,
        ttl_seconds: float | None = 3600,
        jurisdiction: str = "local",
        issuer: str = "",
    ) -> AuthorizationScope:
        valid_until = (time.time() + ttl_seconds) if ttl_seconds is not None else None
        return cls(
            subject_did=subject_did,
            max_risk_level=max_risk_level,
            allowed_actions=allowed_actions or [],
            valid_until=valid_until,
            jurisdiction=jurisdiction,
            issuer=issuer,
        )



@dataclass
class VerifiableCredential:
    """DEPRECATED (v0.50 W7-S3 / A5) — use
    :class:`maref.governance.verifiable_governance_credential.VerifiableGovernanceCredential`
    instead.  Removed from the ``maref.identity`` package exports.

    HMAC-based legacy credential.  ``issue`` requires an explicit
    ``issuer_secret`` (fail-closed since v0.50 W7-S2 / A6).
    """

    id: str
    issuer: AgentDID
    subject: AgentDID
    issued_at: float
    expires_at: float | None
    credential_type: str
    claims: dict[str, Any]
    proof: dict[str, str] = field(default_factory=dict)

    def to_json_ld(self) -> dict[str, Any]:
        return {
            "@context": ["https://www.w3.org/2018/credentials/v1"],
            "id": self.id,
            "type": ["VerifiableCredential", self.credential_type],
            "issuer": self.issuer.did_string,
            "issuanceDate": self.issued_at,
            "expirationDate": self.expires_at,
            "credentialSubject": {
                "id": self.subject.did_string,
                **self.claims,
            },
            "proof": self.proof,
        }

    def verify(self, issuer_secret: bytes) -> bool:
        expected = VerifiableCredential._compute_proof_signature(
            issuer_secret,
            self.issuer.did_string,
            self.subject.did_string,
            issued_at=self.issued_at,
            expires_at=self.expires_at or 0.0,
        )
        return self.proof.get("signature") == expected

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    @classmethod
    def issue(
        cls,
        issuer: AgentDID,
        subject: AgentDID,
        credential_type: str,
        claims: dict[str, Any],
        ttl_seconds: float | None = 3600,
        issuer_secret: bytes | None = None,
    ) -> VerifiableCredential:
        if issuer_secret is None:
            raise ValueError(
                "issuer_secret is required to issue a credential "
                "(fail-closed; implicit random secrets are disabled)"
            )
        now = time.time()
        vc_id = f"vc-{secrets.token_hex(8)}"
        expires = (now + ttl_seconds) if ttl_seconds is not None else None
        signature = cls._compute_proof_signature(
            issuer_secret,
            issuer.did_string,
            subject.did_string,
            issued_at=now,
            expires_at=expires or 0.0,
        )
        proof = {"type": "HMAC-SHA256", "signature": signature}
        return cls(
            id=vc_id,
            issuer=issuer,
            subject=subject,
            issued_at=now,
            expires_at=expires,
            credential_type=credential_type,
            claims=claims,
            proof=proof,
        )

    @staticmethod
    def _compute_proof_signature(
        secret: bytes,
        issuer_str: str,
        subject_str: str,
        issued_at: float = 0.0,
        expires_at: float = 0.0,
    ) -> str:
        message = f"{issuer_str}:{subject_str}:{issued_at}:{expires_at}".encode()
        return hmac.new(secret, message, hashlib.sha256).hexdigest()


class CredentialStore:
    """DEPRECATED (v0.50 W7-S3 / A5) — use
    :class:`maref.governance.verifiable_governance_credential.GovernanceCredentialStore`
    instead.  Removed from the ``maref.identity`` package exports.
    """

    def __init__(self) -> None:
        self._credentials: dict[str, VerifiableCredential] = {}
        self._revoked: dict[str, str] = {}

    def store(self, vc: VerifiableCredential) -> None:
        self._credentials[vc.id] = vc

    def revoke(self, vc_id: str, reason: str = "unspecified") -> None:
        if vc_id not in self._credentials:
            raise ValueError(f"Credential {vc_id} not found")
        self._revoked[vc_id] = reason

    def is_revoked(self, vc_id: str) -> bool:
        return vc_id in self._revoked

    def get(self, vc_id: str) -> VerifiableCredential | None:
        return self._credentials.get(vc_id)

    def list_valid(self) -> list[VerifiableCredential]:
        return [
            vc
            for vc in self._credentials.values()
            if not self.is_revoked(vc.id) and not vc.is_expired()
        ]

    def count(self) -> int:
        return len(self._credentials)

    def revoked_count(self) -> int:
        return len(self._revoked)
