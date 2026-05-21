"""MAREF RED Metrics Collector.

Collects Rate, Errors, and Duration metrics for all API requests.
Provides P50, P95, P99 latency calculations.
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RequestMetric:
    """Single request metric record."""
    path: str
    method: str
    status_code: int
    duration_ms: float
    timestamp: float = field(default_factory=time.time)
    is_error: bool = False

    def __post_init__(self) -> None:
        self.is_error = self.status_code >= 400


class REDMetricsCollector:
    """Collects and aggregates RED (Rate, Errors, Duration) metrics.

    Thread-safe collector that tracks:
    - Rate: requests per second (QPS)
    - Errors: error rate by status code category
    - Duration: P50, P95, P99 latency percentiles
    """

    MAX_SAMPLES = 10000

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._metrics: list[RequestMetric] = []
        self._path_metrics: dict[str, list[float]] = defaultdict(list)
        self._error_counts: dict[str, int] = defaultdict(int)
        self._request_counts: dict[str, int] = defaultdict(int)
        self._total_requests: int = 0
        self._total_errors: int = 0
        self._start_time: float = time.time()

    def record_request(
        self,
        path: str,
        method: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        """Record a completed HTTP request."""
        metric = RequestMetric(
            path=path,
            method=method,
            status_code=status_code,
            duration_ms=duration_ms,
        )

        with self._lock:
            self._metrics.append(metric)
            if len(self._metrics) > self.MAX_SAMPLES:
                self._metrics = self._metrics[-self.MAX_SAMPLES:]

            self._path_metrics[path].append(duration_ms)
            if len(self._path_metrics[path]) > self.MAX_SAMPLES:
                self._path_metrics[path] = self._path_metrics[path][-self.MAX_SAMPLES:]

            self._request_counts[path] += 1
            self._total_requests += 1

            if metric.is_error:
                self._total_errors += 1
                error_category = self._categorize_error(status_code)
                self._error_counts[error_category] += 1

    def get_rate(self, window_seconds: int = 60) -> float:
        """Get requests per second (QPS) for the given time window."""
        cutoff = time.time() - window_seconds
        with self._lock:
            recent = [m for m in self._metrics if m.timestamp >= cutoff]
        return len(recent) / window_seconds if window_seconds > 0 else 0.0

    def get_error_rate(self, window_seconds: int = 60) -> float:
        """Get error rate (0.0 - 1.0) for the given time window."""
        cutoff = time.time() - window_seconds
        with self._lock:
            recent = [m for m in self._metrics if m.timestamp >= cutoff]
        if not recent:
            return 0.0
        errors = sum(1 for m in recent if m.is_error)
        return errors / len(recent)

    def get_duration_percentiles(self, path: str | None = None) -> dict[str, float]:
        """Get P50, P95, P99 latency percentiles."""
        with self._lock:
            if path:
                durations = list(self._path_metrics.get(path, []))
            else:
                durations = [m.duration_ms for m in self._metrics]

        if not durations:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "avg": 0.0, "min": 0.0, "max": 0.0}

        durations.sort()
        return {
            "p50": self._percentile(durations, 50),
            "p95": self._percentile(durations, 95),
            "p99": self._percentile(durations, 99),
            "avg": sum(durations) / len(durations),
            "min": durations[0],
            "max": durations[-1],
        }

    def get_red_summary(self, window_seconds: int = 60) -> dict[str, Any]:
        """Get complete RED metrics summary."""
        return {
            "rate": {
                "qps": round(self.get_rate(window_seconds), 2),
                "total_requests": self._total_requests,
                "window_seconds": window_seconds,
            },
            "errors": {
                "rate": round(self.get_error_rate(window_seconds), 4),
                "total_errors": self._total_errors,
                "by_category": dict(self._error_counts),
            },
            "duration": {
                **self.get_duration_percentiles(),
                "unit": "ms",
            },
            "uptime_seconds": round(time.time() - self._start_time, 1),
        }

    def get_path_metrics(self) -> dict[str, dict[str, Any]]:
        """Get RED metrics broken down by API path."""
        with self._lock:
            paths = list(self._path_metrics.keys())

        result = {}
        for path in paths:
            durations = self._path_metrics.get(path, [])
            if not durations:
                continue

            path_requests = self._request_counts.get(path, 0)
            path_errors = sum(
                1 for m in self._metrics
                if m.path == path and m.is_error
            )

            result[path] = {
                "request_count": path_requests,
                "error_count": path_errors,
                "error_rate": round(path_errors / path_requests, 4) if path_requests > 0 else 0.0,
                "duration": self.get_duration_percentiles(path),
            }

        return result

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._metrics.clear()
            self._path_metrics.clear()
            self._error_counts.clear()
            self._request_counts.clear()
            self._total_requests = 0
            self._total_errors = 0
            self._start_time = time.time()

    @staticmethod
    def _percentile(sorted_data: list[float], percentile: float) -> float:
        """Calculate percentile from sorted data."""
        if not sorted_data:
            return 0.0
        k = (len(sorted_data) - 1) * (percentile / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_data[int(k)]
        d0 = sorted_data[int(f)] * (c - k)
        d1 = sorted_data[int(c)] * (k - f)
        return round(d0 + d1, 2)

    @staticmethod
    def _categorize_error(status_code: int) -> str:
        """Categorize HTTP error by status code range."""
        if 400 <= status_code < 500:
            return "4xx_client_error"
        if status_code >= 500:
            return "5xx_server_error"
        return "other"
