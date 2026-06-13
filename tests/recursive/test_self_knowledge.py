from __future__ import annotations

import time
from pathlib import Path

import pytest

from maref.knowledge.graph import KnowledgeNode
from maref.recursive.self_knowledge import SelfKnowledge


class TestSelfKnowledgeM12:
    """M1.2: SelfKnowledge provenance integration."""

    def test_extract_arch_kg_deweights_ai_generated(self):
        sk = SelfKnowledge()
        sk.kg.add_node(KnowledgeNode(
            id="ai_module",
            type="module",
            content="AI generated module",
            confidence=1.0,
            source="test",
            timestamp=time.time(),
            metadata={"provenance": "ai_generated"},
        ))
        sk.kg.add_node(KnowledgeNode(
            id="human_module",
            type="module",
            content="Human authored module",
            confidence=1.0,
            source="test",
            timestamp=time.time(),
            metadata={"provenance": "human"},
        ))

        src = str(Path(__file__).resolve().parent.parent.parent / "src" / "maref" / "recursive")
        sk.extract_arch_kg(src)

        ai_node = sk.kg.get_node("ai_module")
        assert ai_node is not None
        assert ai_node.confidence == 0.5

        human_node = sk.kg.get_node("human_module")
        assert human_node is not None
        assert human_node.confidence == 1.0

    def test_extract_arch_kg_untouched_without_provenance(self):
        sk = SelfKnowledge()
        sk.kg.add_node(KnowledgeNode(
            id="plain_module",
            type="module",
            content="No provenance",
            confidence=1.0,
            source="test",
            timestamp=time.time(),
        ))

        src = str(Path(__file__).resolve().parent.parent.parent / "src" / "maref" / "recursive")
        sk.extract_arch_kg(src)

        node = sk.kg.get_node("plain_module")
        assert node is not None
        assert node.confidence == 1.0

    def test_arch_hypothesis_cycle_prioritizes_human_nodes(self):
        sk = SelfKnowledge()
        sk.kg.add_node(KnowledgeNode(
            id="human_src_a", type="module", content="",
            confidence=1.0, source="test", timestamp=time.time(),
            metadata={"provenance": "human"},
        ))
        sk.kg.add_node(KnowledgeNode(
            id="human_src_b", type="module", content="",
            confidence=1.0, source="test", timestamp=time.time(),
            metadata={"provenance": "human"},
        ))
        sk.kg.add_node(KnowledgeNode(
            id="ai_src", type="module", content="",
            confidence=1.0, source="test", timestamp=time.time(),
            metadata={"provenance": "ai_generated"},
        ))
        sk.kg.add_node(KnowledgeNode(
            id="target_module", type="module", content="",
            confidence=1.0, source="test", timestamp=time.time(),
        ))

        sk.kg.add_relation("human_src_a", "target_module", "precedes")
        sk.kg.add_relation("human_src_b", "target_module", "precedes")
        sk.kg.add_relation("ai_src", "target_module", "precedes")

        sk.kg.add_node(KnowledgeNode(
            id="low_dep_module", type="module", content="",
            confidence=1.0, source="test", timestamp=time.time(),
        ))
        sk.kg.add_relation("human_src_a", "low_dep_module", "precedes")

        hypotheses = sk.arch_hypothesis_cycle()

        decouple_h = [h for h in hypotheses if "耦合度偏高" in h.description]
        assert len(decouple_h) == 1
        h = decouple_h[0]
        assert "人类" in h.description
        assert h.target_module == "target_module"

    def test_arch_hypothesis_cycle_low_dep_no_hypothesis(self):
        sk = SelfKnowledge()
        sk.kg.add_node(KnowledgeNode(
            id="src_a", type="module", content="",
            confidence=1.0, source="test", timestamp=time.time(),
            metadata={"provenance": "human"},
        ))
        sk.kg.add_node(KnowledgeNode(
            id="lonely_module", type="module", content="",
            confidence=1.0, source="test", timestamp=time.time(),
        ))
        sk.kg.add_relation("src_a", "lonely_module", "precedes")

        hypotheses = sk.arch_hypothesis_cycle()

        decouple_h = [h for h in hypotheses if "耦合度偏高" in h.description]
        assert len(decouple_h) == 0

    def test_extract_arch_kg_deweights_newly_labeled_nodes(self):
        sk = SelfKnowledge()
        src = str(Path(__file__).resolve().parent.parent.parent / "src" / "maref" / "recursive")
        sk.extract_arch_kg(src)

        parsed_nodes = [n for n in sk.kg.nodes if n.source == "code_parser"]
        assert len(parsed_nodes) > 0

        for node in parsed_nodes:
            node.metadata["provenance"] = "ai_generated"

        sk2 = SelfKnowledge()
        sk2.kg.add_node(KnowledgeNode(
            id="exist_ai", type="module", content="",
            confidence=1.0, source="test", timestamp=time.time(),
            metadata={"provenance": "ai_generated"},
        ))
        src2 = str(Path(__file__).resolve().parent.parent.parent / "src" / "maref" / "immunity")
        sk2.extract_arch_kg(src2)

        exist_node = sk2.kg.get_node("exist_ai")
        assert exist_node is not None
        assert exist_node.confidence == 0.5
