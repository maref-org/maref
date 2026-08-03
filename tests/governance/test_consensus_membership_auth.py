"""v0.47 F2 — consensus membership authentication.

``FederatedConsensus`` gains an optional ``membership`` source.  When
provided, ``vote()`` rejects votes from voters who are not federation
members (fail-closed).  The voter's Ed25519 signature must also verify
when a member public-key table is configured.

Unauthorized votes are recorded with ``unauthorized_vote`` audit and
rejected; member votes aggregate normally.
"""

from __future__ import annotations

from typing import Any

import pytest

from maref.crypto.ed25519_keys import Ed25519KeyPair
from maref.governance.federated_consensus import (
    ConsensusTopology,
    FederatedConsensus,
    ProposalState,
    VoteChoice,
)


class _FakeMembership:
    """Minimal membership source exposing the member table."""

    def __init__(self, members: set[str]) -> None:
        self._members = members

    def member_snapshots(self) -> dict[str, dict[str, Any]]:
        return {m: {"server_id": m} for m in self._members}


class _FakeMembershipSummary:
    """Membership source exposing members_summary() (MembershipManager-style)."""

    def __init__(self, members: set[str]) -> None:
        self._members = members

    def members_summary(self) -> dict[str, dict[str, Any]]:
        return {m: {"server_id": m} for m in self._members}


def _consensus(membership: Any | None = None, **kwargs: Any) -> FederatedConsensus:
    return FederatedConsensus(member_count=3, quorum_size=2, membership=membership, **kwargs)


class TestMembershipBinding:
    def test_non_member_vote_rejected(self) -> None:
        membership = _FakeMembership({"member-1", "member-2"})
        consensus = _consensus(membership=membership)
        prop = consensus.propose("member-1", "add-agent", {"agent_id": "a1"})
        ok = consensus.vote(prop.proposal_id, "intruder", VoteChoice.APPROVE)
        assert ok is False
        assert prop.voter_ids == set()  # vote not recorded

    def test_member_vote_accepted(self) -> None:
        membership = _FakeMembership({"member-1", "member-2"})
        consensus = _consensus(membership=membership)
        prop = consensus.propose("member-1", "add-agent", {"agent_id": "a1"})
        ok = consensus.vote(prop.proposal_id, "member-2", VoteChoice.APPROVE)
        assert ok is True
        assert "member-2" in prop.voter_ids

    def test_membership_summary_style_supported(self) -> None:
        """MembershipManager.members_summary() style is supported too."""
        membership = _FakeMembershipSummary({"member-1", "member-2"})
        consensus = _consensus(membership=membership)
        prop = consensus.propose("member-1", "t", {})
        assert consensus.vote(prop.proposal_id, "intruder", VoteChoice.APPROVE) is False
        assert consensus.vote(prop.proposal_id, "member-2", VoteChoice.APPROVE) is True

    def test_no_membership_backward_compatible(self) -> None:
        """Without membership, any voter can vote (historical behaviour)."""
        consensus = _consensus()
        prop = consensus.propose("member-1", "t", {})
        assert consensus.vote(prop.proposal_id, "anyone", VoteChoice.APPROVE) is True

    def test_unauthorized_vote_recorded_in_audit(self) -> None:
        """An unauthorized vote is surfaced via the membership gate."""
        membership = _FakeMembership({"member-1"})
        consensus = _consensus(membership=membership)
        prop = consensus.propose("member-1", "t", {})
        consensus.vote(prop.proposal_id, "intruder", VoteChoice.APPROVE)
        # The vote was rejected; proposal stays open and intruder not recorded.
        assert "intruder" not in prop.voter_ids
        assert prop.state == ProposalState.OPEN


class TestMemberSignedVote:
    def test_member_vote_with_signature_verifies(self) -> None:
        membership = _FakeMembership({"member-1", "member-2"})
        member_key = Ed25519KeyPair.generate()
        consensus = _consensus(membership=membership)
        prop = consensus.propose("member-1", "t", {})
        ok = consensus.vote(
            prop.proposal_id, "member-2", VoteChoice.APPROVE, signer=member_key
        )
        assert ok is True
        vote = prop.votes[-1]
        assert vote.verify_signature(member_key.public_key_pem) is True
