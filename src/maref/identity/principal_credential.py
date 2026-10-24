"""Principal identity anchoring — 委托人签名凭证 (P1-6).

Verifier Tax (arXiv:2603.19328) 的 Integrity Leak：直接违规被拦后，agent 会幻觉出
user_id/委托人身份绕过强制认证。根因是身份字段由 agent 自报、不可验证。

本模块把"委托人身份"做成不可伪造的 Ed25519 签名凭证：委托人用**自己的私钥**签发
``PrincipalCredential``(绑定被授权 agent + 动作范围)，治理边界校验签名而非自报字段。
agent 不持有委托人私钥，因此无法伪造——把身份伪造从"检测"升级为"结构性不可能"。

签名基座复用 :class:`maref.signing.signing_key.ReportSigningKey`，与
:class:`maref.identity.credential.AuthorizationScope` 同构。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from maref.security.decorators import security_critical


@dataclass
class PrincipalDecision:
    """Result of a principal authorization check."""

    allowed: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reason": self.reason}


@dataclass
class PrincipalCredential:
    """委托人签发的身份凭证，绑定被授权 agent 与动作范围。

    ``allowed_actions`` 为空表示不授权任何动作（fail-closed），与
    ``AuthorizationScope``（空=不限制动作）语义相反——身份锚定场景下更严格。
    """

    principal_did: str
    agent_did: str
    allowed_actions: list[str] = field(default_factory=list)
    valid_until: float | None = None
    issuer: str = ""
    signature: str = ""

    def canonical_payload(self) -> bytes:
        """Canonical bytes the principal signs over."""
        return (
            f"{self.principal_did}\n"
            f"{self.agent_did}\n"
            f"{','.join(sorted(self.allowed_actions))}\n"
            f"{self.valid_until!r}\n"
            f"{self.issuer}"
        ).encode()

    def sign(self, signing_key: Any) -> None:
        """Sign the credential with the principal's Ed25519 key."""
        self.signature = signing_key.sign_report(self.canonical_payload())

    @security_critical
    def verify_signature(self, public_key_pem: str) -> bool:
        """Verify the principal's Ed25519 signature against a public key."""
        if not self.signature or not public_key_pem:
            return False
        from maref.signing.signing_key import ReportSigningKey

        return ReportSigningKey.verify_signature(
            public_key_pem, self.signature, self.canonical_payload()
        )

    def is_expired(self, now: float | None = None) -> bool:
        """Whether the credential has expired (fail-closed on unparseable time)."""
        if self.valid_until is None:
            return False
        current = now if now is not None else time.time()
        try:
            valid_until = float(self.valid_until)
        except (TypeError, ValueError):
            return True
        return current > valid_until

    def allows_action(self, action: str) -> bool:
        """Whether ``action`` is in the granted scope (empty scope denies all)."""
        if not self.allowed_actions:
            return False
        return action in self.allowed_actions

    def to_dict(self) -> dict[str, Any]:
        return {
            "principal_did": self.principal_did,
            "agent_did": self.agent_did,
            "allowed_actions": list(self.allowed_actions),
            "valid_until": self.valid_until,
            "issuer": self.issuer,
            "signature": self.signature,
        }

    @classmethod
    def issue(
        cls,
        principal_did: str,
        agent_did: str,
        allowed_actions: list[str] | None = None,
        ttl_seconds: float | None = 3600,
        issuer: str = "",
    ) -> PrincipalCredential:
        """Build an unsigned credential (call :meth:`sign` with the principal key)."""
        valid_until = (time.time() + ttl_seconds) if ttl_seconds is not None else None
        return cls(
            principal_did=principal_did,
            agent_did=agent_did,
            allowed_actions=list(allowed_actions or []),
            valid_until=valid_until,
            issuer=issuer or principal_did,
        )


class PrincipalRegistry:
    """Holds principal public keys and authorizes declared-identity claims.

    This is the enforcement point against Integrity Leak: an agent that declares
    a principal must present a credential signed by that principal's registered
    key, bound to the agent and covering the action. Otherwise → denied.
    """

    def __init__(self) -> None:
        self._keys: dict[str, str] = {}

    def register(self, principal_did: str, public_key_pem: str) -> None:
        """Register (or replace) the public key for a principal DID."""
        if not principal_did or not public_key_pem:
            raise ValueError("principal_did and public_key_pem are required")
        self._keys[principal_did] = public_key_pem

    def is_registered(self, principal_did: str) -> bool:
        """Whether a public key is on file for the principal."""
        return principal_did in self._keys

    @property
    def principal_count(self) -> int:
        """Number of registered principals."""
        return len(self._keys)

    @security_critical
    def authorize(
        self,
        credential: PrincipalCredential | None,
        declaring_agent: str,
        action: str,
        now: float | None = None,
    ) -> PrincipalDecision:
        """Authorize an agent's declared principal for ``action`` (fail-closed)."""
        if credential is None:
            return PrincipalDecision(False, "no principal credential presented")
        if not credential.principal_did or not credential.agent_did:
            return PrincipalDecision(False, "credential missing principal/agent binding")
        public_key = self._keys.get(credential.principal_did)
        if public_key is None:
            return PrincipalDecision(False, f"unknown principal: {credential.principal_did}")
        if credential.issuer and credential.issuer != credential.principal_did:
            return PrincipalDecision(False, "issuer does not match principal")
        if not credential.verify_signature(public_key):
            return PrincipalDecision(False, "invalid principal signature")
        if credential.agent_did != declaring_agent:
            return PrincipalDecision(False, "credential not bound to declaring agent")
        if credential.is_expired(now):
            return PrincipalDecision(False, "credential expired")
        if not credential.allows_action(action):
            return PrincipalDecision(False, f"action not in principal scope: {action}")
        return PrincipalDecision(True, "authorized")
