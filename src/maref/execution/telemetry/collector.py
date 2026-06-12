"""HarnessTelemetryCollector — 记录 Harness 执行的遥测数据。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TelemetryEvent:
    timestamp: float = field(default_factory=time.time)
    harness_id: str = ""
    lifecycle_stage: str = ""
    latency_ms: float = 0.0
    error: str = ""
    tool_calls: int = 0
    token_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "harness_id": self.harness_id,
            "lifecycle_stage": self.lifecycle_stage,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "tool_calls": self.tool_calls,
            "token_count": self.token_count,
            "metadata": self.metadata,
        }


@dataclass
class TelemetryReport:
    total_events: int = 0
    total_duration_ms: float = 0.0
    total_tool_calls: int = 0
    total_token_count: int = 0
    error_count: int = 0
    stage_summary: dict[str, int] = field(default_factory=dict)
    harness_summary: dict[str, int] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_events": self.total_events,
            "total_duration_ms": self.total_duration_ms,
            "total_tool_calls": self.total_tool_calls,
            "total_token_count": self.total_token_count,
            "error_count": self.error_count,
            "stage_summary": self.stage_summary,
            "harness_summary": self.harness_summary,
        }


class HarnessTelemetryCollector:
    """记录 Harness 执行的遥测数据并生成报告。"""

    def __init__(self) -> None:
        self._events: list[TelemetryEvent] = []

    def record(self, event: TelemetryEvent) -> None:
        self._events.append(event)

    def record_event(
        self,
        harness_id: str = "",
        lifecycle_stage: str = "",
        latency_ms: float = 0.0,
        error: str = "",
        tool_calls: int = 0,
        token_count: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> TelemetryEvent:
        event = TelemetryEvent(
            harness_id=harness_id,
            lifecycle_stage=lifecycle_stage,
            latency_ms=latency_ms,
            error=error,
            tool_calls=tool_calls,
            token_count=token_count,
            metadata=metadata or {},
        )
        self._events.append(event)
        return event

    def report(self) -> TelemetryReport:
        if not self._events:
            return TelemetryReport()

        stage_summary: dict[str, int] = {}
        harness_summary: dict[str, int] = {}
        total_duration = 0.0
        total_tool_calls = 0
        total_tokens = 0
        error_count = 0

        for e in self._events:
            stage_summary[e.lifecycle_stage] = stage_summary.get(e.lifecycle_stage, 0) + 1
            harness_summary[e.harness_id] = harness_summary.get(e.harness_id, 0) + 1
            total_duration += e.latency_ms
            total_tool_calls += e.tool_calls
            total_tokens += e.token_count
            if e.error:
                error_count += 1

        return TelemetryReport(
            total_events=len(self._events),
            total_duration_ms=total_duration,
            total_tool_calls=total_tool_calls,
            total_token_count=total_tokens,
            error_count=error_count,
            stage_summary=stage_summary,
            harness_summary=harness_summary,
            events=[e.to_dict() for e in self._events[-20:]],
        )

    def clear(self) -> None:
        self._events.clear()

    @property
    def event_count(self) -> int:
        return len(self._events)
