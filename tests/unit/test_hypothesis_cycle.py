from __future__ import annotations

import pytest

from maref.knowledge.graph import KnowledgeGraph
from maref.knowledge.hypothesis_cycle import (
    HypothesisCycle,
    HypothesisStatus,
)


@pytest.fixture
def kg() -> KnowledgeGraph:
    return KnowledgeGraph()


@pytest.fixture
def cycle(kg: KnowledgeGraph) -> HypothesisCycle:
    return HypothesisCycle(kg)


class TestHypothesisPropose:
    def test_propose_creates_nodes_and_record(self, cycle: HypothesisCycle) -> None:
        hyp = cycle.propose("What is X?", "X is Y")
        assert hyp.status == HypothesisStatus.PROPOSED
        assert hyp.confidence == 0.6
        assert cycle.hypothesis_count == 1

    def test_propose_adds_question_and_hypothesis_to_kg(
        self, cycle: HypothesisCycle, kg: KnowledgeGraph
    ) -> None:
        cycle.propose("What is X?", "X is Y")
        node_types = {n.type for n in kg.nodes}
        assert "question" in node_types
        assert "hypothesis" in node_types


class TestHypothesisExperiment:
    def test_run_experiment_links_experiment_node(
        self, cycle: HypothesisCycle, kg: KnowledgeGraph
    ) -> None:
        hyp = cycle.propose("Q?", "H!")
        exp_id = cycle.run_experiment(hyp.node_id, "Test H")
        assert exp_id is not None
        exp_node = kg.get_node(exp_id)
        assert exp_node is not None
        assert exp_node.type == "experiment"

    def test_run_experiment_unknown_hypothesis(self, cycle: HypothesisCycle) -> None:
        assert cycle.run_experiment("nonexistent", "Test") is None

    def test_experiment_updates_status(self, cycle: HypothesisCycle) -> None:
        hyp = cycle.propose("Q?", "H!")
        cycle.run_experiment(hyp.node_id, "Test")
        updated = cycle.get_hypothesis(hyp.node_id)
        assert updated is not None
        assert updated.status == HypothesisStatus.TESTING


class TestFindings:
    def test_record_finding_supports(self, cycle: HypothesisCycle, kg: KnowledgeGraph) -> None:
        hyp = cycle.propose("Q?", "H!")
        cycle.run_experiment(hyp.node_id, "Test")
        result = cycle.record_finding(hyp.node_id, "Evidence supports", True, 0.9)
        assert result is True
        finding_types = {n.type for n in kg.nodes}
        assert "finding" in finding_types

    def test_record_finding_contradicts(self, cycle: HypothesisCycle) -> None:
        hyp = cycle.propose("Q?", "H!")
        result = cycle.record_finding(hyp.node_id, "Evidence against", False, 0.8)
        assert result is True
        updated = cycle.get_hypothesis(hyp.node_id)
        assert updated is not None
        assert len(updated.evidence) == 1
        assert updated.evidence[0]["supports"] is False

    def test_record_finding_unknown(self, cycle: HypothesisCycle) -> None:
        assert cycle.record_finding("nonexistent", "F", True, 0.5) is False


class TestConclude:
    def test_conclude_confirmed(self, cycle: HypothesisCycle) -> None:
        hyp = cycle.propose("Q?", "H!")
        result = cycle.conclude(hyp.node_id, "Yes, confirmed", True)
        assert result is not None
        assert result.status == HypothesisStatus.CONFIRMED

    def test_conclude_refuted(self, cycle: HypothesisCycle) -> None:
        hyp = cycle.propose("Q?", "H!")
        result = cycle.conclude(hyp.node_id, "No, wrong", False)
        assert result is not None
        assert result.status == HypothesisStatus.REFUTED

    def test_conclude_unknown(self, cycle: HypothesisCycle) -> None:
        assert cycle.conclude("nonexistent", "N/A", True) is None


class TestTimeDecay:
    def test_decay_reduces_confidence(self, cycle: HypothesisCycle) -> None:
        hyp = cycle.propose("Q?", "H!")
        cycle.apply_time_decay(days_elapsed=60.0, decay_factor=0.02)
        updated = cycle.get_hypothesis(hyp.node_id)
        assert updated is not None
        decay = 0.02 * 60.0
        expected = max(0.0, 0.6 - decay)
        assert updated.confidence == pytest.approx(expected)

    def test_decay_above_60_percent_reduction_in_60_days(self, cycle: HypothesisCycle) -> None:
        hyp = cycle.propose("Q?", "H!")
        cycle.apply_time_decay(days_elapsed=60.0, decay_factor=0.02)
        updated = cycle.get_hypothesis(hyp.node_id)
        assert updated is not None
        original = 0.6
        reduction = (original - updated.confidence) / original if original > 0 else 0
        assert reduction >= 0.60 or updated.confidence == 0.0

    def test_decay_bottom_floor(self, cycle: HypothesisCycle) -> None:
        hyp = cycle.propose("Q?", "H!")
        cycle.apply_time_decay(days_elapsed=1000.0, decay_factor=0.02)
        updated = cycle.get_hypothesis(hyp.node_id)
        assert updated is not None
        assert updated.confidence >= 0.0


class TestFullCycle:
    def test_hypothesis_experiment_finding_closed_loop(
        self, cycle: HypothesisCycle, kg: KnowledgeGraph
    ) -> None:
        hyp = cycle.propose("What causes X?", "Y causes X")
        cycle.run_experiment(hyp.node_id, "Controlled study of Y")
        cycle.record_finding(hyp.node_id, "Data shows correlation", True, 0.85)
        cycle.record_finding(hyp.node_id, "Alternative explanation", False, 0.4)
        result = cycle.conclude(hyp.node_id, "Y likely causes X", True)
        assert result is not None
        assert result.status == HypothesisStatus.CONFIRMED
        node_types = {n.type for n in kg.nodes}
        for t in ("question", "hypothesis", "experiment", "finding"):
            assert t in node_types
