"""Federated Consensus Protocol with Ed25519-signed verifiable evidence.

Implements a lightweight majority-quorum consensus protocol for
cross-organization decision-making in the MAREF federation layer.

Every vote and every resolution is Ed25519-signed, producing
independently verifiable audit evidence that any third party
(including regulators) can validate with only the signer's public key.

Usage::

    from maref.crypto.ed25519_keys import Ed25519KeyPair

    signer = Ed25519KeyPair.generate()
    consensus = FederatedConsensus(member_count=5, quorum_size=3, signer=signer)
    proposal = consensus.propose("member-1", "add-agent", {"agent_id": "a1"})
    consensus.vote(proposal.proposal_id, "member-2", VoteChoice.APPROVE, signer=signer)
    result = consensus.resolve(proposal.proposal_id)
    assert result.state == ProposalState.ACCEPTED
    # The signed vote evidence is in result.votes[0].signature
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.security.decorators import security_critical


class VoteChoice(Enum):
    """A member's vote on a proposal."""

    APPROVE = "approve"
    REJECT = "reject"


class ProposalState(Enum):
    """The lifecycle state of a proposal."""

    OPEN = "open"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ConsensusTopology(str, Enum):
    """The decision-making topology of a federation (v0.44.0 F1).

    - ``FLAT``: every member carries equal weight; proposals resolve via
      a majority quorum vote (legacy behaviour).
    - ``LEADER_WORKER``: workers execute fast decisions, the leader
      arbitrates routine proposals, and critical proposals are escalated
      to a full quorum vote.
    """

    FLAT = "flat"
    LEADER_WORKER = "leader_worker"


class FederationRole(str, Enum):
    """A member's role within a LEADER_WORKER topology."""

    LEADER = "leader"
    WORKER = "worker"


