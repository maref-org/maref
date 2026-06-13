import time

import pytest

from maref.immunity.provenance_tracker import (
    PRE_2023_CUTOFF,
    ProvenanceTracker,
)
from maref.knowledge.graph import KnowledgeGraph, KnowledgeNode


@pytest.fixture
def kg() -> KnowledgeGraph:
    return KnowledgeGraph()


@pytest.fixture
def tracker(kg: KnowledgeGraph) -> ProvenanceTracker:
    return ProvenanceTracker(kg)


def _add_node(
    kg: KnowledgeGraph,
    node_id: str,
    ts: float,
    content: str = "test content",
) -> str:
    node = KnowledgeNode(
        id=node_id,
        type="finding",
        content=content,
        confidence=0.8,
        source="test",
        timestamp=ts,
    )
    kg.add_node(node)
    return node_id


class TestLabelNode:
    def test_label_node_stores_in_metadata(self, kg: KnowledgeGraph, tracker: ProvenanceTracker) -> None:
        _add_node(kg, "node-1", time.time())
        tracker.label_node("node-1", "human")
        node = kg.get_node("node-1")
        assert node is not None
        assert node.metadata["provenance"] == "human"

    def test_label_node_invalid_provenance_raises(self, kg: KnowledgeGraph, tracker: ProvenanceTracker) -> None:
        _add_node(kg, "node-1", time.time())
        with pytest.raises(ValueError, match="Invalid provenance"):
            tracker.label_node("node-1", "robot")

    def test_label_nonexistent_node(self, tracker: ProvenanceTracker) -> None:
        tracker.label_node("nonexistent", "ai_generated")
        assert tracker.get_provenance("nonexistent") == "ai_generated"

    def test_all_provenance_labels_accepted(self, kg: KnowledgeGraph, tracker: ProvenanceTracker) -> None:
        _add_node(kg, "n1", time.time())
        _add_node(kg, "n2", time.time())
        _add_node(kg, "n3", time.time())
        _add_node(kg, "n4", time.time())
        tracker.label_node("n1", "human")
        tracker.label_node("n2", "ai_assisted")
        tracker.label_node("n3", "ai_generated")
        tracker.label_node("n4", "unknown")
        assert tracker.get_provenance("n1") == "human"
        assert tracker.get_provenance("n2") == "ai_assisted"
        assert tracker.get_provenance("n3") == "ai_generated"
        assert tracker.get_provenance("n4") == "unknown"

    def test_label_overwrites_previous(self, kg: KnowledgeGraph, tracker: ProvenanceTracker) -> None:
        _add_node(kg, "node-1", time.time())
        tracker.label_node("node-1", "human")
        tracker.label_node("node-1", "ai_generated")
        assert tracker.get_provenance("node-1") == "ai_generated"


class TestGetProvenance:
    def test_get_provenance_nonexistent_returns_none(self, tracker: ProvenanceTracker) -> None:
        assert tracker.get_provenance("nonexistent") is None

    def test_get_provenance_no_kg(self) -> None:
        tracker_no_kg = ProvenanceTracker()
        assert tracker_no_kg.get_provenance("anything") is None


