from __future__ import annotations

from maref.recursive.distributed_bft import (
    BFTNode,
    ConsensusResult,
    DistributedBFT,
    NodeStatus,
    Vote,
)


class TestDistributedBFTInit:
    def test_default_init_7_nodes(self):
        bft = DistributedBFT(7)
        assert bft.f == 2
        assert bft.quorum == 5

    def test_init_4_nodes(self):
        bft = DistributedBFT(4)
        assert bft.f == 1
        assert bft.quorum == 3

    def test_init_10_nodes(self):
        bft = DistributedBFT(10)
        assert bft.f == 3
        assert bft.quorum == 7


class TestNodeRegistration:
    def test_register_single_node(self):
        bft = DistributedBFT(7)
        node = bft.register_node("node_1", 0.8)
        assert node.node_id == "node_1"
        assert node.credit_score == 0.8

    def test_register_multiple_nodes(self):
        bft = DistributedBFT(7)
        nodes = bft.register_nodes(7, "n")
        assert len(nodes) == 7
        assert bft.total_nodes == 7

    def test_node_weight_by_credit(self):
        bft = DistributedBFT(7)
        node = bft.register_node("node_1", 0.9)
        assert node.vote_weight > 0.5


class TestByzantineSetup:
    def test_set_byzantine(self):
        bft = DistributedBFT(7)
        bft.register_nodes(7, "n")
        result = bft.set_byzantine("n_0")
        assert result
        assert bft.byzantine_count == 1

    def test_cannot_exceed_f_byzantine(self):
        bft = DistributedBFT(7)
        bft.register_nodes(7, "n")
        bft.set_byzantine("n_0")
        bft.set_byzantine("n_1")
        result = bft.set_byzantine("n_2")
        assert not result
        assert bft.byzantine_count == 2

    def test_set_honest(self):
        bft = DistributedBFT(7)
        bft.register_nodes(7, "n")
        bft.set_byzantine("n_0")
        bft.set_honest("n_0")
        assert bft.byzantine_count == 0

    def test_set_degraded(self):
        bft = DistributedBFT(7)
        bft.register_nodes(7, "n")
        bft.set_degraded("n_0")
        node = bft.get_node("n_0")
        assert node.status == NodeStatus.DEGRADED

    def test_byzantine_weight_zero(self):
        bft = DistributedBFT(7)
        node = bft.register_node("biz", 0.5)
        bft.set_byzantine("biz")
        assert node.vote_weight == 0.0


class TestConsensusFlow:
    def test_propose_consensus(self):
        bft = DistributedBFT(7)
        r = bft.propose_consensus("value_v1")
        assert r.proposal_value == "value_v1"

    def test_cast_vote(self):
        bft = DistributedBFT(7)
        bft.register_nodes(7, "n")
        bft.propose_consensus("test")
        vote = bft.cast_vote(0, "n_1", "test")
        assert vote is not None
        assert vote.value == "test"

    def test_byzantine_vote_spoofed(self):
        bft = DistributedBFT(7)
        bft.register_nodes(7, "n")
        bft.set_byzantine("n_0")
        bft.propose_consensus("honest_value")
        vote = bft.cast_vote(0, "n_0", "honest_value")
        assert vote is not None
        assert "byzantine_spoof" in vote.value

    def test_check_quorum(self):
        bft = DistributedBFT(7)
        bft.register_nodes(7, "n")
        bft.propose_consensus("test")
        for i in range(7):
            bft.cast_vote(0, f"n_{i}", "test")
        assert bft.check_quorum(0)

    def test_quorum_with_byzantine(self):
        bft = DistributedBFT(7)
        bft.register_nodes(7, "n")
        bft.set_byzantine("n_0")
        bft.set_byzantine("n_1")
        bft.propose_consensus("test")
        for i in range(7):
            bft.cast_vote(0, f"n_{i}", "test")
        assert bft.check_quorum(0)


class TestReachConsensus:
    def test_reach_consensus_all_honest(self):
        bft = DistributedBFT(7)
        bft.register_nodes(7, "n")
        bft.propose_consensus("agree_value")
        for i in range(7):
            bft.cast_vote(0, f"n_{i}", "agree_value")
        result = bft.reach_consensus(0)
        assert result == ConsensusResult.REACHED

    def test_reach_consensus_with_f_byzantine(self):
        bft = DistributedBFT(7)
        bft.register_nodes(7, "n")
        bft.set_byzantine("n_0")
        bft.set_byzantine("n_1")
        bft.propose_consensus("correct_value")
        for i in range(7):
            bft.cast_vote(0, f"n_{i}", "correct_value")
        result = bft.reach_consensus(0)
        assert result == ConsensusResult.REACHED

    def test_consensus_fails_without_quorum(self):
        bft = DistributedBFT(7)
        bft.register_nodes(7, "n")
        bft.set_byzantine("n_0")
        bft.set_byzantine("n_1")
        bft.propose_consensus("test")
        for i in range(4):
            bft.cast_vote(0, f"n_{i}", "test")
        result = bft.reach_consensus(0)
        assert result == ConsensusResult.FAILED


