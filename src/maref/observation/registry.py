"""MAREF Probe Registry — plugin-style probe management."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

from maref.observation.probes import Probe, ProbeReading


class ProbeRegistry:
    """Registry for observation probes with plugin-style registration."""

    def __init__(self) -> None:
        self._probes: dict[str, Probe] = {}
        self._readings: list[ProbeReading] = []
        self._callbacks: list[Callable[[ProbeReading], None]] = []

    def register(self, probe: Probe) -> None:
        """Register a probe. Replaces any existing probe with the same name."""
        self._probes[probe.name] = probe

    def unregister(self, name: str) -> bool:
        """Remove a probe by name. Returns True if it existed."""
        return self._probes.pop(name, None) is not None

    def get(self, name: str) -> Probe | None:
        """Get a registered probe by name."""
        return self._probes.get(name)

    def list_probes(self) -> list[str]:
        """List all registered probe names."""
        return list(self._probes.keys())

    def add_callback(self, callback: Callable[[ProbeReading], None]) -> None:
        """Register a callback invoked on every reading."""
        self._callbacks.append(callback)

    def read_all(self, **context: Any) -> list[ProbeReading]:
        """Read all registered probes with shared context."""
        all_readings: list[ProbeReading] = []
        for probe in self._probes.values():
            readings = probe.read(**context)
            all_readings.extend(readings)
            self._readings.extend(readings)
            for r in readings:
                for cb in self._callbacks:
                    with contextlib.suppress(Exception):
                        cb(r)
        return all_readings

    def get_recent(self, n: int = 100) -> list[ProbeReading]:
        """Get n most recent readings across all probes."""
        return self._readings[-n:]

    def get_reading_count(self) -> int:
        """Total number of readings collected."""
        return len(self._readings)

    def get_counts_by_probe(self) -> dict[str, int]:
        """Get reading count per probe."""
        return {name: probe.reading_count for name, probe in self._probes.items()}

    def get_counts_by_severity(self) -> dict[str, int]:
        """Get reading counts grouped by severity."""
        counts: dict[str, int] = {"normal": 0, "warning": 0, "critical": 0}
        for r in self._readings:
            counts[r.severity.value] = counts.get(r.severity.value, 0) + 1
        return counts
