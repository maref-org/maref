from __future__ import annotations

import time

from maref.cross_validator.consensus_algorithm import (
    ConsensusResult,
    ConsensusStatus,
    Proposal,
    ValidatorNode,
    Vote,
    VoteValue,
    WeightedConsensusEngine,
)


class TestConsensusStatus:
    def test_values(self) -> None:
        assert ConsensusStatus.PENDING.value == "pending"
        assert ConsensusStatus.REACHED.value == "reached"
        assert ConsensusStatus.FAILED.value == "failed"
        assert ConsensusStatus.INCONCLUSIVE.value == "inconclusive"
        assert ConsensusStatus.BYZANTINE_DETECTED.value == "byzantine_detected"


class TestVoteValue:
    def test_values(self) -> None:
        assert VoteValue.APPROVE.value == "approve"
        assert VoteValue.REJECT.value == "reject"
        assert VoteValue.ABSTAIN.value == "abstain"


class TestValidatorNode:
    def test_defaults(self) -> None:
        node = ValidatorNode(node_id="v1")
        assert node.node_id == "v1"
        assert node.weight == 1.0
        assert node.trust_score == 1.0
        assert node.is_byzantine is False
        assert node.is_active is True

    def test_update_weight(self) -> None:
        node = ValidatorNode(node_id="v1", weight=5.0)
        node.update_weight(3.0)
        assert node.weight == 3.0

    def test_weight_clamping(self) -> None:
        node = ValidatorNode(node_id="v1")
        node.update_weight(-1.0)
        assert node.weight == 0.0
        node.update_weight(20.0)
        assert node.weight == 10.0

    def test_penalize(self) -> None:
        node = ValidatorNode(node_id="v1", weight=1.0, trust_score=1.0)
        node.penalize(factor=0.5)
        assert node.weight == 0.5
        assert node.trust_score == 0.5
        assert len(node.reputation_history) == 1

    def test_reward(self) -> None:
        node = ValidatorNode(node_id="v1", initial_weight=1.0)
        node.reward(factor=1.5)
        assert node.weight == 1.5
        assert node.trust_score == 1.0
        assert len(node.reputation_history) == 1

    def test_to_dict(self) -> None:
        node = ValidatorNode(node_id="v1")
        d = node.to_dict()
        assert d["node_id"] == "v1"


class TestVote:
    def test_defaults(self) -> None:
        v = Vote(
            validator_id="v1",
            vote_value=VoteValue.APPROVE,
            proposal_id="p1",
            timestamp=time.time(),
        )
        assert v.justification is None
        assert v.signature is None

    def test_to_dict(self) -> None:
        v = Vote(
            validator_id="v1",
            vote_value=VoteValue.REJECT,
            proposal_id="p1",
            timestamp=1000.0,
            justification="bad idea",
        )
        d = v.to_dict()
        assert d["vote"] == "reject"
        assert d["justification"] == "bad idea"


class TestProposal:
    def test_defaults(self) -> None:
        p = Proposal(
            proposal_id="p1",
            content={"action": "deploy"},
            proposer_id="v1",
            timestamp=time.time(),
        )
        assert p.quorum_threshold == 0.67
        assert p.byzantine_threshold == 0.33

    def test_compute_hash(self) -> None:
        p = Proposal(
            proposal_id="p1",
            content={},
            proposer_id="v1",
            timestamp=1000.0,
        )
        h = p.compute_hash()
        assert isinstance(h, str)
        assert len(h) == 64

    def test_to_dict(self) -> None:
        p = Proposal(
            proposal_id="p1",
            content={"key": "val"},
            proposer_id="v1",
            timestamp=1000.0,
            quorum_threshold=0.75,
        )
        d = p.to_dict()
        assert d["proposal_id"] == "p1"
        assert d["quorum_threshold"] == 0.75


class TestConsensusResult:
    def test_defaults(self) -> None:
        cr = ConsensusResult(
            status=ConsensusStatus.PENDING,
            proposal_id="p1",
            winning_vote=None,
            approve_weight=0.0,
            reject_weight=0.0,
            abstain_weight=0.0,
            total_weight=0.0,
            participation_rate=0.0,
        )
        assert cr.byzantine_nodes_detected == []
        assert cr.confidence == 0.0

    def test_to_dict(self) -> None:
        cr = ConsensusResult(
            status=ConsensusStatus.REACHED,
            proposal_id="p1",
            winning_vote=VoteValue.APPROVE,
            approve_weight=10.0,
            reject_weight=2.0,
            abstain_weight=1.0,
            total_weight=13.0,
            participation_rate=1.0,
            confidence=0.95,
        )
        d = cr.to_dict()
        assert d["status"] == "reached"
        assert d["confidence"] == 0.95


class TestWeightedConsensusEngine:
    def test_init(self) -> None:
        engine = WeightedConsensusEngine()
        assert engine.has_validator("any") is False

    def test_register_validator(self) -> None:
        engine = WeightedConsensusEngine()
        node = engine.register_validator("v1", initial_weight=5.0)
        assert node.node_id == "v1"
        assert node.weight == 5.0
        assert engine.has_validator("v1") is True

    def test_simple_consensus(self) -> None:
        engine = WeightedConsensusEngine()
        engine.register_validator("v1", initial_weight=5.0)
        engine.register_validator("v2", initial_weight=5.0)
        engine.create_proposal("p1", {}, "v1")
        engine.cast_vote("p1", "v1", VoteValue.APPROVE)
        engine.cast_vote("p1", "v2", VoteValue.APPROVE)
        result = engine.evaluate_consensus("p1")
        assert result.status == ConsensusStatus.REACHED
        assert result.winning_vote == VoteValue.APPROVE

    def test_consensus_rejected(self) -> None:
        engine = WeightedConsensusEngine()
        engine.register_validator("v1", initial_weight=5.0)
        engine.register_validator("v2", initial_weight=5.0)
        engine.create_proposal("p1", {}, "v1")
        engine.cast_vote("p1", "v1", VoteValue.REJECT)
        engine.cast_vote("p1", "v2", VoteValue.REJECT)
        result = engine.evaluate_consensus("p1")
        assert result.winning_vote == VoteValue.REJECT

    def test_consensus_split(self) -> None:
        engine = WeightedConsensusEngine()
        engine.register_validator("v1", initial_weight=5.0)
        engine.register_validator("v2", initial_weight=5.0)
        engine.create_proposal("p1", {}, "v1")
        engine.cast_vote("p1", "v1", VoteValue.APPROVE)
        engine.cast_vote("p1", "v2", VoteValue.REJECT)
        result = engine.evaluate_consensus("p1")
        # 5 approve vs 5 reject with quorum 0.67 → inconclusive
        assert result.status == ConsensusStatus.INCONCLUSIVE

    def test_unregister_validator(self) -> None:
        engine = WeightedConsensusEngine()
        engine.register_validator("v1")
        assert engine.has_validator("v1") is True
        assert engine.unregister_validator("v1") is True
        assert engine.has_validator("v1") is False
        assert engine.unregister_validator("nonexistent") is False

    def test_evaluate_nonexistent_proposal(self) -> None:
        engine = WeightedConsensusEngine()
        result = engine.evaluate_consensus("nope")
        assert result.status == ConsensusStatus.FAILED

    def test_proposals(self) -> None:
        engine = WeightedConsensusEngine()
        assert len(engine._proposals) == 0
        engine.create_proposal("p1", {}, "v1")
        assert len(engine._proposals) == 1

    def test_consensus_history(self) -> None:
        engine = WeightedConsensusEngine()
        assert len(engine._consensus_history) == 0
