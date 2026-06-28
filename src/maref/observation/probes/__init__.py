"""
MAREF Observation Probes

Multi-dimensional probe system that replaces the single-event
self-observation pattern. Each probe monitors a specific aspect
of the governance system and fires independently.

Probe types:
- entropy_probe: State machine entropy level monitoring
- anomaly_probe: Anomaly event count and severity tracking
- latency_probe: Decision latency measurement
- kg_probe: Knowledge graph health (node count, relation density)
- oscillation_probe: State oscillation frequency detection
- playwright_probe: Playwright installation status
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProbeSeverity(Enum):
    """Severity level for probe readings."""

    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class ProbeReading:
    """A single reading from a probe."""

    probe_name: str
    severity: ProbeSeverity
    value: float
    threshold: float
    timestamp: float = field(default_factory=time.time)
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "probe_name": self.probe_name,
            "severity": self.severity.value,
            "value": self.value,
            "threshold": self.threshold,
            "timestamp": self.timestamp,
            "context": self.context,
        }


class Probe(ABC):
    """Base class for all observation probes."""

    def __init__(
        self, name: str, primary_threshold: float, shadow_threshold: float | None = None
    ) -> None:
        self.name = name
        self.primary_threshold = primary_threshold
        self.shadow_threshold = shadow_threshold
        self._readings: list[ProbeReading] = []

    @abstractmethod
    def read(self, **context: Any) -> list[ProbeReading]:
        """Take a reading and return any triggered alerts."""

    def get_readings(self, n: int = 100) -> list[ProbeReading]:
        return self._readings[-n:]

    @property
    def reading_count(self) -> int:
        return len(self._readings)

    def _evaluate(
        self,
        value: float,
        context: dict[str, Any],
    ) -> list[ProbeReading]:
        readings: list[ProbeReading] = []

        if value >= self.primary_threshold:
            readings.append(
                ProbeReading(
                    probe_name=self.name,
                    severity=ProbeSeverity.CRITICAL,
                    value=value,
                    threshold=self.primary_threshold,
                    context=context,
                )
            )
        elif self.shadow_threshold is not None and value >= self.shadow_threshold:
            readings.append(
                ProbeReading(
                    probe_name=self.name,
                    severity=ProbeSeverity.WARNING,
                    value=value,
                    threshold=self.shadow_threshold,
                    context=context,
                )
            )

        self._readings.extend(readings)
        return readings


class EntropyProbe(Probe):
    """Monitors state machine entropy level.

    Primary threshold at 4 (ACT = max entropy) for critical.
    Shadow threshold at 2 for early warning.
    """

    def __init__(
        self,
        primary_threshold: float = 4.0,
        shadow_threshold: float = 2.0,
    ) -> None:
        super().__init__("entropy", primary_threshold, shadow_threshold)

    def read(self, **context: Any) -> list[ProbeReading]:
        entropy = context.get("entropy", 0)
        return self._evaluate(float(entropy), {"entropy": entropy, **context})


class AnomalyProbe(Probe):
    """Monitors anomaly event counts."""

    def __init__(
        self,
        primary_threshold: float = 10.0,
        shadow_threshold: float = 3.0,
    ) -> None:
        super().__init__("anomaly", primary_threshold, shadow_threshold)

    def read(self, **context: Any) -> list[ProbeReading]:
        count = float(context.get("anomaly_count", 0))
        return self._evaluate(count, {"anomaly_count": count})


class LatencyProbe(Probe):
    """Monitors decision-making latency."""

    def __init__(
        self,
        primary_threshold: float = 5.0,
        shadow_threshold: float = 1.0,
    ) -> None:
        super().__init__("latency", primary_threshold, shadow_threshold)

    def read(self, **context: Any) -> list[ProbeReading]:
        latency = float(context.get("latency_ms", 0))
        return self._evaluate(
            latency,
            {"latency_ms": latency, "decision_type": context.get("decision_type", "")},
        )


class KGProbe(Probe):
    """Monitors knowledge graph health."""

    def __init__(
        self,
        primary_threshold: float = 0.95,
    ) -> None:
        super().__init__("knowledge_graph", primary_threshold, shadow_threshold=0.5)

    def read(self, **context: Any) -> list[ProbeReading]:
        total_nodes = float(context.get("total_nodes", 0))
        orphaned = float(context.get("orphaned_nodes", 0))
        if total_nodes > 0:
            orphan_ratio = orphaned / total_nodes
        else:
            orphan_ratio = 0.0 if total_nodes == 0 else 1.0

        return self._evaluate(
            orphan_ratio,
            {
                "total_nodes": int(total_nodes),
                "orphaned_nodes": int(orphaned),
                "orphan_ratio": orphan_ratio,
            },
        )


class OscillationProbe(Probe):
    """Monitors state oscillation frequency."""

    def __init__(
        self,
        primary_threshold: float = 10.0,
        shadow_threshold: float = 4.0,
        window_seconds: float = 60.0,
    ) -> None:
        super().__init__("oscillation", primary_threshold, shadow_threshold)
        self._window = window_seconds
        self._change_times: list[float] = []

    def record_change(self) -> None:
        self._change_times.append(time.time())
        self._prune()

    def _prune(self) -> None:
        cutoff = time.time() - self._window
        self._change_times = [t for t in self._change_times if t > cutoff]

    def read(self, **context: Any) -> list[ProbeReading]:
        self._prune()
        rate = float(len(self._change_times))
        return self._evaluate(
            rate,
            {"change_rate": rate, "window_seconds": self._window},
        )


class BaseProbe(ABC):
    """Simplified base class for observation probes.

    Provides a measure() interface that returns a single ProbeReading,
    suitable for lightweight / stateless probes.
    """

    def __init__(
        self,
        name: str,
        description: str,
        critical_threshold: float,
        warning_threshold: float,
    ) -> None:
        self.name = name
        self.description = description
        self.critical_threshold = critical_threshold
        self.warning_threshold = warning_threshold
        self._readings: list[ProbeReading] = []

    @abstractmethod
    def measure(self, context: dict[str, Any] | None = None) -> ProbeReading:
        """Take a single measurement and return the reading."""

    def get_readings(self, n: int = 100) -> list[ProbeReading]:
        return self._readings[-n:]

    @property
    def reading_count(self) -> int:
        return len(self._readings)


from maref.observation.probes.desktop_probe import (  # noqa: E402
    DesktopProbe as DesktopProbe,
)
from maref.observation.probes.gui_build_probe import (  # noqa: E402
    GUIBuildProbe as GUIBuildProbe,
)
from maref.observation.probes.playwright_probe import (  # noqa: E402
    PlaywrightProbe as PlaywrightProbe,
)

__all__ = [
    "AnomalyProbe",
    "BaseProbe",
    "DesktopProbe",
    "EntropyProbe",
    "GUIBuildProbe",
    "KGProbe",
    "LatencyProbe",
    "OscillationProbe",
    "PlaywrightProbe",
    "Probe",
    "ProbeReading",
    "ProbeSeverity",
]
