"""v0.47 F4 — FederatedConsensus SQLite persistence + restart recovery."""

from __future__ import annotations

from pathlib import Path

from maref.crypto.ed25519_keys import Ed25519KeyPair
from maref.governance.federated_consensus import (
    ConsensusProposal,
    ConsensusVote,
    FederatedConsensus,
    ProposalState,
    VoteChoice,
)


def _consensus(db_path: Path | None = None) -> FederatedConsensus:
    return FederatedConsensus(member_count=3, quorum_size=2, db_path=db_path)


class TestConsensusPersistence:
    def test_proposal_recovered_after_reload(self, tmp_path: Path) -> None:
        db = tmp_path / "consensus.db"
        consensus = _consensus(db)
        prop = consensus.propose("member-1", "add-agent", {"agent_id": "a1"})

        reloaded = _consensus(db)
        restored = reloaded.get_proposal(prop.proposal_id)
        assert restored is not None
        assert restored.topic == "add-agent"
        assert restored.payload == {"agent_id": "a1"}

    def test_votes_recovered_with_signature(self, tmp_path: Path) -> None:
        db = tmp_path / "consensus.db"
        consensus = _consensus(db)
        prop = consensus.propose("member-1", "add-agent", {"agent_id": "a1"})
        member_key = Ed25519KeyPair.generate()
        consensus.vote(prop.proposal_id, "member-2", VoteChoice.APPROVE, signer=member_key)

        reloaded = _consensus(db)
        restored = reloaded.get_proposal(prop.proposal_id)
        assert restored is not None
        assert len(restored.votes) == 1
        vote = restored.votes[0]
        assert vote.voter_id == "member-2"
        # The Ed25519 signature must survive persistence and re-verify.
        assert vote.verify_signature(member_key.public_key_pem) is True

    def test_resolved_state_recovered(self, tmp_path: Path) -> None:
        db = tmp_path / "consensus.db"
        consensus = _consensus(db)
        prop = consensus.propose("member-1", "add-agent", {"agent_id": "a1"})
        consensus.vote(prop.proposal_id, "member-2", VoteChoice.APPROVE)
        consensus.vote(prop.proposal_id, "member-3", VoteChoice.APPROVE)
        resolved = consensus.resolve(prop.proposal_id)
        assert resolved.state == ProposalState.ACCEPTED

        reloaded = _consensus(db)
        restored = reloaded.get_proposal(prop.proposal_id)
        assert restored.state == ProposalState.ACCEPTED

    def test_no_db_path_in_memory(self) -> None:
        consensus = _consensus()
        prop = consensus.propose("member-1", "t", {})
        assert consensus.get_proposal(prop.proposal_id) is not None


class TestConsensusSerialization:
    def test_vote_to_from_dict_roundtrip(self) -> None:
        key = Ed25519KeyPair.generate()
        vote = ConsensusVote(
            voter_id="m1",
            choice=VoteChoice.APPROVE,
            proposal_id="p1",
        )
        from maref.crypto.ed25519_keys import Ed25519KeyPair as _K

        vote.signature = key.sign(vote.message_to_sign).hex()
        vote.signer_fingerprint = key.fingerprint
        restored = ConsensusVote.from_dict(vote.to_dict())
        assert restored.voter_id == "m1"
        assert restored.signature == vote.signature
        assert restored.verify_signature(key.public_key_pem) is True
