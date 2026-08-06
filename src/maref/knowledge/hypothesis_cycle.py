from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.knowledge.compiled_truth import CompiledTruth, TruthPage
from maref.knowledge.graph import KnowledgeGraph, KnowledgeNode
from maref.knowledge.truth_store import TruthStore

NODE_TYPES = frozenset({"finding", "hypothesis", "question", "experiment"})

# 保守写回：低于该置信度的确认结论只追加证据，不升级 current_best
_CONFIRM_THRESHOLD = 0.7


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
    entity_id: str = ""


class HypothesisCycle:
    NODE_TYPES_COUNT = 4

    def __init__(self, kg: KnowledgeGraph, truth_store: TruthStore | None = None) -> None:
        self._kg = kg
        self._truth_store = truth_store
        self._hypotheses: dict[str, HypothesisRecord] = {}

    def propose(
        self,
        question: str,
        hypothesis_text: str,
        source: str = "agent",
        entity_id: str | None = None,
        prior_truth: dict[str, Any] | None = None,
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

        entity_id = entity_id or self._default_entity_id(question)
        prior = prior_truth or {}
        prior_best = prior.get("current_best")
        h_content = hypothesis_text
        if prior_best:
            h_content = (
                f"{hypothesis_text}\n[prior_truth] {prior_best}"
                f" (conf {prior.get('confidence', 0.0):.2f})"
            )
        h_node = KnowledgeNode(
            id=f"h-{int(time.time())}-{hash(hypothesis_text) % 10000}",
            type="hypothesis",
            content=h_content,
            confidence=0.6,
            source=source,
            timestamp=time.time(),
        )
        h_node.metadata["entity_id"] = entity_id
        if prior_best:
            h_node.metadata["prior_truth"] = prior_best
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
            entity_id=entity_id,
        )
        self._hypotheses[h_node.id] = record
        return record

    def run_experiment(
        self, hyp_id: str, experiment_desc: str, source: str = "agent"
    ) -> str | None:
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
        self,
        hyp_id: str,
        finding_text: str,
        supports: bool,
        confidence: float,
        source: str = "agent",
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
        self._append_evidence(hyp.entity_id, finding_text, source, confidence, supports)
        hyp.updated_at = time.time()
        return True

    def conclude(
        self,
        hyp_id: str,
        conclusion: str,
        confirmed: bool,
        agent_id: str = "agent",
    ) -> HypothesisRecord | None:
        hyp = self._hypotheses.get(hyp_id)
        if hyp is None:
            return None
        hyp.status = HypothesisStatus.CONFIRMED if confirmed else HypothesisStatus.REFUTED
        hyp.conclusion = conclusion
        hyp.updated_at = time.time()

        # 递归回写：确认且置信度达标才升级 current_best；否则仅追加证据
        if self._truth_store is not None and hyp.entity_id:
            if confirmed and hyp.confidence >= _CONFIRM_THRESHOLD:
                self._compile_truth(hyp.entity_id, conclusion, agent_id, hyp.confidence)
            else:
                self._append_evidence(
                    hyp.entity_id, conclusion, agent_id, hyp.confidence, confirmed
                )
        return hyp

    @staticmethod
    def _default_entity_id(question: str) -> str:
        norm = " ".join(question.strip().lower().split())
        return f"topic:{norm[:48]}"

    def _append_evidence(
        self,
        entity_id: str,
        text: str,
        source: str,
        confidence: float,
        supports: bool = True,
    ) -> None:
        """追加证据到 TruthPage（只追加，不升级 current_best）。"""
        if self._truth_store is None or not entity_id:
            return
        page = self._truth_store.load(entity_id)
        if page is None:
            page = self._new_page(entity_id, source)
        prefix = "支持" if supports else "否定"
        page.add_evidence(text=f"[{prefix}] {text}", source=source, confidence=confidence)
        self._truth_store.save(page)

    def _compile_truth(
        self, entity_id: str, new_best: str, agent_id: str, confidence: float
    ) -> None:
        """确认结论升级 current_best，旧版本自动进入证据链。"""
        if self._truth_store is None:
            return
        page = self._truth_store.load(entity_id)
        if page is None:
            page = self._new_page(entity_id, agent_id)
        page.compile(new_best, agent_id, confidence)
        self._truth_store.save(page)

    @staticmethod
    def _new_page(entity_id: str, agent_id: str) -> TruthPage:
        return TruthPage(
            entity_id=entity_id,
            compiled_truth=CompiledTruth(
                entity_id=entity_id,
                current_best="",
                confidence=0.0,
                last_updated=time.time(),
                updated_by=agent_id,
            ),
        )

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
