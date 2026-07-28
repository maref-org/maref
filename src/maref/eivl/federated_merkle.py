"""Federated Merkle Root Aggregation.

Aggregates Merkle roots from multiple organizations into a single
federated Merkle tree, enabling cross-organization audit verification
without a central authority.

The federated tree is built from per-organization root hashes::

    org1_root, org2_root, org3_root  -->  federated_root

Each organization can prove its root is included in the federated
root via a :class:`FederatedProof`, verifiable offline by any third
party with just the federated root hash.

Usage::

    aggregator = FederatedMerkleAggregator()
    aggregator.submit_root("org-1", org1_merkle.get_root_hash())
    aggregator.submit_root("org-2", org2_merkle.get_root_hash())

    # Any third party can verify org-1's inclusion offline:
    proof = aggregator.generate_proof("org-1")
    assert proof.verify()  # Only needs the federated root
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class OrgRootEntry:
    """An organization's Merkle root entry in the federated tree.

    Attributes:
        org_id: Organization identifier.
        root_hash: The organization's local Merkle root hash.
        timestamp: When this root was submitted/updated.
        tree_size: Number of evidence leaves in the org's local tree.
        metadata: Optional metadata (e.g. org name, region).
    """

    org_id: str
    root_hash: str
    timestamp: float
    tree_size: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FederatedProof:
    """Proof that an organization's root is included in the federated root.

    This proof is verifiable offline -- the verifier only needs the
    ``federated_root_hash`` and does not need to contact the federation
    server or any other organization.

    Attributes:
        org_id: The organization being proven.
        org_root_hash: The org's local Merkle root hash.
        proof_path: List of (sibling_hash, direction) pairs from leaf to root.
        federated_root_hash: The aggregated federated root hash.
        org_count: Total number of organizations in the federated tree.
        timestamp: When the federated tree was last aggregated.
    """

    org_id: str
    org_root_hash: str
    proof_path: list[tuple[str, str]]
    federated_root_hash: str
    org_count: int
    timestamp: float

    def verify(self) -> bool:
        """Verify this proof offline.

        Recomputes the Merkle path from the org root to the federated
        root and checks equality. No network access required.
        """
        current_hash = self.org_root_hash
        for sibling_hash, direction in self.proof_path:
            if direction == "left":
                current_hash = FederatedMerkleAggregator._hash_pair(
                    sibling_hash, current_hash
                )
            else:
                current_hash = FederatedMerkleAggregator._hash_pair(
                    current_hash, sibling_hash
                )
        return current_hash == self.federated_root_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "org_id": self.org_id,
            "org_root_hash": self.org_root_hash,
            "proof_path": self.proof_path,
            "federated_root_hash": self.federated_root_hash,
            "org_count": self.org_count,
            "timestamp": self.timestamp,
            "ed25519_signature": getattr(self, "_signature", None),
            "signer_fingerprint": getattr(self, "_signer_fingerprint", None),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FederatedProof:
        proof = cls(
            org_id=data["org_id"],
            org_root_hash=data["org_root_hash"],
            proof_path=[(s, d) for s, d in data["proof_path"]],
            federated_root_hash=data["federated_root_hash"],
            org_count=data["org_count"],
            timestamp=data["timestamp"],
        )
        if data.get("ed25519_signature"):
            proof._signature = data["ed25519_signature"]
        if data.get("signer_fingerprint"):
            proof._signer_fingerprint = data["signer_fingerprint"]
        return proof

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, data: str) -> FederatedProof:
        return cls.from_dict(json.loads(data))

    def to_file(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json())

    @classmethod
    def from_file(cls, path: str | Path) -> FederatedProof:
        return cls.from_json(Path(path).read_text())

    def sign(self, keypair: Any) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        if not isinstance(keypair, Ed25519KeyPair):
            raise TypeError("keypair must be an Ed25519KeyPair instance")
        payload = self._signing_payload()
        sig = keypair.sign(payload.encode())
        self._signature = sig.hex() if isinstance(sig, bytes) else sig
        self._signer_fingerprint = keypair.fingerprint

    def verify_signature(self, public_key_pem: str) -> bool:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        sig = getattr(self, "_signature", None)
        if not sig:
            return False
        payload = self._signing_payload()
        return Ed25519KeyPair.verify(
            public_key_pem=public_key_pem,
            message=payload.encode(),
            signature=bytes.fromhex(sig) if isinstance(sig, str) else sig,
        )

    def _signing_payload(self) -> str:
        return json.dumps(
            {
                "org_id": self.org_id,
                "org_root_hash": self.org_root_hash,
                "proof_path": self.proof_path,
                "federated_root_hash": self.federated_root_hash,
                "org_count": self.org_count,
                "timestamp": self.timestamp,
            },
            sort_keys=True,
            ensure_ascii=False,
        )


class FederatedMerkleAggregator:
    """Aggregates Merkle roots from multiple organizations.

    Builds a federated Merkle tree from per-org root hashes. Each
    organization submits its local Merkle root; the aggregator
    constructs a higher-level tree whose leaves are the org roots.

    The federated root enables:
    - **Cross-org verification**: Any org can prove its audit trail
      is part of the global federated state.
    - **Offline verification**: A third party verifies inclusion with
      just the federated root hash -- no live server needed.
    - **Tamper detection**: If any org's root changes, the federated
      root changes, making tampering globally visible.
    """

    def __init__(self) -> None:
        self._entries: list[OrgRootEntry] = []
        self._entry_index: dict[str, int] = {}
        self._federated_root: str | None = None
        self._tree_levels: list[list[str]] = []
        self._last_aggregated: float = 0.0

    @staticmethod
    def _hash_pair(left: str, right: str) -> str:
        """Hash two child hashes into a parent hash."""
        combined = left + right
        return hashlib.sha256(combined.encode()).hexdigest()

    def submit_root(
        self,
        org_id: str,
        root_hash: str,
        tree_size: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Submit or update an organization's Merkle root.

        If the org has already submitted a root, it is updated in place
        and the federated tree is rebuilt.

        Args:
            org_id: Organization identifier.
            root_hash: The org's local Merkle root hash.
            tree_size: Number of evidence leaves in the org's local tree.
            metadata: Optional metadata.
        """
        entry = OrgRootEntry(
            org_id=org_id,
            root_hash=root_hash,
            timestamp=time.time(),
            tree_size=tree_size,
            metadata=metadata or {},
        )
        if org_id in self._entry_index:
            idx = self._entry_index[org_id]
            self._entries[idx] = entry
        else:
            self._entry_index[org_id] = len(self._entries)
            self._entries.append(entry)
        self._rebuild()

    def _rebuild(self) -> None:
        """Rebuild the federated Merkle tree from submitted roots."""
        if not self._entries:
            self._federated_root = None
            self._tree_levels = []
            return

        leaves = [e.root_hash for e in self._entries]
        self._tree_levels = [leaves]
        current = leaves

        while len(current) > 1:
            next_level: list[str] = []
            i = 0
            while i < len(current):
                left = current[i]
                if i + 1 < len(current):
                    right = current[i + 1]
                    next_level.append(self._hash_pair(left, right))
                else:
                    next_level.append(left)
                i += 2
            self._tree_levels.append(next_level)
            current = next_level

        self._federated_root = current[0]
        self._last_aggregated = time.time()

    def get_federated_root(self) -> str | None:
        """Return the current federated root hash, or None if empty."""
        return self._federated_root

    def generate_proof(self, org_id: str) -> FederatedProof | None:
        """Generate an inclusion proof for an organization.

        The proof can be verified offline by anyone who knows the
        federated root hash.

        Returns:
            A :class:`FederatedProof`, or None if the org is not
            registered or no federated root exists.
        """
        if org_id not in self._entry_index:
            return None
        if self._federated_root is None or not self._tree_levels:
            return None

        idx = self._entry_index[org_id]
        org_root = self._entries[idx].root_hash
        proof_path: list[tuple[str, str]] = []

        current_idx = idx
        for level in range(len(self._tree_levels) - 1):
            current_level = self._tree_levels[level]
            if current_idx % 2 == 0:
                sibling_idx = current_idx + 1
                if sibling_idx < len(current_level):
                    proof_path.append((current_level[sibling_idx], "right"))
                    current_idx //= 2
                else:
                    current_idx = len(current_level) // 2
            else:
                proof_path.append((current_level[current_idx - 1], "left"))
                current_idx //= 2

        return FederatedProof(
            org_id=org_id,
            org_root_hash=org_root,
            proof_path=proof_path,
            federated_root_hash=self._federated_root,
            org_count=len(self._entries),
            timestamp=self._last_aggregated,
        )

    def verify_org_inclusion(self, org_id: str) -> dict[str, Any]:
        """Verify that an org's root is included in the federated root.

        This is a convenience method that generates and verifies a proof
        in one call. For offline verification, use :meth:`generate_proof`
        and :meth:`FederatedProof.verify` separately.
        """
        proof = self.generate_proof(org_id)
        if proof is None:
            return {
                "valid": False,
                "reason": "org not found or no federated root",
                "org_id": org_id,
            }
        return {
            "valid": proof.verify(),
            "org_id": org_id,
            "org_root_hash": proof.org_root_hash,
            "federated_root_hash": proof.federated_root_hash,
            "org_count": proof.org_count,
        }

    def list_orgs(self) -> list[OrgRootEntry]:
        """Return all registered organization entries."""
        return list(self._entries)

    def remove_org(self, org_id: str) -> bool:
        """Remove an organization and rebuild the federated tree.

        Returns:
            True if the org was found and removed, False otherwise.
        """
        if org_id not in self._entry_index:
            return False
        idx = self._entry_index[org_id]
        self._entries.pop(idx)
        # Rebuild index
        self._entry_index = {}
        for i, entry in enumerate(self._entries):
            self._entry_index[entry.org_id] = i
        self._rebuild()
        return True

    def summary(self) -> dict[str, Any]:
        """Return a summary of the federated aggregation state."""
        return {
            "org_count": len(self._entries),
            "federated_root": self._federated_root,
            "last_aggregated": self._last_aggregated,
            "total_evidence_count": sum(e.tree_size for e in self._entries),
        }

    def get_org_entry(self, org_id: str) -> OrgRootEntry | None:
        """Return an org's entry, or None if not found."""
        idx = self._entry_index.get(org_id)
        if idx is None:
            return None
        return self._entries[idx]

    def save_state(self, path: str | Path) -> None:
        """Persist aggregator state to a JSON file."""
        data = {
            "entries": [
                {
                    "org_id": e.org_id,
                    "root_hash": e.root_hash,
                    "timestamp": e.timestamp,
                    "tree_size": e.tree_size,
                    "metadata": e.metadata,
                }
                for e in self._entries
            ],
            "federated_root": self._federated_root,
            "last_aggregated": self._last_aggregated,
        }
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False))

    @classmethod
    def load_state(cls, path: str | Path) -> FederatedMerkleAggregator:
        """Load aggregator state from a JSON file."""
        data = json.loads(Path(path).read_text())
        agg = cls()
        for e in data["entries"]:
            agg.submit_root(
                org_id=e["org_id"],
                root_hash=e["root_hash"],
                tree_size=e.get("tree_size", 0),
                metadata=e.get("metadata", {}),
            )
        return agg


__all__ = [
    "FederatedMerkleAggregator",
    "FederatedProof",
    "OrgRootEntry",
]
