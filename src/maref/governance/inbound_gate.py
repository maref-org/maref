"""入向边界 — 外部智能体请求进入联邦分发前的强制校验。

按顺序回答四个问题：

1. 请求是否由受信 peer 签名，且未过期、未被重放；
2. 携带的自治护照是否由受信签发方签发、未过期/吊销；
3. 护照是否允许该工具与动作，且主体与请求方一致；
4. 委托链是否通过入口闸，并与护照的 ``delegation_root`` 绑定。

默认不改变网关行为：只有显式注入 ``InboundGate`` 的
``FederationGateway`` 才会执行。
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from maref.federation.federation_auth import FederationRequestVerifier
from maref.governance.autonomy_passport import AutonomyPassport
from maref.governance.entry_gate import EntryGate

INBOUND_EVENT = "federation_inbound"


@dataclass(frozen=True)
class InboundRequest:
    """外部智能体入向请求的治理信封。"""

    source_agent_did: str
    action: str
    tool: str
    method: str
    path: str
    body: bytes
    auth_header: str = ""
    body_hash_header: str = ""
    nonce: str = ""
    passport: dict[str, Any] | None = None
    delegation_chain: dict[str, Any] | None = None
    principal_did: str = ""
    principal_credential: dict[str, Any] | None = None
    intent: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InboundDecision:
    """入向闸裁决。"""

    allowed: bool
    rule: str = ""
    reason: str = ""
    source_agent_did: str = ""
    passport_id: str = ""
    chain_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "rule": self.rule,
            "reason": self.reason,
            "source_agent_did": self.source_agent_did,
            "passport_id": self.passport_id,
            "chain_digest": self.chain_digest,
        }


class InboundGate:
    """认证 + 护照 + 委托链的入向边界。"""

    def __init__(
        self,
        verifier: FederationRequestVerifier,
        passport_public_keys: dict[str, str] | None = None,
        *,
        revoked: Mapping[str, Any] | Iterable[str] = (),
        entry_gate: EntryGate | None = None,
        hmac_keys: bytes | str | list[bytes | str] | dict[str, bytes | str] | None = None,
        public_keys: dict[str, str] | None = None,
        max_depth: int = 5,
        audit: Any | None = None,
    ) -> None:
        self._verifier = verifier
        self._passport_keys = dict(passport_public_keys or {})
        self._revoked = revoked
        self._entry_gate = entry_gate or EntryGate(
            require_identity=False,
            hmac_keys=hmac_keys or [],
            public_keys=public_keys or {},
            max_depth=max_depth,
        )
        self._audit = audit

    def evaluate(self, request: InboundRequest) -> InboundDecision:
        """允许则返回 ``allowed=True``；任何一步不满足都 fail-closed。"""
        source = request.source_agent_did.strip()
        chain_digest = ""
        passport_id = ""

        def finalize(
            allowed: bool,
            rule: str = "",
            reason: str = "",
            *,
            current_digest: str = "",
            current_passport: str = "",
        ) -> InboundDecision:
            decision = InboundDecision(
                allowed=allowed,
                rule=rule,
                reason=reason,
                source_agent_did=source,
                passport_id=current_passport,
                chain_digest=current_digest,
            )
            self._record(request, decision)
            return decision

        if not source:
            return finalize(False, "inbound_gate:source_missing", "source_agent_did is required")
        if not request.nonce:
            return finalize(False, "inbound_gate:nonce_missing", "nonce is required")
        if not self._verifier.verify(
            method=request.method,
            path=request.path,
            body_bytes=request.body,
            auth_header=request.auth_header or None,
            body_hash_header=request.body_hash_header or None,
            nonce=request.nonce,
        ):
            return finalize(
                False,
                "inbound_gate:unauthenticated",
                "request signature is missing, invalid, expired or replayed",
            )

        if request.passport is None:
            return finalize(False, "inbound_gate:passport_missing", "passport is required")
        try:
            passport = AutonomyPassport.from_dict(dict(request.passport))
        except (KeyError, TypeError, ValueError) as exc:
            return finalize(False, "inbound_gate:passport_malformed", str(exc))
        passport_id = passport.passport_id

        public_key_pem = self._passport_keys.get(passport.issuer_did, "")
        if not public_key_pem:
            return finalize(
                False,
                "inbound_gate:passport_untrusted_issuer",
                f"issuer {passport.issuer_did!r} is not trusted",
                current_passport=passport_id,
            )
        verification = passport.verify_offline(
            public_key_pem, revoked=self._revoked
        )
        if not verification["valid"]:
            return finalize(
                False,
                f"inbound_gate:passport_{verification['reason']}",
                f"passport invalid: {verification['reason']}",
                current_passport=passport_id,
            )
        if passport.subject_did != source:
            return finalize(
                False,
                "inbound_gate:passport_subject_mismatch",
                "passport subject does not match the requesting agent",
                current_passport=passport_id,
            )
        if not passport.is_tool_allowed(request.tool):
            return finalize(
                False,
                "inbound_gate:passport_tool_not_allowed",
                f"tool {request.tool!r} is not allowed by the passport",
                current_passport=passport_id,
            )
        if not passport.is_action_in_scope(request.action):
            return finalize(
                False,
                "inbound_gate:passport_action_out_of_scope",
                f"action {request.action!r} is out of the passport task scope",
                current_passport=passport_id,
            )

        if not request.delegation_chain:
            return finalize(
                False,
                "inbound_gate:delegation_missing",
                "delegation chain is required",
                current_passport=passport_id,
            )
        entry = self._entry_gate.evaluate(
            SimpleNamespace(
                agent_id=source,
                action=request.action,
                principal_did=request.principal_did,
                principal_credential=request.principal_credential,
                delegation_chain=request.delegation_chain,
                intent=request.intent,
                parameters=request.parameters,
            )
        )
        chain_digest = entry.chain_digest
        if not entry.allowed:
            return finalize(
                False,
                "inbound_gate:delegation_denied",
                entry.reason,
                current_digest=chain_digest,
                current_passport=passport_id,
            )
        chain_root = str(dict(request.delegation_chain).get("root_principal", ""))
        if chain_root != passport.delegation_root:
            return finalize(
                False,
                "inbound_gate:delegation_root_mismatch",
                "chain root principal does not match the passport delegation root",
                current_digest=chain_digest,
                current_passport=passport_id,
            )

        return finalize(
            True,
            reason="inbound gate passed",
            current_digest=chain_digest,
            current_passport=passport_id,
        )

    def _record(self, request: InboundRequest, decision: InboundDecision) -> None:
        if self._audit is None:
            return
        self._audit.log(
            event_type=INBOUND_EVENT,
            actor=decision.source_agent_did or "unknown",
            action=request.action,
            details=(
                f"inbound {'allowed' if decision.allowed else 'denied'}: "
                f"{decision.rule or 'ok'}"
            ),
            metadata={
                "source_agent_did": decision.source_agent_did,
                "passport_id": decision.passport_id,
                "chain_digest": decision.chain_digest,
                "tool": request.tool,
                "action": request.action,
                "nonce": request.nonce,
                "decision": decision.allowed,
                "rule": decision.rule,
                "reason": decision.reason,
                "recorded_at": time.time(),
            },
        )


__all__ = [
    "INBOUND_EVENT",
    "InboundDecision",
    "InboundGate",
    "InboundRequest",
]
