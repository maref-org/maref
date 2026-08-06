from __future__ import annotations

import time
from collections import defaultdict
from unittest.mock import MagicMock, patch

from maref.security.byzantine_enhancer import (
    ByzantineIsolationEnhancer,
    IsolationDecision,
)


class TestIsolationDecision:
    def test_construction(self) -> None:
        d = IsolationDecision(
            node_id="node1",
            is_isolated=True,
            reason="byzantine behavior",
            confidence=0.85,
        )
        assert d.node_id == "node1"
        assert d.is_isolated is True
        assert d.reason == "byzantine behavior"
        assert d.confidence == 0.85
        assert d.timestamp > 0

    def test_to_dict(self) -> None:
        d = IsolationDecision(
            node_id="node1",
            is_isolated=True,
            reason="bad votes",
            confidence=0.756,
            timestamp=1000.0,
        )
        dumped = d.to_dict()
        assert dumped["node_id"] == "node1"
        assert dumped["is_isolated"] is True
        assert dumped["reason"] == "bad votes"
        assert dumped["confidence"] == 0.756

    def test_to_dict_not_isolated(self) -> None:
        d = IsolationDecision(
            node_id="node2",
            is_isolated=False,
            reason="",
            confidence=0.0,
        )
        dumped = d.to_dict()
        assert dumped["is_isolated"] is False


class FakeVote:
    def __init__(
        self, validator_id: str, vote_value: str, timestamp: float = 0.0
    ) -> None:
        self.validator_id = validator_id
        self.vote_value = vote_value
        self.timestamp = timestamp


class FakeValidator:
    def __init__(
        self,
        node_id: str,
        weight: float = 1.0,
        initial_weight: float = 1.0,
        is_byzantine: bool = False,
        is_active: bool = True,
    ) -> None:
        self.node_id = node_id
        self.weight = weight
        self.initial_weight = initial_weight
        self.is_byzantine = is_byzantine
        self.is_active = is_active


