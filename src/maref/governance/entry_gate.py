"""入口闸 — 身份、委托链与入向消毒的前置校验。

在策略评估之前回答三个问题：

1. 谁在发起（NHI + 人类委托人凭证）；
2. 授权链是否完整且不可剥离（根委托人 + 每跳签名 + 能力单调）；
3. 入向文本是否安全（消毒与注入关键词检测）。

默认关闭：只有显式注入到 ``GovernancePipeline`` 时才会执行。``shadow``
模式只记录不阻断，用于上线前对比误报。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maref.identity.principal_credential import (
    PrincipalCredential,
    PrincipalRegistry,
)
from maref.security.sanitizer import Sanitizer
from maref.security.trust_chain import DelegationChain, ValidationStatus

TEXT_PARAMETER_KEYS = frozenset(
    {"prompt", "content", "query", "message", "text", "input", "instruction"}
)


@dataclass
class EntryDecision:
    """入口闸裁决。``blocking`` 已考虑 shadow 模式。"""

    allowed: bool
    blocking: bool
    rule: str = ""
    reason: str = ""
    root_principal: str = ""
    chain_digest: str = ""
    detections: list[str] = field(default_factory=list)
    sanitized_intent: str = ""
    sanitized_parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "blocking": self.blocking,
            "rule": self.rule,
            "reason": self.reason,
            "root_principal": self.root_principal,
            "chain_digest": self.chain_digest,
            "detections": list(self.detections),
        }


def _credential_from_dict(data: dict[str, Any]) -> PrincipalCredential:
    return PrincipalCredential(
        principal_did=str(data.get("principal_did") or ""),
        agent_did=str(data.get("agent_did") or ""),
        allowed_actions=list(data.get("allowed_actions") or []),
        valid_until=data.get("valid_until"),
        issuer=str(data.get("issuer") or ""),
        signature=str(data.get("signature") or ""),
    )


def _blocked_detection(result: Any) -> list[str]:
    """按实际阻断原因标注，避免把超长输入误记为 SQL 注入。"""
    return ["sql_risk"] if getattr(result, "sql_risk", False) else ["input_length"]


def _chain_digest(chain: DelegationChain) -> str:
    payload = json.dumps(
        chain.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class EntryGate:
    """身份 + 委托链 + 消毒的统一入口闸。"""

    def __init__(
        self,
        principal_registry: PrincipalRegistry | None = None,
        hmac_keys: bytes | str | list[bytes | str] | dict[str, bytes | str] | None = None,
        public_keys: dict[str, str] | None = None,
        sanitizer: Sanitizer | None = None,
        require_identity: bool = True,
        require_delegation: bool = False,
        max_depth: int = 5,
        shadow: bool = False,
    ) -> None:
        self._registry = principal_registry
        self._hmac_keys = hmac_keys or []
        self._public_keys = public_keys or {}
        self._sanitizer = sanitizer or Sanitizer()
        self._require_identity = require_identity
        self._require_delegation = require_delegation
        self._max_depth = max_depth
        self.shadow = shadow

    @classmethod
    def from_env(cls) -> EntryGate:
        """Build a gate from environment; fail-closed on missing configuration."""
        registry_path = os.environ.get("MAREF_PRINCIPAL_REGISTRY", "")
        if not registry_path:
            raise ValueError(
                "MAREF_PRINCIPAL_REGISTRY is required when the entry gate is enabled"
            )
        try:
            raw = json.loads(Path(registry_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"cannot load principal registry: {exc}") from exc
        if not isinstance(raw, dict) or not raw:
            raise ValueError("principal registry must be a non-empty JSON object")

        registry = PrincipalRegistry()
        for principal_did, public_key_pem in raw.items():
            registry.register(principal_did, public_key_pem)

        hmac_key = os.environ.get("MAREF_ENTRY_GATE_HMAC_KEY", "")

        def _flag(name: str) -> bool:
            return os.environ.get(name, "").lower() in {"1", "true", "yes"}

        return cls(
            principal_registry=registry,
            hmac_keys=[hmac_key.encode("utf-8")] if hmac_key else [],
            require_delegation=_flag("MAREF_ENTRY_GATE_REQUIRE_DELEGATION"),
            max_depth=int(os.environ.get("MAREF_ENTRY_GATE_MAX_DEPTH", "5")),
            shadow=_flag("MAREF_ENTRY_GATE_SHADOW"),
        )

    def evaluate(self, request: Any) -> EntryDecision:
        """Evaluate an incoming governance request."""
        root_principal = ""
        chain_digest = ""
        detections: list[str] = []

        def deny(rule: str, reason: str) -> EntryDecision:
            return EntryDecision(
                allowed=False,
                blocking=not self.shadow,
                rule=rule,
                reason=reason,
                root_principal=root_principal,
                chain_digest=chain_digest,
                detections=list(detections),
            )

        # 1. 身份
        if not getattr(request, "agent_id", ""):
            return deny("entry_gate:identity_missing", "agent_id is required")
        if self._require_identity:
            raw_credential = getattr(request, "principal_credential", None)
            if not raw_credential:
                return deny(
                    "entry_gate:identity_missing",
                    "principal credential is required",
                )
            credential = _credential_from_dict(dict(raw_credential))
            declared = getattr(request, "principal_did", "") or ""
            if declared and declared != credential.principal_did:
                return deny(
                    "entry_gate:identity_invalid",
                    "declared principal does not match credential",
                )
            if self._registry is None:
                return deny(
                    "entry_gate:identity_invalid",
                    "principal registry is not configured",
                )
            authority = self._registry.authorize(
                credential,
                request.agent_id,
                getattr(request, "action", ""),
            )
            if not authority.allowed:
                return deny("entry_gate:identity_invalid", authority.reason)
            root_principal = credential.principal_did

        # 2. 委托链
        raw_chain = getattr(request, "delegation_chain", None)
        if not raw_chain:
            if self._require_delegation:
                return deny(
                    "entry_gate:delegation_missing",
                    "delegation chain is required",
                )
        else:
            try:
                chain = DelegationChain.from_dict(dict(raw_chain))
            except (KeyError, TypeError, ValueError) as exc:
                return deny("entry_gate:delegation_malformed", str(exc))

            validation = chain.validate()
            if not validation.is_valid:
                rule = {
                    ValidationStatus.INVALID_MAX_DEPTH: "entry_gate:delegation_depth",
                    ValidationStatus.INVALID_CYCLE: "entry_gate:delegation_cycle",
                    ValidationStatus.INVALID_POLICY: "entry_gate:delegation_policy",
                }.get(validation.status, "entry_gate:delegation_invalid")
                return deny(rule, validation.message)

            if chain.depth > self._max_depth:
                return deny(
                    "entry_gate:delegation_depth",
                    f"chain depth {chain.depth} exceeds gate limit {self._max_depth}",
                )

            if root_principal and chain.root_principal != root_principal:
                return deny(
                    "entry_gate:root_principal",
                    "chain root principal does not match credential",
                )

            if not self._chain_structure_valid(chain):
                return deny(
                    "entry_gate:delegation_continuity",
                    "chain parent links are not continuous",
                )

            if not self._capabilities_monotonic(chain):
                return deny(
                    "entry_gate:capability_escalation",
                    "child capability exceeds parent capability",
                )

            if chain.nodes and chain.nodes[-1].agent_id != request.agent_id:
                return deny(
                    "entry_gate:delegation_tail",
                    "requester is not the last node of the delegation chain",
                )

            signature_error = self._verify_chain_signature(chain)
            if signature_error:
                return deny("entry_gate:delegation_signature", signature_error)

            chain_digest = _chain_digest(chain)

        # 3. 入向消毒
        (
            sanitized_intent,
            sanitized_parameters,
            sanitize_detections,
            sanitize_error,
        ) = self._sanitize(request)
        detections.extend(sanitize_detections)
        if sanitize_error:
            return deny("entry_gate:unsafe_content", sanitize_error)

        return EntryDecision(
            allowed=True,
            blocking=False,
            rule="",
            reason="entry gate passed",
            root_principal=root_principal,
            chain_digest=chain_digest,
            detections=detections,
            sanitized_intent=sanitized_intent,
            sanitized_parameters=sanitized_parameters,
        )

    def _chain_structure_valid(self, chain: DelegationChain) -> bool:
        previous = None
        for node in chain.nodes:
            if previous is None:
                if node.parent_id is not None:
                    return False
            elif node.parent_id != previous.agent_id:
                return False
            previous = node
        return True

    def _capabilities_monotonic(self, chain: DelegationChain) -> bool:
        for parent, child in zip(chain.nodes, chain.nodes[1:], strict=False):
            if child.capability.rank > parent.capability.rank:
                return False
        return True

    def _verify_chain_signature(self, chain: DelegationChain) -> str:
        if any(node.signature_alg == "hmac-sha256" for node in chain.nodes):
            if not self._hmac_keys:
                return "HMAC key is not configured"
            result = chain.validate_hmac(self._hmac_keys)
            return "" if result.is_valid else result.message
        unsigned = [node.agent_id for node in chain.nodes if not node.signature]
        if unsigned:
            # validate_signed 会跳过无签名节点；入口闸要求每跳可验证。
            return f"nodes are not signed: {', '.join(unsigned)}"
        if self._public_keys:
            result = chain.validate_signed(self._public_keys)
            return "" if result.is_valid else result.message
        return "no verification key is configured"

    def _sanitize(
        self, request: Any
    ) -> tuple[str, dict[str, Any], list[str], str]:
        detections: list[str] = []
        sanitized_parameters: dict[str, Any] = {}
        intent = getattr(request, "intent", "") or ""
        sanitized_intent = intent

        if intent:
            result = self._sanitizer.sanitize_input(intent)
            if result.blocked:
                return (
                    intent,
                    {},
                    _blocked_detection(result),
                    result.reason or "input blocked by sanitizer",
                )
            sanitized_intent = result.text
            detections.extend(f"pii:{name}" for name in result.pii_found)

        parameters = getattr(request, "parameters", None)
        if isinstance(parameters, dict):
            sanitized_parameters = dict(parameters)
            for key, value in parameters.items():
                if key not in TEXT_PARAMETER_KEYS or not isinstance(value, str):
                    continue
                result = self._sanitizer.sanitize_input(value)
                if result.blocked:
                    return (
                        sanitized_intent,
                        {},
                        _blocked_detection(result),
                        result.reason or "input blocked by sanitizer",
                    )
                sanitized_parameters[key] = result.text
                detections.extend(f"pii:{name}" for name in result.pii_found)

        return sanitized_intent, sanitized_parameters, detections, ""
