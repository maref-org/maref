"""TruthWriteback — 将演进假设结果递归写回 TruthStore.

对齐桥水 Pat 案例的"组织学习复利"：分析输出落回同一存储库，
人和智能体互相复利。daily_loop 生成架构假设 → 登记到 HypothesisCycle
（注入 prior_truth 作为推理上下文）→ engine.run() 实验结果出来后
resolve_outcome 写回 TruthPage（确认升级 / 失败仅追加证据）。
"""

from __future__ import annotations

from typing import Any

from maref.knowledge.compiled_truth import TruthPage
from maref.knowledge.graph import KnowledgeGraph
from maref.knowledge.hypothesis_cycle import HypothesisCycle, HypothesisRecord
from maref.knowledge.truth_store import TruthStore

# 实验通过/失败时结论的后验置信度（供保守写回阈值判定）
_CONFIRM_CONFIDENCE = 0.9
_REFUTE_CONFIDENCE = 0.4


class TruthWriteback:
    """Bridges optimization hypotheses to HypothesisCycle + TruthStore."""

    def __init__(self, store: TruthStore | None = None) -> None:
        self._store = store or TruthStore()
        self._kg = KnowledgeGraph()
        self._cycle = HypothesisCycle(self._kg, truth_store=self._store)
        self._hyp_map: dict[str, str] = {}

    @property
    def cycle(self) -> HypothesisCycle:
        return self._cycle

    @property
    def store(self) -> TruthStore:
        return self._store

    def register_hypothesis(
        self,
        hypothesis_id: str,
        description: str,
        target_module: str,
        confidence: float = 0.5,
    ) -> HypothesisRecord | None:
        """登记一条假设到假设循环，注入该实体的 prior_truth 作为推理上下文。"""
        entity_id = f"arch:{target_module}"
        prior = self._store.get_truth_context(entity_id)
        record = self._cycle.propose(
            question=f"架构假设: {description}",
            hypothesis_text=description,
            source="daily_loop",
            entity_id=entity_id,
            prior_truth=prior,
        )
        record.confidence = confidence
        self._hyp_map[hypothesis_id] = record.node_id
        return record

    def resolve_outcome(
        self,
        hypothesis_id: str,
        all_passed: bool,
        summary: str,
        source: str = "daily_loop",
    ) -> TruthPage | None:
        """把演进实验结果写回 TruthPage（确认升级 current_best / 失败仅追加证据）。"""
        node_id = self._hyp_map.get(hypothesis_id)
        if node_id is None:
            return None
        record = self._cycle.get_hypothesis(node_id)
        if record is None:
            return None
        confidence = _CONFIRM_CONFIDENCE if all_passed else _REFUTE_CONFIDENCE
        self._cycle.record_finding(
            node_id,
            finding_text=f"evolution outcome: all_passed={all_passed} ({summary})",
            supports=all_passed,
            confidence=confidence,
            source=source,
        )
        record.confidence = confidence
        self._cycle.conclude(
            node_id,
            conclusion=summary if all_passed else f"未通过: {summary}",
            confirmed=all_passed,
            agent_id=source,
        )
        return self._store.load(record.entity_id)

    def get_truth_context(self, entity_id: str) -> dict[str, Any] | None:
        """回读指定实体的真值上下文，供后续推理注入。"""
        return self._store.get_truth_context(entity_id)
