"""Observation coverage + incident-silence metrics — 静默失败可观测性 (P2-10).

arXiv:2606.14589（fail-plausible 生产事故研究）：事故不以任务失败呈现、探测器全绿，
数小时至数月后才发现。作者指出事故报告最该记录两字段：**静默了多久、最终谁注意到**。

本模块提供：
- :class:`ObservationCoverage`：观察覆盖率 = 治理系统近 N 分钟实际观察到的动作数 /
  agent 实际执行的动作数。覆盖率是静默失败的前提——存在观察盲区才可能"探测器全绿"。
- :class:`IncidentRecord` / :class:`IncidentLedger`：事故记录含 ``silent_duration``
  与 ``discovered_by``，量化静默时长与发现来源，可汇总。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

_DEFAULT_ORIGIN = "unknown"


@dataclass
class ObservationCoverage:
    """Windowed ratio of observed actions to actually-executed actions."""

    window_seconds: float = 300.0
    threshold: float = 0.9
    clock: Callable[[], float] = time.time

    def __post_init__(self) -> None:
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("threshold must be in [0, 1]")
        self._observed: list[tuple[float, int]] = []
        self._actual: list[tuple[float, int]] = []

    def _prune(self, samples: list[tuple[float, int]]) -> None:
        cutoff = self.clock() - self.window_seconds
        index = 0
        for timestamp, _ in samples:
            if timestamp >= cutoff:
                break
            index += 1
        if index:
            del samples[:index]

    def _total(self, samples: list[tuple[float, int]]) -> int:
        self._prune(samples)
        return sum(count for _, count in samples)

    def record_observed(self, count: int = 1, at: float | None = None) -> None:
        """Record actions the governance system actually observed."""
        self._observed.append((self.clock() if at is None else at, max(0, count)))

    def record_actual(self, count: int = 1, at: float | None = None) -> None:
        """Record actions the agent actually executed."""
        self._actual.append((self.clock() if at is None else at, max(0, count)))

    def coverage(self) -> float:
        """Observed / actual within the window; 1.0 when nothing was executed."""
        actual = self._total(self._actual)
        if actual == 0:
            return 1.0
        return min(1.0, self._total(self._observed) / actual)

    def blind_spot(self) -> bool:
        """Whether coverage is below the alert threshold."""
        return self.coverage() < self.threshold

    def snapshot(self) -> dict[str, Any]:
        observed = self._total(self._observed)
        actual = self._total(self._actual)
        return {
            "observed": observed,
            "actual": actual,
            "coverage": self.coverage() if actual else 1.0,
            "blind_spot": self.blind_spot(),
            "window_seconds": self.window_seconds,
        }


@dataclass
class IncidentRecord:
    """A recorded incident with silence duration and discovery provenance."""

    incident_id: str
    started_at: float
    detected_at: float
    discovered_by: str = _DEFAULT_ORIGIN
    severity: str = _DEFAULT_ORIGIN
    description: str = ""

    @property
    def silent_duration(self) -> float:
        """How long the incident stayed silent (detected - started, floored at 0)."""
        return max(0.0, self.detected_at - self.started_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "started_at": self.started_at,
            "detected_at": self.detected_at,
            "silent_duration": self.silent_duration,
            "discovered_by": self.discovered_by,
            "severity": self.severity,
            "description": self.description,
        }


@dataclass
class IncidentLedger:
    """Accumulates incident records and reports silence statistics."""

    _records: list[IncidentRecord] = field(default_factory=list)

    def record(self, incident: IncidentRecord) -> None:
        """Append an incident record."""
        self._records.append(incident)

    def all(self) -> list[IncidentRecord]:
        """Recorded incidents (copy)."""
        return list(self._records)

    @property
    def count(self) -> int:
        """Number of incidents."""
        return len(self._records)

    def summary(self) -> dict[str, Any]:
        """Aggregate silence duration and discovery-source breakdown."""
        if not self._records:
            return {
                "count": 0,
                "total_silent": 0.0,
                "mean_silent": 0.0,
                "max_silent": 0.0,
                "by_discoverer": {},
            }
        durations = [record.silent_duration for record in self._records]
        by_discoverer: dict[str, int] = {}
        for record in self._records:
            by_discoverer[record.discovered_by] = by_discoverer.get(record.discovered_by, 0) + 1
        total = sum(durations)
        return {
            "count": len(self._records),
            "total_silent": total,
            "mean_silent": total / len(self._records),
            "max_silent": max(durations),
            "by_discoverer": by_discoverer,
        }
