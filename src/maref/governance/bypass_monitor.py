"""BypassMonitor: consumes governance bypass events and triggers alerts.

Listens for bypass audit events from CLI flags, MCP fail_mode, and ReliabilityMatrix.
Maintains a rolling counter and exposes alert thresholds.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from typing import Any


class BypassMonitor:
    """Tracks governance bypass events within a rolling time window.

    Records bypass events from sources like CLI --live/--no-dry-run/--execute-proposals,
    MCP fail_mode, and ReliabilityMatrix. Fires callbacks when the count
    within *window_seconds* exceeds *threshold*.
    """

    def __init__(self, threshold: int = 3, window_seconds: float = 3600.0) -> None:
        self._threshold = threshold
        self._window = window_seconds
        self._events: deque[tuple[float, str, str, dict]] = deque()
        self._callbacks: list[Callable[[dict], None]] = []
        self._alert_count = 0

    def record_bypass(
        self, source: str, reason: str, metadata: dict | None = None
    ) -> dict:
        """Record a bypass event and return alert status.

        Returns ``{"alert": True, "count": N}`` if the number of bypasses
        in the rolling window exceeds *threshold*, else ``{"alert": False, "count": N}``.
        """
        now = time.time()
        self._events.append((now, source, reason, metadata or {}))
        self._prune(now)
        count = len(self._events)
        alert = count > self._threshold
        result: dict[str, Any] = {"alert": alert, "count": count}
        if alert:
            self._alert_count += 1
            self._fire_callbacks(result)
        return result

    def get_stats(self) -> dict:
        """Return bypass statistics."""
        now = time.time()
        self._prune(now)
        recent = len(self._events)
        return {
            "total_recorded": len(self._events) + self._alert_count,
            "recent": recent,
            "alert_count": self._alert_count,
            "threshold": self._threshold,
            "window_seconds": self._window,
        }

    def add_alert_callback(self, callback: Callable[[dict], None]) -> None:
        """Register a callback invoked when an alert triggers."""
        self._callbacks.append(callback)

    def _prune(self, now: float) -> None:
        cut = now - self._window
        while self._events and self._events[0][0] < cut:
            self._events.popleft()

    def _fire_callbacks(self, result: dict) -> None:
        for cb in self._callbacks:
            cb(result)
