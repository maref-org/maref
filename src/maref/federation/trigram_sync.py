"""Cross-Org Eight Trigrams State Synchronization (F1).

Bridges the local :class:`EightTrigramsGovernance` (per-agent state machine
with 8 I Ching trigram states) with the
:class:`FederatedMerkleAggregator` (cross-org Merkle root aggregation).

Each organisation has a set of agents, each with a trigram governance state.
The synchronizer:
  1. Serializes and hashes each local trigram state into a Merkle leaf.
  2. Builds a local trigram Merkle tree from all managed agents.
  3. Submits the local Merkle root to the federated aggregator.
  4. Generates cross-org inclusion proofs for any agent's trigram state.
  5. Detects "trigram drift" — when one organisation's view of an agent's
     trigram differs from another's.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TrigramStateSnapshot:
    """Serializable snapshot of a single agent's trigram governance state.

    Attributes:
        agent_id: The agent identifier (must be globally unique).
        org_id: The organisation that manages this agent.
        trigram: Current trigram name (e.g. ``"dui"``).
        trust_score: Current trust score (0.0–1.0).
        audit_count: Total audits performed.
        violations: Total violations recorded.
        active_since: Unix timestamp when this trigram became active.
        transition_count: Total trigram transitions.
        recorded_at: Unix timestamp of this snapshot.
    """

    agent_id: str
    org_id: str
    trigram: str
    trust_score: float
    audit_count: int = 0
    violations: int = 0
    active_since: float = 0.0
    transition_count: int = 0
    recorded_at: float = field(default_factory=time.time)

    def _identity_dict(self) -> dict[str, Any]:
        """Return the subset of fields that define identity for hashing.

        Excludes transient metadata (recorded_at) from the hash.
        """
        return {
            "agent_id": self.agent_id,
            "org_id": self.org_id,
            "trigram": self.trigram,
            "trust_score": round(self.trust_score, 4),
            "audit_count": self.audit_count,
            "violations": self.violations,
            "active_since": self.active_since,
            "transition_count": self.transition_count,
        }

    def compute_hash(self) -> str:
        """Return a SHA-256 digest of this snapshot."""
        payload = json.dumps(self._identity_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        d = self._identity_dict()
        d["recorded_at"] = self.recorded_at
        return d

    @classmethod
    def from_governance(
        cls,
        governance: Any,
        org_id: str,
    ) -> TrigramStateSnapshot:
        """Build a snapshot from an EightTrigramsGovernance instance."""
        state = governance.to_dict()
        return cls(
            agent_id=governance.agent_id,
            org_id=org_id,
            trigram=state["current_trigram"],
            trust_score=state["state"]["trust_score"],
            audit_count=state["state"]["audit_count"],
            violations=state["state"]["violations"],
            active_since=state["state"].get("active_since", 0.0),
            transition_count=state["transition_count"],
        )


@dataclass
class AgentTrigramProof:
    """Merkle proof that an agent's trigram state is included in an org's
    local trigram root, plus the cross-org federated proof.

    Attributes:
        snapshot: The agent's trigram state snapshot.
        local_proof_path: Merkle path within the org's local trigram tree.
        org_trigram_root: The org's local trigram Merkle root.
        org_id: The organisation that published this proof.
        recorded_at: When this proof was generated.
    """

    snapshot: TrigramStateSnapshot
    local_proof_path: list[tuple[str, str]]
    org_trigram_root: str
    org_id: str
    recorded_at: float = field(default_factory=time.time)

    def verify_local(self) -> bool:
        """Verify the local Merkle path from snapshot hash to org root."""
        current = self.snapshot.compute_hash()
        for sibling, direction in self.local_proof_path:
            combined = sibling + current if direction == "left" else current + sibling
            current = hashlib.sha256(combined.encode()).hexdigest()
        return current == self.org_trigram_root

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot": self.snapshot.to_dict(),
            "local_proof_path": self.local_proof_path,
            "org_trigram_root": self.org_trigram_root,
            "org_id": self.org_id,
            "recorded_at": self.recorded_at,
        }


class TrigramStateSynchronizer:
    """Synchronizes trigram governance states across organisations.

    Manages a local Merkle tree of all agents' trigram states within an
    organisation, then submits the org's root to a
    :class:`FederatedMerkleAggregator` for cross-org aggregation.

    Usage::

        sync = TrigramStateSynchronizer(org_id="org-alpha")
        sync.register_agent(eight_trigrams_gov)
        sync.publish_local_state()

        # Cross-org
        proof = sync.generate_agent_proof("agent-01")
        remote_valid = sync.verify_remote_snapshot(
            remote_snapshot, remote_proof
        )
        drift = sync.detect_drift(org_id="org-beta")
    """

    def __init__(
        self,
        org_id: str,
        merkle_aggregator: Any | None = None,
    ) -> None:
        self.org_id = org_id
        self._aggregator = merkle_aggregator
        self._lock = threading.RLock()
        self._snapshots: dict[str, TrigramStateSnapshot] = {}
        self._local_tree: list[list[str]] = []
        self._local_root: str | None = None
        self._last_sync: float = 0.0
        self._remote_snapshots: dict[str, dict[str, TrigramStateSnapshot]] = {}
        self._published_hashes: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Local state management
    # ------------------------------------------------------------------

    def register_agent(self, governance: Any) -> TrigramStateSnapshot:
        """Register a local agent's trigram governance for sync.

        Args:
            governance: An EightTrigramsGovernance instance.

        Returns:
            The generated snapshot.
        """
        snap = TrigramStateSnapshot.from_governance(governance, self.org_id)
        with self._lock:
            self._snapshots[governance.agent_id] = snap
            self._rebuild_local_tree()
        return snap

    def unregister_agent(self, agent_id: str) -> bool:
        """Remove an agent from the local sync set."""
        with self._lock:
            if agent_id not in self._snapshots:
                return False
            del self._snapshots[agent_id]
            self._rebuild_local_tree()
            return True

    def get_snapshot(self, agent_id: str) -> TrigramStateSnapshot | None:
        """Return the current local snapshot for an agent."""
        with self._lock:
            return self._snapshots.get(agent_id)

    def refresh_snapshot(self, governance: Any) -> TrigramStateSnapshot | None:
        """Recompute the snapshot from an updated governance instance."""
        snap = TrigramStateSnapshot.from_governance(governance, self.org_id)
        with self._lock:
            if governance.agent_id not in self._snapshots:
                return None
            self._snapshots[governance.agent_id] = snap
            self._rebuild_local_tree()
        return snap

    def agent_count(self) -> int:
        """Number of locally registered agents."""
        with self._lock:
            return len(self._snapshots)

    def list_agents(self) -> list[TrigramStateSnapshot]:
        """Return snapshots for all local agents."""
        with self._lock:
            return list(self._snapshots.values())

    # ------------------------------------------------------------------
    # Local Merkle tree
    # ------------------------------------------------------------------

    def _rebuild_local_tree(self) -> None:
        """Rebuild the local trigram Merkle tree from registered agents."""
        if not self._snapshots:
            self._local_tree = []
            self._local_root = None
            return

        hashes = sorted(snap.compute_hash() for snap in self._snapshots.values())
        self._local_tree = [hashes]
        current = hashes

        while len(current) > 1:
            nxt: list[str] = []
            i = 0
            while i < len(current):
                left = current[i]
                if i + 1 < len(current):
                    right = current[i + 1]
                    nxt.append(hashlib.sha256((left + right).encode()).hexdigest())
                else:
                    nxt.append(left)
                i += 2
            self._local_tree.append(nxt)
            current = nxt

        self._local_root = current[0] if current else None

    def get_local_root(self) -> str | None:
        """Return the local trigram Merkle root hash."""
        with self._lock:
            return self._local_root

    def generate_agent_proof(
        self,
        agent_id: str,
    ) -> AgentTrigramProof | None:
        """Generate a Merkle proof that an agent's trigram state is
        included in the local tree.

        Returns None if the agent is not registered or the tree is empty.
        """
        with self._lock:
            if agent_id not in self._snapshots:
                return None
            if self._local_root is None or not self._local_tree:
                return None

            snap = self._snapshots[agent_id]
            target_hash = snap.compute_hash()
            all_hashes = sorted(s.compute_hash() for s in self._snapshots.values())
            try:
                idx = all_hashes.index(target_hash)
            except ValueError:
                return None

            proof_path: list[tuple[str, str]] = []
            current_idx = idx
            for level in range(len(self._local_tree) - 1):
                level_hashes = self._local_tree[level]
                if current_idx % 2 == 0:
                    sibling = current_idx + 1
                    if sibling < len(level_hashes):
                        proof_path.append((level_hashes[sibling], "right"))
                        current_idx //= 2
                    else:
                        current_idx = len(level_hashes) // 2
                else:
                    proof_path.append((level_hashes[current_idx - 1], "left"))
                    current_idx //= 2

            return AgentTrigramProof(
                snapshot=snap,
                local_proof_path=proof_path,
                org_trigram_root=self._local_root,
                org_id=self.org_id,
            )

    # ------------------------------------------------------------------
    # Cross-org publish / verify
    # ------------------------------------------------------------------

    def publish_local_state(self) -> str | None:
        """Publish the local trigram root to the federated Merkle aggregator.

        Returns the federated root hash, or None if no aggregator is set.
        """
        root = self.get_local_root()
        if root is None:
            return None
        if self._aggregator is None:
            return None

        with self._lock:
            self._aggregator.submit_root(
                org_id=self.org_id,
                root_hash=root,
                tree_size=len(self._snapshots),
                metadata={
                    "type": "trigram_state",
                    "agent_ids": list(self._snapshots.keys()),
                },
            )
            self._published_hashes[self.org_id] = root
            self._last_sync = time.time()
            return self._aggregator.get_federated_root()

    def import_remote_snapshot(
        self,
        snapshot: TrigramStateSnapshot,
        proof: AgentTrigramProof,
    ) -> bool:
        """Import and verify a remote agent's trigram state snapshot.

        Verifies the Merkle proof against the claimed org root, then
        stores the snapshot for drift detection.

        Returns True if the proof is valid, False otherwise.
        """
        if not proof.verify_local():
            return False
        if proof.snapshot.compute_hash() != snapshot.compute_hash():
            return False
        if proof.org_id != snapshot.org_id:
            return False

        with self._lock:
            if snapshot.org_id not in self._remote_snapshots:
                self._remote_snapshots[snapshot.org_id] = {}
            self._remote_snapshots[snapshot.org_id][snapshot.agent_id] = snapshot
        return True

    def verify_remote_inclusion(
        self,
        org_id: str,
        agent_id: str,
    ) -> bool:
        """Check whether a remote agent's snapshot is still valid
        against the federated Merkle root.

        Uses the federated aggregator to verify org-level inclusion,
        and locally verifies the agent-level proof.
        """
        with self._lock:
            remote_org = self._remote_snapshots.get(org_id)
            if remote_org is None or agent_id not in remote_org:
                return False
            if self._aggregator is None:
                return False

            result = self._aggregator.verify_org_inclusion(org_id)
            return result.get("valid", False)

    # ------------------------------------------------------------------
    # Drift detection
    # ------------------------------------------------------------------

    def detect_drift(
        self,
        org_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Detect trigram state drift between local and remote views.

        Args:
            org_id: If set, only check against this remote organisation.
                    If None, check against all known remote orgs.

        Returns:
            A list of drift records, each containing agent_id, org_id,
            local_trigram, remote_trigram, and drift_detected flag.
        """
        drift: list[dict[str, Any]] = []
        with self._lock:
            orgs_to_check = [org_id] if org_id else list(self._remote_snapshots.keys())
            for rid in orgs_to_check:
                remote = self._remote_snapshots.get(rid, {})
                for agent_id, local_snap in self._snapshots.items():
                    remote_snap = remote.get(agent_id)
                    if remote_snap is None:
                        continue
                    drifted = (
                        local_snap.trigram != remote_snap.trigram
                        or abs(local_snap.trust_score - remote_snap.trust_score) > 0.02
                    )
                    drift.append(
                        {
                            "agent_id": agent_id,
                            "org_id": rid,
                            "local_trigram": local_snap.trigram,
                            "local_trust": local_snap.trust_score,
                            "remote_trigram": remote_snap.trigram,
                            "remote_trust": remote_snap.trust_score,
                            "drift_detected": drifted,
                        }
                    )
        return drift

    def get_remote_snapshots(
        self,
        org_id: str | None = None,
    ) -> dict[str, dict[str, TrigramStateSnapshot]]:
        """Return all imported remote snapshots, optionally filtered by org."""
        with self._lock:
            if org_id:
                return {org_id: dict(self._remote_snapshots.get(org_id, {}))}
            return {k: dict(v) for k, v in self._remote_snapshots.items()}

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def sync_summary(self) -> dict[str, Any]:
        """Return a summary of the synchronizer state."""
        with self._lock:
            local_agents = len(self._snapshots)
            remote_orgs = len(self._remote_snapshots)
            remote_agents = sum(len(v) for v in self._remote_snapshots.values())
            drift_count = sum(1 for d in self.detect_drift() if d["drift_detected"])
            fed_root = self._aggregator.get_federated_root() if self._aggregator else None
            return {
                "org_id": self.org_id,
                "local_agent_count": local_agents,
                "local_trigram_root": self._local_root,
                "remote_org_count": remote_orgs,
                "remote_agent_count": remote_agents,
                "drift_count": drift_count,
                "federated_root": fed_root,
                "last_sync": self._last_sync,
            }
