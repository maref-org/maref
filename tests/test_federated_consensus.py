"""Tests for Federated Consensus Protocol with Ed25519 signing."""

from __future__ import annotations

import time
from typing import Any

import pytest

from maref.governance.federated_consensus import (
    ConsensusProposal,
    ConsensusTopology,
    ConsensusVote,
    FederatedConsensus,
    FederationRole,
    ProposalState,
    VoteChoice,
)


@pytest.fixture
def signer() -> Any:
    from maref.crypto.ed25519_keys import Ed25519KeyPair
    return Ed25519KeyPair.generate()


class TestConsensusProposal:
    def test_create_proposal(self) -> None:
        p = ConsensusProposal(
            proposal_id="prop-1",
            proposer_id="member-1",
            topic="add-agent",
        )
        assert p.state == ProposalState.OPEN
        assert p.approve_count == 0
        assert p.reject_count == 0
        assert len(p.voter_ids) == 0

    def test_vote_counts(self) -> None:
        p = ConsensusProposal(
            proposal_id="prop-1",
            proposer_id="member-1",
            topic="test",
        )
        p.votes.append(ConsensusVote(voter_id="m1", choice=VoteChoice.APPROVE))
        p.votes.append(ConsensusVote(voter_id="m2", choice=VoteChoice.APPROVE))
        p.votes.append(ConsensusVote(voter_id="m3", choice=VoteChoice.REJECT))
        assert p.approve_count == 2
        assert p.reject_count == 1
        assert len(p.voter_ids) == 3

    def test_to_dict(self) -> None:
        p = ConsensusProposal(
            proposal_id="prop-1",
            proposer_id="member-1",
            topic="test",
            payload={"key": "value"},
        )
        d = p.to_dict()
        assert d["proposal_id"] == "prop-1"
        assert d["state"] == "open"
        assert d["payload"] == {"key": "value"}


