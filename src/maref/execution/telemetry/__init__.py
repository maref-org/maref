from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TelemetryEvent(str, Enum):
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


@dataclass
class TelemetryReport:
    run_id: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


class HarnessTelemetryCollector:
    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []

    def record(self, event: TelemetryEvent, data: dict[str, Any] | None = None) -> None:
        self._events.append({"event": event.value, "data": data or {}})

    def report(self, run_id: str = "") -> TelemetryReport:
        return TelemetryReport(run_id=run_id, events=list(self._events), summary={"count": len(self._events)})


class EvolutionDataFeed:
    def __init__(self) -> None:
        self._data: list[dict[str, Any]] = []

    def push(self, payload: dict[str, Any]) -> None:
        self._data.append(payload)

    def pull(self, limit: int = 10) -> list[dict[str, Any]]:
        return self._data[-limit:]


__all__ = [
    "HarnessTelemetryCollector",
    "TelemetryEvent",
    "TelemetryReport",
    "EvolutionDataFeed",
]
