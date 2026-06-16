"""
Safety Dashboard — 安全仪表板

实时信任分数展示 + 威胁检测面板 + 合规状态可视化。
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class DashboardWidget(ABC):
    widget_id: str
    title: str
    widget_type: str

    @abstractmethod
    def snapshot(self) -> dict[str, Any]: ...


class TrustScoreWidget(DashboardWidget):
    def __init__(self) -> None:
        super().__init__(
            widget_id="trust-score", title="Agent Trust Scores", widget_type="trust_score"
        )
        self._scores: dict[str, float] = {}

    def update_trust(self, agent_id: str, score: float) -> None:
        self._scores[agent_id] = score

    def snapshot(self) -> dict[str, Any]:
        if not self._scores:
            return {"widget_type": "trust_score", "agents": [], "avg_trust": 0.0}
        agents = [{"agent_id": aid, "trust_score": s} for aid, s in self._scores.items()]
        avg = sum(self._scores.values()) / len(self._scores)
        highest = max(agents, key=lambda a: float(a.get("trust_score", 0.0)))  # type: ignore[arg-type]
        lowest = min(agents, key=lambda a: float(a.get("trust_score", 0.0)))  # type: ignore[arg-type]
        return {
            "widget_type": "trust_score",
            "agents": agents,
            "avg_trust": round(avg, 1),
            "highest": highest,
            "lowest": lowest,
        }


class ThreatDetectionWidget(DashboardWidget):
    def __init__(self) -> None:
        super().__init__(
            widget_id="threat-detection", title="Threat Detection", widget_type="threat_detection"
        )
        self._threats: dict[str, dict[str, Any]] = {}

    def report_threat(
        self, threat_id: str, severity: str, description: str, source: str = ""
    ) -> None:
        self._threats[threat_id] = {
            "threat_id": threat_id,
            "severity": severity,
            "description": description,
            "source": source,
            "timestamp": time.time(),
            "active": True,
        }

    def resolve_threat(self, threat_id: str) -> None:
        if threat_id in self._threats:
            self._threats[threat_id]["active"] = False
            self._threats[threat_id]["resolved_at"] = time.time()

    def snapshot(self) -> dict[str, Any]:
        active = [t for t in self._threats.values() if t["active"]]
        return {
            "widget_type": "threat_detection",
            "total_threats": len(active),
            "critical_count": sum(1 for t in active if t["severity"] == "critical"),
            "high_count": sum(1 for t in active if t["severity"] == "high"),
            "medium_count": sum(1 for t in active if t["severity"] == "medium"),
            "low_count": sum(1 for t in active if t["severity"] == "low"),
            "threats": active,
        }

    def get_timeline(
        self, start_time: float = 0.0, end_time: float | None = None
    ) -> list[dict[str, Any]]:
        end = end_time or time.time()
        return sorted(
            [t for t in self._threats.values() if start_time <= t["timestamp"] <= end],
            key=lambda t: t["timestamp"],
        )


class ComplianceStatusWidget(DashboardWidget):
    def __init__(self) -> None:
        super().__init__(
            widget_id="compliance-status",
            title="Compliance Status",
            widget_type="compliance_status",
        )
        self._frameworks: dict[str, str] = {}

    def update_status(self, framework: str, status: str) -> None:
        self._frameworks[framework] = status

    def snapshot(self) -> dict[str, Any]:
        order = {"compliant": 0, "partial": 1, "non_compliant": 2, "unknown": 3}
        statuses = list(self._frameworks.values())
        worst = max(statuses, key=lambda s: order.get(s, 99)) if statuses else "unknown"
        return {
            "widget_type": "compliance_status",
            "frameworks": self._frameworks,
            "overall": worst,
        }


class SafetyDashboard:
    def __init__(self, title: str = "MAREF Safety Dashboard") -> None:
        self.title = title
        self.widgets: list[DashboardWidget] = []

    def add_widget(self, widget: DashboardWidget) -> None:
        self.widgets.append(widget)

    def snapshot(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "timestamp": time.time(),
            "widgets": {w.widget_type: w.snapshot() for w in self.widgets},
        }
