"""v0.48 W3 — federated production assembly of v0.47 governance gates.

``create_default_federation`` gains optional wiring so a production
platform closes the loop without manual assembly:
  - trusted_peer_public_keys → FederatedTrustEngine (S4 report signing);
  - boundary → FederatedPlanExecutor (F3 dispatch gate);
  - membership → FederatedConsensus (F2 voter authentication).
"""

from __future__ import annotations

from maref.crypto.ed25519_keys import Ed25519KeyPair
from maref.federation import create_default_federation
from maref.governance.trust_boundary import TrustBoundaryManager
from maref.orchestration.federated_plan_executor import FederatedPlanExecutor


def _membership_source(members: set[str]) -> object:
    class _M:
        def members_summary(self):
            return {m: {"server_id": m} for m in members}

    return _M()


class TestFederationAssembly:
    def test_trust_engine_wired_with_peer_keys(self) -> None:
        key = Ed25519KeyPair.generate()
        platform = create_default_federation(
            server_id="w3-test",
            trusted_peer_public_keys={"org-beta": key.public_key_pem},
        )
        assert platform.trust_engine.trusted_peer_count == 1

    def test_boundary_wired_into_executor(self) -> None:
        boundary = TrustBoundaryManager()
        platform = create_default_federation(server_id="w3-test")
        executor = FederatedPlanExecutor(platform=platform, boundary=boundary)
        assert executor._boundary is boundary

    def test_consensus_membership_wired(self) -> None:
        membership = _membership_source({"member-1", "member-2"})
        platform = create_default_federation(
            server_id="w3-test",
            consensus_membership=membership,
        )
        # A non-member vote is rejected via the wired membership.
        proposal = platform.consensus.propose("member-1", "add-agent", {"agent_id": "a1"})
        from maref.governance.federated_consensus import VoteChoice

        assert platform.consensus.vote(proposal.proposal_id, "intruder", VoteChoice.APPROVE) is False
        assert platform.consensus.vote(proposal.proposal_id, "member-2", VoteChoice.APPROVE) is True

    def test_default_assembly_backward_compatible(self) -> None:
        platform = create_default_federation(server_id="w3-default")
        assert platform.trust_engine.trusted_peer_count == 0
