from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maref.governance.audit_bus import AuditBus


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
    tenant_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
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
        if self.tenant_id:
            result["tenant_id"] = self.tenant_id
        return result

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
            tenant_id=data.get("tenant_id", ""),
        )


class NullAuditStore:
    """No-op audit store for dev/test.

    **安全要求**：审计记录不得静默丢弃。append() 时发出显式告警，
    提醒调用方记录未被持久化；仅在确认丢弃可接受的场景显式使用。
    """

    def append(self, record: UnifiedAuditRecord) -> None:
        import warnings

        warnings.warn(
            f"NullAuditStore: audit record dropped (event_type={record.event_type}, "
            f"source={record.source_module}). Audit trail not persisted.",
            RuntimeWarning,
            stacklevel=2,
        )

    def query_by_layer(self, layer: str) -> list[UnifiedAuditRecord]:
        return []

    def query_by_event(self, event_type: str) -> list[UnifiedAuditRecord]:
        return []

    def query_by_module(self, module: str) -> list[UnifiedAuditRecord]:
        return []


class UnifiedAuditStore:
    """Audit store that delegates persistence to AuditBus.

    When *persist_path* is provided, an ``AuditBus`` with an underlying
    ``AuditLogger`` is created automatically.  An externally-owned bus
    can be passed via the *audit_bus* parameter instead.
    """

    def __init__(
        self,
        persist_path: str | Path | None = None,
        audit_bus: AuditBus | None = None,
    ) -> None:
        self._records: list[UnifiedAuditRecord] = []
        self._by_layer: dict[str, list[int]] = defaultdict(list)
        self._by_module: dict[str, list[int]] = defaultdict(list)
        self._by_event_type: dict[str, list[int]] = defaultdict(list)
        self._by_round: dict[int, list[int]] = defaultdict(list)
        self._persist_path: Path | None = (
            Path(persist_path) if persist_path else None
        )
        if audit_bus is not None:
            self._audit_bus = audit_bus
        elif self._persist_path is not None:
            from maref.governance.audit import AuditLogger
            self._audit_bus = AuditBus(AuditLogger(self._persist_path))
        else:
            self._audit_bus = AuditBus()
        if self._persist_path:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    def append(self, record: UnifiedAuditRecord) -> None:
        idx = len(self._records)
        self._records.append(record)
        self._by_layer[record.layer].append(idx)
        self._by_module[record.source_module].append(idx)
        self._by_module[record.target_module].append(idx)
        self._by_event_type[record.event_type].append(idx)
        self._by_round[record.round].append(idx)
        # AuditBus has no `publish`; log_from_unified persists via the bus
        # logger (when configured) and fans out to pub/sub subscribers.
        self._audit_bus.log_from_unified(record)

    def query_by_layer(self, layer: str) -> list[UnifiedAuditRecord]:
        return [self._records[i] for i in self._by_layer.get(layer, [])]

    def query_by_event(self, event_type: str) -> list[UnifiedAuditRecord]:
        return [self._records[i] for i in self._by_event_type.get(event_type, [])]

    def query_by_module(self, module: str) -> list[UnifiedAuditRecord]:
        return [self._records[i] for i in self._by_module.get(module, [])]

    def query_by_round(self, round_num: int) -> list[UnifiedAuditRecord]:
        return [self._records[i] for i in self._by_round.get(round_num, [])]

    def query_decision_chain(
        self, record_id: str, max_depth: int = 10
    ) -> list[UnifiedAuditRecord]:
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

    def query(self, **kwargs: Any) -> list[UnifiedAuditRecord]:
        """Generic query — filters records by arbitrary field values."""
        results: list[UnifiedAuditRecord] = []
        for record in self._records:
            match = True
            for key, value in kwargs.items():
                if not hasattr(record, key) or getattr(record, key) != value:
                    match = False
                    break
            if match:
                results.append(record)
        return results

    @property
    def persist_path(self) -> Path | None:
        return self._persist_path

    def _load_from_disk(self) -> None:
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            with open(self._persist_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    record = UnifiedAuditRecord.from_dict(data)
                    idx = len(self._records)
                    self._records.append(record)
                    self._by_layer[record.layer].append(idx)
                    self._by_module[record.source_module].append(idx)
                    self._by_module[record.target_module].append(idx)
                    self._by_event_type[record.event_type].append(idx)
                    self._by_round[record.round].append(idx)
        except (OSError, json.JSONDecodeError):
            pass


def make_record_id(prefix: str, counter: int) -> str:
    return f"{prefix}_{counter:06d}_{int(time.time() * 1000)}"


class UnifiedAudit:
    """Stub for backward compatibility — delegates to UnifiedAuditStore."""

    def __init__(self) -> None:
        self.store = UnifiedAuditStore()

    def log(self, record: UnifiedAuditRecord) -> None:
        self.store.append(record)

    def query(self, **kwargs: Any) -> list[UnifiedAuditRecord]:
        return self.store.query(**kwargs)
