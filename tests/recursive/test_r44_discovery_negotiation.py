from __future__ import annotations

from maref.recursive.agent_24_state_machine import Agent24StateMachine
from maref.recursive.agent_discovery_negotiation import (
    AgentDiscovery,
    AgentNegotiator,
    TrustEstablishment,
)


class TestAgentDiscovery:
    def setup_method(self) -> None:
        self.sm = Agent24StateMachine()
        self.discovery = AgentDiscovery(self.sm)

    def test_discover(self) -> None:
        msg = self.discovery.discover("agent_1", ["search", "compute"])
        assert msg.source_id == "agent_1"
        assert "search" in msg.source_capabilities

    def test_register_peer(self) -> None:
        peer = self.discovery.register_peer("peer_1", ["analyze"], trust=0.7)
        assert peer.agent_id == "peer_1"
        assert "analyze" in peer.capabilities

    def test_find_peers_with_capability(self) -> None:
        self.discovery.register_peer("p1", ["compute"])
        self.discovery.register_peer("p2", ["search"])
        found = self.discovery.find_peers_with_capability("compute")
        assert len(found) == 1
        assert found[0].agent_id == "p1"

    def test_list_active_peers(self) -> None:
        self.discovery.register_peer("p1", ["x"])
        self.discovery.register_peer("p2", ["y"])
        assert len(self.discovery.list_active_peers()) == 2

    def test_update_trust(self) -> None:
        self.discovery.register_peer("p1", ["x"])
        self.discovery.update_trust("p1", 0.2)
        peers = self.discovery.list_active_peers()
        assert peers[0].trust_estimate == 0.7

    def test_deactivate_peer(self) -> None:
        self.discovery.register_peer("p1", ["x"])
        self.discovery.deactivate_peer("p1")
        assert len(self.discovery.list_active_peers()) == 0


class TestAgentNegotiator:
    def setup_method(self) -> None:
        self.negotiator = AgentNegotiator()

    def test_propose(self) -> None:
        proposal = self.negotiator.propose(
            "agent_a", "agent_b", "task_assign",
            {"task": "search", "reward": 10.0},
            trust_level=0.5,
        )
        assert proposal.source_id == "agent_a"
        assert proposal.proposal_type == "task_assign"

    def test_evaluate_accept(self) -> None:
        proposal = self.negotiator.propose(
            "a", "b", "collaboration", {"scope": "full"},
        )
        result = self.negotiator.evaluate(proposal, 0.8)
        assert result.accepted

    def test_evaluate_reject_low_trust(self) -> None:
        proposal = self.negotiator.propose("a", "b", "task", {})
        result = self.negotiator.evaluate(proposal, 0.1)
        assert not result.accepted

    def test_evaluate_reject_counterparty_min(self) -> None:
        proposal = self.negotiator.propose(
            "a", "b", "task", {}, trust_level=0.9,
        )
        result = self.negotiator.evaluate(proposal, 0.5)
        assert not result.accepted

    def test_get_result(self) -> None:
        proposal = self.negotiator.propose("a", "b", "x", {})
        result = self.negotiator.evaluate(proposal, 0.8)
        retrieved = self.negotiator.get_result(result.agreement_id)
        assert retrieved is not None
        assert retrieved.accepted

    def test_negotiation_stats(self) -> None:
        p1 = self.negotiator.propose("a", "b", "t1", {})
        p2 = self.negotiator.propose("c", "d", "t2", {})
        self.negotiator.evaluate(p1, 0.8)
        self.negotiator.evaluate(p2, 0.1)
        stats = self.negotiator.negotiation_stats()
        assert stats["total_negotiations"] == 2
        assert stats["accepted"] == 1


class TestTrustEstablishment:
    def setup_method(self) -> None:
        self.te = TrustEstablishment()

    def test_establish_trust(self) -> None:
        self.te.establish_trust("a", "b", 0.5)
        assert self.te.get_trust("a", "b") == 0.5

    def test_update_trust_up(self) -> None:
        self.te.establish_trust("a", "b", 0.5)
        self.te.update_trust("a", "b", 0.1)
        assert self.te.get_trust("a", "b") == 0.6

    def test_update_trust_down(self) -> None:
        self.te.establish_trust("a", "b", 0.5)
        self.te.update_trust("a", "b", 0.2, successful_interaction=False)
        assert self.te.get_trust("a", "b") == 0.3

    def test_mutual_trust(self) -> None:
        self.te.establish_trust("a", "b", 0.7)
        self.te.establish_trust("b", "a", 0.3)
        a_trusts, b_trusts = self.te.mutual_trust("a", "b")
        assert a_trusts == 0.7
        assert b_trusts == 0.3

    def test_trust_network(self) -> None:
        self.te.establish_trust("center", "p1", 0.5)
        self.te.establish_trust("center", "p2", 0.8)
        network = self.te.trust_network("center")
        assert len(network) == 2
