"""Agent health and load tracking for real-time dispatch decisions.

Provides AgentHealthMonitor which tracks per-agent load metrics and
exposes them to the dispatcher so that `current_load` and `trust_score`
are no longer hard-coded constants.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AgentLoadSnapshot:
    """Point-in-time load metrics for a single agent."""

    agent_id: str
    current_tasks: int = 0
    max_tasks: int = 10
    queue_depth: int = 0
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @property
    def load_ratio(self) -> float:
        """Normalized load in [0, 1]."""
        if self.max_tasks <= 0:
            return 1.0
        return min(1.0, self.current_tasks / self.max_tasks)

    @property
    def is_overloaded(self) -> bool:
        return self.load_ratio >= 0.9 or self.queue_depth >= self.max_tasks

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "current_tasks": self.current_tasks,
            "max_tasks": self.max_tasks,
            "queue_depth": self.queue_depth,
            "cpu_percent": round(self.cpu_percent, 2),
            "memory_percent": round(self.memory_percent, 2),
            "load_ratio": round(self.load_ratio, 3),
            "is_overloaded": self.is_overloaded,
            "timestamp": self.timestamp,
        }


class AgentHealthMonitor:
    """Maintains a live view of agent load and health.

    In a production deployment this would be backed by a metrics collector
    (Prometheus, StatsD, etc.).  The fallback values keep the system running
    when no external telemetry is available.
    """

    def __init__(self) -> None:
        self._snapshots: dict[str, AgentLoadSnapshot] = {}
        self._default_max_tasks = 10

    # ------------------------------------------------------------------ #
    # Registration / update
    # ------------------------------------------------------------------ #
    def register(self, agent_id: str, max_tasks: int = 10) -> None:
        self._snapshots[agent_id] = AgentLoadSnapshot(
            agent_id=agent_id,
            max_tasks=max_tasks,
        )

    def update(
        self,
        agent_id: str,
        current_tasks: int | None = None,
        queue_depth: int | None = None,
        cpu_percent: float | None = None,
        memory_percent: float | None = None,
    ) -> None:
        snap = self._snapshots.get(agent_id)
        if snap is None:
            snap = AgentLoadSnapshot(agent_id=agent_id)
            self._snapshots[agent_id] = snap

        if current_tasks is not None:
            snap.current_tasks = current_tasks
        if queue_depth is not None:
            snap.queue_depth = queue_depth
        if cpu_percent is not None:
            snap.cpu_percent = cpu_percent
        if memory_percent is not None:
            snap.memory_percent = memory_percent
        snap.timestamp = time.time()

    def increment_tasks(self, agent_id: str) -> None:
        snap = self._snapshots.get(agent_id)
        if snap is None:
            self.register(agent_id)
            snap = self._snapshots[agent_id]
        snap.current_tasks += 1
        snap.timestamp = time.time()

    def decrement_tasks(self, agent_id: str) -> None:
        snap = self._snapshots.get(agent_id)
        if snap is not None:
            snap.current_tasks = max(0, snap.current_tasks - 1)
            snap.timestamp = time.time()

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #
    def get_snapshot(self, agent_id: str) -> AgentLoadSnapshot | None:
        return self._snapshots.get(agent_id)

    def get_load_ratio(self, agent_id: str) -> float:
        snap = self._snapshots.get(agent_id)
        if snap is None:
            return 0.5  # neutral when unknown
        return snap.load_ratio

    def list_overloaded(self) -> list[str]:
        return [sid for sid, snap in self._snapshots.items() if snap.is_overloaded]

    def summary(self) -> dict[str, Any]:
        return {
            "agent_count": len(self._snapshots),
            "overloaded": self.list_overloaded(),
            "agents": {sid: snap.to_dict() for sid, snap in self._snapshots.items()},
        }


class PulseWriter:
    """Writes agent heartbeat pulse files for M0 survivability checks.

    Each agent writes a pulse.json to .governance/pulses/<agent_id>.json.
    The meta-monitor checks freshness: if mtime > interval * 3, the agent
    is considered dead.
    """

    def __init__(
        self,
        agent_id: str,
        pulses_dir: Path | str | None = None,
        interval_seconds: float = 30.0,
    ) -> None:
        self._agent_id = agent_id
        if pulses_dir is None:
            base = Path(os.environ.get("MAREF_AUDIT_PATH", ".governance"))
            self._dir = base / "pulses"
        else:
            self._dir = Path(pulses_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / f"{agent_id}.json"
        self._interval = interval_seconds
        self._cycle = 0
        self._epoch = int(time.time())

    def write_pulse(self, status: str = "alive") -> dict[str, Any]:
        """Write a heartbeat pulse file. Returns the pulse data."""
        self._cycle += 1
        pulse: dict[str, Any] = {
            "agent": self._agent_id,
            "status": status,
            "cycle": self._cycle,
            "pid": os.getpid(),
            "timestamp": time.time(),
            "epoch": self._epoch,
            "interval": self._interval,
        }
        tmp_path = self._path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(pulse, f)
        os.replace(tmp_path, self._path)
        return pulse

    def is_alive(self, max_age_seconds: float | None = None) -> bool:
        """Check if this agent's pulse is fresh."""
        if max_age_seconds is None:
            max_age_seconds = self._interval * 3
        if not self._path.exists():
            return False
        age = time.time() - self._path.stat().st_mtime
        return age <= max_age_seconds

    @property
    def path(self) -> Path:
        return self._path

    @staticmethod
    def check_pulse_staleness(
        pulses_dir: Path | str | None = None,
        max_stale_ratio: float = 0.30,
    ) -> dict[str, Any]:
        """Check all pulse files for staleness (M0.3 check)."""
        if pulses_dir is None:
            base = Path(os.environ.get("MAREF_AUDIT_PATH", ".governance"))
            pulses_dir = base / "pulses"
        else:
            pulses_dir = Path(pulses_dir)

        if not pulses_dir.exists() or not any(pulses_dir.glob("*.json")):
            return {"total": 0, "stale": 0, "stale_ratio": 0.0, "status": "no_pulses"}

        now = time.time()
        total = 0
        stale = 0
        stale_agents: list[str] = []

        for pulse_file in pulses_dir.glob("*.json"):
            total += 1
            try:
                with open(pulse_file) as f:
                    data = json.load(f)
                interval = data.get("interval", 30.0)
                age = now - data.get("timestamp", 0)
                if age > interval * 3:
                    stale += 1
                    stale_agents.append(data.get("agent", pulse_file.stem))
            except (json.JSONDecodeError, OSError):
                stale += 1
                stale_agents.append(pulse_file.stem)

        stale_ratio = stale / total if total > 0 else 0.0
        return {
            "total": total,
            "stale": stale,
            "stale_ratio": round(stale_ratio, 3),
            "stale_agents": stale_agents,
            "status": "healthy" if stale_ratio <= max_stale_ratio else "degraded",
        }
