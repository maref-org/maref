from __future__ import annotations

import hashlib
import hmac as _hmac
import json
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ValidationStatus(str, Enum):
    VALID = "valid"
    INVALID_MAX_DEPTH = "invalid_max_depth"
    INVALID_CYCLE = "invalid_cycle"
    INVALID_POLICY = "invalid_policy"
    INVALID_SIGNATURE = "invalid_signature"


class DelegationCapability(str, Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    DELEGATE = "delegate"
    ADMIN = "admin"

    @property
    def rank(self) -> int:
        """Capability hierarchy rank (higher = more powerful)."""
        return {
            DelegationCapability.READ: 1,
            DelegationCapability.WRITE: 2,
            DelegationCapability.EXECUTE: 3,
            DelegationCapability.DELEGATE: 4,
            DelegationCapability.ADMIN: 5,
        }[self]


@dataclass
class ChainNode:
    agent_id: str
    capability: DelegationCapability
    timestamp: datetime
    parent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    signature: str = ""
    signer_id: str = ""
    signature_alg: str = "ed25519"
    key_id: str = ""
    nonce: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "capability": self.capability.value,
            "timestamp": self.timestamp.isoformat(),
            "parent_id": self.parent_id,
            "metadata": self.metadata,
            "signature": self.signature,
            "signer_id": self.signer_id,
            "signature_alg": self.signature_alg,
            "key_id": self.key_id,
            "nonce": self.nonce,
        }


def hmac_payload(
    node: ChainNode, chain_id: str, root_principal: str, hop_index: int
) -> bytes:
    """Canonical bytes covered by a per-hop HMAC signature."""
    data = {
        "chain_id": chain_id,
        "root_principal": root_principal,
        "hop_index": hop_index,
        "agent_id": node.agent_id,
        "capability": node.capability.value,
        "parent_id": node.parent_id or "",
        "timestamp": node.timestamp.isoformat(),
        "nonce": node.nonce,
    }
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


@dataclass
class ValidationResult:
    status: ValidationStatus
    message: str
    depth: int
    max_depth: int

    @property
    def is_valid(self) -> bool:
        return self.status == ValidationStatus.VALID


