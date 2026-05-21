from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RecursiveSpan:
    span_id: str
    parent_id: str | None
    round_num: int
    layer: str
    decision: str
    outcome: str | None
    start_time: float
    end_time: float = 0.0
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def finish(self) -> None:
        self.end_time = time.time()

    @property
    def duration_ms(self) -> float:
        end = self.end_time if self.end_time > 0 else time.time()
        return (end - self.start_time) * 1000.0


class RecursiveTracer:
    def __init__(self) -> None:
        self._spans: list[RecursiveSpan] = []
        self._active: dict[str, RecursiveSpan] = {}
        self._span_stack: list[str] = []

    def start_span(
        self,
        round_num: int,
        layer: str,
        decision: str = "",
        outcome: str | None = None,
        parent_id: str | None = None,
        **attributes: Any,
    ) -> RecursiveSpan:
        span_id = f"span_r{round_num}_{layer}_{uuid.uuid4().hex[:8]}"
        if parent_id is None and self._span_stack:
            parent_id = self._span_stack[-1]

        span = RecursiveSpan(
            span_id=span_id,
            parent_id=parent_id,
            round_num=round_num,
            layer=layer,
            decision=decision,
            outcome=outcome,
            start_time=time.time(),
            attributes=dict(attributes),
        )
        self._spans.append(span)
        self._active[span_id] = span
        self._span_stack.append(span_id)
        return span

    def end_span(self, span_id: str, outcome: str | None = None) -> None:
        span = self._active.get(span_id)
        if span is not None:
            span.finish()
            if outcome is not None:
                span.outcome = outcome
            del self._active[span_id]
            if self._span_stack and self._span_stack[-1] == span_id:
                self._span_stack.pop()

    def add_event(self, span_id: str, name: str, **attributes: Any) -> None:
        span = self._active.get(span_id)
        if span is not None:
            span.events.append({
                "name": name,
                "timestamp": time.time(),
                "attributes": attributes,
            })

    def set_attribute(self, span_id: str, key: str, value: Any) -> None:
        span = self._active.get(span_id)
        if span is not None:
            span.attributes[key] = value

    def get_span(self, span_id: str) -> RecursiveSpan | None:
        for s in self._spans:
            if s.span_id == span_id:
                return s
        return None

    def get_span_hierarchy(self) -> dict[str, list[str]]:
        hierarchy: dict[str, list[str]] = {}
        for span in self._spans:
            key = span.parent_id or "root"
            if key not in hierarchy:
                hierarchy[key] = []
            hierarchy[key].append(span.span_id)
        return hierarchy

    def spans_by_round(self, round_num: int) -> list[RecursiveSpan]:
        return [s for s in self._spans if s.round_num == round_num]

    def spans_by_layer(self, layer: str) -> list[RecursiveSpan]:
        return [s for s in self._spans if s.layer == layer]

    def span_count(self) -> int:
        return len(self._spans)

    def all_spans(self) -> list[RecursiveSpan]:
        return list(self._spans)

    def clear(self) -> None:
        self._spans.clear()
        self._active.clear()
        self._span_stack.clear()


@dataclass
class GovernanceMetrics:
    cb_trips_total: int = 0
    cb_trips_last_hour: int = 0
    meta_cb_interventions: int = 0

    heal_attempts: int = 0
    heal_success_rate: float = 0.0
    avg_heal_cycle_count: float = 0.0

    optimization_proposals: int = 0
    optimization_adoptions: int = 0
    adoption_rate: float = 0.0

    chaos_injections_total: int = 0
    survival_rate: float = 1.0
    avg_recovery_time_ms: float = 0.0

    federation_sync_latency_ms: float = 0.0
    cross_framework_task_success_rate: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cb_trips_total": self.cb_trips_total,
            "cb_trips_last_hour": self.cb_trips_last_hour,
            "meta_cb_interventions": self.meta_cb_interventions,
            "heal_attempts": self.heal_attempts,
            "heal_success_rate": self.heal_success_rate,
            "avg_heal_cycle_count": self.avg_heal_cycle_count,
            "optimization_proposals": self.optimization_proposals,
            "optimization_adoptions": self.optimization_adoptions,
            "adoption_rate": self.adoption_rate,
            "chaos_injections_total": self.chaos_injections_total,
            "survival_rate": self.survival_rate,
            "avg_recovery_time_ms": self.avg_recovery_time_ms,
            "federation_sync_latency_ms": self.federation_sync_latency_ms,
            "cross_framework_task_success_rate": self.cross_framework_task_success_rate,
        }

    def record_cb_trip(self) -> None:
        self.cb_trips_total += 1
        self.cb_trips_last_hour += 1

    def record_heal(self, success: bool, cycle_count: int) -> None:
        self.heal_attempts += 1
        if success:
            old_total = (self.heal_attempts - 1) * self.heal_success_rate
            self.heal_success_rate = (old_total + 1) / self.heal_attempts
        else:
            old_total = (self.heal_attempts - 1) * self.heal_success_rate
            self.heal_success_rate = old_total / self.heal_attempts

        if self.heal_attempts > 1:
            self.avg_heal_cycle_count = (
                (self.avg_heal_cycle_count * (self.heal_attempts - 1) + cycle_count)
                / self.heal_attempts
            )
        else:
            self.avg_heal_cycle_count = float(cycle_count)

    def record_optimization(self, adopted: bool) -> None:
        self.optimization_proposals += 1
        if adopted:
            self.optimization_adoptions += 1
        self.adoption_rate = (
            self.optimization_adoptions / self.optimization_proposals
            if self.optimization_proposals > 0
            else 0.0
        )

    def record_chaos(self, survived: bool, recovery_time_ms: float) -> None:
        self.chaos_injections_total += 1
        total_survived = self.survival_rate * (self.chaos_injections_total - 1)
        if survived:
            total_survived += 1
        self.survival_rate = total_survived / self.chaos_injections_total

        prev_total = self.avg_recovery_time_ms * (self.chaos_injections_total - 1)
        self.avg_recovery_time_ms = (prev_total + recovery_time_ms) / self.chaos_injections_total


class StructuredLogger:
    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    def log(self, level: str, message: str, **fields: Any) -> None:
        entry = {
            "timestamp": time.time(),
            "level": level,
            "message": message,
            **fields,
        }
        self._entries.append(entry)

    def entries(self) -> list[dict[str, Any]]:
        return list(self._entries)

    def by_level(self, level: str) -> list[dict[str, Any]]:
        return [e for e in self._entries if e.get("level") == level]

    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()

    def to_json(self) -> str:
        return json.dumps(self._entries, indent=2, default=str)
