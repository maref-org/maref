"""Real wall-clock latency measurement for stress tests."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LatencySample:
    operation: str
    duration_ns: int
    timestamp: float = field(default_factory=time.time)

    @property
    def duration_ms(self) -> float:
        return self.duration_ns / 1_000_000


@dataclass
class LatencyReport:
    operation: str
    count: int
    p50_ms: float = 0.0
    p99_ms: float = 0.0
    p99_9_ms: float = 0.0
    mean_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    throughput_ops_sec: float = 0.0
    total_elapsed_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation, "count": self.count,
            "p50_ms": self.p50_ms, "p99_ms": self.p99_ms, "p99_9_ms": self.p99_9_ms,
            "mean_ms": self.mean_ms, "min_ms": self.min_ms, "max_ms": self.max_ms,
            "throughput_ops_sec": self.throughput_ops_sec,
        }


class RealLatencyTracker:
    """Track real wall-clock latencies with perf_counter_ns precision."""

    def __init__(self) -> None:
        self._samples: dict[str, list[int]] = {}
        self._start_time = time.time()

    def measure(self, operation: str) -> LatencyContext:
        return LatencyContext(self, operation)

    def record(self, operation: str, duration_ns: int) -> None:
        if operation not in self._samples:
            self._samples[operation] = []
        self._samples[operation].append(duration_ns)

    def report(self, operation: str) -> LatencyReport | None:
        samples = self._samples.get(operation)
        if not samples:
            return None
        elapsed = time.time() - self._start_time
        sorted_samples = sorted(samples)
        n = len(sorted_samples)
        return LatencyReport(
            operation=operation, count=n,
            p50_ms=round(sorted_samples[int(n * 0.50)] / 1_000_000, 3),
            p99_ms=round(sorted_samples[int(n * 0.99)] / 1_000_000, 3) if n > 1 else 0,
            p99_9_ms=round(sorted_samples[int(n * 0.999)] / 1_000_000, 3) if n > 2 else 0,
            mean_ms=round(sum(sorted_samples) / n / 1_000_000, 3),
            min_ms=round(sorted_samples[0] / 1_000_000, 3),
            max_ms=round(sorted_samples[-1] / 1_000_000, 3),
            throughput_ops_sec=round(n / max(elapsed, 0.001), 1),
            total_elapsed_s=round(elapsed, 2),
        )

    def all_reports(self) -> dict[str, LatencyReport]:
        return {op: self.report(op) for op in self._samples if self.report(op)}


class LatencyContext:
    def __init__(self, tracker: RealLatencyTracker, operation: str) -> None:
        self._tracker = tracker
        self._operation = operation

    def __enter__(self) -> LatencyContext:
        self._start_ns = time.perf_counter_ns()
        return self

    def __exit__(self, *args: Any) -> None:
        duration_ns = time.perf_counter_ns() - self._start_ns
        self._tracker.record(self._operation, duration_ns)
