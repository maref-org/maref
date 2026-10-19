"""Alert feedback loop tracker — M2 alert→fix→verify tracking.

Tracks alert lifecycle: generation → acknowledged → fixed → verified.
Provides repeat alert rate statistics and alert disappearance detection.

Core questions answered:
  - M2.2: Was every alert fixed? (alert→fix→verify tracking)
  - M2.3: What is the repeat alert rate? (dedup & repeat stats)
  - P1.4: Has the alert system gone silent? (disappearance detection)
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class AlertRecord:
    """A tracked alert with its lifecycle state."""

    alert_id: str
    name: str
    severity: str
    message: str
    triggered_at: float
    acknowledged_at: float | None = None
    fixed_at: float | None = None
    verified_at: float | None = None
    fix_description: str = ""
    closure_reason: str = ""
    closure_evidence: str = ""
    repeat_count: int = 0
    subsystem: str = ""
    check_id: str = ""

    @property
    def is_open(self) -> bool:
        return self.verified_at is None

    @property
    def is_acknowledged(self) -> bool:
        return self.acknowledged_at is not None

    @property
    def is_fixed(self) -> bool:
        return self.fixed_at is not None

    @property
    def time_to_ack(self) -> float | None:
        if self.acknowledged_at and self.triggered_at:
            return self.acknowledged_at - self.triggered_at
        return None

    @property
    def time_to_fix(self) -> float | None:
        if self.fixed_at and self.triggered_at:
            return self.fixed_at - self.triggered_at
        return None

    @property
    def time_to_verify(self) -> float | None:
        if self.verified_at and self.triggered_at:
            return self.verified_at - self.triggered_at
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "name": self.name,
            "severity": self.severity,
            "message": self.message,
            "triggered_at": self.triggered_at,
            "acknowledged_at": self.acknowledged_at,
            "fixed_at": self.fixed_at,
            "verified_at": self.verified_at,
            "fix_description": self.fix_description,
            "closure_reason": self.closure_reason,
            "closure_evidence": self.closure_evidence,
            "repeat_count": self.repeat_count,
            "subsystem": self.subsystem,
            "check_id": self.check_id,
            "is_open": self.is_open,
            "time_to_fix_hours": round(self.time_to_fix / 3600, 2) if self.time_to_fix else None,
        }


class AlertFeedbackTracker:
    """Tracks alert lifecycle and provides feedback loop metrics.

    Stores state in a JSON file under MAREF_META_PATH for persistence
    across meta-monitor runs. Tracks:
      - Alert → Acknowledge → Fix → Verify lifecycle
      - Repeat alert rates (same name within 24h window)
      - Alert disappearance (no new alerts in 15min window)
    """

    def __init__(self, state_path: Path | str | None = None) -> None:
        if state_path is None:
            try:
                from maref._paths import get_meta_base

                meta_base = get_meta_base()
            except Exception:
                meta_base = Path(os.environ.get("MAREF_META_PATH", ".governance/meta")).resolve()
            state_path = meta_base / "alert_feedback_state.json"
        self._path = Path(state_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._alerts: dict[str, AlertRecord] = {}
        self._alert_timestamps: list[float] = []
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load alert state from disk."""
        if not self._path.exists():
            return
        try:
            with open(self._path) as f:
                data = json.load(f)
            valid_fields = set(AlertRecord.__dataclass_fields__.keys())
            for record_data in data.get("alerts", []):
                filtered = {k: v for k, v in record_data.items() if k in valid_fields}
                record = AlertRecord(**filtered)
                self._alerts[record.alert_id] = record
            self._alert_timestamps = data.get("alert_timestamps", [])
        except (json.JSONDecodeError, OSError):
            pass

    def _save(self) -> None:
        """Persist alert state to disk."""
        data = {
            "alerts": [r.to_dict() for r in self._alerts.values()],
            "alert_timestamps": self._alert_timestamps[-1000:],  # keep last 1000
        }
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp, self._path)

    # ------------------------------------------------------------------
    # Alert lifecycle
    # ------------------------------------------------------------------

    def record_alert(
        self,
        name: str,
        severity: str,
        message: str,
        subsystem: str = "",
        check_id: str = "",
    ) -> AlertRecord:
        """Record a new alert. Returns the record (dedup-aware).

        Dedup keys on (name, severity, check_id) for any currently-open
        alert. If a matching open alert exists, its repeat_count is
        incremented instead of creating a duplicate — this keeps the open
        alert count bounded and makes repeat-rate meaningful.
        """
        now = time.time()
        self._alert_timestamps.append(now)

        for existing in self._alerts.values():
            if (
                existing.name == name
                and existing.severity == severity
                and existing.check_id == check_id
                and existing.is_open
            ):
                existing.repeat_count += 1
                self._save()
                return existing

        import uuid

        record = AlertRecord(
            alert_id=uuid.uuid4().hex[:12],
            name=name,
            severity=severity,
            message=message,
            triggered_at=now,
            subsystem=subsystem,
            check_id=check_id,
        )
        self._alerts[record.alert_id] = record
        self._save()
        return record

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged."""
        record = self._alerts.get(alert_id)
        if record is None or record.acknowledged_at is not None:
            return False
        record.acknowledged_at = time.time()
        self._save()
        return True

    def mark_fixed(self, alert_id: str, description: str = "") -> bool:
        """Mark an alert as fixed."""
        record = self._alerts.get(alert_id)
        if record is None or record.fixed_at is not None:
            return False
        record.fixed_at = time.time()
        record.fix_description = description
        self._save()
        return True

    def mark_verified(self, alert_id: str) -> bool:
        """Mark an alert as verified (feedback loop closed)."""
        record = self._alerts.get(alert_id)
        if record is None or record.verified_at is not None:
            return False
        record.verified_at = time.time()
        self._save()
        return True

    def close_alert(
        self,
        alert_id: str,
        reason: str,
        evidence: str = "",
        description: str = "",
    ) -> bool:
        """Close one alert with an explicit reason and evidence trail."""
        record = self._alerts.get(alert_id)
        if record is None or not record.is_open:
            return False
        now = time.time()
        record.fixed_at = record.fixed_at or now
        record.verified_at = now
        record.fix_description = description or reason
        record.closure_reason = reason
        record.closure_evidence = evidence
        self._save()
        return True

    def reopen_alert(self, alert_id: str, reason: str = "") -> bool:
        """Re-open a mistakenly closed alert (audit correction)."""
        record = self._alerts.get(alert_id)
        if record is None or record.is_open:
            return False
        record.fixed_at = None
        record.verified_at = None
        record.fix_description = ""
        record.closure_reason = reason
        record.closure_evidence = ""
        self._save()
        return True

    def bulk_close(
        self,
        alert_ids: list[str],
        reason: str,
        evidence: str = "",
        description: str = "",
    ) -> int:
        """Close multiple alerts with one attribution record."""
        resolved = 0
        now = time.time()
        for alert_id in alert_ids:
            record = self._alerts.get(alert_id)
            if record is None or not record.is_open:
                continue
            record.fixed_at = record.fixed_at or now
            record.verified_at = now
            record.fix_description = description or reason
            record.closure_reason = reason
            record.closure_evidence = evidence
            resolved += 1
        if resolved:
            self._save()
        return resolved

    def resolve_by_check(self, check_id: str, description: str = "", evidence: str = "") -> int:
        """Auto-close all open alerts belonging to a recovered check.

        Marks each matching open alert as fixed+verified (feedback loop
        closure). Returns the number of alerts resolved.
        """
        resolved = 0
        now = time.time()
        for record in self._alerts.values():
            if record.check_id == check_id and record.is_open:
                if record.fixed_at is None:
                    record.fixed_at = now
                    record.fix_description = description or "check recovered"
                if record.verified_at is None:
                    record.verified_at = now
                record.closure_reason = description or "check recovered"
                record.closure_evidence = evidence
                resolved += 1
        if resolved:
            self._save()
        return resolved

    def resolve_all_open(self, description: str = "", evidence: str = "") -> int:
        """Close every currently-open alert (used after remediation).

        Returns the number of alerts resolved.
        """
        resolved = 0
        now = time.time()
        for record in self._alerts.values():
            if record.is_open:
                if record.fixed_at is None:
                    record.fixed_at = now
                    record.fix_description = description or "remediation applied"
                if record.verified_at is None:
                    record.verified_at = now
                record.closure_reason = description or "remediation applied"
                record.closure_evidence = evidence
                resolved += 1
        if resolved:
            self._save()
        return resolved

    def resolve_legacy_open(
        self,
        description: str = "",
        evidence: str = "",
        max_age_hours: float = 24.0,
    ) -> int:
        """Close *old* open alerts that predate check_id tracking.

        Before ``check_id`` was introduced every recorded alert carried an
        empty ``check_id``. A one-shot migration is needed, but it must not
        swallow a current alert (e.g. M4 telemetry) that merely lacks a
        check_id. Only records older than ``max_age_hours`` are closed.
        """
        resolved = 0
        now = time.time()
        cutoff = now - max_age_hours * 3600
        for record in self._alerts.values():
            if record.is_open and record.check_id == "" and record.triggered_at < cutoff:
                if record.fixed_at is None:
                    record.fixed_at = now
                    record.fix_description = description or "legacy alert consumed"
                if record.verified_at is None:
                    record.verified_at = now
                record.closure_reason = description or "legacy alert consumed"
                record.closure_evidence = evidence
                resolved += 1
        if resolved:
            self._save()
        return resolved

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def get_open_alerts(self) -> list[AlertRecord]:
        """Get all alerts that haven't been verified yet."""
        return [r for r in self._alerts.values() if r.is_open]

    def get_alerts(self) -> list[AlertRecord]:
        """Get all tracked alerts (open and closed)."""
        return list(self._alerts.values())

    def get_recently_closed(self, window_hours: float = 24) -> list[AlertRecord]:
        """Get alerts closed in the given time window."""
        cutoff = time.time() - window_hours * 3600
        return [r for r in self._alerts.values() if not r.is_open and (r.verified_at or 0) > cutoff]

    def repeat_alert_rate(self, window_hours: float = 24) -> dict[str, Any]:
        """Calculate repeat alert rate in the given window.

        A "repeat" is an alert with the same name that fired >1 time.
        """
        cutoff = time.time() - window_hours * 3600
        name_counts: dict[str, int] = {}
        name_repeats: dict[str, int] = {}
        for record in self._alerts.values():
            if record.triggered_at < cutoff:
                continue
            name_counts[record.name] = name_counts.get(record.name, 0) + 1
            if name_counts[record.name] > 1:
                name_repeats[record.name] = name_counts[record.name]

        total = sum(name_counts.values())
        # Count only occurrences beyond the first per name. A single
        # long-running incident is not a repeat; a second record means the
        # alert recurred after the previous one was closed.
        repeat_total = sum(c - 1 for c in name_counts.values() if c > 1)
        repeat_names = len(name_repeats)
        return {
            "total_alerts": total,
            "repeat_alerts": repeat_total,
            "unique_alert_names": len(name_counts),
            "repeat_names": repeat_names,
            "repeat_rate": round(repeat_total / total, 3) if total > 0 else 0.0,
            "healthy": (repeat_total / total <= 0.15) if total > 5 else True,
            "repeat_details": name_repeats,
        }

    def check_alert_disappearance(
        self,
        silence_window: float = 900.0,
    ) -> dict[str, Any]:
        """Check if the alert system has gone silent.

        If no new alerts in the last ``silence_window`` seconds (default 15 min),
        this is itself an alert-worthy event.
        """
        now = time.time()
        recent = [t for t in self._alert_timestamps if now - t < silence_window]

        result: dict[str, Any] = {
            "passed": len(recent) > 0,
            "last_alert_seconds_ago": round(now - self._alert_timestamps[-1], 1)
            if self._alert_timestamps
            else None,
            "alerts_in_window": len(recent),
            "silence_window_seconds": silence_window,
        }

        if self._alert_timestamps and now - self._alert_timestamps[-1] > silence_window:
            result["detail"] = (
                f"No alerts in {silence_window / 60:.0f}min — alert system may be silent/silenced"
            )
        elif not self._alert_timestamps:
            result["detail"] = "No alerts ever recorded — tracking may be uninitialized"

        return result

    def alert_recovery_rate(self, window_hours: float = 72) -> dict[str, Any]:
        """Calculate the alert recovery rate.

        Recovery rate = closed alerts / total alerts in the window. An alert
        is "recovered" when it is no longer open (fixed or verified).
        """
        cutoff = time.time() - window_hours * 3600
        window_alerts = [r for r in self._alerts.values() if r.triggered_at > cutoff]
        total = len(window_alerts)
        fixed = sum(1 for r in window_alerts if r.is_fixed)
        verified = sum(1 for r in window_alerts if r.verified_at is not None)
        open_count = sum(1 for r in window_alerts if r.is_open)

        recovered = total - open_count
        recovery_rate = recovered / total if total > 0 else 1.0
        return {
            "total_alerts": total,
            "fixed": fixed,
            "verified": verified,
            "open": open_count,
            "recovered": recovered,
            "recovery_rate": round(recovery_rate, 3),
            "healthy": recovery_rate >= 0.90 or total == 0,
        }

    def mttr_hours(self, window_hours: float = 72) -> dict[str, Any]:
        """Mean time to repair/verify for alerts closed in the window."""
        cutoff = time.time() - window_hours * 3600
        durations = [
            r.time_to_verify
            for r in self._alerts.values()
            if r.verified_at is not None and r.verified_at > cutoff and r.time_to_verify is not None
        ]
        return {
            "closed_alerts": len(durations),
            "mttr_hours": round(sum(durations) / len(durations) / 3600, 2) if durations else None,
            "window_hours": window_hours,
        }

    def summary(self) -> dict[str, Any]:
        """Return a comprehensive summary for M2 reporting."""
        return {
            "total_tracked_alerts": len(self._alerts),
            "open_alerts": len(self.get_open_alerts()),
            "repeat_alert_rate": self.repeat_alert_rate(),
            "alert_recovery": self.alert_recovery_rate(),
            "alert_disappearance": self.check_alert_disappearance(),
            "mttr": self.mttr_hours(),
        }
