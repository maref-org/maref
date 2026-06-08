from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from maref.security.decorators import security_critical


@dataclass
class UnifiedAuditRecord:
    record_id: str
    timestamp: float
    layer: str
    round: int
    event_type: str
    source_module: str
    target_module: str
    decision: str
    justification: str
    outcome: str | None = None
    context_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp,
            "layer": self.layer,
            "round": self.round,
            "event_type": self.event_type,
            "source_module": self.source_module,
            "target_module": self.target_module,
            "decision": self.decision,
            "justification": self.justification,
            "outcome": self.outcome,
            "context_refs": self.context_refs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UnifiedAuditRecord:
        return cls(
            record_id=data["record_id"],
            timestamp=data["timestamp"],
            layer=data["layer"],
            round=data["round"],
            event_type=data["event_type"],
            source_module=data["source_module"],
            target_module=data["target_module"],
            decision=data["decision"],
            justification=data["justification"],
            outcome=data.get("outcome"),
            context_refs=data.get("context_refs", []),
        )


class UnifiedAuditStore:
    def __init__(self) -> None:
        self._records: list[UnifiedAuditRecord] = []
        self._by_layer: dict[str, list[int]] = defaultdict(list)
        self._by_module: dict[str, list[int]] = defaultdict(list)
        self._by_event_type: dict[str, list[int]] = defaultdict(list)
        self._by_round: dict[int, list[int]] = defaultdict(list)

    @security_critical
    def append(self, record: UnifiedAuditRecord) -> None:
        idx = len(self._records)
        self._records.append(record)
        self._by_layer[record.layer].append(idx)
        self._by_module[record.source_module].append(idx)
        self._by_module[record.target_module].append(idx)
        self._by_event_type[record.event_type].append(idx)
        self._by_round[record.round].append(idx)

    def query_by_layer(self, layer: str) -> list[UnifiedAuditRecord]:
        return [self._records[i] for i in self._by_layer.get(layer, [])]

    def query_by_event(self, event_type: str) -> list[UnifiedAuditRecord]:
        return [self._records[i] for i in self._by_event_type.get(event_type, [])]

    def query_by_module(self, module: str) -> list[UnifiedAuditRecord]:
        return [self._records[i] for i in self._by_module.get(module, [])]

    def query_by_round(self, round_num: int) -> list[UnifiedAuditRecord]:
        return [self._records[i] for i in self._by_round.get(round_num, [])]

    def query_decision_chain(self, record_id: str, max_depth: int = 10) -> list[UnifiedAuditRecord]:
        chain: list[UnifiedAuditRecord] = []
        visited: set[str] = set()
        queue = [record_id]
        depth = 0

        while queue and depth < max_depth:
            rid = queue.pop(0)
            if rid in visited:
                continue
            visited.add(rid)
            depth += 1

            for record in self._records:
                if record.record_id == rid:
                    chain.append(record)
                    for ref in record.context_refs:
                        if ref not in visited:
                            queue.append(ref)
                    break

        return chain

    def stats_by_event_type(self) -> dict[str, int]:
        return {k: len(v) for k, v in self._by_event_type.items()}

    def stats_by_module(self) -> dict[str, int]:
        return {k: len(v) for k, v in self._by_module.items()}

    def stats_by_round(self) -> dict[int, int]:
        return {k: len(v) for k, v in self._by_round.items()}

    def count(self) -> int:
        return len(self._records)

    def all(self) -> list[UnifiedAuditRecord]:
        return list(self._records)

    def clear(self) -> None:
        self._records.clear()
        self._by_layer.clear()
        self._by_module.clear()
        self._by_event_type.clear()
        self._by_round.clear()


def make_record_id(prefix: str, counter: int) -> str:
    return f"{prefix}_{counter:06d}_{int(time.time() * 1000)}"