class TestFederatedConsensus:
    def test_propose(self) -> None:
        fc = FederatedConsensus(member_count=3, quorum_size=2)
        proposal = fc.propose("member-1", "add-agent", {"agent_id": "a1"})
        assert proposal.proposer_id == "member-1"
        assert proposal.topic == "add-agent"
        assert proposal.state == ProposalState.OPEN
        assert fc.get_proposal(proposal.proposal_id) is not None

    def test_vote_accepted(self) -> None:
        fc = FederatedConsensus(member_count=3, quorum_size=2)
        proposal = fc.propose("m1", "test")
        assert fc.vote(proposal.proposal_id, "m2", VoteChoice.APPROVE) is True
        assert fc.vote(proposal.proposal_id, "m3", VoteChoice.APPROVE) is True

    def test_vote_rejects_duplicate(self) -> None:
        fc = FederatedConsensus(member_count=3, quorum_size=2)
        proposal = fc.propose("m1", "test")
        assert fc.vote(proposal.proposal_id, "m2", VoteChoice.APPROVE) is True
        assert fc.vote(proposal.proposal_id, "m2", VoteChoice.REJECT) is False

    def test_vote_rejects_unknown_proposal(self) -> None:
        fc = FederatedConsensus()
        assert fc.vote("unknown", "m1", VoteChoice.APPROVE) is False

    def test_resolve_accepted(self) -> None:
        fc = FederatedConsensus(member_count=3, quorum_size=2)
        proposal = fc.propose("m1", "add-agent")
        fc.vote(proposal.proposal_id, "m2", VoteChoice.APPROVE)
        fc.vote(proposal.proposal_id, "m3", VoteChoice.APPROVE)
        result = fc.resolve(proposal.proposal_id)
        assert result is not None
        assert result.state == ProposalState.ACCEPTED

    def test_resolve_rejected(self) -> None:
        fc = FederatedConsensus(member_count=3, quorum_size=2)
        proposal = fc.propose("m1", "add-agent")
        fc.vote(proposal.proposal_id, "m2", VoteChoice.REJECT)
        fc.vote(proposal.proposal_id, "m3", VoteChoice.REJECT)
        result = fc.resolve(proposal.proposal_id)
        assert result is not None
        assert result.state == ProposalState.REJECTED

    def test_resolve_insufficient_quorum(self) -> None:
        fc = FederatedConsensus(member_count=5, quorum_size=3)
        proposal = fc.propose("m1", "test")
        fc.vote(proposal.proposal_id, "m2", VoteChoice.APPROVE)
        result = fc.resolve(proposal.proposal_id)
        assert result is not None
        assert result.state == ProposalState.OPEN

    def test_resolve_tie_remains_open(self) -> None:
        fc = FederatedConsensus(member_count=4, quorum_size=2)
        proposal = fc.propose("m1", "test")
        fc.vote(proposal.proposal_id, "m2", VoteChoice.APPROVE)
        fc.vote(proposal.proposal_id, "m3", VoteChoice.REJECT)
        result = fc.resolve(proposal.proposal_id)
        assert result.state == ProposalState.OPEN

    def test_resolve_majority_approve_with_rejections(self) -> None:
        fc = FederatedConsensus(member_count=5, quorum_size=3)
        proposal = fc.propose("m1", "test")
        fc.vote(proposal.proposal_id, "m2", VoteChoice.APPROVE)
        fc.vote(proposal.proposal_id, "m3", VoteChoice.REJECT)
        fc.vote(proposal.proposal_id, "m4", VoteChoice.APPROVE)
        result = fc.resolve(proposal.proposal_id)
        assert result.state == ProposalState.ACCEPTED
        assert result.approve_count == 2
        assert result.reject_count == 1

    def test_expired_proposal(self) -> None:
        fc = FederatedConsensus(member_count=3, quorum_size=2, default_timeout=0.1)
        proposal = fc.propose("m1", "test", timeout=0.1)
        time.sleep(0.15)
        result = fc.resolve(proposal.proposal_id)
        assert result.state == ProposalState.EXPIRED

    def test_vote_on_expired_rejected(self) -> None:
        fc = FederatedConsensus(member_count=3, quorum_size=2, default_timeout=0.1)
        proposal = fc.propose("m1", "test", timeout=0.1)
        time.sleep(0.15)
        assert fc.vote(proposal.proposal_id, "m2", VoteChoice.APPROVE) is False

    def test_vote_on_resolved_rejected(self) -> None:
        fc = FederatedConsensus(member_count=3, quorum_size=2)
        proposal = fc.propose("m1", "test")
        fc.vote(proposal.proposal_id, "m2", VoteChoice.APPROVE)
        fc.vote(proposal.proposal_id, "m3", VoteChoice.APPROVE)
        fc.resolve(proposal.proposal_id)
        # Already resolved -- further votes rejected
        assert fc.vote(proposal.proposal_id, "m4", VoteChoice.REJECT) is False

    def test_list_proposals_by_state(self) -> None:
        fc = FederatedConsensus(member_count=3, quorum_size=2)
        p1 = fc.propose("m1", "accepted")
        fc.propose("m1", "open")
        fc.vote(p1.proposal_id, "m2", VoteChoice.APPROVE)
        fc.vote(p1.proposal_id, "m3", VoteChoice.APPROVE)
        fc.resolve(p1.proposal_id)

        accepted = fc.list_proposals(ProposalState.ACCEPTED)
        open_props = fc.list_proposals(ProposalState.OPEN)
        assert len(accepted) == 1
        assert len(open_props) == 1

    def test_cleanup_expired(self) -> None:
        fc = FederatedConsensus(member_count=3, quorum_size=2, default_timeout=0.1)
        fc.propose("m1", "test1", timeout=0.1)
        fc.propose("m1", "test2", timeout=0.1)
        fc.propose("m1", "test3", timeout=100)  # Not expired
        time.sleep(0.15)
        expired_count = fc.cleanup_expired()
        assert expired_count == 2
        open_props = fc.list_proposals(ProposalState.OPEN)
        assert len(open_props) == 1

    def test_summary(self) -> None:
        fc = FederatedConsensus(member_count=5, quorum_size=3)
        p1 = fc.propose("m1", "accepted")
        p2 = fc.propose("m1", "rejected")
        fc.propose("m1", "open")
        fc.vote(p1.proposal_id, "m2", VoteChoice.APPROVE)
        fc.vote(p1.proposal_id, "m3", VoteChoice.APPROVE)
        fc.vote(p1.proposal_id, "m4", VoteChoice.APPROVE)
        fc.resolve(p1.proposal_id)
        fc.vote(p2.proposal_id, "m2", VoteChoice.REJECT)
        fc.vote(p2.proposal_id, "m3", VoteChoice.REJECT)
        fc.vote(p2.proposal_id, "m4", VoteChoice.REJECT)
        fc.resolve(p2.proposal_id)

        s = fc.summary()
        assert s["member_count"] == 5
        assert s["quorum_size"] == 3
        assert s["total_proposals"] == 3
        assert s["accepted"] == 1
        assert s["rejected"] == 1
        assert s["open"] == 1

    def test_resolve_unknown_returns_none(self) -> None:
        fc = FederatedConsensus()
        assert fc.resolve("unknown") is None

    def test_get_proposal_unknown(self) -> None:
        fc = FederatedConsensus()
        assert fc.get_proposal("unknown") is None


