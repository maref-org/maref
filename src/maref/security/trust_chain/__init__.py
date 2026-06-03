from __future__ import annotations

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "capability": self.capability.value,
            "timestamp": self.timestamp.isoformat(),
            "parent_id": self.parent_id,
            "metadata": self.metadata,
        }


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
            "depth": self.depth,
            "max_depth": self.max_depth,
            "nodes": [n.to_dict() for n in self.nodes],
            "created_at": self.created_at.isoformat(),
            "policy_version": self.policy_version,
            "chain_hash": self.get_chain_hash(),
            "metadata": self.metadata,
        }
