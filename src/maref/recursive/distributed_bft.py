from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeStatus(Enum):
    HONEST = "honest"
    BYZANTINE = "byzantine"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    RECOVERING = "recovering"


class ConsensusResult(Enum):
    REACHED = "reached"
    FAILED = "failed"
    PENDING = "pending"
    DEADLOCK = "deadlock"


@dataclass
class BFTNode:
    node_id: str
    credit_score: float = 0.5
    status: NodeStatus = NodeStatus.HONEST
    vote_weight: float = 1.0
    last_heartbeat: float = field(default_factory=time.time)
    byzantine_rounds: int = 0
    total_rounds: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "credit_score": round(self.credit_score, 3),
            "status": self.status.value,
            "vote_weight": round(self.vote_weight, 3),
            "byzantine_rounds": self.byzantine_rounds,
            "total_rounds": self.total_rounds,
        }

    def update_weight_by_credit(self) -> None:
        if self.status == NodeStatus.BYZANTINE:
            self.vote_weight = 0.0
        elif self.status == NodeStatus.DEGRADED:
            self.vote_weight = max(0.1, self.credit_score * 0.5)
        elif self.status == NodeStatus.RECOVERING:
            self.vote_weight = max(0.3, self.credit_score * 0.7)
        else:
            self.vote_weight = max(0.5, self.credit_score)


@dataclass
class Vote:
    node_id: str
    value: Any
    round_number: int
    timestamp: float = field(default_factory=time.time)
    is_byzantine: bool = False
    hmac_signature: str = ""  # Phase 3.1: HMAC-SHA256 signature

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "value": self.value,
            "round": self.round_number,
            "is_byzantine": self.is_byzantine,
            "hmac_signature": self.hmac_signature,
        }

    def sign(self, secret_key: bytes) -> None:
        """Generate HMAC-SHA256 over (node_id + round + value)."""
        payload = f"{self.node_id}:{self.round_number}:{self.value}".encode()
        self.hmac_signature = hmac.new(secret_key, payload, hashlib.sha256).hexdigest()

    def verify(self, secret_key: bytes) -> bool:
        """Verify the HMAC signature."""
        if not self.hmac_signature:
            return False
        payload = f"{self.node_id}:{self.round_number}:{self.value}".encode()
        expected = hmac.new(secret_key, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(self.hmac_signature, expected)


@dataclass
class ConsensusRound:
    round_id: str
    round_number: int
    proposal_value: Any
    votes: list[Vote] = field(default_factory=list)
    result: ConsensusResult = ConsensusResult.PENDING
    decided_value: Any = None
    byzantine_count: int = 0
    quorum_met: bool = False
    started_at: float = field(default_factory=time.time)
    completed_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_id": self.round_id,
            "round_number": self.round_number,
            "proposal_value": self.proposal_value,
            "vote_count": len(self.votes),
            "result": self.result.value,
            "decided_value": self.decided_value,
            "byzantine_count": self.byzantine_count,
            "quorum_met": self.quorum_met,
        }