class TestConsensusEd25519Signing:
    """Tests for Ed25519-signed consensus votes and resolution evidence."""

    def test_vote_signed_when_signer_provided(self, signer: Any) -> None:
        fc = FederatedConsensus(member_count=3, quorum_size=2, signer=signer)
        proposal = fc.propose("alice", "test")
        fc.vote(proposal.proposal_id, "bob", VoteChoice.APPROVE, signer=signer)
        vote = proposal.votes[0]
        assert vote.signature not in ("", "unsigned", "sign_error")
        assert vote.signer_fingerprint == signer.fingerprint

    def test_vote_signature_verifiable(self, signer: Any) -> None:
        fc = FederatedConsensus(member_count=3, quorum_size=2, signer=signer)
        proposal = fc.propose("alice", "test")
        fc.vote(proposal.proposal_id, "bob", VoteChoice.APPROVE, signer=signer)
        vote = proposal.votes[0]
        assert vote.verify_signature(signer.public_key_pem) is True

    def test_vote_signature_rejects_wrong_key(self, signer: Any) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair
        fc = FederatedConsensus(member_count=3, quorum_size=2, signer=signer)
        proposal = fc.propose("alice", "test")
        fc.vote(proposal.proposal_id, "bob", VoteChoice.APPROVE, signer=signer)
        vote = proposal.votes[0]
        wrong_kp = Ed25519KeyPair.generate()
        assert vote.verify_signature(wrong_kp.public_key_pem) is False

    def test_resolution_signed_when_signer_configured(self, signer: Any) -> None:
        fc = FederatedConsensus(member_count=3, quorum_size=2, signer=signer)
        proposal = fc.propose("alice", "test")
        fc.vote(proposal.proposal_id, "bob", VoteChoice.APPROVE, signer=signer)
        fc.vote(proposal.proposal_id, "carol", VoteChoice.APPROVE, signer=signer)
        result = fc.resolve(proposal.proposal_id)
        assert result.resolution_signature not in ("", "sign_error")
        assert result.signer_fingerprint == signer.fingerprint

    def test_vote_unsigned_when_no_signer(self) -> None:
        fc = FederatedConsensus(member_count=3, quorum_size=2)
        proposal = fc.propose("alice", "test")
        fc.vote(proposal.proposal_id, "bob", VoteChoice.APPROVE)
        vote = proposal.votes[0]
        assert vote.signature == "unsigned"
        assert vote.verify_signature("") is False

    def test_unsigned_vote_verify_returns_false(self) -> None:
        vote = ConsensusVote(voter_id="alice", choice=VoteChoice.APPROVE)
        assert vote.verify_signature("") is False

    def test_vote_signer_fingerprint_stored(self, signer: Any) -> None:
        fc = FederatedConsensus(member_count=2, quorum_size=1, signer=signer)
        proposal = fc.propose("alice", "test")
        fc.vote(proposal.proposal_id, "bob", VoteChoice.APPROVE, signer=signer)
        assert proposal.votes[0].signer_fingerprint == signer.fingerprint

    def test_multi_vote_all_signed(self, signer: Any) -> None:
        fc = FederatedConsensus(member_count=5, quorum_size=3, signer=signer)
        proposal = fc.propose("alice", "test")
        for voter in ["bob", "carol", "dave"]:
            fc.vote(proposal.proposal_id, voter, VoteChoice.APPROVE, signer=signer)
        for vote in proposal.votes:
            assert vote.verify_signature(signer.public_key_pem) is True