@dataclass
class DelegationChain:
    chain_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    root_agent_id: str = ""
    depth: int = 0
    max_depth: int = 5
    nodes: list[ChainNode] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    policy_version: str = "1.0"
    root_principal: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls, root_agent_id: str, max_depth: int = 5, policy_version: str = "1.0"
    ) -> DelegationChain:
        root_node = ChainNode(
            agent_id=root_agent_id,
            capability=DelegationCapability.ADMIN,
            timestamp=datetime.now(timezone.utc),
            parent_id=None,
        )
        return cls(
            root_agent_id=root_agent_id,
            max_depth=max_depth,
            nodes=[root_node],
            depth=1,
            policy_version=policy_version,
        )

    def add_delegation(
        self,
        parent_agent_id: str,
        child_agent_id: str,
        capability: DelegationCapability,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        if self.depth > self.max_depth:
            return False

        last_node = self.nodes[-1] if self.nodes else None
        if last_node is None or last_node.agent_id != parent_agent_id:
            return False

        if not self._can_delegate(parent_agent_id, capability):
            return False

        new_node = ChainNode(
            agent_id=child_agent_id,
            capability=capability,
            timestamp=datetime.now(timezone.utc),
            parent_id=parent_agent_id,
            metadata=metadata or {},
        )
        self.nodes.append(new_node)
        self.depth += 1
        return True

    def _can_delegate(self, agent_id: str, capability: DelegationCapability) -> bool:
        """
        Enforce capability hierarchy: ADMIN > DELEGATE > EXECUTE > WRITE > READ.
        Only nodes with delegation rights (DELEGATE or ADMIN) can delegate,
        and they can only grant capabilities with rank <= their own rank.
        """
        for node in reversed(self.nodes):
            if node.agent_id == agent_id:
                if node.capability.rank < DelegationCapability.DELEGATE.rank:
                    return False
                return capability.rank <= node.capability.rank
        return False

    @classmethod
    def create_signed(
        cls,
        root_agent_id: str,
        root_signing_key: Any,
        max_depth: int = 5,
        policy_version: str = "1.0",
    ) -> DelegationChain:
        """Create a chain whose root node carries a signature from the root agent."""
        chain = cls.create(root_agent_id, max_depth=max_depth, policy_version=policy_version)
        chain._sign_node(chain.nodes[0], root_agent_id, root_signing_key)
        return chain

    def add_delegation_signed(
        self,
        parent_agent_id: str,
        child_agent_id: str,
        capability: DelegationCapability,
        signing_key: Any,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Add a delegation node signed by the delegating (parent) agent."""
        if not self.add_delegation(
            parent_agent_id,
            child_agent_id,
            capability,
            metadata=metadata,
        ):
            return False
        self._sign_node(self.nodes[-1], parent_agent_id, signing_key)
        return True

    @classmethod
    def create_hmac(
        cls,
        root_agent_id: str,
        hmac_key: bytes | str,
        key_id: str = "",
        root_principal: str = "",
        max_depth: int = 5,
        policy_version: str = "1.0",
    ) -> DelegationChain:
        """Create a chain whose nodes are HMAC-signed with a deployment key."""
        chain = cls.create(
            root_agent_id,
            max_depth=max_depth,
            policy_version=policy_version,
        )
        chain.root_principal = root_principal
        chain.sign_hmac(hmac_key, key_id=key_id)
        return chain

    def sign_hmac(self, hmac_key: bytes | str, key_id: str = "") -> None:
        """Sign every node with HMAC-SHA256 (idempotent)."""
        key = hmac_key.encode("utf-8") if isinstance(hmac_key, str) else hmac_key
        for index, node in enumerate(self.nodes):
            node.nonce = node.nonce or secrets.token_hex(8)
            node.signature_alg = "hmac-sha256"
            node.key_id = key_id
            node.signature = _hmac.new(
                key,
                hmac_payload(node, self.chain_id, self.root_principal, index),
                hashlib.sha256,
            ).hexdigest()

    def add_delegation_hmac(
        self,
        parent_agent_id: str,
        child_agent_id: str,
        capability: DelegationCapability,
        hmac_key: bytes | str,
        key_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Add a delegation and HMAC-sign the new node.

        The parent node must already be signed by :meth:`sign_hmac` or
        :meth:`create_hmac`; otherwise verification fails (fail-closed).
        """
        if not self.add_delegation(
            parent_agent_id,
            child_agent_id,
            capability,
            metadata=metadata,
        ):
            return False
        node = self.nodes[-1]
        node.nonce = secrets.token_hex(8)
        key = hmac_key.encode("utf-8") if isinstance(hmac_key, str) else hmac_key
        node.signature_alg = "hmac-sha256"
        node.key_id = key_id
        node.signature = _hmac.new(
            key,
            hmac_payload(node, self.chain_id, self.root_principal, len(self.nodes) - 1),
            hashlib.sha256,
        ).hexdigest()
        return True

    def validate_hmac(
        self, keys: bytes | str | list[bytes | str] | dict[str, bytes | str]
    ) -> ValidationResult:
        """Verify every node's HMAC signature against the supplied key(s)."""
        if isinstance(keys, dict):
            candidates = [
                (key_id, key.encode("utf-8") if isinstance(key, str) else key)
                for key_id, key in keys.items()
            ]
        elif isinstance(keys, (bytes, str)):
            candidates = [("", keys.encode("utf-8") if isinstance(keys, str) else keys)]
        else:
            candidates = [
                ("", key.encode("utf-8") if isinstance(key, str) else key)
                for key in keys
            ]

        for index, node in enumerate(self.nodes):
            if node.signature_alg != "hmac-sha256" or not node.signature:
                return ValidationResult(
                    status=ValidationStatus.INVALID_SIGNATURE,
                    message=f"Node {node.agent_id} is not HMAC-signed",
                    depth=self.depth,
                    max_depth=self.max_depth,
                )
            payload = hmac_payload(node, self.chain_id, self.root_principal, index)
            matched = False
            for key_id, key in candidates:
                if node.key_id and key_id and node.key_id != key_id:
                    continue
                expected = _hmac.new(key, payload, hashlib.sha256).hexdigest()
                if _hmac.compare_digest(expected, node.signature):
                    matched = True
                    break
            if not matched:
                return ValidationResult(
                    status=ValidationStatus.INVALID_SIGNATURE,
                    message=f"HMAC mismatch for node {node.agent_id}",
                    depth=self.depth,
                    max_depth=self.max_depth,
                )
        return ValidationResult(
            status=ValidationStatus.VALID,
            message="Chain HMAC signatures verified",
            depth=self.depth,
            max_depth=self.max_depth,
        )

    def validate_signed(self, public_keys: dict[str, str]) -> ValidationResult:
        """Verify every signed node against the provided public keys.

        Unsigned nodes are skipped for backwards compatibility; a signed node
        whose signer is unknown or whose signature fails verification yields
        :attr:`ValidationStatus.INVALID_SIGNATURE`.
        """
        for node in self.nodes:
            if not node.signature:
                continue
            if node.signer_id not in public_keys:
                return ValidationResult(
                    status=ValidationStatus.INVALID_SIGNATURE,
                    message=f"Unknown signer {node.signer_id} for node {node.agent_id}",
                    depth=self.depth,
                    max_depth=self.max_depth,
                )
            if not self._verify_node(node, public_keys[node.signer_id]):
                return ValidationResult(
                    status=ValidationStatus.INVALID_SIGNATURE,
                    message=f"Signature mismatch for node {node.agent_id}",
                    depth=self.depth,
                    max_depth=self.max_depth,
                )
        return ValidationResult(
            status=ValidationStatus.VALID,
            message="Chain signatures verified",
            depth=self.depth,
            max_depth=self.max_depth,
        )

    def _node_payload(self, node: ChainNode) -> bytes:
        payload = (
            f"{node.signer_id}|{node.parent_id or ''}|{node.agent_id}|"
            f"{node.capability.value}|{node.timestamp.isoformat()}|{self.chain_id}"
        )
        return payload.encode("utf-8")

    def _sign_node(self, node: ChainNode, signer_id: str, signing_key: Any) -> None:
        node.signer_id = signer_id
        node.signature = signing_key.sign_report(self._node_payload(node))

    def _verify_node(self, node: ChainNode, public_key_pem: str) -> bool:
        from maref.signing.signing_key import ReportSigningKey

        return ReportSigningKey.verify_signature(
            public_key_pem, node.signature, self._node_payload(node)
        )

    def validate(self) -> ValidationResult:
        if self.depth > self.max_depth:
            return ValidationResult(
                status=ValidationStatus.INVALID_MAX_DEPTH,
                message=f"Chain depth {self.depth} exceeds max {self.max_depth}",
                depth=self.depth,
                max_depth=self.max_depth,
            )

        if self._has_cycle():
            return ValidationResult(
                status=ValidationStatus.INVALID_CYCLE,
                message="Circular delegation detected",
                depth=self.depth,
                max_depth=self.max_depth,
            )

        return ValidationResult(
            status=ValidationStatus.VALID,
            message="Chain is valid",
            depth=self.depth,
            max_depth=self.max_depth,
        )

    def _has_cycle(self) -> bool:
        visited: set[str] = set()
        for node in self.nodes:
            if node.agent_id in visited:
                return True
            visited.add(node.agent_id)
        return False

    def get_chain_hash(self) -> str:
        import hashlib

        content = "".join(n.agent_id + n.capability.value for n in self.nodes)
        return hashlib.sha256(content.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "root_agent_id": self.root_agent_id,
            "root_principal": self.root_principal,
            "depth": self.depth,
            "max_depth": self.max_depth,
            "nodes": [n.to_dict() for n in self.nodes],
            "created_at": self.created_at.isoformat(),
            "policy_version": self.policy_version,
            "chain_hash": self.get_chain_hash(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DelegationChain:
        """Rebuild a chain from :meth:`to_dict` output."""
        nodes = [
            ChainNode(
                agent_id=item["agent_id"],
                capability=DelegationCapability(item["capability"]),
                timestamp=datetime.fromisoformat(item["timestamp"]),
                parent_id=item.get("parent_id"),
                metadata=dict(item.get("metadata") or {}),
                signature=item.get("signature", ""),
                signer_id=item.get("signer_id", ""),
                signature_alg=item.get("signature_alg", "ed25519"),
                key_id=item.get("key_id", ""),
                nonce=item.get("nonce", ""),
            )
            for item in data.get("nodes", [])
        ]
        created_at = data.get("created_at")
        return cls(
            chain_id=data.get("chain_id") or str(uuid.uuid4()),
            root_agent_id=data.get("root_agent_id", ""),
            # 深度由节点数推导：声明的 depth 不在签名载荷内，不可信。
            depth=len(nodes),
            max_depth=int(data.get("max_depth", 5)),
            nodes=nodes,
            created_at=(
                datetime.fromisoformat(created_at)
                if created_at
                else datetime.now(timezone.utc)
            ),
            policy_version=data.get("policy_version", "1.0"),
            root_principal=data.get("root_principal", ""),
            metadata=dict(data.get("metadata") or {}),
        )