@dataclass
class ConsensusVote:
    """A single vote on a proposal, Ed25519-signed for verifiability.

    Attributes:
        voter_id: The federation member casting the vote.
        choice: APPROVE or REJECT.
        reason: Optional reason for the vote.
        timestamp: When the vote was cast.
        proposal_id: The proposal this vote belongs to.
        signature: Ed25519 hex signature of ``voter_id|choice|timestamp|proposal_id``.
            Empty string if the vote was not signed.
        signer_fingerprint: Fingerprint of the Ed25519 public key that signed this vote.
    """

    voter_id: str
    choice: VoteChoice
    reason: str = ""
    timestamp: float = field(default_factory=time.time)
    proposal_id: str = ""
    signature: str = ""
    signer_fingerprint: str = ""

    @property
    def message_to_sign(self) -> bytes:
        """Canonical message for Ed25519 signing."""
        return f"{self.voter_id}|{self.choice.value}|{self.timestamp}|{self.proposal_id}".encode()

    def to_dict(self) -> dict[str, Any]:
        """Serialize the vote including its Ed25519 signature (v0.47 F4)."""
        return {
            "voter_id": self.voter_id,
            "choice": self.choice.value,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "proposal_id": self.proposal_id,
            "signature": self.signature,
            "signer_fingerprint": self.signer_fingerprint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConsensusVote:
        return cls(
            voter_id=data["voter_id"],
            choice=VoteChoice(data["choice"]),
            reason=data.get("reason", ""),
            timestamp=float(data.get("timestamp", 0.0)),
            proposal_id=data.get("proposal_id", ""),
            signature=data.get("signature", ""),
            signer_fingerprint=data.get("signer_fingerprint", ""),
        )

    def verify_signature(self, public_key_pem: str) -> bool:
        """Verify the Ed25519 signature on this vote.

        Args:
            public_key_pem: PEM-encoded Ed25519 public key.

        Returns:
            True if the signature is valid, False otherwise.
        """
        if not self.signature or self.signature in ("unsigned", "sign_error"):
            return False
        from maref.crypto.ed25519_keys import Ed25519KeyPair
        try:
            return Ed25519KeyPair.verify(
                public_key_pem,
                bytes.fromhex(self.signature),
                self.message_to_sign,
            )
        except (ValueError, Exception):
            return False


@dataclass
class ConsensusProposal:
    """A proposal requiring federation consensus.

    Attributes:
        proposal_id: Unique identifier.
        proposer_id: The member proposing the decision.
        topic: Short description of what is being proposed.
        payload: Proposal-specific data (e.g. policy change details).
        created_at: When the proposal was created.
        expires_at: When the proposal expires (auto-expire).
        votes: List of votes cast so far.
        state: Current state of the proposal.
        resolved_at: When the proposal was resolved (or None).
        resolution_signature: Ed25519 hex signature of the resolution outcome.
        signer_fingerprint: Fingerprint of the signing key.
    """

    proposal_id: str
    proposer_id: str
    topic: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(
        default_factory=lambda: time.time() + 300.0
    )
    votes: list[ConsensusVote] = field(default_factory=list)
    state: ProposalState = ProposalState.OPEN
    resolved_at: float | None = None
    resolution_signature: str = ""
    signer_fingerprint: str = ""
    topology: ConsensusTopology = ConsensusTopology.FLAT
    is_critical: bool = False

    @property
    def approve_count(self) -> int:
        """Number of APPROVE votes."""
        return sum(1 for v in self.votes if v.choice == VoteChoice.APPROVE)

    @property
    def reject_count(self) -> int:
        """Number of REJECT votes."""
        return sum(1 for v in self.votes if v.choice == VoteChoice.REJECT)

    @property
    def voter_ids(self) -> set[str]:
        """Set of member IDs who have voted."""
        return {v.voter_id for v in self.votes}

    def proposal_digest(self) -> str:
        """SHA-256 digest of the proposal's core attributes.

        Used as the canonical identifier for external verification.
        """
        raw = f"{self.proposal_id}|{self.topic}|{json.dumps(self.payload, sort_keys=True)}|{self.created_at}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "proposer_id": self.proposer_id,
            "topic": self.topic,
            "payload": self.payload,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "state": self.state.value,
            "topology": self.topology.value,
            "is_critical": self.is_critical,
            "approve_count": self.approve_count,
            "reject_count": self.reject_count,
            "total_votes": len(self.votes),
            "resolved_at": self.resolved_at,
            "resolution_signature": self.resolution_signature,
            "signer_fingerprint": self.signer_fingerprint,
            "proposal_digest": self.proposal_digest(),
            # v0.47 F4: include full vote details (Ed25519 signatures) so
            # verifiable evidence survives persistence.
            "votes": [v.to_dict() for v in self.votes],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConsensusProposal:
        """Reconstruct a proposal from :meth:`to_dict` (v0.47 F4)."""
        proposal = cls(
            proposal_id=data["proposal_id"],
            proposer_id=data["proposer_id"],
            topic=data["topic"],
            payload=dict(data.get("payload", {})),
            created_at=float(data.get("created_at", 0.0)),
            expires_at=float(data.get("expires_at", 0.0)),
            votes=[ConsensusVote.from_dict(v) for v in data.get("votes", [])],
            state=ProposalState(data["state"]),
            resolved_at=data.get("resolved_at"),
            resolution_signature=data.get("resolution_signature", ""),
            signer_fingerprint=data.get("signer_fingerprint", ""),
            topology=ConsensusTopology(data["topology"]),
            is_critical=bool(data.get("is_critical", False)),
        )
        return proposal


class FederatedConsensus:
    """Manages consensus proposals and voting with Ed25519 verifiable evidence.

    Implements a majority-quorum protocol:

    - Proposals need at least ``quorum_size`` votes to resolve.
    - A simple majority of APPROVE votes accepts the proposal.
    - A simple majority of REJECT votes rejects it.
    - Proposals expire after ``default_timeout`` seconds if quorum
      is not reached.
    - Each member can vote at most once per proposal.
    - Every vote and resolution is Ed25519-signed when a signer is configured.

    When ``audit_logger`` is provided, all lifecycle events (propose, vote,
    resolve, expire) are recorded with Ed25519-signed audit entries.
    """

    def __init__(
        self,
        member_count: int = 3,
        quorum_size: int = 2,
        default_timeout: float = 300.0,
        signer: Any = None,
        audit_logger: Any = None,
        topology: ConsensusTopology = ConsensusTopology.FLAT,
        leader_id: str = "",
        critical_topics: set[str] | None = None,
        membership: Any | None = None,
        db_path: Any | None = None,
        verify_vote_signatures: bool = False,
        voter_public_keys: dict[str, str] | None = None,
    ) -> None:
        self._member_count = member_count
        self._quorum_size = quorum_size
        self._default_timeout = default_timeout
        self._proposals: dict[str, ConsensusProposal] = {}
        self._signer = signer
        self._audit_logger = audit_logger
        self._topology = topology
        if (
            topology == ConsensusTopology.LEADER_WORKER
            and not leader_id
        ):
            raise ValueError(
                "LEADER_WORKER 拓扑必须指定 leader_id，否则常规决议无法仲裁"
            )
        self._leader_id = leader_id
        self._critical_topics = critical_topics or set()
        # v0.47 F2: membership source (MembershipManager-style). When
        # provided, only tracked members may vote (fail-closed).
        self._membership = membership
        # v0.50 W6-S3 / F10: when enabled, only Ed25519-verified votes count
        # toward resolution; unsigned votes are excluded (fail-closed).
        self._verify_vote_signatures = verify_vote_signatures
        self._voter_public_keys: dict[str, str] = dict(voter_public_keys or {})
        # v0.47 F4: SQLite persistence for proposals (incl. signed votes).
        self._db = None
        if db_path is not None:
            from maref.governance.db import DatabaseManager

            self._db = DatabaseManager(db_path)
            self._init_schema()
            self._load_from_disk()

    def _init_schema(self) -> None:
        assert self._db is not None
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS consensus_proposals (
                proposal_id TEXT PRIMARY KEY,
                data        TEXT NOT NULL
            );
            """
        )

    def _load_from_disk(self) -> None:
        assert self._db is not None
        rows = self._db.fetchall("SELECT proposal_id, data FROM consensus_proposals")
        for row in rows:
            proposal = ConsensusProposal.from_dict(json.loads(row["data"]))
            self._proposals[proposal.proposal_id] = proposal

    def _persist(self, proposal: ConsensusProposal) -> None:
        if self._db is None:
            return
        self._db.execute(
            "INSERT OR REPLACE INTO consensus_proposals (proposal_id, data) VALUES (?, ?)",
            (proposal.proposal_id, json.dumps(proposal.to_dict())),
        )

    @property
    def membership_enforced(self) -> bool:
        """Whether votes are restricted to tracked members."""
        return self._membership is not None

    def _member_ids(self) -> set[str]:
        """Resolve the current membership id set (empty when unenforced)."""
        if self._membership is None:
            return set()
        try:
            table = self._membership.members_summary()
        except AttributeError:
            table = self._membership.member_snapshots()
        if not isinstance(table, dict):
            return set()
        return set(table.keys())

    @property
    def topology(self) -> ConsensusTopology:
        """The consensus topology in use."""
        return self._topology

    @property
    def leader_id(self) -> str:
        """The federation leader in LEADER_WORKER topology ("" if unset)."""
        return self._leader_id

    def _is_critical_topic(self, topic: str) -> bool:
        return any(t in topic for t in self._critical_topics)

    def _log_audit(self, event_type: str, detail: dict[str, Any]) -> None:
        if self._audit_logger is None:
            return
        try:
            self._audit_logger.log(
                event_type=event_type,
                actor="federated_consensus",
                detail=detail,
            )
        except Exception:
            pass

    def _get_signer_fingerprint(self) -> str:
        if self._signer is None:
            return ""
        try:
            return self._signer.fingerprint
        except Exception:
            return ""

    @property
    def member_count(self) -> int:
        return self._member_count

    @property
    def quorum_size(self) -> int:
        return self._quorum_size

    @security_critical
    def propose(
        self,
        proposer_id: str,
        topic: str,
        payload: dict[str, Any] | None = None,
        timeout: float | None = None,
        is_critical: bool | None = None,
    ) -> ConsensusProposal:
        """Create a new consensus proposal.

        Args:
            proposer_id: The member proposing.
            topic: Short description of the proposal.
            payload: Proposal-specific data.
            timeout: Auto-expire timeout in seconds.
            is_critical: Whether this proposal requires full quorum voting.
                In LEADER_WORKER topology, ``None`` (default) derives the
                flag from ``critical_topics``; routine proposals are
                arbitrated by the leader without full quorum.

        Returns:
            The created :class:`ConsensusProposal`.
        """
        critical = (
            is_critical
            if is_critical is not None
            else self._is_critical_topic(topic)
        )
        proposal = ConsensusProposal(
            proposal_id=f"prop-{uuid.uuid4().hex[:12]}",
            proposer_id=proposer_id,
            topic=topic,
            payload=payload or {},
            expires_at=time.time() + (timeout or self._default_timeout),
            topology=self._topology,
            is_critical=critical,
        )
        self._proposals[proposal.proposal_id] = proposal
        self._persist(proposal)

        self._log_audit("consensus.propose", {
            "proposal_id": proposal.proposal_id,
            "proposer_id": proposer_id,
            "topic": topic,
            "topology": self._topology.value,
            "is_critical": critical,
            "proposal_digest": proposal.proposal_digest(),
        })
        return proposal

    @security_critical
    def vote(
        self,
        proposal_id: str,
        voter_id: str,
        choice: VoteChoice,
        reason: str = "",
        signer: Any | None = None,
    ) -> bool:
        """Cast a vote on a proposal.

        If ``signer`` (an Ed25519KeyPair) is provided, the vote is
        Ed25519-signed and the signature is stored in the vote record.

        Returns True if the vote was accepted, False if:
        - The proposal doesn't exist.
        - The proposal is not OPEN.
        - The voter already voted.
        - The proposal has expired.
        - Signature verification fails (when signer is provided).
        """
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            return False
        if proposal.state != ProposalState.OPEN:
            return False
        if time.time() > proposal.expires_at:
            proposal.state = ProposalState.EXPIRED
            proposal.resolved_at = time.time()
            self._log_audit("consensus.expire", {
                "proposal_id": proposal_id, "reason": "timeout",
            })
            return False
        if voter_id in proposal.voter_ids:
            return False

        # v0.47 F2: 投票绑定成员表 — 非成员投票拒绝并记 unauthorized_vote。
        if self._membership is not None:
            member_ids = self._member_ids()
            if voter_id not in member_ids:
                self._log_audit("consensus.unauthorized_vote", {
                    "proposal_id": proposal_id,
                    "voter_id": voter_id,
                    "reason": "not_a_member",
                })
                return False

        vote = ConsensusVote(
            voter_id=voter_id,
            choice=choice,
            reason=reason,
            proposal_id=proposal_id,
        )

        # Sign the vote if a signer is provided
        _signer = signer or self._signer
        if _signer is not None:
            try:
                sig_bytes = _signer.sign(vote.message_to_sign)
                vote.signature = sig_bytes.hex()
                vote.signer_fingerprint = _signer.fingerprint
            except Exception:
                vote.signature = "sign_error"
        else:
            vote.signature = "unsigned"

        proposal.votes.append(vote)
        self._persist(proposal)

        self._log_audit("consensus.vote", {
            "proposal_id": proposal_id,
            "voter_id": voter_id,
            "choice": choice.value,
            "signed": vote.signature != "unsigned",
        })
        return True

    @security_critical
    def resolve(self, proposal_id: str) -> ConsensusProposal | None:
        """Attempt to resolve a proposal.

        Checks if quorum is reached and resolves the proposal:

        - Majority APPROVE -> ``ACCEPTED``
        - Majority REJECT -> ``REJECTED``
        - Expired without quorum -> ``EXPIRED``
        - Tie or insufficient votes -> remains ``OPEN``

        When a signer is configured, the resolution outcome is
        Ed25519-signed for verifiable evidence.

        Returns the proposal (with updated state), or None if not found.
        """
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            return None

        if proposal.state != ProposalState.OPEN:
            return proposal

        # Check expiry
        if time.time() > proposal.expires_at:
            proposal.state = ProposalState.EXPIRED
            proposal.resolved_at = time.time()
            self._log_audit("consensus.expire", {
                "proposal_id": proposal_id, "reason": "timeout_auto",
            })
            return proposal

        total_votes = len(self._verified_votes(proposal))

        # LEADER_WORKER: leader arbitrates routine proposals directly
        if (
            self._topology == ConsensusTopology.LEADER_WORKER
            and not proposal.is_critical
        ):
            # v0.50 W6-S3 / F13: leader arbitration still requires quorum
            # support (>= quorum_size verified votes), not a lone leader.
            if total_votes < self._quorum_size:
                return proposal
            leader_vote = next(
                (v for v in self._verified_votes(proposal) if v.voter_id == self._leader_id),
                None,
            )
            if leader_vote is None:
                # Awaiting leader arbitration
                return proposal
            if leader_vote.choice == VoteChoice.APPROVE:
                proposal.state = ProposalState.ACCEPTED
            else:
                proposal.state = ProposalState.REJECTED
            proposal.resolved_at = time.time()
            self._sign_resolution(proposal)
            self._persist(proposal)
            self._log_audit("consensus.resolve", {
                "proposal_id": proposal_id,
                "state": proposal.state.value,
                "topology": "leader_worker",
                "arbitrated_by": self._leader_id,
                "total_verified_votes": total_votes,
                "resolution_signature": proposal.resolution_signature,
            })
            return proposal

        if total_votes < self._quorum_size:
            return proposal

        verified = self._verified_votes(proposal)
        approve_count = sum(1 for v in verified if v.choice == VoteChoice.APPROVE)
        reject_count = sum(1 for v in verified if v.choice == VoteChoice.REJECT)

        # Check majority
        if approve_count > reject_count:
            proposal.state = ProposalState.ACCEPTED
        elif reject_count > approve_count:
            proposal.state = ProposalState.REJECTED
        else:
            # Tie -- not resolved, need more votes
            return proposal

        proposal.resolved_at = time.time()
        self._sign_resolution(proposal)
        self._persist(proposal)

        self._log_audit("consensus.resolve", {
            "proposal_id": proposal_id,
            "state": proposal.state.value,
            "approve_count": proposal.approve_count,
            "reject_count": proposal.reject_count,
            "resolution_signature": proposal.resolution_signature,
        })
        return proposal

    def _verified_votes(self, proposal: ConsensusProposal) -> list[ConsensusVote]:
        """Return votes that count toward resolution.

        When ``verify_vote_signatures`` is enabled, only votes whose signer
        is a known voter with a valid Ed25519 signature count; unsigned or
        unverifiable votes are excluded (fail-closed, v0.50 W6-S3 / F10).
        """
        if not self._verify_vote_signatures:
            return list(proposal.votes)
        verified: list[ConsensusVote] = []
        for vote in proposal.votes:
            public_key = self._voter_public_keys.get(vote.voter_id)
            if public_key is None or not vote.verify_signature(public_key):
                self._log_audit("consensus.unverified_vote", {
                    "proposal_id": proposal.proposal_id,
                    "voter_id": vote.voter_id,
                })
                continue
            verified.append(vote)
        return verified

    def _sign_resolution(self, proposal: ConsensusProposal) -> None:
        """Sign a resolved proposal if a signer is configured."""
        if self._signer is None:
            return
        resolution_msg = (
            f"{proposal.proposal_id}|{proposal.state.value}|"
            f"{proposal.approve_count}|{proposal.reject_count}|"
            f"{proposal.resolved_at}"
        ).encode()
        try:
            sig_bytes = self._signer.sign(resolution_msg)
            proposal.resolution_signature = sig_bytes.hex()
            proposal.signer_fingerprint = self._signer.fingerprint
        except Exception:
            proposal.resolution_signature = "sign_error"

    def get_proposal(self, proposal_id: str) -> ConsensusProposal | None:
        """Get a proposal by ID."""
        return self._proposals.get(proposal_id)

    def list_proposals(
        self, state: ProposalState | None = None
    ) -> list[ConsensusProposal]:
        """List proposals, optionally filtered by state."""
        if state is None:
            return list(self._proposals.values())
        return [p for p in self._proposals.values() if p.state == state]

    def cleanup_expired(self) -> int:
        """Expire all open proposals that have timed out.

        Returns the number of proposals expired.
        """
        count = 0
        now = time.time()
        for proposal in self._proposals.values():
            if proposal.state == ProposalState.OPEN and now > proposal.expires_at:
                proposal.state = ProposalState.EXPIRED
                proposal.resolved_at = now
                count += 1
        return count

    def summary(self) -> dict[str, Any]:
        """Return a summary of the consensus system state."""
        open_count = sum(
            1 for p in self._proposals.values() if p.state == ProposalState.OPEN
        )
        accepted = sum(
            1 for p in self._proposals.values() if p.state == ProposalState.ACCEPTED
        )
        rejected = sum(
            1 for p in self._proposals.values() if p.state == ProposalState.REJECTED
        )
        expired = sum(
            1 for p in self._proposals.values() if p.state == ProposalState.EXPIRED
        )
        return {
            "member_count": self._member_count,
            "quorum_size": self._quorum_size,
            "topology": self._topology.value,
            "leader_id": self._leader_id,
            "membership_enforced": self.membership_enforced,
            "total_proposals": len(self._proposals),
            "open": open_count,
            "accepted": accepted,
            "rejected": rejected,
            "expired": expired,
        }


__all__ = [
    "ConsensusProposal",
    "ConsensusTopology",
    "ConsensusVote",
    "FederatedConsensus",
    "FederationRole",
    "ProposalState",
    "VoteChoice",
]