class TestConsensusTopology:
    """Tests for F1: ConsensusTopology (FLAT / LEADER_WORKER)."""

    def test_default_topology_is_flat(self) -> None:
        fc = FederatedConsensus()
        assert fc.topology == ConsensusTopology.FLAT
        assert fc.topology.value == "flat"

    def test_flat_proposal_marks_topology(self) -> None:
        fc = FederatedConsensus(topology=ConsensusTopology.FLAT)
        proposal = fc.propose("m1", "routine")
        assert proposal.topology == ConsensusTopology.FLAT
        assert proposal.is_critical is False

    def test_leader_worker_proposal_topology(self) -> None:
        fc = FederatedConsensus(
            topology=ConsensusTopology.LEADER_WORKER,
            leader_id="leader-1",
        )
        proposal = fc.propose("worker-1", "routine")
        assert proposal.topology == ConsensusTopology.LEADER_WORKER

    def test_routine_proposal_default_not_critical(self) -> None:
        fc = FederatedConsensus(
            topology=ConsensusTopology.LEADER_WORKER,
            leader_id="leader-1",
        )
        proposal = fc.propose("worker-1", "routine-task")
        assert proposal.is_critical is False

    def test_critical_topic_matches_substring(self) -> None:
        fc = FederatedConsensus(
            topology=ConsensusTopology.LEADER_WORKER,
            leader_id="leader-1",
            critical_topics={"cross-border-transfer", "payment"},
        )
        proposal = fc.propose("worker-1", "payment:cross-border")
        assert proposal.is_critical is True

    def test_explicit_is_critical_overrides_topic(self) -> None:
        fc = FederatedConsensus(
            topology=ConsensusTopology.LEADER_WORKER,
            leader_id="leader-1",
        )
        proposal = fc.propose("worker-1", "routine-task", is_critical=True)
        assert proposal.is_critical is True

    def test_to_dict_contains_topology(self) -> None:
        fc = FederatedConsensus(topology=ConsensusTopology.FLAT)
        proposal = fc.propose("m1", "test")
        d = proposal.to_dict()
        assert d["topology"] == "flat"
        assert d["is_critical"] is False

    def test_summary_contains_topology(self) -> None:
        fc = FederatedConsensus(
            topology=ConsensusTopology.LEADER_WORKER,
            leader_id="leader-1",
        )
        s = fc.summary()
        assert s["topology"] == "leader_worker"
        assert s["leader_id"] == "leader-1"


class TestLeaderWorkerResolution:
    """LEADER_WORKER: leader arbitrates routine, quorum escalates critical."""

    def _consensus(self, leader: str = "leader-1") -> FederatedConsensus:
        return FederatedConsensus(
            member_count=5,
            quorum_size=3,
            topology=ConsensusTopology.LEADER_WORKER,
            leader_id=leader,
        )

    def test_routine_awaits_leader_vote(self) -> None:
        fc = self._consensus()
        proposal = fc.propose("worker-1", "routine-task")
        # Only a worker voted — leader arbitration pending
        fc.vote(proposal.proposal_id, "worker-2", VoteChoice.APPROVE)
        result = fc.resolve(proposal.proposal_id)
        assert result.state == ProposalState.OPEN

    def test_routine_leader_approve_resolves(self) -> None:
        fc = self._consensus()
        proposal = fc.propose("worker-1", "routine-task")
        # v0.50 W6-S3: leader arbitration still requires quorum support.
        fc.vote(proposal.proposal_id, "leader-1", VoteChoice.APPROVE)
        fc.vote(proposal.proposal_id, "worker-2", VoteChoice.APPROVE)
        fc.vote(proposal.proposal_id, "worker-3", VoteChoice.APPROVE)
        result = fc.resolve(proposal.proposal_id)
        assert result.state == ProposalState.ACCEPTED

    def test_routine_leader_reject_resolves(self) -> None:
        fc = self._consensus()
        proposal = fc.propose("worker-1", "routine-task")
        # v0.50 W6-S3: leader arbitration still requires quorum support.
        fc.vote(proposal.proposal_id, "leader-1", VoteChoice.REJECT)
        fc.vote(proposal.proposal_id, "worker-2", VoteChoice.REJECT)
        fc.vote(proposal.proposal_id, "worker-3", VoteChoice.REJECT)
        result = fc.resolve(proposal.proposal_id)
        assert result.state == ProposalState.REJECTED

    def test_routine_resolves_below_quorum(self) -> None:
        # v0.50 W6-S3: leader arbitration needs quorum (>= quorum_size
        # votes); a lone leader vote must not resolve a routine proposal.
        fc = self._consensus()
        proposal = fc.propose("worker-1", "routine-task")
        fc.vote(proposal.proposal_id, "leader-1", VoteChoice.APPROVE)
        result = fc.resolve(proposal.proposal_id)
        assert result.approve_count == 1
        assert result.state == ProposalState.OPEN

    def test_critical_escalates_to_quorum(self) -> None:
        fc = self._consensus()
        proposal = fc.propose(
            "worker-1",
            "cross-border-transfer",
            is_critical=True,
        )
        # Leader alone is insufficient for critical decisions
        fc.vote(proposal.proposal_id, "leader-1", VoteChoice.APPROVE)
        result = fc.resolve(proposal.proposal_id)
        assert result.state == ProposalState.OPEN

    def test_critical_quorum_reached_accepts(self) -> None:
        fc = self._consensus()
        proposal = fc.propose(
            "worker-1",
            "payment:cross-border",
            is_critical=True,
        )
        fc.vote(proposal.proposal_id, "leader-1", VoteChoice.APPROVE)
        fc.vote(proposal.proposal_id, "worker-2", VoteChoice.APPROVE)
        fc.vote(proposal.proposal_id, "worker-3", VoteChoice.APPROVE)
        result = fc.resolve(proposal.proposal_id)
        assert result.state == ProposalState.ACCEPTED

    def test_critical_quorum_rejects(self) -> None:
        fc = self._consensus()
        proposal = fc.propose("worker-1", "pay", is_critical=True)
        fc.vote(proposal.proposal_id, "worker-1", VoteChoice.REJECT)
        fc.vote(proposal.proposal_id, "worker-2", VoteChoice.REJECT)
        fc.vote(proposal.proposal_id, "worker-3", VoteChoice.REJECT)
        result = fc.resolve(proposal.proposal_id)
        assert result.state == ProposalState.REJECTED

    def test_worker_approve_below_quorum_stays_open(self) -> None:
        fc = self._consensus()
        proposal = fc.propose("worker-1", "routine-task")
        # Worker votes don't resolve a routine task — leader decides
        fc.vote(proposal.proposal_id, "worker-1", VoteChoice.APPROVE)
        fc.vote(proposal.proposal_id, "worker-2", VoteChoice.APPROVE)
        result = fc.resolve(proposal.proposal_id)
        assert result.state == ProposalState.OPEN


