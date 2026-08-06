from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SamplingStrategy(Enum):
    FULL = "full"
    SAMPLING = "sampling"
    LAZY = "lazy"


_SAMPLING_RATES: dict[SamplingStrategy, float] = {
    SamplingStrategy.FULL: 1.0,
    SamplingStrategy.SAMPLING: 0.1,
    SamplingStrategy.LAZY: 0.01,
}


@dataclass
class RuntimeCallRecord:
    caller: str
    callee: str
    call_count: int = 0
    avg_latency: float = 0.0
    error_count: int = 0
    last_error: str = ""


class RuntimeInstrumentor:
    def __init__(self) -> None:
        self._records: list[RuntimeCallRecord] = []
        self._by_caller: dict[str, list[int]] = defaultdict(list)
        self._strategy: SamplingStrategy = SamplingStrategy.FULL
        self._critical_callers: set[str] = set()
        self._sampling_counters: dict[str, int] = defaultdict(int)
        self._sampling_interval: int = 10

    def configure_sampling(
        self,
        strategy: SamplingStrategy = SamplingStrategy.FULL,
        critical_callers: set[str] | None = None,
        sampling_interval: int = 10,
    ) -> None:
        self._strategy = strategy
        if critical_callers is not None:
            self._critical_callers = critical_callers
        self._sampling_interval = max(1, sampling_interval)

    def _should_record(self, caller: str) -> bool:
        if caller in self._critical_callers:
            return True
        if self._strategy == SamplingStrategy.FULL:
            return True
        if self._strategy == SamplingStrategy.LAZY:
            self._sampling_counters[caller] += 1
            return self._sampling_counters[caller] % self._sampling_interval == 0
        return random.random() < _SAMPLING_RATES[self._strategy]

    def record_call(
        self, caller: str, callee: str, latency_ms: float = 0.0, error: str = ""
    ) -> None:
        if not self._should_record(caller):
            return
        record = RuntimeCallRecord(
            caller=caller,
            callee=callee,
            call_count=1,
            avg_latency=latency_ms,
            error_count=1 if error else 0,
            last_error=error,
        )
        self._records.append(record)
        self._by_caller[caller].append(len(self._records) - 1)

    def get_calls_from(self, caller: str) -> list[RuntimeCallRecord]:
        return [self._records[i] for i in self._by_caller.get(caller, [])]

    def all_records(self) -> list[RuntimeCallRecord]:
        return list(self._records)

    def clear(self) -> None:
        self._records.clear()
        self._by_caller.clear()


@dataclass
class RuntimeKGNode:
    node_id: str
    node_type: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeKGRelation:
    from_node: str
    to_node: str
    relation_type: str
    properties: dict[str, Any] = field(default_factory=dict)


class RuntimeKGEnricher:
    def __init__(self) -> None:
        self._nodes: dict[str, RuntimeKGNode] = {}
        self._relations: list[RuntimeKGRelation] = []

    def add_node(self, node_id: str, node_type: str, **properties: Any) -> RuntimeKGNode:
        node = RuntimeKGNode(node_id=node_id, node_type=node_type, properties=dict(properties))
        self._nodes[node_id] = node
        return node

    def add_relation(
        self, from_node: str, to_node: str, relation_type: str, **properties: Any
    ) -> RuntimeKGRelation:
        rel = RuntimeKGRelation(
            from_node=from_node,
            to_node=to_node,
            relation_type=relation_type,
            properties=dict(properties),
        )
        self._relations.append(rel)
        return rel

    def inject_from_instrumentor(self, instrumentor: RuntimeInstrumentor) -> None:
        for record in instrumentor.all_records():
            if record.callee not in self._nodes:
                self.add_node(record.callee, "module", call_count=record.call_count)
            if record.caller not in self._nodes:
                self.add_node(record.caller, "module")

            rtype = "CALLS_FREQUENTLY" if record.call_count > 10 else "CALLS"
            self.add_relation(
                record.caller,
                record.callee,
                rtype,
                avg_latency=record.avg_latency,
                error_count=record.error_count,
            )
            if record.error_count > 0:
                self.add_relation(
                    record.caller,
                    record.callee,
                    "PROPAGATES_ERROR_TO",
                    last_error=record.last_error,
                )

    def query_hot_paths(self, min_frequency: int = 10) -> list[RuntimeKGRelation]:
        return [
            r
            for r in self._relations
            if r.relation_type == "CALLS_FREQUENTLY"
            and r.properties.get("call_count", 0) >= min_frequency
        ]

    def query_error_propagation(self) -> list[RuntimeKGRelation]:
        return [r for r in self._relations if r.relation_type == "PROPAGATES_ERROR_TO"]

    def query_bottlenecks(self, latency_threshold_ms: float = 100.0) -> list[RuntimeKGRelation]:
        return [
            r for r in self._relations if r.properties.get("avg_latency", 0) > latency_threshold_ms
        ]

    def node_count(self) -> int:
        return len(self._nodes)

    def relation_count(self) -> int:
        return len(self._relations)

    def get_node(self, node_id: str) -> RuntimeKGNode | None:
        return self._nodes.get(node_id)