class TestByzantineIsolationEnhancer:
    def _make_engine(self, validators: dict | None = None) -> MagicMock:
        engine = MagicMock()
        engine._validators = validators or {}
        engine._votes = {}
        return engine

    def test_initial_construction(self) -> None:
        engine = self._make_engine()
        enhancer = ByzantineIsolationEnhancer(engine)
        assert enhancer._isolated_nodes == set()
        assert enhancer._vote_history == {}
        assert enhancer._weight_history == {}

    def test_evaluate_proposal_delegates_to_engine(self) -> None:
        engine = self._make_engine()
        enhancer = ByzantineIsolationEnhancer(engine)

        mock_result = MagicMock()
        mock_result.status = "reached"
        mock_result.byzantine_nodes_detected = []
        engine.evaluate_consensus.return_value = mock_result

        result = enhancer.evaluate_proposal("prop-1")
        engine.evaluate_consensus.assert_called_once_with("prop-1")
        assert result.status == "reached"

    def test_detect_inconsistent_voters(self) -> None:
        now = time.time()
        validators = {
            "bad-node": FakeValidator("bad-node", weight=0.2, initial_weight=1.0),
            "good-node": FakeValidator("good-node", weight=1.0, initial_weight=1.0),
        }
        engine = self._make_engine(validators)

        class VoteValue:
            APPROVE = "approve"
            REJECT = "reject"
            ABSTAIN = "abstain"

        enhancer = ByzantineIsolationEnhancer(engine)
        enhancer._vote_history = defaultdict(
            list,
            {
                "bad-node": [
                    FakeVote("bad-node", VoteValue.REJECT, now - 100 + i)
                    for i in range(5)
                ],
                "good-node": [
                    FakeVote("good-node", VoteValue.APPROVE, now - 50 + i)
                    for i in range(3)
                ],
            },
        )
        enhancer._weight_history = defaultdict(
            list,
            {
                "bad-node": [(now - 100, 0.2), (now - 50, 0.2)],
                "good-node": [(now - 50, 1.0)],
            },
        )

        mock_result = MagicMock()
        mock_result.status = "inconclusive"
        mock_result.byzantine_nodes_detected = []
        engine.evaluate_consensus.return_value = mock_result

        all_approve_votes = [
            FakeVote("bad-node", VoteValue.REJECT, now),
            FakeVote("good-node", VoteValue.APPROVE, now),
        ]
        engine._votes = {"prop-1": all_approve_votes}

        with patch(
            "maref.security.byzantine_enhancer.VoteValue",
            APPROVE="approve",
            REJECT="reject",
            ABSTAIN="abstain",
        ):
            result = enhancer.evaluate_proposal("prop-1")

        assert "bad-node" in result.byzantine_nodes_detected
        assert "good-node" not in result.byzantine_nodes_detected

    def test_detect_weight_anomaly(self) -> None:
        validators = {
            "weight-node": FakeValidator(
                "weight-node", weight=0.1, initial_weight=1.0
            ),
            "other": FakeValidator("other", weight=1.0, initial_weight=1.0),
        }
        engine = self._make_engine(validators)

        enhancer = ByzantineIsolationEnhancer(engine)

        enhancer._vote_history = defaultdict(
            list,
            {
                "weight-node": [
                    FakeVote("weight-node", "approve", 100.0),
                    FakeVote("weight-node", "approve", 100.3),
                    FakeVote("weight-node", "approve", 100.6),
                ],
                "other": [
                    FakeVote("other", "approve", 100.0),
                ],
            },
        )
        enhancer._weight_history = defaultdict(
            list,
            {
                "weight-node": [
                    (100.0, 0.1),
                    (101.0, 0.1),
                ],
                "other": [
                    (100.0, 1.0),
                ],
            },
        )

        votes = [
            FakeVote("weight-node", "approve", 200.0),
            FakeVote("other", "approve", 200.0),
        ]

        decisions = enhancer._detect_multidimensional(votes)
        weight_decisions = [d for d in decisions if "Weight anomaly" in d.reason]
        assert len(weight_decisions) >= 1

    def test_detect_temporal_pattern(self) -> None:
        validators = {
            "fast-node": FakeValidator("fast-node", weight=0.2, initial_weight=1.0),
            "other": FakeValidator("other", weight=1.0, initial_weight=1.0),
        }
        engine = self._make_engine(validators)

        enhancer = ByzantineIsolationEnhancer(engine)

        enhancer._vote_history = defaultdict(
            list,
            {
                "fast-node": [
                    FakeVote("fast-node", "approve", 100.0),
                    FakeVote("fast-node", "approve", 100.2),
                    FakeVote("fast-node", "approve", 100.4),
                ],
                "other": [
                    FakeVote("other", "approve", 100.0),
                ],
            },
        )
        enhancer._weight_history = defaultdict(
            list,
            {
                "fast-node": [(100.0, 0.2), (101.0, 0.2)],
                "other": [(100.0, 1.0)],
            },
        )

        votes = [
            FakeVote("fast-node", "approve", 100.6),
            FakeVote("other", "approve", 200.0),
        ]

        decisions = enhancer._detect_multidimensional(votes)
        temporal_decisions = [d for d in decisions if "Temporal anomaly" in d.reason]
        assert len(temporal_decisions) >= 1

    def test_detect_multidimensional_no_detection_for_good_node(self) -> None:
        validators = {
            "good-node": FakeValidator("good-node", weight=1.0, initial_weight=1.0),
        }
        engine = self._make_engine(validators)

        enhancer = ByzantineIsolationEnhancer(engine)
        enhancer._vote_history = defaultdict(
            list,
            {
                "good-node": [
                    FakeVote("good-node", "approve", 100.0),
                    FakeVote("good-node", "approve", 110.0),
                ],
            },
        )
        enhancer._weight_history = defaultdict(
            list,
            {
                "good-node": [(100.0, 1.0)],
            },
        )

        votes = [FakeVote("good-node", "approve", 120.0)]

        decisions = enhancer._detect_multidimensional(votes)
        assert len(decisions) == 0

    def test_detect_multidimensional_unknown_validator_skipped(self) -> None:
        engine = self._make_engine({})
        enhancer = ByzantineIsolationEnhancer(engine)
        votes = [FakeVote("unknown", "approve", 100.0)]
        decisions = enhancer._detect_multidimensional(votes)
        assert decisions == []

    def test_isolate_node_sets_weight_zero(self) -> None:
        validator = FakeValidator(
            "node1", weight=1.0, is_byzantine=False, is_active=True
        )
        engine = self._make_engine({"node1": validator})
        enhancer = ByzantineIsolationEnhancer(engine)

        enhancer._isolate_node("node1")
        assert validator.weight == 0.0
        assert validator.is_byzantine is True
        assert validator.is_active is False
        assert "node1" in enhancer._isolated_nodes

    def test_isolate_node_missing_validator(self) -> None:
        engine = self._make_engine({})
        enhancer = ByzantineIsolationEnhancer(engine)
        enhancer._isolate_node("missing")
        assert "missing" in enhancer._isolated_nodes

    def test_restore_node_success(self) -> None:
        validator = FakeValidator("node1", weight=0.0, initial_weight=10.0)
        engine = self._make_engine({"node1": validator})
        enhancer = ByzantineIsolationEnhancer(engine)
        enhancer._isolated_nodes.add("node1")

        result = enhancer.restore_node("node1")
        assert result is True
        assert validator.is_byzantine is False
        assert validator.is_active is True
        assert validator.weight == 10.0 * 0.1
        assert "node1" not in enhancer._isolated_nodes

    def test_restore_node_not_isolated(self) -> None:
        engine = self._make_engine({})
        enhancer = ByzantineIsolationEnhancer(engine)
        result = enhancer.restore_node("never-isolated")
        assert result is False

    def test_restore_node_missing_validator(self) -> None:
        engine = self._make_engine({})
        enhancer = ByzantineIsolationEnhancer(engine)
        enhancer._isolated_nodes.add("ghost")
        result = enhancer.restore_node("ghost")
        assert result is True
        assert "ghost" not in enhancer._isolated_nodes

    def test_get_isolated_nodes(self) -> None:
        engine = self._make_engine({})
        enhancer = ByzantineIsolationEnhancer(engine)
        enhancer._isolated_nodes = {"z-node", "a-node"}
        isolated = enhancer.get_isolated_nodes()
        assert isolated == ["a-node", "z-node"]

    def test_update_histories_adds_vote_and_weight(self) -> None:
        validator = FakeValidator("node1", weight=5.0)
        engine = self._make_engine({"node1": validator})
        enhancer = ByzantineIsolationEnhancer(engine)

        vote = FakeVote("node1", "approve", time.time())
        enhancer._update_histories([vote])

        assert len(enhancer._vote_history["node1"]) == 1
        assert enhancer._vote_history["node1"][0] is vote
        assert len(enhancer._weight_history["node1"]) == 1
        assert enhancer._weight_history["node1"][0][1] == 5.0

    def test_update_histories_missing_validator(self) -> None:
        engine = self._make_engine({})
        enhancer = ByzantineIsolationEnhancer(engine)

        vote = FakeVote("ghost", "approve", time.time())
        enhancer._update_histories([vote])

        assert len(enhancer._vote_history["ghost"]) == 1
        assert "ghost" not in enhancer._weight_history

    def test_evaluate_proposal_merges_byzantine(self) -> None:
        validators = {
            "bad1": FakeValidator("bad1", weight=0.2, initial_weight=1.0),
            "good": FakeValidator("good", weight=1.0, initial_weight=1.0),
        }
        engine = self._make_engine(validators)

        enhancer = ByzantineIsolationEnhancer(engine)

        enhancer._vote_history = defaultdict(
            list,
            {
                "bad1": [
                    FakeVote("bad1", "reject", 100.0 + i) for i in range(5)
                ],
                "good": [
                    FakeVote("good", "approve", 100.0 + i) for i in range(3)
                ],
            },
        )
        enhancer._weight_history = defaultdict(
            list,
            {
                "bad1": [(100.0, 0.2), (150.0, 0.2)],
                "good": [(100.0, 1.0)],
            },
        )

        mock_result = MagicMock()
        mock_result.status = "inconclusive"
        mock_result.byzantine_nodes_detected = ["already-bad"]
        engine.evaluate_consensus.return_value = mock_result

        votes = [
            FakeVote("bad1", "reject", 200.0),
            FakeVote("good", "approve", 200.0),
        ]
        engine._votes = {"prop-1": votes}

        with patch(
            "maref.security.byzantine_enhancer.VoteValue",
        ) as mock_vv:
            mock_vv.APPROVE = "approve"
            mock_vv.REJECT = "reject"
            mock_vv.ABSTAIN = "abstain"

            result = enhancer.evaluate_proposal("prop-1")

        assert "already-bad" in result.byzantine_nodes_detected
        bad1_detected = any("bad1" in n for n in result.byzantine_nodes_detected)
        assert bad1_detected, "bad1 should be in byzantine nodes"

    def test_confidence_below_threshold_no_decision(self) -> None:
        engine = self._make_engine(
            {"low-conf": FakeValidator("low-conf", weight=1.0)}
        )
        enhancer = ByzantineIsolationEnhancer(engine)
        enhancer._vote_history = defaultdict(
            list,
            {
                "low-conf": [
                    FakeVote("low-conf", "approve", 100.0),
                ],
            },
        )
        votes = [FakeVote("low-conf", "approve", 110.0)]
        decisions = enhancer._detect_multidimensional(votes)
        assert len(decisions) == 0

    def test_evaluate_proposal_sets_byzantine_status(self) -> None:
        validators = {
            "bad-node": FakeValidator("bad-node", weight=0.2, initial_weight=1.0),
            "good": FakeValidator("good", weight=1.0, initial_weight=1.0),
        }
        engine = self._make_engine(validators)
        enhancer = ByzantineIsolationEnhancer(engine)

        enhancer._vote_history = defaultdict(
            list,
            {
                "bad-node": [
                    FakeVote("bad-node", "reject", 100.0 + i) for i in range(5)
                ],
                "good": [
                    FakeVote("good", "approve", 100.0 + i) for i in range(3)
                ],
            },
        )
        enhancer._weight_history = defaultdict(
            list,
            {
                "bad-node": [(100.0, 0.2), (150.0, 0.2)],
                "good": [(100.0, 1.0)],
            },
        )

        class FakeConsensusStatus:
            REACHED = "reached"
            BYZANTINE_DETECTED = "byzantine_detected"

        mock_result = MagicMock()
        mock_result.status = FakeConsensusStatus.INCONCLUSIVE = "inconclusive"
        mock_result.byzantine_nodes_detected = []
        engine.evaluate_consensus.return_value = mock_result

        votes = [
            FakeVote("bad-node", "reject", 200.0),
            FakeVote("good", "approve", 200.0),
        ]
        engine._votes = {"prop-1": votes}

        with patch(
            "maref.security.byzantine_enhancer.ConsensusStatus",
            FakeConsensusStatus,
        ), patch(
            "maref.security.byzantine_enhancer.VoteValue",
        ) as mock_vv:
            mock_vv.APPROVE = "approve"
            mock_vv.REJECT = "reject"
            mock_vv.ABSTAIN = "abstain"

            result = enhancer.evaluate_proposal("prop-1")

        assert result.status == FakeConsensusStatus.BYZANTINE_DETECTED
