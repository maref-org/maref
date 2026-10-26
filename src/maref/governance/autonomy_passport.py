"""自治护照（P1-T1）——绑定人类委托人的可离线验证行动授权。

护照复用 :class:`VerifiableGovernanceCredential` 的 Ed25519 签发/验签与
``GovernanceCredentialStore`` 的吊销机制，只额外定义护照语义：

- 工具白名单（``allowed_tools``，支持 glob）；
- 任务范围（``task_scope``，支持 glob）；
- 强制绑定 ``human_principal`` 与 ``delegation_root``，任一缺失拒绝签发。

离线验证只需签发方公钥与吊销列表。放行时可传入 audit logger，
每次放行都会写入一条含 ``passport_id`` 的审计事件。
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any

from maref.governance.verifiable_governance_credential import (
    VerifiableGovernanceCredential,
)
from maref.signing.signing_key import ReportSigningKey

PASSPORT_KIND = "autonomy_passport"
PASSPORT_EVENT = "passport_allowance"

# 拒绝原因（稳定标识，供审计与测试断言）
REASON_OK = "ok"
REASON_SIGNATURE = "signature_invalid"
REASON_NOT_PASSPORT = "not_a_passport"
REASON_EXPIRED = "expired"
REASON_REVOKED = "revoked"
REASON_TOOL = "tool_not_allowed"
REASON_SCOPE = "action_out_of_scope"


@dataclass(frozen=True)
class PassportDecision:
    """一次护照授权判定。"""

    allowed: bool
    reason: str
    passport_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "passport_id": self.passport_id,
        }


class AutonomyPassport(VerifiableGovernanceCredential):
    """绑定人类委托人与委托根的自治护照凭证。"""

    @classmethod
    def issue_passport(
        cls,
        *,
        agent_did: str,
        human_principal: str,
        delegation_root: str,
        allowed_tools: Iterable[str],
        task_scope: Iterable[str],
        signing_key: ReportSigningKey,
        issuer_did: str = "",
        ttl_seconds: float = 86400,
        source_event: str = "",
    ) -> AutonomyPassport:
        """签发自自治护照；缺少人类委托人或委托根时拒绝签发。"""
        if not agent_did.strip():
            raise ValueError("agent_did is required")
        if not human_principal.strip():
            raise ValueError("human_principal is required")
        if not delegation_root.strip():
            raise ValueError("delegation_root is required")

        now = time.time()
        passport = cls(
            credential_id=f"passport-{secrets.token_hex(8)}",
            subject_did=agent_did,
            issuer_did=issuer_did or human_principal,
            scope=[],
            merkle_proof={},
            valid_from=now,
            expires_at=now + ttl_seconds,
            source_event=source_event,
            extensions={
                "kind": PASSPORT_KIND,
                "human_principal": human_principal,
                "delegation_root": delegation_root,
                "allowed_tools": sorted(
                    {str(tool) for tool in allowed_tools if str(tool).strip()}
                ),
                "task_scope": sorted(
                    {str(item) for item in task_scope if str(item).strip()}
                ),
            },
        )
        passport.signature = signing_key.sign_report(passport._signing_payload())
        passport.signer_public_key_pem = signing_key.public_key_pem
        return passport

    # -- 护照语义 --

    @property
    def passport_id(self) -> str:
        return self.credential_id

    @property
    def human_principal(self) -> str:
        return str(self.extensions.get("human_principal", ""))

    @property
    def delegation_root(self) -> str:
        return str(self.extensions.get("delegation_root", ""))

    @property
    def allowed_tools(self) -> list[str]:
        return [str(item) for item in self.extensions.get("allowed_tools", [])]

    @property
    def task_scope(self) -> list[str]:
        return [str(item) for item in self.extensions.get("task_scope", [])]

    @property
    def is_passport(self) -> bool:
        return self.extensions.get("kind") == PASSPORT_KIND

    def is_tool_allowed(self, tool: str) -> bool:
        return any(fnmatchcase(tool, pattern) for pattern in self.allowed_tools)

    def is_action_in_scope(self, action: str) -> bool:
        return any(fnmatchcase(action, pattern) for pattern in self.task_scope)

    # -- 离线验证与授权 --

    def verify_offline(
        self,
        public_key_pem: str,
        *,
        revoked: Mapping[str, Any] | Iterable[str] = (),
        now: float | None = None,
    ) -> dict[str, Any]:
        """仅凭公钥与吊销列表离线验证护照。"""
        current = time.time() if now is None else now
        signature_valid = bool(
            public_key_pem
            and self.signature
            and ReportSigningKey.verify_signature(
                public_key_pem, self.signature, self._signing_payload()
            )
        )
        expired = self.is_expired(current)
        revoked_flag = self.passport_id in revoked
        bound = bool(self.is_passport and self.human_principal and self.delegation_root)

        if not signature_valid:
            reason = REASON_SIGNATURE
        elif not bound:
            reason = REASON_NOT_PASSPORT
        elif expired:
            reason = REASON_EXPIRED
        elif revoked_flag:
            reason = REASON_REVOKED
        else:
            reason = REASON_OK
        return {
            "valid": reason == REASON_OK,
            "reason": reason,
            "signature_valid": signature_valid,
            "bound": bound,
            "expired": expired,
            "revoked": revoked_flag,
        }

    def authorize(
        self,
        tool: str,
        action: str,
        *,
        public_key_pem: str = "",
        revoked: Mapping[str, Any] | Iterable[str] = (),
        now: float | None = None,
        audit: Any | None = None,
    ) -> PassportDecision:
        """授权一次工具调用；白名单/范围/有效期/吊销任一不满足即拒绝。

        放行且传入 ``audit`` 时写入 ``passport_allowance`` 事件，
        元数据包含 ``passport_id``。
        """
        # 回退到护照自带公钥只保证内容完整，不构成独立信任锚；
        # 离线核验方应显式传入签发方公钥。
        verification = self.verify_offline(
            public_key_pem or self.signer_public_key_pem,
            revoked=revoked,
            now=now,
        )
        if not verification["valid"]:
            return PassportDecision(False, str(verification["reason"]), self.passport_id)
        if not self.is_tool_allowed(tool):
            return PassportDecision(False, REASON_TOOL, self.passport_id)
        if not self.is_action_in_scope(action):
            return PassportDecision(False, REASON_SCOPE, self.passport_id)

        if audit is not None:
            audit.log(
                event_type=PASSPORT_EVENT,
                actor=self.subject_did,
                action=action,
                details=f"passport allow: tool={tool}",
                metadata={
                    "passport_id": self.passport_id,
                    "tool": tool,
                    "action": action,
                    "human_principal": self.human_principal,
                    "delegation_root": self.delegation_root,
                },
            )
        return PassportDecision(True, REASON_OK, self.passport_id)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutonomyPassport:
        """复用基类解析逻辑，保留护照子类型。"""
        return cls(**vars(VerifiableGovernanceCredential.from_dict(data)))


__all__ = [
    "PASSPORT_EVENT",
    "PASSPORT_KIND",
    "REASON_EXPIRED",
    "REASON_NOT_PASSPORT",
    "REASON_OK",
    "REASON_REVOKED",
    "REASON_SCOPE",
    "REASON_SIGNATURE",
    "REASON_TOOL",
    "AutonomyPassport",
    "PassportDecision",
]
