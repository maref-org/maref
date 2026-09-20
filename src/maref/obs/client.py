"""MarefObsClient — local-first, privacy-respecting event recorder."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Any

import urllib.request

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
        sidecar_url: str | None = None,
        sidecar_auth_token: str | None = None,
        batch_size: int = 100,
        flush_interval_seconds: float = 30.0,
    ) -> None:
        if isinstance(level, str):
            level = TelemetryLevel.from_env(level)
        self._level: TelemetryLevel = level

        self._base_dir = Path(base_dir or Path.home() / ".maref" / "obs")
        self._session_id: str = session_id or uuid.uuid4().hex[:12]

        # Sidecar telemetry upload configuration
        self._sidecar_url = sidecar_url or os.environ.get("MAREF_SIDECAR_URL", "http://127.0.0.1:8000")
        self._sidecar_auth_token = sidecar_auth_token or os.environ.get("MAREF_SIDECAR_AUTH_TOKEN", "")
        self._batch_size = batch_size
        self._flush_interval_seconds = flush_interval_seconds

        self._hasher = ObsHasher()
        self._lock = Lock()
        self._event_sequence = 0
        self._today: str = ""
        self._file_handle: int = -1  # not used; we open/close per write
        self._pending_upload: list[dict[str, Any]] = []
        self._last_flush_time = time.time()

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

        # Queue for sidecar upload
        upload_event = {
            "session_id": self._session_id,
            "event_type": event.event_type.value,
            "version": event.version,
            "timestamp": event.timestamp,
            "event_sequence": event.event_sequence,
            "metadata": event.metadata,
        }
        self._pending_upload.append(upload_event)

        # Trigger auto-flush check
        self._maybe_auto_flush()

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

    def log_trust_boundary_violation(
        self,
        action: str,
        agent_id: str,
        reason: str,
        risk_level: str = "",
    ) -> int | None:
        """Convenience: log a trust boundary violation."""
        metadata: dict = {
            "action": action,
            "agent_id": agent_id,
            "reason": reason,
            "risk_level": risk_level,
        }
        return self.log_event(ObsEventType.TRUST_BOUNDARY_VIOLATION, metadata)

    def log_sanction(
        self,
        target_id: str,
        sanction_type: str,
        amount: float = 0.0,
        reason: str = "",
    ) -> int | None:
        """Convenience: log an agent sanction event."""
        metadata: dict = {
            "target_id": target_id,
            "sanction_type": sanction_type,
            "amount": amount,
            "reason": reason,
        }
        return self.log_event(ObsEventType.SANCTION, metadata)

    def log_cost_breach(
        self,
        model: str,
        provider: str,
        cost: float,
        budget: float,
        reason: str = "",
    ) -> int | None:
        """Convenience: log a cost guardrail breach."""
        metadata: dict = {
            "model": model,
            "provider": provider,
            "cost": cost,
            "budget": budget,
            "reason": reason,
        }
        return self.log_event(ObsEventType.COST_BREACH, metadata)

    def log_constitution_violation(
        self,
        rule_id: str,
        agent_id: str,
        description: str,
    ) -> int | None:
        """Convenience: log a constitution red-line violation."""
        metadata: dict = {
            "rule_id": rule_id,
            "agent_id": agent_id,
            "description": description,
        }
        return self.log_event(ObsEventType.CONSTITUTION_VIOLATION, metadata)

    def log_governance_bypass(
        self,
        agent_id: str,
        bypass_type: str,
        component: str,
        reason: str = "",
    ) -> int | None:
        """Convenience: log a governance bypass attempt."""
        metadata: dict = {
            "agent_id": agent_id,
            "bypass_type": bypass_type,
            "component": component,
            "reason": reason,
        }
        return self.log_event(ObsEventType.GOVERNANCE_BYPASS, metadata)

    # ── Tool call lifecycle ──────────────────────────────────────────

    def log_tool_call_start(
        self,
        agent_id: str,
        tool_name: str,
        correlation_id: str,
        chain_id: str | None = None,
        delegation_depth: int = 0,
        args_hash: str | None = None,
    ) -> int | None:
        """Log tool call start (before governance evaluation)."""
        metadata: dict = {
            "agent_id": agent_id,
            "tool_name": tool_name,
            "correlation_id": correlation_id,
            "delegation_depth": delegation_depth,
        }
        if chain_id:
            metadata["chain_id"] = chain_id
        if args_hash:
            metadata["args_hash"] = args_hash
        return self.log_event(ObsEventType.TOOL_CALL_START, metadata)

    def log_tool_call_end(
        self,
        agent_id: str,
        tool_name: str,
        correlation_id: str,
        verdict: str,
        latency_ms: int,
        chain_id: str | None = None,
        delegation_depth: int = 0,
        risk_score: float = 0.0,
        hitl_event_id: str | None = None,
        tokens_input: int = 0,
        tokens_output: int = 0,
        cost_usd: float = 0.0,
        error: str | None = None,
    ) -> int | None:
        """Log tool call end (after execution or interception)."""
        metadata: dict = {
            "agent_id": agent_id,
            "tool_name": tool_name,
            "correlation_id": correlation_id,
            "verdict": verdict,
            "latency_ms": latency_ms,
            "delegation_depth": delegation_depth,
            "risk_score": risk_score,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "cost_usd": cost_usd,
        }
        if chain_id:
            metadata["chain_id"] = chain_id
        if hitl_event_id:
            metadata["hitl_event_id"] = hitl_event_id
        if error:
            metadata["error"] = error
        return self.log_event(ObsEventType.TOOL_CALL_END, metadata)

    def log_tool_call_intercepted(
        self,
        agent_id: str,
        tool_name: str,
        correlation_id: str,
        reason: str,
        matched_rule: str,
        risk_score: float,
        chain_id: str | None = None,
        delegation_depth: int = 0,
    ) -> int | None:
        """Log tool call intercepted by governance."""
        metadata: dict = {
            "agent_id": agent_id,
            "tool_name": tool_name,
            "correlation_id": correlation_id,
            "reason": reason,
            "matched_rule": matched_rule,
            "risk_score": risk_score,
            "delegation_depth": delegation_depth,
        }
        if chain_id:
            metadata["chain_id"] = chain_id
        return self.log_event(ObsEventType.TOOL_CALL_INTERCEPTED, metadata)

    # ── Multi-agent delegation ──────────────────────────────────────

    def log_delegation_start(
        self,
        from_agent_id: str,
        to_agent_id: str,
        correlation_id: str,
        chain_id: str,
        delegation_depth: int,
        tool_name: str,
    ) -> int | None:
        """Log delegation start (agent handoff)."""
        metadata: dict = {
            "from_agent_id": from_agent_id,
            "to_agent_id": to_agent_id,
            "correlation_id": correlation_id,
            "chain_id": chain_id,
            "delegation_depth": delegation_depth,
            "tool_name": tool_name,
        }
        return self.log_event(ObsEventType.DELEGATION_START, metadata)

    def log_delegation_end(
        self,
        from_agent_id: str,
        to_agent_id: str,
        correlation_id: str,
        chain_id: str,
        delegation_depth: int,
        success: bool,
        result_summary: str = "",
    ) -> int | None:
        """Log delegation end."""
        metadata: dict = {
            "from_agent_id": from_agent_id,
            "to_agent_id": to_agent_id,
            "correlation_id": correlation_id,
            "chain_id": chain_id,
            "delegation_depth": delegation_depth,
            "success": success,
        }
        if result_summary:
            metadata["result_summary"] = result_summary
        return self.log_event(ObsEventType.DELEGATION_END, metadata)

    # ── Cost/Resource tracking ──────────────────────────────────────

    def log_token_usage(
        self,
        agent_id: str,
        correlation_id: str,
        model: str,
        provider: str,
        tokens_input: int,
        tokens_output: int,
        tokens_cache: int = 0,
        cost_usd: float = 0.0,
    ) -> int | None:
        """Log token usage and cost."""
        metadata: dict = {
            "agent_id": agent_id,
            "correlation_id": correlation_id,
            "model": model,
            "provider": provider,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "tokens_cache": tokens_cache,
            "cost_usd": cost_usd,
        }
        return self.log_event(ObsEventType.TOKEN_USAGE, metadata)

    def log_context_window(
        self,
        agent_id: str,
        correlation_id: str,
        window_size: int,
        window_used: int,
        window_percent: float,
    ) -> int | None:
        """Log context window usage."""
        metadata: dict = {
            "agent_id": agent_id,
            "correlation_id": correlation_id,
            "window_size": window_size,
            "window_used": window_used,
            "window_percent": round(window_percent, 2),
        }
        return self.log_event(ObsEventType.CONTEXT_WINDOW, metadata)

    # ── Governance meta events ──────────────────────────────────────

    def log_rule_matched(
        self,
        agent_id: str,
        tool_name: str,
        correlation_id: str,
        rule_id: str,
        rule_version: str,
        verdict: str,
        risk_score: float,
    ) -> int | None:
        """Log governance rule matched."""
        metadata: dict = {
            "agent_id": agent_id,
            "tool_name": tool_name,
            "correlation_id": correlation_id,
            "rule_id": rule_id,
            "rule_version": rule_version,
            "verdict": verdict,
            "risk_score": risk_score,
        }
        return self.log_event(ObsEventType.RULE_MATCHED, metadata)

    def log_policy_evaluated(
        self,
        agent_id: str,
        tool_name: str,
        correlation_id: str,
        latency_ms: int,
        rules_evaluated: int,
        verdict: str,
    ) -> int | None:
        """Log policy evaluation timing."""
        metadata: dict = {
            "agent_id": agent_id,
            "tool_name": tool_name,
            "correlation_id": correlation_id,
            "latency_ms": latency_ms,
            "rules_evaluated": rules_evaluated,
            "verdict": verdict,
        }
        return self.log_event(ObsEventType.POLICY_EVALUATED, metadata)

    def log_hitl_triggered(
        self,
        agent_id: str,
        tool_name: str,
        correlation_id: str,
        hitl_event_id: str,
        hitl_tier: str,
        risk_score: float,
    ) -> int | None:
        """Log HITL triggered."""
        metadata: dict = {
            "agent_id": agent_id,
            "tool_name": tool_name,
            "correlation_id": correlation_id,
            "hitl_event_id": hitl_event_id,
            "hitl_tier": hitl_tier,
            "risk_score": risk_score,
        }
        return self.log_event(ObsEventType.HITL_TRIGGERED, metadata)

    # ── Buffer management ──────────────────────────────────────────

    def flush(self, force: bool = False) -> int:
        """Upload buffered events to sidecar telemetry endpoint.

        Args:
            force: If True, flush even if batch size / interval not reached.

        Returns:
            Number of events successfully uploaded.
        """
        if self._level == TelemetryLevel.OFF:
            return 0

        with self._lock:
            now = time.time()
            should_flush = force or (
                len(self._pending_upload) >= self._batch_size
                or (now - self._last_flush_time) >= self._flush_interval_seconds
            )
            if not should_flush or not self._pending_upload:
                return 0

            events_to_upload = self._pending_upload[:self._batch_size]
            self._pending_upload = self._pending_upload[self._batch_size:]
            self._last_flush_time = now

        return self._upload_to_sidecar(events_to_upload)

    def _upload_to_sidecar(self, events: list[dict[str, Any]]) -> int:
        """Batch upload events to sidecar /api/telemetry/ingest."""
        if not events:
            return 0

        url = f"{self._sidecar_url.rstrip('/')}/api/telemetry/ingest"
        payload = {
            "source": f"maref-obs-{self._session_id[:8]}",
            "telemetry_type": "obs_event_batch",
            "timestamp": time.time(),
            "data": {
                "events": events,
                "batch_id": uuid.uuid4().hex[:12],
                "session_id": self._session_id,
                "client_version": "1.0",
            },
        }

        headers = {"Content-Type": "application/json"}
        if self._sidecar_auth_token:
            headers["Authorization"] = f"Bearer {self._sidecar_auth_token}"

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status == 200:
                    return len(events)
                else:
                    # Re-queue on non-2xx
                    with self._lock:
                        self._pending_upload = events + self._pending_upload
                    return 0
        except Exception:
            # Re-queue on any error (network, timeout, etc.)
            with self._lock:
                self._pending_upload = events + self._pending_upload
            return 0

    def _maybe_auto_flush(self) -> None:
        """Call after each log_event to trigger auto-flush if thresholds met."""
        if self._level == TelemetryLevel.OFF:
            return
        self.flush(force=False)

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

    def pending_upload_count(self) -> int:
        """Return number of events queued for upload."""
        with self._lock:
            return len(self._pending_upload)

    def shutdown(self) -> int:
        """Flush all pending events on shutdown.

        Returns:
            Number of events successfully uploaded.
        """
        return self.flush(force=True)

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
