from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from maref.recursive.code_parser import CodeNode, ModuleHierarchy
from maref.recursive.self_knowledge import ArchHypothesis, SelfKnowledge


class TestArchHypothesis:
    def test_default_construction(self) -> None:
        h = ArchHypothesis(
            hypothesis_id="h1",
            description="test",
            target_module="mod",
        )
        assert h.hypothesis_id == "h1"
        assert h.description == "test"
        assert h.target_module == "mod"
        assert h.confidence == 0.0

    def test_with_confidence(self) -> None:
        h = ArchHypothesis(
            hypothesis_id="h1",
            description="test",
            target_module="mod",
            confidence=0.85,
        )
        assert h.confidence == 0.85


class TestSelfKnowledge:
    def test_default_construction(self) -> None:
        sk = SelfKnowledge()
        assert sk.kg is not None
        assert sk.provenance_tracker is not None

    def test_extract_arch_kg(self) -> None:
        hierarchy = ModuleHierarchy(
            root_path="/fake",
            modules=[CodeNode(name="mod_a", node_type="module")],
            classes=[CodeNode(name="ClassA", node_type="class", parent="mod_a")],
            functions=[CodeNode(name="func_a", node_type="function", parent="mod_a")],
            imports=[("mod_a", "mod_b")],
        )
        sk = SelfKnowledge()
        sk._parser = MagicMock()
        sk._parser.extract_module_hierarchy.return_value = hierarchy

        mock_kg = MagicMock()
        sk._kg = mock_kg

        mock_kg.get_node.side_effect = lambda nid: MagicMock(
            id=nid,
            metadata={"provenance": "human"} if nid == "mod_b" else {},
        )

        result = sk.extract_arch_kg("/fake")
        assert result is hierarchy
        assert mock_kg.add_node.call_count == 3
        assert mock_kg.add_relation.called

    def test_extract_arch_kg_ai_generated_lowers_confidence(self) -> None:
        hierarchy = ModuleHierarchy(
            root_path="/fake",
            modules=[CodeNode(name="mod_a", node_type="module")],
        )
        sk = SelfKnowledge()
        sk._parser = MagicMock()
        sk._parser.extract_module_hierarchy.return_value = hierarchy

        node_with_ai_meta = MagicMock()
        node_with_ai_meta.id = "mod_a"
        node_with_ai_meta.type = "module"
        node_with_ai_meta.confidence = 1.0
        node_with_ai_meta.metadata = {"provenance": "ai_generated"}

        mock_kg = MagicMock()
        mock_kg.nodes = [node_with_ai_meta]
        sk._kg = mock_kg

        sk.extract_arch_kg("/fake")
        assert node_with_ai_meta.confidence == 0.5

    def test_extract_arch_kg_import_to_module_not_found_falls_back_to_top(self) -> None:
        hierarchy = ModuleHierarchy(
            root_path="/fake",
            modules=[
                CodeNode(name="mod_a", node_type="module"),
                CodeNode(name="mod_b", node_type="module"),
            ],
            imports=[("mod_a", "mod_b.submod")],
        )
        sk = SelfKnowledge()
        sk._parser = MagicMock()
        sk._parser.extract_module_hierarchy.return_value = hierarchy

        mock_kg = MagicMock()
        mock_kg.get_node.side_effect = lambda nid: (
            MagicMock(id=nid, metadata={}) if nid in ("mod_a", "mod_b") else None
        )
        sk._kg = mock_kg

        sk.extract_arch_kg("/fake")
        mock_kg.add_relation.assert_called_with("mod_a", "mod_b", "precedes")

    def test_extract_test_coverage_relations(self) -> None:
        test_hierarchy = ModuleHierarchy(
            root_path="/tests",
            functions=[CodeNode(name="test_foo", node_type="function", parent="test_mod")],
        )
        sk = SelfKnowledge()
        sk._parser = MagicMock()
        mock_test_parser = MagicMock()
        mock_test_parser.extract_module_hierarchy.return_value = test_hierarchy

        with patch("maref.recursive.self_knowledge.CodeParser", return_value=mock_test_parser):
            mock_kg = MagicMock()
            mod_node = MagicMock()
            mod_node.id = "test_foo"  # Make mod_node.id match test function name
            mod_node.type = "module"
            mock_kg.get_nodes_by_type.return_value = [mod_node]
            sk._kg = mock_kg

            count = sk.extract_test_coverage_relations("/tests", "/src")
            assert count == 1
            mock_kg.add_node.assert_called_once()
            # add_relation should be called since mod_node.id matches test function name
            mock_kg.add_relation.assert_called_with("test:test_foo", "test_foo", "tests")

    def test_arch_hypothesis_cycle_empty_kg(self) -> None:
        sk = SelfKnowledge()
        mock_kg = MagicMock()
        mock_kg.nodes = []
        mock_kg.get_nodes_by_type.return_value = []
        sk._kg = mock_kg

        hypotheses = sk.arch_hypothesis_cycle()
        assert hypotheses == []

    def test_arch_hypothesis_cycle_high_dependency(self) -> None:
        sk = SelfKnowledge()
        target_node = MagicMock()
        target_node.id = "core_mod"
        target_node.type = "module"
        target_node.metadata = {"provenance": "human"}
        target_node.out_edges = []

        source_node = MagicMock()
        source_node.id = "dep_a"
        source_node.type = "module"
        source_node.metadata = {"provenance": "human"}
        edge = MagicMock()
        edge.relation.value = "precedes"
        edge.target_id = "core_mod"
        source_node.out_edges = [edge]

        mock_kg = MagicMock()
        mock_kg.nodes = [target_node, source_node]
        mock_kg.get_nodes_by_type.side_effect = lambda t: (
            [target_node, source_node] if t == "module" else []
        )
        sk._kg = mock_kg

        hypotheses = sk.arch_hypothesis_cycle()
        assert len(hypotheses) >= 1
        assert any("core_mod" in h.description for h in hypotheses)

    def test_arch_hypothesis_cycle_few_classes(self) -> None:
        sk = SelfKnowledge()
        mod_node = MagicMock()
        mod_node.id = "mod_a"
        mod_node.type = "module"
        mod_node.metadata = {}
        mod_node.out_edges = []

        mock_kg = MagicMock()
        mock_kg.nodes = [mod_node]
        mock_kg.get_nodes_by_type.side_effect = lambda t: (
            [mod_node] if t == "module" else []
        )
        sk._kg = mock_kg

        hypotheses = sk.arch_hypothesis_cycle()
        assert len(hypotheses) >= 1
        assert any("平均类数量偏低" in h.description for h in hypotheses)

    def test_arch_hypothesis_cycle_untested_module(self) -> None:
        sk = SelfKnowledge()
        mod_node = MagicMock()
        mod_node.id = "mod_a"
        mod_node.type = "module"
        mod_node.metadata = {}
        mod_node.out_edges = []

        mock_kg = MagicMock()
        mock_kg.nodes = [mod_node]
        mock_kg.get_nodes_by_type.side_effect = lambda t: [mod_node] if t == "module" else []
        sk._kg = mock_kg

        hypotheses = sk.arch_hypothesis_cycle()
        assert len(hypotheses) >= 1
        assert any("缺少测试覆盖" in h.description for h in hypotheses)

    def test_arch_hypothesis_cycle_limits_to_5(self) -> None:
        sk = SelfKnowledge()
        nodes = []
        for i in range(10):
            n = MagicMock()
            n.id = f"mod_{i}"
            n.type = "module"
            n.metadata = {}
            edge = MagicMock()
            edge.relation.value = "precedes"
            edge.target_id = f"target_{i}"
            n.out_edges = [edge]
            nodes.append(n)

        target_node = MagicMock()
        target_node.id = "target_0"
        target_node.type = "module"
        target_node.metadata = {}
        target_node.out_edges = []
        nodes.append(target_node)

        mock_kg = MagicMock()
        mock_kg.nodes = nodes
        mock_kg.get_nodes_by_type.return_value = [n for n in nodes if n.type == "module"]
        sk._kg = mock_kg

        hypotheses = sk.arch_hypothesis_cycle()
        assert len(hypotheses) <= 5

    def test_query_coverage_gaps_no_tests(self) -> None:
        sk = SelfKnowledge()
        mod_node = MagicMock()
        mod_node.id = "untested_mod"
        mod_node.type = "module"
        mod_node.metadata = {}
        mod_node.out_edges = []

        mock_kg = MagicMock()
        mock_kg.nodes = [mod_node]
        mock_kg.get_nodes_by_type.return_value = [mod_node]
        sk._kg = mock_kg

        gaps = sk.query_coverage_gaps()
        assert "untested_mod" in gaps

    def test_query_coverage_gaps_with_tests(self) -> None:
        sk = SelfKnowledge()

        test_node = MagicMock()
        test_node.id = "test:test_foo"
        test_node.type = "test"
        test_node.metadata = {}
        test_edge = MagicMock()
        test_edge.relation.value = "TESTS"
        test_edge.target_id = "tested_mod"
        test_node.out_edges = [test_edge]

        mod_node = MagicMock()
        mod_node.id = "tested_mod"
        mod_node.type = "module"
        mod_node.metadata = {}
        mod_node.out_edges = []

        mock_kg = MagicMock()
        mock_kg.nodes = [test_node, mod_node]
        mock_kg.get_nodes_by_type.return_value = [mod_node]
        sk._kg = mock_kg

        gaps = sk.query_coverage_gaps()
        assert "tested_mod" not in gaps

    def test_node_count(self) -> None:
        sk = SelfKnowledge()
        mock_kg = MagicMock()
        mock_kg.nodes = [MagicMock(), MagicMock(), MagicMock()]
        sk._kg = mock_kg
        assert sk.node_count() == 3

    def test_node_types(self) -> None:
        sk = SelfKnowledge()
        n1 = MagicMock()
        n1.type = "module"
        n2 = MagicMock()
        n2.type = "module"
        n3 = MagicMock()
        n3.type = "class"
        mock_kg = MagicMock()
        mock_kg.nodes = [n1, n2, n3]
        sk._kg = mock_kg
        types = sk.node_types()
        assert types == {"module": 2, "class": 1}

    def test_relation_types(self) -> None:
        sk = SelfKnowledge()
        n1 = MagicMock()
        e1 = MagicMock()
        e1.relation.value = "precedes"
        n1.out_edges = [e1]
        n2 = MagicMock()
        e2 = MagicMock()
        e2.relation.value = "precedes"
        n2.out_edges = [e2]
        n3 = MagicMock()
        e3 = MagicMock()
        e3.relation.value = "tests"
        n3.out_edges = [e3]
        mock_kg = MagicMock()
        mock_kg.nodes = [n1, n2, n3]
        sk._kg = mock_kg
        types = sk.relation_types()
        assert types == {"precedes", "tests"}

    def test_kg_property(self) -> None:
        sk = SelfKnowledge()
        assert sk.kg is sk._kg

    def test_provenance_tracker_property(self) -> None:
        sk = SelfKnowledge()
        assert sk.provenance_tracker is sk._provenance_tracker