class DistributedBFT:
    def __init__(self, total_nodes: int = 7, secret_key: bytes | None = None):
        self._f = (total_nodes - 1) // 3
        self._quorum = 2 * self._f + 1
        self._nodes: dict[str, BFTNode] = {}
        self._rounds: list[ConsensusRound] = []
        self._round_counter: int = 0
        self._consensus_history: list[ConsensusRound] = []
        self._byzantine_tolerance_violations: int = 0
        # Phase 3.1: HMAC-SHA256 key for vote signing
        self._secret_key = secret_key or b"maref-bft-dev-key"
        self._audit_log: list[dict[str, Any]] = []

    @property
    def f(self) -> int:
        return self._f

    @property
    def quorum(self) -> int:
        return self._quorum

    @property
    def total_nodes(self) -> int:
        return len(self._nodes)

    @property
    def honest_count(self) -> int:
        return sum(1 for n in self._nodes.values() if n.status == NodeStatus.HONEST)

    @property
    def byzantine_count(self) -> int:
        return sum(1 for n in self._nodes.values() if n.status == NodeStatus.BYZANTINE)

    def register_node(self, node_id: str, credit_score: float = 0.5) -> BFTNode:
        node = BFTNode(node_id=node_id, credit_score=credit_score)
        node.update_weight_by_credit()
        self._nodes[node_id] = node
        return node

    def register_nodes(self, count: int, prefix: str = "node") -> list[BFTNode]:
        nodes = []
        for i in range(count):
            node_id = f"{prefix}_{i}"
            node = self.register_node(node_id, credit_score=0.5 + i * 0.07)
            nodes.append(node)
        return nodes

    def set_byzantine(self, node_id: str) -> bool:
        node = self._nodes.get(node_id)
        if not node:
            return False
        if self.byzantine_count >= self._f:
            self._byzantine_tolerance_violations += 1
            return False
        node.status = NodeStatus.BYZANTINE
        node.update_weight_by_credit()
        return True

    def set_honest(self, node_id: str) -> bool:
        node = self._nodes.get(node_id)
        if not node:
            return False
        node.status = NodeStatus.HONEST
        node.update_weight_by_credit()
        return True

    def set_degraded(self, node_id: str) -> None:
        node = self._nodes.get(node_id)
        if node:
            node.status = NodeStatus.DEGRADED
            node.update_weight_by_credit()

    def propose_consensus(self, value: Any, proposer_id: str | None = None) -> ConsensusRound:
        self._round_counter += 1
        round_id = f"round_{self._round_counter}_{uuid.uuid4().hex[:4]}"

        r = ConsensusRound(
            round_id=round_id,
            round_number=self._round_counter,
            proposal_value=value,
        )
        self._rounds.append(r)
        return r

    def cast_vote(self, round_index: int, node_id: str, value: Any) -> Vote | None:
        if round_index >= len(self._rounds):
            return None

        node = self._nodes.get(node_id)
        if not node or node.status == NodeStatus.OFFLINE:
            return None

        r = self._rounds[round_index]
        is_byzantine = node.status == NodeStatus.BYZANTINE

        vote_value = value
        if is_byzantine:
            vote_value = f"byzantine_spoof_{uuid.uuid4().hex[:4]}"

        vote = Vote(
            node_id=node_id,
            value=vote_value,
            round_number=self._round_counter,
            is_byzantine=is_byzantine,
        )
        # Phase 3.1: sign every honest vote
        if not is_byzantine:
            vote.sign(self._secret_key)

        r.votes.append(vote)
        node.total_rounds += 1
        if is_byzantine:
            node.byzantine_rounds += 1
            r.byzantine_count += 1

        return vote

    def check_quorum(self, round_index: int) -> bool:
        if round_index >= len(self._rounds):
            return False
        r = self._rounds[round_index]
        honest_votes = [v for v in r.votes if not v.is_byzantine]
        r.quorum_met = len(honest_votes) >= self._quorum
        return r.quorum_met

    def reach_consensus(self, round_index: int) -> ConsensusResult:
        if round_index >= len(self._rounds):
            return ConsensusResult.FAILED

        r = self._rounds[round_index]

        if not self.check_quorum(round_index):
            r.result = ConsensusResult.FAILED
            return r.result

        # Phase 3.1: verify HMAC signatures before counting
        honest_votes: list[Vote] = []
        for v in r.votes:
            if v.is_byzantine:
                continue
            if v.verify(self._secret_key):
                honest_votes.append(v)
            else:
                # Tampered vote treated as byzantine
                v.is_byzantine = True
                r.byzantine_count += 1

        if not honest_votes:
            r.result = ConsensusResult.FAILED
            return r.result

        values: dict[str, int] = {}
        for v in honest_votes:
            key = str(v.value)
            values[key] = values.get(key, 0) + 1

        max_value, max_count = max(values.items(), key=lambda x: x[1])

        if max_count >= self._quorum:
            r.result = ConsensusResult.REACHED
            r.decided_value = max_value
            r.completed_at = time.time()
            self._consensus_history.append(r)
            # Audit log entry with signature proof
            self._audit_log.append(
                {
                    "round_id": r.round_id,
                    "decided_value": max_value,
                    "honest_vote_count": len(honest_votes),
                    "timestamp": time.time(),
                    "signature_verified": True,
                }
            )
        else:
            r.result = ConsensusResult.FAILED

        return r.result

    def run_consensus_cycle(self, value: Any, proposer_id: str | None = None) -> ConsensusRound:
        r = self.propose_consensus(value, proposer_id)
        ri = len(self._rounds) - 1

        for node_id, node in self._nodes.items():
            if node.status != NodeStatus.OFFLINE:
                # cast_vote internally handles byzantine spoofing;
                # always pass the honest value and let cast_vote decide.
                self.cast_vote(ri, node_id, value)

        self.reach_consensus(ri)
        return r

    def verify_byzantine_tolerance(self, test_value: Any = "test_value") -> dict[str, Any]:
        byzantine_count = self.byzantine_count

        r = self.run_consensus_cycle(test_value)
        success = r.result == ConsensusResult.REACHED

        return {
            "byzantine_nodes": byzantine_count,
            "f_tolerance": self._f,
            "quorum_required": self._quorum,
            "consensus_reached": success,
            "decided_value": r.decided_value,
            "tolerance_intact": success and byzantine_count <= self._f,
            "violations": self._byzantine_tolerance_violations,
        }

    def get_node(self, node_id: str) -> BFTNode | None:
        return self._nodes.get(node_id)

    def get_all_nodes(self) -> list[BFTNode]:
        return list(self._nodes.values())

    def get_round(self, round_index: int) -> ConsensusRound | None:
        if round_index < len(self._rounds):
            return self._rounds[round_index]
        return None

    def get_consensus_history(self) -> list[ConsensusRound]:
        return self._consensus_history.copy()

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_nodes": self.total_nodes,
            "f": self._f,
            "quorum": self._quorum,
            "honest_count": self.honest_count,
            "byzantine_count": self.byzantine_count,
            "tolerance_violations": self._byzantine_tolerance_violations,
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "round_count": len(self._rounds),
            "consensus_reached": len(self._consensus_history),
            "audit_log_size": len(self._audit_log),
        }

    def verify_all_signatures(self, round_index: int) -> dict[str, Any]:
        """Return signature verification summary for a round."""
        if round_index >= len(self._rounds):
            return {"error": "round not found"}
        r = self._rounds[round_index]
        verified = 0
        failed = 0
        for v in r.votes:
            if v.is_byzantine:
                continue
            if v.verify(self._secret_key):
                verified += 1
            else:
                failed += 1
        return {
            "round_id": r.round_id,
            "verified": verified,
            "failed": failed,
            "byzantine": r.byzantine_count,
        }