class TestRetrieve:
    def test_retrieve_pre_2023_filters_post_2023(self, kg: KnowledgeGraph, tracker: ProvenanceTracker) -> None:
        _add_node(kg, "old-node", PRE_2023_CUTOFF - 86400)
        _add_node(kg, "new-node", PRE_2023_CUTOFF + 86400)
        results = tracker.retrieve(pre_2023=True)
        ids = {n.id for n in results}
        assert "old-node" in ids
        assert "new-node" not in ids

    def test_retrieve_pre_2023_empty_when_all_new(self, kg: KnowledgeGraph, tracker: ProvenanceTracker) -> None:
        _add_node(kg, "n1", PRE_2023_CUTOFF + 86400)
        _add_node(kg, "n2", PRE_2023_CUTOFF + 99999999)
        results = tracker.retrieve(pre_2023=True)
        assert len(results) == 0

    def test_retrieve_pre_2023_all_old(self, kg: KnowledgeGraph, tracker: ProvenanceTracker) -> None:
        _add_node(kg, "n1", PRE_2023_CUTOFF - 86400)
        _add_node(kg, "n2", PRE_2023_CUTOFF - 99999999)
        results = tracker.retrieve(pre_2023=True)
        assert len(results) == 2

    def test_retrieve_provenance_prioritizes_human(self, kg: KnowledgeGraph, tracker: ProvenanceTracker) -> None:
        _add_node(kg, "human-node", time.time())
        _add_node(kg, "ai-node", time.time())
        tracker.label_node("human-node", "human")
        tracker.label_node("ai-node", "ai_generated")
        results = tracker.retrieve(provenance="human")
        assert len(results) == 2
        assert results[0].id == "human-node"

    def test_retrieve_provenance_empty_when_no_match(self, kg: KnowledgeGraph, tracker: ProvenanceTracker) -> None:
        _add_node(kg, "node-1", time.time())
        tracker.label_node("node-1", "ai_generated")
        results = tracker.retrieve(provenance="human")
        assert len(results) == 1
        assert results[0].id == "node-1"  # no human node, so ai_generated returned

    def test_retrieve_no_kg_returns_empty(self) -> None:
        tracker_no_kg = ProvenanceTracker()
        assert tracker_no_kg.retrieve() == []
        assert tracker_no_kg.retrieve(pre_2023=True) == []
        assert tracker_no_kg.retrieve(provenance="human") == []

    def test_retrieve_provenance_with_pre_2023(self, kg: KnowledgeGraph, tracker: ProvenanceTracker) -> None:
        _add_node(kg, "old-human", PRE_2023_CUTOFF - 86400)
        _add_node(kg, "old-ai", PRE_2023_CUTOFF - 86400)
        _add_node(kg, "new-human", PRE_2023_CUTOFF + 86400)
        tracker.label_node("old-human", "human")
        tracker.label_node("old-ai", "ai_generated")
        tracker.label_node("new-human", "human")
        results = tracker.retrieve(pre_2023=True, provenance="human")
        ids = {n.id for n in results}
        assert "old-human" in ids
        assert "old-ai" in ids
        assert "new-human" not in ids
        assert results[0].id == "old-human"


class TestSummarize:
    def test_summarize_empty(self, tracker: ProvenanceTracker) -> None:
        summary = tracker.summarize()
        assert summary == {}

    def test_summarize_counts(self, kg: KnowledgeGraph, tracker: ProvenanceTracker) -> None:
        _add_node(kg, "n1", time.time())
        _add_node(kg, "n2", time.time())
        _add_node(kg, "n3", time.time())
        _add_node(kg, "n4", time.time())
        tracker.label_node("n1", "human")
        tracker.label_node("n2", "ai_generated")
        tracker.label_node("n3", "ai_generated")
        tracker.label_node("n4", "unknown")
        summary = tracker.summarize()
        assert summary.get("human") == 1
        assert summary.get("ai_generated") == 2
        assert summary.get("unknown") == 1

    def test_summarize_no_kg(self) -> None:
        tracker_no_kg = ProvenanceTracker()
        assert tracker_no_kg.summarize() == {}


class TestProvenanceRecord:
    def test_provenance_record_defaults(self) -> None:
        from maref.immunity.provenance_tracker import ProvenanceRecord
        rec = ProvenanceRecord(
            node_id="n1",
            provenance="human",
            timestamp=123.0,
            source="test",
        )
        assert rec.node_id == "n1"
        assert rec.provenance == "human"
        assert rec.timestamp == 123.0
        assert rec.source == "test"


class TestIntegrationWithKnowledgeGraph:
    def test_label_appears_in_kg_metadata(self, kg: KnowledgeGraph, tracker: ProvenanceTracker) -> None:
        _add_node(kg, "node-1", time.time(), content="def foo(): pass")
        tracker.label_node("node-1", "human")
        node = kg.get_node("node-1")
        assert node is not None
        assert node.metadata.get("provenance") == "human"

    def test_provenance_survives_reload(self, kg: KnowledgeGraph, tracker: ProvenanceTracker) -> None:
        _add_node(kg, "node-1", time.time(), content="def foo(): pass")
        tracker.label_node("node-1", "ai_assisted")
        data = kg.get_node("node-1")
        assert data is not None
        restored = KnowledgeNode.from_dict(data.to_dict())
        assert restored.metadata.get("provenance") == "ai_assisted"

    def test_multiple_nodes_with_different_provenance(self, kg: KnowledgeGraph, tracker: ProvenanceTracker) -> None:
        for i in range(5):
            _add_node(kg, f"node-{i}", time.time())
        tracker.label_node("node-0", "human")
        tracker.label_node("node-1", "human")
        tracker.label_node("node-2", "ai_assisted")
        tracker.label_node("node-3", "ai_generated")
        results = tracker.retrieve(provenance="human")
        assert results[0].id == "node-0"
        assert results[1].id == "node-1"
