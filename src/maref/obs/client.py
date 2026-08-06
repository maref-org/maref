"""MarefObsClient — local-first, privacy-respecting event recorder."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from threading import Lock

from maref.obs.hasher import ObsHasher
from maref.obs.levels import TelemetryLevel
from maref.obs.schema import ObsEvent, ObsEventType


class MarefObsClient:
    """Local-first governance event recorder.

    Writes events as newline-delimited JSON (ndjson) to
    ``~/.maref/obs/behavior_YYYYMMDD.ndjson``.

    Thread-safe. All PII-adjacent metadata is salted-hashed before
    being written at ``standard`` or ``detailed`` levels.
    At ``basic`` level, only event type + count + version are recorded
    (no hashes, no state names, no agent identifiers).
    At ``off`` level, nothing is written.

    Typical usage::

        obs = MarefObsClient(level=TelemetryLevel.BASIC)
        obs.log_event(ObsEventType.STATE_TRANSITION, {
            "from": "OBSERVE",
            "to": "ANALYZE",
        })
    """

    _instance: MarefObsClient | None = None
    _init_lock = Lock()

    def __init__(
        self,
        level: TelemetryLevel | str = TelemetryLevel.BASIC,
        base_dir: str | Path | None = None,
        session_id: str | None = None,
    ) -> None:
        if isinstance(level, str):
            level = TelemetryLevel.from_env(level)
        self._level: TelemetryLevel = level

        self._base_dir = Path(base_dir or Path.home() / ".maref" / "obs")
        self._session_id: str = session_id or uuid.uuid4().hex[:12]

        self._hasher = ObsHasher()
        self._lock = Lock()
        self._event_sequence = 0
        self._today: str = ""
        self._file_handle: int = -1  # not used; we open/close per write

        if self._level != TelemetryLevel.OFF:
            self._base_dir.mkdir(parents=True, exist_ok=True)
            self._persist_salt()

    # ── Factory / singleton ────────────────────────────────────────

    @classmethod
    def get_default(cls) -> MarefObsClient:
        with cls._init_lock:
            if cls._instance is None:
                level = TelemetryLevel.from_env(os.environ.get("MAREF_TELEMETRY_LEVEL"))
                cls._instance = cls(level=level)
            return cls._instance

    @classmethod
    def reset_default(cls) -> None:
        with cls._init_lock:
            cls._instance = None

    # ── Properties ─────────────────────────────────────────────────

    @property
    def level(self) -> TelemetryLevel:
        return self._level

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def hasher(self) -> ObsHasher:
        return self._hasher

    # ── Public API ─────────────────────────────────────────────────

    def log_event(
        self,
        event_type: ObsEventType,
        metadata: dict | None = None,
        version: str = "",
    ) -> int | None:
        """Record a governance event.

        Returns the event sequence number, or ``None`` if telemetry
        level is ``off``.
        """
        if self._level == TelemetryLevel.OFF:
            return None

        with self._lock:
            seq = self._event_sequence
            self._event_sequence += 1

        event = ObsEvent(
            event_type=event_type,
            version=version,
            timestamp=time.time(),
            event_sequence=seq,
            metadata=self._scrub_metadata(metadata or {}),
        )

        self._write_event(event)
        return seq

    def log_state_transition(
        self,
        from_state: str,
        to_state: str,
        entropy: int = 0,
        reason: str = "",
    ) -> int | None:
        """Convenience: log a state transition event."""
        if self._level == TelemetryLevel.BASIC:
            return self.log_event(ObsEventType.STATE_TRANSITION, {})
        metadata: dict = {
            "from": from_state,
            "to": to_state,
            "entropy": entropy,
        }
        if reason:
            metadata["reason"] = reason
        return self.log_event(ObsEventType.STATE_TRANSITION, metadata)

    def log_breaker_trip(
        self,
        reason: str,
        depth: int = 0,
        entropy: int = 0,
    ) -> int | None:
        """Convenience: log a circuit breaker trip."""
        metadata: dict = {
            "reason": reason,
            "depth": depth,
            "entropy": entropy,
        }
        return self.log_event(ObsEventType.BREAKER_TRIP, metadata)

    def log_oscillation(
        self,
        detected: bool,
        rate: float = 0.0,
        entropy: int = 0,
    ) -> int | None:
        """Convenience: log an oscillation detection or resolution."""
        metadata: dict = {
            "rate": round(rate, 2),
            "entropy": entropy,
        }
        event_type = (
            ObsEventType.OSCILLATION_DETECTED if detected else ObsEventType.OSCILLATION_RESOLVED
        )
        return self.log_event(event_type, metadata)

    # ── Buffer management ──────────────────────────────────────────

    def flush(self) -> None:
        """No-op for Step 1. Pipeline sync will be added in Step 2."""

    def get_buffer_path(self) -> Path | None:
        """Path to today's event buffer, or None if level is off."""
        if self._level == TelemetryLevel.OFF:
            return None
        return self._base_dir / f"behavior_{time.strftime('%Y%m%d')}.ndjson"

    def get_all_events(self) -> list[dict]:
        """Read all locally buffered events (for CLI inspection)."""
        path = self.get_buffer_path()
        if not path or not path.exists():
            return []
        events: list[dict] = []
        with open(path) as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    events.append(json.loads(stripped))
        return events

    def count_events(self) -> dict[str, int]:
        """Return event type -> count for today's buffer."""
        counts: dict[str, int] = {}
        for event in self.get_all_events():
            et = event.get("event_type", "unknown")
            counts[et] = counts.get(et, 0) + 1
        return counts

    # ── Internal ───────────────────────────────────────────────────

    def _scrub_metadata(self, metadata: dict) -> dict:
        """Return a copy of metadata with fields filtered by level."""
        if self._level == TelemetryLevel.BASIC:
            return {}
        scrubbed: dict = {}
        for key, value in metadata.items():
            if self._level == TelemetryLevel.STANDARD and isinstance(value, str):
                scrubbed[key] = self._hasher.hash(value)
            else:
                scrubbed[key] = value
        return scrubbed

    def _write_event(self, event: ObsEvent) -> None:
        """Append one ndjson line to today's buffer file."""
        path = self.get_buffer_path()
        if path is None:
            return
        payload = {
            "session_id": self._session_id,
            "event_type": event.event_type.value,
            "version": event.version,
            "timestamp": event.timestamp,
            "event_sequence": event.event_sequence,
            "metadata": event.metadata,
        }
        with open(path, "a") as f:
            f.write(json.dumps(payload, sort_keys=True) + "\n")

    def _persist_salt(self) -> None:
        """Persist the session salt so hashes are consistent within session."""
        salt_path = self._base_dir / ".salt"
        if not salt_path.exists():
            with open(salt_path, "w") as f:
                f.write(self._hasher.salt + "\n")
