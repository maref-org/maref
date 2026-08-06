import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maref.knowledge.graph import KnowledgeGraph, KnowledgeNode
else:
    # P0-A fix: TYPE_CHECKING is import-time only. The `kg: KnowledgeGraph | None`
    # annotation on ProvenanceTracker.__init__ is evaluated at runtime when the
    # module is imported (no `from __future__ import annotations`), so we need
    # a runtime placeholder to avoid NameError in downstream consumers (e.g.
    # PERCV's `percv.governance` import chain). `Any` keeps the optional hint
    # semantically equivalent for tooling.
    KnowledgeGraph = Any  # type: ignore[misc,assignment]
    KnowledgeNode = Any  # type: ignore[misc,assignment]
PRE_2023_CUTOFF = 1672531200.0

@dataclass
class ProvenanceRecord:
    node_id: str
    provenance: str
    timestamp: float
    source: str

class ProvenanceTracker:
    PROVENANCE_LABELS = frozenset({'human', 'ai_assisted', 'ai_generated', 'unknown'})

    def __init__(self, kg: KnowledgeGraph | None=None):
        self._kg = kg
        self._records: dict[str, ProvenanceRecord] = {}

    def label_node(self, node_id: str, provenance: str, source: str='manual') -> None:
        if provenance not in self.PROVENANCE_LABELS:
            raise ValueError(f'Invalid provenance: {provenance}. Must be one of {sorted(self.PROVENANCE_LABELS)}')
        if self._kg is not None:
            node = self._kg.get_node(node_id)
            if node is not None:
                node.metadata['provenance'] = provenance
        self._records[node_id] = ProvenanceRecord(node_id=node_id, provenance=provenance, timestamp=time.time(), source=source)

    def get_provenance(self, node_id: str) -> str | None:
        if self._kg is not None:
            node = self._kg.get_node(node_id)
            if node is not None:
                return node.metadata.get('provenance')
        record = self._records.get(node_id)
        return record.provenance if record is not None else None

    def retrieve(self, pre_2023: bool=False, provenance: str | None=None) -> list[KnowledgeNode]:
        if self._kg is None:
            return []
        nodes = list(self._kg.nodes)
        if pre_2023:
            nodes = [n for n in nodes if n.timestamp < PRE_2023_CUTOFF]
        if provenance is not None:
            matching = [n for n in nodes if n.metadata.get('provenance') == provenance]
            others = [n for n in nodes if n.metadata.get('provenance') != provenance]
            nodes = matching + others
        return nodes

    def summarize(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        if self._kg is not None:
            for node in self._kg.nodes:
                prov = node.metadata.get('provenance', 'unknown')
                counts[prov] = counts.get(prov, 0) + 1
        return counts