class TestFederationRoleAssignment:
    """F1 role assignment via JurisdictionPolicyRouter."""

    def _router(self) -> Any:
        from maref.federation.jurisdiction_router import JurisdictionPolicyRouter
        return JurisdictionPolicyRouter()

    def test_leader_designated(self) -> None:
        router = self._router()
        roles = router.assign_federation_roles(["leader-1", "w1", "w2"], "leader-1")
        assert roles["leader-1"] == FederationRole.LEADER

    def test_others_are_workers(self) -> None:
        router = self._router()
        roles = router.assign_federation_roles(["leader-1", "w1", "w2"], "leader-1")
        assert roles["w1"] == FederationRole.WORKER
        assert roles["w2"] == FederationRole.WORKER

    def test_deterministic(self) -> None:
        router = self._router()
        a = router.assign_federation_roles(["m1", "m2", "m3"], "m2")
        b = router.assign_federation_roles(["m1", "m2", "m3"], "m2")
        assert {k: v.value for k, v in a.items()} == {k: v.value for k, v in b.items()}

    def test_missing_leader_has_no_role(self) -> None:
        router = self._router()
        roles = router.assign_federation_roles(["m1", "m2"], "ghost")
        assert set(roles) == {"m1", "m2"}
        assert all(r == FederationRole.WORKER for r in roles.values())

    def test_suggest_topology_for_critical_uses_flat(self) -> None:
        router = self._router()
        assert router.suggest_consensus_topology(critical_topic=True) == "flat"

    def test_suggest_topology_for_routine_uses_leader_worker(self) -> None:
        router = self._router()
        assert router.suggest_consensus_topology(critical_topic=False) == "leader_worker"


class TestLeaderWorkerValidation:
    def test_leader_worker_requires_leader_id(self) -> None:
        with pytest.raises(ValueError, match="leader_id"):
            FederatedConsensus(
                topology=ConsensusTopology.LEADER_WORKER,
            )

    def test_flat_does_not_require_leader(self) -> None:
        fc = FederatedConsensus(topology=ConsensusTopology.FLAT)
        assert fc.topology == ConsensusTopology.FLAT
