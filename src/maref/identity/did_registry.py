from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from maref.governance.state_machine import GovernanceStateMachine

# 撤销事件监听器签名：fn(did_string: str, reason: str, signer: str)
RevocationListener = Callable[[str, str, str], Any]

# W3C DID Core 1.0 context
_DID_CONTEXT = "https://www.w3.org/ns/did/v1"
_ED25519_VERIFICATION_METHOD_TYPE = "Ed25519VerificationKey2018"
_ED25519_AUTHENTICATION_TYPE = "Ed25519SignatureAuthentication2018"


@dataclass(frozen=True)
class AgentDID:
    namespace: str
    agent_short_id: str

    @property
    def did_string(self) -> str:
        return f"did:maref:{self.namespace}:{self.agent_short_id}"

    @classmethod
    def parse(cls, did_string: str) -> AgentDID:
        parts = did_string.split(":")
        if len(parts) != 4 or parts[0] != "did" or parts[1] != "maref":
            raise ValueError(f"Invalid MAREF DID: {did_string}")
        return cls(namespace=parts[2], agent_short_id=parts[3])

    @classmethod
    def generate(cls, namespace: str = "default") -> AgentDID:
        short_id = secrets.token_hex(4)
        return cls(namespace=namespace, agent_short_id=short_id)

    def to_did_document(
        self,
        ed25519_public_key_pem: str = "",
        service_endpoints: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Generate a W3C DID Document (DID Core 1.0) for this MAREF DID.

        Args:
            ed25519_public_key_pem: Optional Ed25519 public key PEM to include
                as a verification method.
            service_endpoints: Optional list of service endpoint dicts, each
                with ``id``, ``type``, ``serviceEndpoint`` keys.

        Returns:
            A dict conforming to the W3C DID Document data model.
        """
        doc: dict[str, Any] = {
            "@context": _DID_CONTEXT,
            "id": self.did_string,
        }
        if ed25519_public_key_pem:
            vm_id = f"{self.did_string}#ed25519-key"
            doc["verificationMethod"] = [
                {
                    "id": vm_id,
                    "type": _ED25519_VERIFICATION_METHOD_TYPE,
                    "controller": self.did_string,
                    "publicKeyPem": ed25519_public_key_pem,
                }
            ]
            doc["authentication"] = [vm_id]
            doc["assertionMethod"] = [vm_id]

        if service_endpoints:
            doc["service"] = service_endpoints

        return doc


@dataclass
class AgentIdentityRecord:
    did: AgentDID
    state_machine: GovernanceStateMachine
    roles: list[str] = field(default_factory=list)
    registered_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    # 版本化生命周期（方案 E）：
    # status 取值 active / revoked / deactivated；revocation_entry 保留撤销历史。
    version: int = 1
    status: str = "active"
    revocation_entry: dict[str, Any] = field(default_factory=dict)

    def ed25519_public_key(self) -> str:
        return self.metadata.get("ed25519_public_key_pem", "")


@dataclass
class DIDResolutionResult:
    """W3C DID Resolution result (DID Resolution v1.0).

    Attributes:
        did_document: The resolved DID Document (or None if not found).
        resolution_metadata: Metadata about the resolution process.
        document_metadata: Metadata about the DID Document itself.
    """

    did_document: dict[str, Any] | None
    resolution_metadata: dict[str, Any]
    document_metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "resolution_metadata": self.resolution_metadata,
            "document_metadata": self.document_metadata,
        }
        if self.did_document is not None:
            result["did_document"] = self.did_document
        return result

    @property
    def resolved(self) -> bool:
        return self.did_document is not None


class DIDRegistry:
    def __init__(self) -> None:
        self._agents: dict[AgentDID, AgentIdentityRecord] = {}
        self._revocation_listeners: list[RevocationListener] = []

    def add_revocation_listener(self, listener: RevocationListener) -> None:
        """订阅 DID 撤销事件（方案 E M3 联动机制）。

        ``listener(did_string, reason, signer)`` 在每次 :meth:`revoke`
        或 :meth:`deactivate` 成功变更状态后同步调用（先注册先通知）。

        Args:
            listener: 接收 (did_string, reason, signer) 的回调。
        """
        if listener not in self._revocation_listeners:
            self._revocation_listeners.append(listener)

    def remove_revocation_listener(self, listener: RevocationListener) -> bool:
        """取消订阅撤销事件；返回是否找到并移除。"""
        if listener in self._revocation_listeners:
            self._revocation_listeners.remove(listener)
            return True
        return False

    def _notify_revocation(
        self, did: AgentDID, reason: str, signer: str
    ) -> None:
        """向所有监听器广播撤销事件；单个监听器异常不影响其余与主流程。"""
        for listener in list(self._revocation_listeners):
            try:
                listener(did.did_string, reason, signer)
            except Exception:
                continue

    def register(
        self,
        did: AgentDID,
        state_machine: GovernanceStateMachine,
        initial_roles: list[str] | None = None,
    ) -> AgentIdentityRecord:
        record = AgentIdentityRecord(
            did=did,
            state_machine=state_machine,
            roles=initial_roles or [],
            metadata={"registered_via": "DIDRegistry"},
        )
        record.registered_at = time.time()
        self._agents[did] = record
        return record

    def resolve(self, did: AgentDID) -> AgentIdentityRecord | None:
        return self._agents.get(did)

    def resolve_did_document(
        self,
        did: AgentDID,
        service_endpoints: list[dict[str, Any]] | None = None,
    ) -> DIDResolutionResult:
        """Resolve a MAREF DID to a W3C DID Document (DID Resolution v1.0).

        Args:
            did: The MAREF DID to resolve.
            service_endpoints: Optional service endpoints for the DID Document.

        Returns:
            A :class:`DIDResolutionResult` with the DID Document and metadata.
        """
        record = self._agents.get(did)
        if record is None:
            return DIDResolutionResult(
                did_document=None,
                resolution_metadata={
                    "error": "notFound",
                    "message": f"DID {did.did_string} not found",
                },
                document_metadata={},
            )

        doc = did.to_did_document(
            ed25519_public_key_pem=record.ed25519_public_key(),
            service_endpoints=service_endpoints,
        )
        document_metadata: dict[str, Any] = {
            "created": record.registered_at,
            "updated": record.registered_at,
            "deactivated": record.status in ("deactivated", "revoked"),
            "versionId": str(record.version),
            # 方案 E：DID 文档增加 version 与 status 字段。
            "version": record.version,
            "status": record.status,
        }
        if record.revocation_entry:
            document_metadata["revocation_entry"] = dict(record.revocation_entry)
        return DIDResolutionResult(
            did_document=doc,
            resolution_metadata={
                "method": "maref",
                "resolved": True,
                "retrieved": time.time(),
            },
            document_metadata=document_metadata,
        )

    def revoke(
        self,
        did: AgentDID,
        reason: str = "unspecified",
        signer: str = "",
    ) -> AgentIdentityRecord | None:
        """版本化撤销一个 DID（方案 E）。

        将状态置为 revoked 并写入 ``revocation_entry``，保留历史记录，
        不删除注册。解析时可通过 ``document_metadata.status`` 判定。
        支持再次调用实现版本递增（deactivated 为不可逆终态）。

        Args:
            did: 待撤销的 DID。
            reason: 撤销原因。
            signer: 撤销签署者标识。

        Returns:
            更新后的记录；若 DID 不存在返回 None。
        """
        record = self._agents.get(did)
        if record is None:
            return None
        # deactivated 是不可逆终态，拒绝再次撤销/改写。
        if record.status == "deactivated":
            return record
        # 幂等：已 revoked 的 DID 重复撤销不再递增版本/重复广播。
        if record.status == "revoked":
            return record
        new_version = record.version + 1
        record.version = new_version
        record.status = "revoked"
        record.revocation_entry = {
            "did": did.did_string,
            "version": new_version,
            "revoked_at": time.time(),
            "reason": reason,
            "signer": signer,
        }
        self._notify_revocation(did, reason, signer)
        return record

    def deactivate(self, did: AgentDID, reason: str = "", signer: str = "") -> AgentIdentityRecord | None:
        """将 DID 置为不可逆的 deactivated 终态（方案 E）。"""
        record = self._agents.get(did)
        if record is None:
            return None
        if record.status == "deactivated":
            return record
        record.version += 1
        record.status = "deactivated"
        record.revocation_entry = {
            "did": did.did_string,
            "version": record.version,
            "revoked_at": time.time(),
            "reason": reason or "deactivated",
            "signer": signer,
        }
        self._notify_revocation(did, reason or "deactivated", signer)
        return record

    def is_active(self, did: AgentDID) -> bool:
        """DID 是否处于 active 状态。"""
        record = self._agents.get(did)
        return record is not None and record.status == "active"

    def unregister(self, did: AgentDID) -> AgentIdentityRecord | None:
        """Remove a DID record from the registry.

        Args:
            did: The MAREF DID to unregister.

        Returns:
            The removed record if found, None otherwise.
        """
        return self._agents.pop(did, None)

    def list_all(self) -> list[AgentIdentityRecord]:
        return list(self._agents.values())

    def agent_count(self) -> int:
        return len(self._agents)
