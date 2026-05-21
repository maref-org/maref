from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.knowledge.graph import KnowledgeGraph, KnowledgeNode

NODE_TYPES = frozenset({"finding", "hypothesis", "question", "experiment"})


class HypothesisStatus(str, Enum):
    PROPOSED = "proposed"
    TESTING = "testing"
    CONFIRMED = "confirmed"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"


@dataclass
class HypothesisRecord:
    node_id: str
    question: str
    hypothesis: str
    status: HypothesisStatus
    confidence: float
    created_at: float
    updated_at: float
    evidence: list[dict[str, Any]] = field(default_factory=list)
    conclusion: str = ""


class HypothesisCycle:
    NODE_TYPES_COUNT = 4

    def __init__(self, kg: KnowledgeGraph) -> None:
        self._kg = kg
        self._hypotheses: dict[str, HypothesisRecord] = {}

    def propose(
        self, question: str, hypothesis_text: str, source: str = "agent"
    ) -> HypothesisRecord:
        q_node = KnowledgeNode(
            id=f"q-{int(time.time())}-{hash(question) % 10000}",
            type="question",
            content=question,
            confidence=0.9,
            source=source,
            timestamp=time.time(),
        )
        self._kg.add_node(q_node)

        h_node = KnowledgeNode(
            id=f"h-{int(time.time())}-{hash(hypothesis_text) % 10000}",
            type="hypothesis",
            content=hypothesis_text,
            confidence=0.6,
            source=source,
            timestamp=time.time(),
        )
        self._kg.add_node(h_node)
        self._kg.add_relation(q_node.id, h_node.id, "suggests")

        record = HypothesisRecord(
            node_id=h_node.id,
            question=question,
            hypothesis=hypothesis_text,
            status=HypothesisStatus.PROPOSED,
            confidence=0.6,
            created_at=time.time(),
            updated_at=time.time(),
        )
        self._hypotheses[h_node.id] = record
        return record

    def run_experiment(self, hyp_id: str, experiment_desc: str, source: str = "agent") -> str | None:
        hyp = self._hypotheses.get(hyp_id)
        if hyp is None:
            return None
        exp_node = KnowledgeNode(
            id=f"e-{int(time.time())}-{hash(experiment_desc) % 10000}",
            type="experiment",
            content=experiment_desc,
            confidence=hyp.confidence,
            source=source,
            timestamp=time.time(),
        )
        self._kg.add_node(exp_node)
        self._kg.add_relation(hyp_id, exp_node.id, "tests")
        hyp.status = HypothesisStatus.TESTING
        hyp.updated_at = time.time()
        return exp_node.id

    def record_finding(
        self, hyp_id: str, finding_text: str, supports: bool, confidence: float, source: str = "agent"
    ) -> bool:
        hyp = self._hypotheses.get(hyp_id)
        if hyp is None:
            return False
        finding_node = KnowledgeNode(
            id=f"f-{int(time.time())}-{hash(finding_text) % 10000}",
            type="finding",
            content=finding_text,
            confidence=confidence,
            source=source,
            timestamp=time.time(),
        )
        self._kg.add_node(finding_node)
        relation = "supports" if supports else "contradicts"
        self._kg.add_relation(hyp_id, finding_node.id, relation)
        hyp.evidence.append(
            {
                "finding_id": finding_node.id,
                "content": finding_text,
                "supports": supports,
                "confidence": confidence,
            }
        )
        hyp.updated_at = time.time()
        return True

    def conclude(self, hyp_id: str, conclusion: str, confirmed: bool) -> HypothesisRecord | None:
        hyp = self._hypotheses.get(hyp_id)
        if hyp is None:
            return None
        hyp.status = HypothesisStatus.CONFIRMED if confirmed else HypothesisStatus.REFUTED
        hyp.conclusion = conclusion
        hyp.updated_at = time.time()
        return hyp

    def apply_time_decay(self, days_elapsed: float, decay_factor: float = 0.02) -> None:
        for hyp in self._hypotheses.values():
            decay = decay_factor * days_elapsed
            hyp.confidence = max(0.0, hyp.confidence - decay)
            node = self._kg.get_node(hyp.node_id)
            if node is not None:
                node.confidence = hyp.confidence
                nodes_by_type = self._kg.get_nodes_by_type("finding")
                for finding_node in nodes_by_type:
                    finding_node.metadata["hypothesis_confidence"] = hyp.confidence

    def get_hypothesis(self, hyp_id: str) -> HypothesisRecord | None:
        return self._hypotheses.get(hyp_id)

    @property
    def hypothesis_count(self) -> int:
        return len(self._hypotheses)
