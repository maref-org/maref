"""
MAREF ↔ Memory System Bridge (autoDream + Karpathy Wiki)

M6.5: Connects MAREF's knowledge graph to Athena's memory cognition system.

Flow:
  KnowledgeGraph.get_insights() → autoDream.ORIENT stage
  High-confidence hypotheses → autoDream.ORIENT as固化 candidates
  Structured findings → Karpathy Wiki entries

Bridge operations:
- push_to_autodream(hypothesis) — send hypothesis to autoDream queue
- push_to_karpathy(finding) — write finding as a Karpathy Wiki entry
- pull_insights() — query memory system for relevant prior knowledge
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MemoryStage(Enum):
    ORIENT = "orient"
    CONSOLIDATE = "consolidate"
    RETRIEVE = "retrieve"


class MemoryPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class MemoryEntry:
    entry_id: str
    content: str
    source: str
    priority: MemoryPriority = MemoryPriority.MEDIUM
    stage: MemoryStage = MemoryStage.ORIENT
    confidence: float = 0.5
    tags: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_autodream_payload(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "stage": self.stage.value,
            "content": self.content,
            "confidence": self.confidence,
            "source": self.source,
            "priority": self.priority.value,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    def to_karpathy_wiki_entry(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "content": self.content,
            "tags": self.tags,
            "source": self.source,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class KnowledgeInsight:
    insight_id: str
    insight_type: str
    summary: str
    related_nodes: list[str] = field(default_factory=list)
    evidence_strength: float = 0.5
    actions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "insight_id": self.insight_id,
            "type": self.insight_type,
            "summary": self.summary,
            "related_nodes": self.related_nodes,
            "evidence_strength": self.evidence_strength,
            "actions": self.actions,
            "metadata": self.metadata,
        }


class MemoryBridge:
    """
    Bridge between MAREF knowledge graph and Athena memory systems.

    autoDream integration:
    - hypothesis → ORIENT stage queue
    - evidence_strength > 0.7 → consolidate candidate

    Karpathy Wiki integration:
    - finding → wiki entry
    - cross-references by tags
    """

    def __init__(self, bridge_id: str = "maref-memory") -> None:
        self._bridge_id = bridge_id
        self._entries: list[MemoryEntry] = []
        self._insights: list[KnowledgeInsight] = []
        self._entry_counter = 0

    def push_to_autodream(
        self,
        content: str,
        confidence: float = 0.5,
        priority: MemoryPriority = MemoryPriority.MEDIUM,
        source: str = "knowledge_graph",
        tags: list[str] | None = None,
        **meta: Any,
    ) -> MemoryEntry:
        self._entry_counter += 1
        entry = MemoryEntry(
            entry_id=f"autodream-{self._entry_counter:06d}",
            content=content,
            source=source,
            priority=priority,
            stage=MemoryStage.ORIENT,
            confidence=confidence,
            tags=tags or [],
            metadata=meta,
        )
        self._entries.append(entry)
        return entry

    def push_to_karpathy(
        self,
        content: str,
        confidence: float = 0.5,
        source: str = "knowledge_graph",
        tags: list[str] | None = None,
        **meta: Any,
    ) -> MemoryEntry:
        self._entry_counter += 1
        entry = MemoryEntry(
            entry_id=f"karpathy-{self._entry_counter:06d}",
            content=content,
            source=source,
            priority=MemoryPriority.MEDIUM if confidence < 0.7 else MemoryPriority.HIGH,
            stage=MemoryStage.CONSOLIDATE,
            confidence=confidence,
            tags=tags or [],
            metadata=meta,
        )
        self._entries.append(entry)
        return entry

    def record_insight(self, insight: KnowledgeInsight) -> None:
        self._insights.append(insight)

    def extract_insights_from_graph(
        self,
        stats: dict[str, Any],
        min_confidence: float = 0.5,
    ) -> list[KnowledgeInsight]:
        insights: list[KnowledgeInsight] = []

        if stats.get("orphan_ratio", 1.0) > 0.5:
            insights.append(
                KnowledgeInsight(
                    insight_id=f"insi-{time.time():.0f}-01",
                    insight_type="orphan_warning",
                    summary="More than 50% of knowledge graph nodes are orphaned",
                    evidence_strength=0.85,
                    actions=["extract_relations", "reconnect_nodes"],
                )
            )

        for hypo in stats.get("active_hypotheses", []):
            conf = hypo.get("confidence", 0)
            if conf >= min_confidence:
                insights.append(
                    KnowledgeInsight(
                        insight_id=f"insi-{time.time():.0f}-{hypo.get('id', '?')}",
                        insight_type="hypothesis",
                        summary=hypo.get("description", ""),
                        evidence_strength=conf,
                        actions=["push_to_autodream"] if conf > 0.7 else [],
                    )
                )

        return insights

    def query_memory(
        self,
        query: str,
        tag_filter: list[str] | None = None,
        min_confidence: float = 0.3,
    ) -> list[MemoryEntry]:
        results = []
        query_lower = query.lower()
        for entry in self._entries:
            if entry.confidence < min_confidence:
                continue
            if tag_filter and not any(t in entry.tags for t in tag_filter):
                continue
            if query_lower in entry.content.lower():
                results.append(entry)
        return results

    def get_autodream_queue(self) -> list[MemoryEntry]:
        return [e for e in self._entries if e.stage == MemoryStage.ORIENT]

    def get_karpathy_entries(self) -> list[dict[str, Any]]:
        return [
            e.to_karpathy_wiki_entry() for e in self._entries if e.stage == MemoryStage.CONSOLIDATE
        ]

    def export_all(self) -> dict[str, Any]:
        return {
            "bridge_id": self._bridge_id,
            "autodream_queue": [e.to_autodream_payload() for e in self.get_autodream_queue()],
            "karpathy_entries": self.get_karpathy_entries(),
            "insights": [i.to_dict() for i in self._insights],
            "total_entries": len(self._entries),
        }

    def export_json(self) -> str:
        return json.dumps(self.export_all(), indent=2, default=str)

    def get_stats(self) -> dict[str, Any]:
        autodream_count = len(self.get_autodream_queue())
        karpathy_count = len(self.get_karpathy_entries())
        return {
            "total_entries": len(self._entries),
            "insight_count": len(self._insights),
            "autodream_queue_size": autodream_count,
            "karpathy_entry_count": karpathy_count,
            "by_priority": {
                p.value: sum(1 for e in self._entries if e.priority == p) for p in MemoryPriority
            },
            "high_confidence_count": sum(1 for e in self._entries if e.confidence >= 0.7),
        }
