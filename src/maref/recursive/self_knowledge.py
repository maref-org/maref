from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from maref.immunity.provenance_tracker import ProvenanceTracker
from maref.knowledge.graph import KnowledgeGraph, KnowledgeNode
from maref.recursive.code_parser import CodeParser, ModuleHierarchy


@dataclass
class ArchHypothesis:
    hypothesis_id: str
    description: str
    target_module: str
    confidence: float = 0.0


class SelfKnowledge:
    def __init__(self, provenance_tracker: ProvenanceTracker | None = None) -> None:
        self._kg = KnowledgeGraph()
        self._parser = CodeParser()
        self._provenance_tracker = provenance_tracker or ProvenanceTracker(self._kg)

    @property
    def kg(self) -> KnowledgeGraph:
        return self._kg

    @property
    def provenance_tracker(self) -> ProvenanceTracker:
        return self._provenance_tracker

    def extract_arch_kg(self, root_path: str) -> ModuleHierarchy:
        hierarchy = self._parser.extract_module_hierarchy(root_path)

        for mod in hierarchy.modules:
            self._kg.add_node(
                KnowledgeNode(
                    id=mod.name,
                    type="module",
                    content=f"Module: {mod.name}",
                    confidence=1.0,
                    source="code_parser",
                    timestamp=time.time(),
                )
            )

        for cls in hierarchy.classes:
            self._kg.add_node(
                KnowledgeNode(
                    id=cls.name,
                    type="class",
                    content=f"Class: {cls.name} in {cls.parent}",
                    confidence=1.0,
                    source="code_parser",
                    timestamp=time.time(),
                )
            )

        for func in hierarchy.functions:
            self._kg.add_node(
                KnowledgeNode(
                    id=func.name,
                    type="function",
                    content=f"Function: {func.name} in {func.parent}",
                    confidence=1.0,
                    source="code_parser",
                    timestamp=time.time(),
                )
            )

        for imp_from, imp_to in hierarchy.imports:
            from_node = self._kg.get_node(imp_from)
            if from_node is None:
                continue
            to_node = self._kg.get_node(imp_to)
            if to_node is not None:
                self._kg.add_relation(imp_from, imp_to, "precedes")
            else:
                top_module = imp_to.split(".")[0]
                if self._kg.get_node(top_module) is not None:
                    self._kg.add_relation(imp_from, top_module, "precedes")

        for node in self._kg.nodes:
            if node.metadata.get("provenance") == "ai_generated":
                node.confidence /= 2.0

        return hierarchy

    def extract_test_coverage_relations(self, test_root: str, source_root: str) -> int:
        test_parser = CodeParser()
        test_hierarchy = test_parser.extract_module_hierarchy(test_root)

        test_count = 0
        for func in test_hierarchy.functions:
            test_node_id = f"test:{func.name}"
            test_count += 1
            self._kg.add_node(
                KnowledgeNode(
                    id=test_node_id,
                    type="test",
                    content=f"Test: {func.name}",
                    confidence=1.0,
                    source="test_parser",
                    timestamp=time.time(),
                )
            )

            for mod_node in self._kg.get_nodes_by_type("module"):
                if mod_node.id in test_node_id or test_node_id.replace("test:", "") in mod_node.id:
                    self._kg.add_relation(test_node_id, mod_node.id, "tests")

        return test_count

    def arch_hypothesis_cycle(self) -> list[ArchHypothesis]:
        hypotheses: list[ArchHypothesis] = []

        dep_count: dict[str, int] = {}
        human_dep_count: dict[str, int] = {}
        for node in self._kg.nodes:
            prov = node.metadata.get("provenance", "unknown")
            for edge in node.out_edges:
                if edge.relation.value == "precedes":
                    dep_count[edge.target_id] = dep_count.get(edge.target_id, 0) + 1
                    if prov == "human":
                        human_dep_count[edge.target_id] = human_dep_count.get(edge.target_id, 0) + 1

        for module_name, count in dep_count.items():
            if count >= 3:
                human_count = human_dep_count.get(module_name, 0)
                suffix = f"（其中 {human_count} 个来自人类标注节点）" if human_count > 0 else ""
                hypotheses.append(
                    ArchHypothesis(
                        hypothesis_id=f"h_decouple_{uuid.uuid4().hex[:8]}",
                        description=f"{module_name} 被 {count} 个模块依赖，耦合度偏高{suffix}",
                        target_module=module_name,
                        confidence=min(1.0, (count + human_count) / 10.0),
                    )
                )

        modules = self._kg.get_nodes_by_type("module")
        classes = self._kg.get_nodes_by_type("class")

        if len(modules) > 0 and len(classes) / len(modules) < 2:
            hypotheses.append(
                ArchHypothesis(
                    hypothesis_id=f"h_more_classes_{uuid.uuid4().hex[:8]}",
                    description="模块平均类数量偏低，建议拆分大类",
                    target_module="global",
                    confidence=0.6,
                )
            )

        tested_modules: set[str] = set()
        for node in self._kg.nodes:
            for edge in node.out_edges:
                if edge.relation.value == "tests":
                    tested_modules.add(edge.target_id)

        for mod in modules:
            if mod.id not in tested_modules:
                hypotheses.append(
                    ArchHypothesis(
                        hypothesis_id=f"h_untested_{uuid.uuid4().hex[:8]}",
                        description=f"{mod.id} 缺少测试覆盖",
                        target_module=mod.id,
                        confidence=0.8,
                    )
                )

        hypotheses.sort(
            key=lambda h: (
                0 if "人类" in h.description else 1,
                -h.confidence,
            )
        )

        return hypotheses[:5]

    def query_coverage_gaps(self) -> list[str]:
        gaps: list[str] = []
        modules = self._kg.get_nodes_by_type("module")
        tested: set[str] = set()
        for node in self._kg.nodes:
            for edge in node.out_edges:
                if edge.relation.value == "TESTS":
                    tested.add(edge.target_id)

        for mod in modules:
            if mod.id not in tested:
                gaps.append(mod.id)
        return gaps

    def node_count(self) -> int:
        return len(self._kg.nodes)

    def node_types(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for node in self._kg.nodes:
            counts[node.type] = counts.get(node.type, 0) + 1
        return counts

    def relation_types(self) -> set[str]:
        types: set[str] = set()
        for node in self._kg.nodes:
            for edge in node.out_edges:
                types.add(edge.relation.value)
        return types