class TestConsensusCycle:
    def test_run_consensus_cycle(self):
        bft = DistributedBFT(7)
        bft.register_nodes(7, "n")
        r = bft.run_consensus_cycle("cycle_value")
        assert r.result == ConsensusResult.REACHED

    def test_run_cycle_with_byzantine(self):
        bft = DistributedBFT(7)
        bft.register_nodes(7, "n")
        bft.set_byzantine("n_0")
        bft.set_byzantine("n_1")
        r = bft.run_consensus_cycle("distributed_truth")
        assert r.result == ConsensusResult.REACHED

    def test_verify_byzantine_tolerance(self):
        bft = DistributedBFT(7)
        bft.register_nodes(7, "n")
        bft.set_byzantine("n_0")
        bft.set_byzantine("n_1")
        report = bft.verify_byzantine_tolerance("global_truth")
        assert report["consensus_reached"]
        assert report["tolerance_intact"]


class TestQueryAndSerialization:
    def test_get_node(self):
        bft = DistributedBFT(7)
        bft.register_node("special", 0.75)
        node = bft.get_node("special")
        assert node is not None

    def test_get_all_nodes(self):
        bft = DistributedBFT(7)
        bft.register_nodes(7, "n")
        nodes = bft.get_all_nodes()
        assert len(nodes) == 7

    def test_get_round(self):
        bft = DistributedBFT(7)
        bft.register_nodes(7, "n")
        bft.run_consensus_cycle("test")
        r = bft.get_round(0)
        assert r is not None
        assert r.result == ConsensusResult.REACHED

    def test_get_consensus_history(self):
        bft = DistributedBFT(7)
        bft.register_nodes(7, "n")
        bft.run_consensus_cycle("v1")
        bft.run_consensus_cycle("v2")
        history = bft.get_consensus_history()
        assert len(history) == 2

    def test_to_dict(self):
        bft = DistributedBFT(7)
        bft.register_nodes(7, "n")
        bft.run_consensus_cycle("test")
        d = bft.to_dict()
        assert d["f"] == 2
        assert d["quorum"] == 5
        assert "nodes" in d
        assert "consensus_reached" in d

    def test_node_to_dict(self):
        node = BFTNode("n1", 0.7)
        d = node.to_dict()
        assert d["node_id"] == "n1"
        assert d["status"] == "honest"


class TestToleranceBoundaries:
    def test_exact_byzantine_limit(self):
        bft = DistributedBFT(7)
        bft.register_nodes(7, "n")
        for i in range(bft.f):
            bft.set_byzantine(f"n_{i}")
        r = bft.run_consensus_cycle("boundary_test")
        assert r.result == ConsensusResult.REACHED


class TestEdgeCases:
    def test_set_byzantine_nonexistent_node(self):
        bft = DistributedBFT(7)
        result = bft.set_byzantine("ghost_node")
        assert not result

    def test_set_honest_nonexistent_node(self):
        bft = DistributedBFT(7)
        result = bft.set_honest("ghost_node")
        assert not result

    def test_cast_vote_invalid_round(self):
        bft = DistributedBFT(7)
        vote = bft.cast_vote(99, "node_0", "test")
        assert vote is None

    def test_cast_vote_offline_node(self):
        bft = DistributedBFT(7)
        bft.register_node("offline_n", 0.5)
        node = bft.get_node("offline_n")
        node.status = NodeStatus.OFFLINE
        bft.propose_consensus("test")
        vote = bft.cast_vote(0, "offline_n", "test")
        assert vote is None

    def test_reach_consensus_invalid_round(self):
        bft = DistributedBFT(7)
        result = bft.reach_consensus(99)
        assert result == ConsensusResult.FAILED

    def test_get_round_out_of_bounds(self):
        bft = DistributedBFT(7)
        assert bft.get_round(0) is None

    def test_propose_with_proposer(self):
        bft = DistributedBFT(7)
        r = bft.propose_consensus("v1", proposer_id="leader_0")
        assert r.proposal_value == "v1"

    def test_vote_to_dict(self):
        vote = Vote("n1", "val", 1)
        d = vote.to_dict()
        assert d["node_id"] == "n1"
        assert d["value"] == "val"
        assert d["round"] == 1

    def test_vote_byzantine_to_dict(self):
        vote = Vote("n1", "val", 1, is_byzantine=True)
        d = vote.to_dict()
        assert d["is_byzantine"] is True
