from __future__ import annotations

import logging
from typing import Any

from maref.observation.probes import BaseProbe, ProbeReading, ProbeSeverity

logger = logging.getLogger(__name__)


class DesktopProbe(BaseProbe):
    """检测桌面代理 + 浏览器引擎运行时健康。

    Metrics:
    - pool_available: bool
    - active_sessions: int (ref_count > 0 and not expired)
    - total_sessions: int
    - value: 1.0=active sessions exist, 0.5=pool ok but idle, 0.0=unavailable
    """

    def __init__(self, critical_threshold: float = 0.3, warning_threshold: float = 0.6) -> None:
        super().__init__(
            name="desktop",
            description="桌面代理与浏览器引擎运行时健康",
            critical_threshold=critical_threshold,
            warning_threshold=warning_threshold,
        )

    def measure(self, context: dict[str, Any] | None = None) -> ProbeReading:
        from maref.desktop.browser_session_pool import BrowserSessionPool

        pool = BrowserSessionPool()
        if not pool.is_available:
            severity = ProbeSeverity.CRITICAL
            reading = ProbeReading(
                probe_name=self.name,
                severity=severity,
                value=0.0,
                threshold=self.critical_threshold,
                context={
                    "pool_available": False,
                    "active_sessions": 0,
                    "session_pool_size": 0,
                    "error": "playwright_not_available",
                },
            )
            self._readings.append(reading)
            return reading

        sessions = pool.get_all_sessions()
        active = sum(1 for s in sessions.values() if s.ref_count > 0 and not s.is_expired)
        total = len(sessions)
        expired = sum(1 for s in sessions.values() if s.is_expired)
        health = 1.0 if active > 0 else 0.5
        severity = ProbeSeverity.CRITICAL if health < self.critical_threshold else ProbeSeverity.NORMAL
        reading = ProbeReading(
            probe_name=self.name,
            severity=severity,
            value=health,
            threshold=self.critical_threshold,
            context={
                "pool_available": True,
                "active_sessions": active,
                "session_pool_size": total,
                "expired_sessions": expired,
            },
        )
        self._readings.append(reading)
        return reading
