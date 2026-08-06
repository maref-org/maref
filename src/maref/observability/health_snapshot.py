"""Health snapshot writer for M0 survivability assertion.

Periodically writes a JSON health snapshot to .governance/health_snapshot.json.
The meta-monitor checks freshness (mtime <= 120s) to assert the system is alive.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class HealthSnapshotWriter:
    """Writes system health snapshots for M0 survivability checks.

    The snapshot file is read by meta-monitor to verify the audit system
    itself is alive. If the snapshot is stale (>120s), M0 fails.
    """

    def __init__(
        self,
        snapshot_path: Path | str | None = None,
        interval_seconds: float = 60.0,
    ) -> None:
        if snapshot_path is None:
            base = Path(os.environ.get("MAREF_AUDIT_PATH", ".governance"))
            self._path = base / "health_snapshot.json"
        else:
            self._path = Path(snapshot_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._interval = interval_seconds
        self._consecutive_errors = 0
        self._agent_crashes = 0
        self._start_time = time.time()
        self._cycle = 0

    def write_snapshot(
        self,
        status: str = "healthy",
        active_agents: int = 0,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Write a health snapshot to disk."""
        self._cycle += 1
        snapshot: dict[str, Any] = {
            "status": status,
            "timestamp": time.time(),
            "cycle": self._cycle,
            "consecutive_errors": self._consecutive_errors,
            "agent_crashes": self._agent_crashes,
            "active_agents": active_agents,
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "pid": os.getpid(),
        }
        if extra:
            snapshot["extra"] = extra
        tmp_path = self._path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(snapshot, f)
        os.replace(tmp_path, self._path)

    def record_error(self) -> None:
        """Record a consecutive error."""
        self._consecutive_errors += 1

    def record_agent_crash(self) -> None:
        """Record an agent crash."""
        self._agent_crashes += 1

    def reset_errors(self) -> None:
        """Reset error counters after successful operation."""
        self._consecutive_errors = 0

    def read_snapshot(self) -> dict[str, Any] | None:
        """Read the current health snapshot."""
        if not self._path.exists():
            return None
        try:
            with open(self._path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def is_fresh(self, max_age_seconds: float = 120.0) -> bool:
        """Check if the snapshot is fresh enough for M0 assertion."""
        if not self._path.exists():
            return False
        age = time.time() - self._path.stat().st_mtime
        return age <= max_age_seconds

    @property
    def path(self) -> Path:
        return self._path

    @property
    def interval(self) -> float:
        return self._interval
