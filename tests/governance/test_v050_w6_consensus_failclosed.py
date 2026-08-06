"""
v0.50 W6-S3 — F9/F10/F13 联邦安全默认强制

覆盖：
- (a) FederationGateway require_acs_signature=True 时无签名/公钥 → 拒绝；
      有效 Ed25519 签名 → 接受
- (b) FederatedConsensus verify_vote_signatures=True 时无签名票在 resolve
      前被拒绝（提案保持 OPEN）
- (c) LEADER_WORKER 常规提案需 ≥ quorum 支持票才能由 leader 仲裁
"""

from __future__ import annotations

import json

from maref.crypto.ed25519_keys import Ed25519KeyPair
from maref.federation.gateway import FederationGateway, FederationRequest
from maref.governance.federated_consensus import (
    ConsensusTopology,
    FederatedConsensus,
    ProposalState,
    VoteChoice,
)


class TestGatewayACSRequired:
    def _make_request(self) -> FederationRequest:
        from maref.identity.aic_adapter import AIC

        aic = AIC.generate()
        doc = {
            "aic": aic.aic_string,
            "name": "agent",
            "description": "d",
            "capabilities": {},
            "securitySchemes": {},
            "endpoints": [],
            "skills": [],
        }
        return FederationRequest(
            aic_string=aic.aic_string,
            acs_document=doc,
            endpoint_url="https://example.com/api",
        )

    def test_require_signature_rejects_unsigned(self) -> None:
        gateway = FederationGateway(require_acs_signature=True)
        resp = gateway.register_agent(self._make_request())
        assert resp.success is False
        assert "signature" in resp.error.lower()

    def test_require_signature_accepts_signed(self) -> None:
        gateway = FederationGateway(require_acs_signature=True)
        request = self._make_request()
        key = Ed25519KeyPair.generate()
        payload = json.dumps(request.acs_document, sort_keys=True).encode()
        sig = key.sign(payload)
        request.acs_signature = sig.hex()
        request.acs_public_key_pem = key.public_key_pem
        resp = gateway.register_agent(request)
        assert resp.success is True

    def test_require_signature_rejects_bad_signature(self) -> None:
        gateway = FederationGateway(require_acs_signature=True)
        request = self._make_request()
        key = Ed25519KeyPair.generate()
        other = Ed25519KeyPair.generate()
        request.acs_signature = other.sign(json.dumps(request.acs_document, sort_keys=True).encode()).hex()
        request.acs_public_key_pem = key.public_key_pem
        resp = gateway.register_agent(request)
        assert resp.success is False

    def test_default_off_backwards_compatible(self) -> None:
        gateway = FederationGateway(require_acs_signature=False)
        resp = gateway.register_agent(self._make_request())
        assert resp.success is True


class TestConsensusVoteVerification:
    def test_unsigned_vote_blocks_resolution(self) -> None:
        fc = FederatedConsensus(
            member_count=3,
            quorum_size=2,
            verify_vote_signatures=True,
            voter_public_keys={},
        )
        proposal = fc.propose("proposer", "topic", {})
        assert fc.vote(proposal.proposal_id, "bob", VoteChoice.APPROVE) is True
        resolved = fc.resolve(proposal.proposal_id)
        assert resolved.state == ProposalState.OPEN

    def test_signed_vote_allows_resolution(self) -> None:
        signer = Ed25519KeyPair.generate()
        fc = FederatedConsensus(
            member_count=3,
            quorum_size=2,
            verify_vote_signatures=True,
            voter_public_keys={
                "bob": signer.public_key_pem,
                "carol": signer.public_key_pem,
            },
        )
        proposal = fc.propose("proposer", "topic", {})
        assert fc.vote(proposal.proposal_id, "bob", VoteChoice.APPROVE, signer=signer) is True
        assert fc.vote(proposal.proposal_id, "carol", VoteChoice.APPROVE, signer=signer) is True
        resolved = fc.resolve(proposal.proposal_id)
        assert resolved.state == ProposalState.ACCEPTED


class TestLeaderWorkerQuorum:
    def test_leader_cannot_resolve_below_quorum(self) -> None:
        fc = FederatedConsensus(
            member_count=4,
            quorum_size=2,
            topology=ConsensusTopology.LEADER_WORKER,
            leader_id="leader",
        )
        proposal = fc.propose("proposer", "routine", {})
        fc.vote(proposal.proposal_id, "leader", VoteChoice.APPROVE)
        resolved = fc.resolve(proposal.proposal_id)
        assert resolved.state == ProposalState.OPEN

    def test_leader_resolves_at_quorum(self) -> None:
        fc = FederatedConsensus(
            member_count=4,
            quorum_size=2,
            topology=ConsensusTopology.LEADER_WORKER,
            leader_id="leader",
        )
        proposal = fc.propose("proposer", "routine", {})
        fc.vote(proposal.proposal_id, "leader", VoteChoice.APPROVE)
        fc.vote(proposal.proposal_id, "worker", VoteChoice.APPROVE)
        resolved = fc.resolve(proposal.proposal_id)
        assert resolved.state == ProposalState.ACCEPTED
