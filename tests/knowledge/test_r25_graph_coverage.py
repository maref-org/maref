from __future__ import annotations

import json
import tempfile
from pathlib import Path

from maref.knowledge.graph import (
    KnowledgeGraph,
    KnowledgeNode,
    RelationEdge,
)
from maref.knowledge.relations import RelationType


def _make_node(node_id: str, ntype: str = "finding", content: str = "test",
               confidence: float = 0.8, out_edges: list | None = None) -> KnowledgeNode:
    return KnowledgeNode(
        id=node_id,
        type=ntype,
        content=content,
        confidence=confidence,
        source="test",
        timestamp=1000.0,
        out_edges=out_edges or [],
    )


class TestAddRelation:
    def test_add_relation_success(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(_make_node("a", content="node a"))
        kg.add_node(_make_node("b", content="node b"))
        result = kg.add_relation("a", "b", "supports")
        assert result is True

    def test_add_relation_source_not_found(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(_make_node("b", content="node b"))
        result = kg.add_relation("nonexistent", "b", "supports")
        assert result is False

    def test_add_relation_target_not_found(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(_make_node("a", content="node a"))
        result = kg.add_relation("a", "nonexistent", "supports")
        assert result is False

    def test_add_relation_sets_edge_on_source(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(_make_node("a"))
        kg.add_node(_make_node("b"))
        kg.add_relation("a", "b", "causes")
        node_a = kg.get_node("a")
        assert node_a is not None
        assert len(node_a.out_edges) == 1
        assert node_a.out_edges[0].target_id == "b"
        assert node_a.out_edges[0].relation == RelationType.CAUSES


class TestLoadWithErrors:
    def test_load_corrupted_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "kg.json"
            path.write_text("{corrupted json")
            kg = KnowledgeGraph(storage_path=path)
            kg._load()
            assert len(kg.nodes) == 0

    def test_load_missing_nodes_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "kg.json"
            path.write_text(json.dumps({"version": "2.0", "updated_at": 0}))
            kg = KnowledgeGraph(storage_path=path)
            kg._load()
            assert len(kg.nodes) == 0

    def test_load_valid_kg(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "kg.json"
            node = _make_node("n1", content="hello")
            data = {"version": "2.0", "updated_at": 0, "nodes": [node.to_dict()]}
            path.write_text(json.dumps(data))
            kg = KnowledgeGraph(storage_path=path)
            kg._load()
            assert kg.get_node("n1") is not None

    def test_save_and_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "kg.json"
            kg = KnowledgeGraph(storage_path=path)
            kg.add_node(_make_node("a", content="alpha"))
            kg.add_node(_make_node("b", content="beta"))
            kg.add_relation("a", "b", "supports")

            kg2 = KnowledgeGraph(storage_path=path)
            kg2._load()
            assert kg2.get_node("a") is not None
            assert kg2.get_node("b") is not None


class TestConnectivityStats:
    def test_empty_graph(self) -> None:
        kg = KnowledgeGraph()
        stats = kg.get_connectivity_stats()
        assert stats["total_nodes"] == 0
        assert stats["edge_count"] == 0
        assert stats["avg_degree"] == 0.0

    def test_single_node_no_edges(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(_make_node("a"))
        stats = kg.get_connectivity_stats()
        assert stats["total_nodes"] == 1
        assert stats["orphaned_nodes"] == 1
        assert stats["edge_count"] == 0
        assert stats["connected_components"] == 1

    def test_two_connected_nodes(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(_make_node("a"))
        kg.add_node(_make_node("b"))
        kg.add_relation("a", "b", "supports")
        stats = kg.get_connectivity_stats()
        assert stats["orphaned_nodes"] == 0
        assert stats["edge_count"] == 1
        assert stats["connected_components"] == 1
        assert stats["max_component_size"] == 2
        assert stats["avg_degree"] > 0

    def test_two_disconnected_components(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(_make_node("a"))
        kg.add_node(_make_node("b"))
        kg.add_node(_make_node("c"))
        kg.add_node(_make_node("d"))
        kg.add_relation("a", "b", "supports")
        kg.add_relation("c", "d", "causes")
        stats = kg.get_connectivity_stats()
        assert stats["connected_components"] == 2
        assert stats["max_component_size"] == 2

    def test_mixed_orphaned_and_connected(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(_make_node("a"))
        kg.add_node(_make_node("b"))
        kg.add_node(_make_node("orphan"))
        kg.add_relation("a", "b", "supports")
        stats = kg.get_connectivity_stats()
        assert stats["orphaned_nodes"] == 1
        assert stats["total_nodes"] == 3
        assert stats["connected_components"] == 2


class TestTraverseGraph:
    def test_traverse_start_not_found(self) -> None:
        kg = KnowledgeGraph()
        results = kg.traverse("nonexistent")
        assert results == []

    def test_traverse_basic(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(_make_node("a"))
        kg.add_node(_make_node("b"))
        kg.add_node(_make_node("c"))
        kg.add_relation("a", "b", "supports")
        kg.add_relation("b", "c", "causes")
        results = kg.traverse("a")
        assert len(results) >= 1
        assert results[0]["depth"] == 1

    def test_traverse_respects_max_depth(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(_make_node("a"))
        kg.add_node(_make_node("b"))
        kg.add_node(_make_node("c"))
        kg.add_relation("a", "b", "supports")
        kg.add_relation("b", "c", "causes")
        results = kg.traverse("a", max_depth=0)
        assert len(results) == 0

    def test_traverse_filters_relation_type(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(_make_node("a"))
        kg.add_node(_make_node("b"))
        kg.add_node(_make_node("c"))
        kg.add_relation("a", "b", "supports")
        kg.add_relation("a", "c", "causes")
        results = kg.traverse("a", relation_type=RelationType.CAUSES)
        assert len(results) == 1
        assert results[0]["node_id"] == "c"

    def test_traverse_skips_nonexistent_target(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(_make_node("a"))
        a_node = kg.get_node("a")
        assert a_node is not None
        a_node.out_edges.append(RelationEdge(
            relation=RelationType.SUPPORTS,
            target_id="ghost_node",
            confidence=0.5,
            method="test",
        ))
        results = kg.traverse("a")
        assert len(results) == 0

    def test_traverse_path_tracking(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(_make_node("a"))
        kg.add_node(_make_node("b"))
        kg.add_node(_make_node("c"))
        kg.add_relation("a", "b", "supports")
        kg.add_relation("b", "c", "causes")
        results = kg.traverse("a")
        b_result = [r for r in results if r["node_id"] == "b"]
        assert len(b_result) == 1
        assert "supports" in b_result[0]["relation_path"]


class TestOpenQuestions:
    def test_no_open_questions_empty(self) -> None:
        kg = KnowledgeGraph()
        assert kg.get_open_questions() == []

    def test_low_confidence_hypothesis_is_open(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(_make_node("h1", ntype="hypothesis", confidence=0.3))
        questions = kg.get_open_questions()
        assert len(questions) == 1
        assert questions[0].id == "h1"

    def test_high_confidence_hypothesis_not_open(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(_make_node("h1", ntype="hypothesis", confidence=0.9))
        questions = kg.get_open_questions()
        assert len(questions) == 0

    def test_finding_not_open_question(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(_make_node("f1", ntype="finding", confidence=0.3))
        questions = kg.get_open_questions()
        assert len(questions) == 0


class TestQuery:
    def test_query_alias(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(_make_node("a", content="alpha"))
        results = kg.query("alpha")
        assert len(results) == 1
        assert results[0].id == "a"

    def test_query_ranking(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(_make_node("a", content="alpha"))
        kg.add_node(_make_node("b", content="xyz target"))
        results = kg.query("xyz")
        assert len(results) >= 1
        assert results[0].id == "b"


class TestGraphSummary:
    def test_summary_with_data(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(_make_node("a"))
        kg.add_node(_make_node("b"))
        kg.add_relation("a", "b", "supports")
        summary = kg.get_stats()
        assert summary["total_nodes"] == 2
        assert "by_type" in summary
        assert "open_questions" in summary
        assert "edge_count" in summary

    def test_summary_counts_open_questions(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(_make_node("h1", ntype="hypothesis", confidence=0.3))
        kg.add_node(_make_node("h2", ntype="hypothesis", confidence=0.5))
        kg.add_node(_make_node("h3", ntype="hypothesis", confidence=0.9))
        summary = kg.get_stats()
        assert summary["open_questions"] == 2
