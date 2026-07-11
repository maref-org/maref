"""EU AI Act Record-Keeping — Article 12.

Implements Art.12 requirements for automatic event logging, retention
policy configuration, and regulatory log export (JSON/Markdown).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass
class AIActLogEntry:
    """Art.12(1) a-k: single automatically logged event entry.

    Fields mirror the EU AI Act Article 12 logging requirements
    for high-risk AI system event records.
    """

    entry_id: str
    system_id: str
    system_version: str
    session_id: str
    event_timestamp_utc: str
    use_period_start: str
    use_period_end: str
    input_data_hash: str
    input_data_fields: list[str] = field(default_factory=list)
    reference_database: str = ""
    reference_version: str = ""
    decision_type: str = ""
    decision_rationale: str = ""
    confidence_score: float | None = None
    human_oversight_person_id: str | None = None
    human_oversight_action: str | None = None
    automated_only_exemption: str | None = None
    risk_event: bool = False
    anomaly_flag: bool = False
    error_type: str | None = None
    failsafe_triggered: bool = False


@dataclass
class RetentionPolicy:
    """Art.12(3): retention duration for log entries.

    Default 183 days (6 months) per Art.12(3) first paragraph.
    Public authority deployments may require extended retention.
    """

    duration_days: int = 183
    apply_to_public_authority: bool = False


class AIActLogger:
    """Art.12 automatic event logger.

    Wraps the AIActLogEntry schema with in-memory storage.
    Provides log_event creation with SHA-256 input hashing,
    query filtering, and retention status reporting.
    """

    def __init__(
        self,
        system_id: str,
        system_version: str = "1.0.0",
        retention: RetentionPolicy | None = None,
    ) -> None:
        self.system_id = system_id
        self.system_version = system_version
        self.retention = retention if retention is not None else RetentionPolicy()
        self._entries: dict[str, AIActLogEntry] = {}

    def log_event(
        self,
        session_id: str,
        use_period_start: str,
        use_period_end: str,
        input_data: str,
        **kwargs: Any,
    ) -> AIActLogEntry:
        """Create and store an AIActLogEntry.

        Args:
            session_id: Identifier for the session.
            use_period_start: ISO 8601 start of use period.
            use_period_end: ISO 8601 end of use period.
            input_data: Raw input string (SHA-256 hashed for storage).
            **kwargs: Additional AIActLogEntry fields.

        Returns:
            The newly created AIActLogEntry.
        """
        valid_fields = {f.name for f in fields(AIActLogEntry)} - {
            "entry_id", "system_id", "system_version", "session_id",
            "event_timestamp_utc", "use_period_start", "use_period_end",
            "input_data_hash",
        }
        unknown = set(kwargs) - valid_fields
        if unknown:
            raise ValueError(f"Unknown log_event kwargs: {unknown}")
        if not session_id or not use_period_start or not use_period_end:
            raise ValueError("session_id, use_period_start, and use_period_end are required")

        input_hash = hashlib.sha256(input_data.encode()).hexdigest()
        now = datetime.now(timezone.utc).isoformat()

        entry = AIActLogEntry(
            entry_id=uuid4().hex[:12],
            system_id=self.system_id,
            system_version=self.system_version,
            session_id=session_id,
            event_timestamp_utc=now,
            use_period_start=use_period_start,
            use_period_end=use_period_end,
            input_data_hash=input_hash,
            input_data_fields=kwargs.pop("input_data_fields", []),
            reference_database=kwargs.pop("reference_database", ""),
            reference_version=kwargs.pop("reference_version", ""),
            decision_type=kwargs.pop("decision_type", ""),
            decision_rationale=kwargs.pop("decision_rationale", ""),
            confidence_score=kwargs.pop("confidence_score", None),
            human_oversight_person_id=kwargs.pop("human_oversight_person_id", None),
            human_oversight_action=kwargs.pop("human_oversight_action", None),
            automated_only_exemption=kwargs.pop("automated_only_exemption", None),
            risk_event=kwargs.pop("risk_event", False),
            anomaly_flag=kwargs.pop("anomaly_flag", False),
            error_type=kwargs.pop("error_type", None),
            failsafe_triggered=kwargs.pop("failsafe_triggered", False),
        )
        self._entries[entry.entry_id] = entry
        return entry

    def query(
        self,
        system_id: str | None = None,
        **filters: Any,
    ) -> list[AIActLogEntry]:
        """Query stored entries with optional filters.

        Supported filter keys: system_id, risk_event, anomaly_flag, session_id.
        When multiple filters are provided they are AND-ed together.

        Args:
            system_id: Optional filter by system ID.
            **filters: Additional field filters (risk_event, anomaly_flag, etc).

        Returns:
            Filtered list of AIActLogEntry objects.
        """
        results = list(self._entries.values())

        if system_id is not None:
            results = [e for e in results if e.system_id == system_id]

        valid_query_fields = {"risk_event", "anomaly_flag", "session_id", "entry_id", "decision_type"}
        for key, value in filters.items():
            if key not in valid_query_fields:
                raise ValueError(f"Unknown query filter field: {key}")
            results = [e for e in results if getattr(e, key, None) == value]

        return results

    def get_retention_status(self) -> dict[str, Any]:
        """Return current retention policy status summary.

        Returns:
            Dict with retention_days, apply_to_public_authority,
            total_events, system_id, and system_version.
        """
        return {
            "retention_days": self.retention.duration_days,
            "apply_to_public_authority": self.retention.apply_to_public_authority,
            "total_events": len(self._entries),
            "system_id": self.system_id,
            "system_version": self.system_version,
        }

    def count_events(self) -> int:
        """Return the total number of stored events.

        Returns:
            Integer count of entries.
        """
        return len(self._entries)


class RegulatoryLogExporter:
    """Art.12(2): export log entries in regulatory formats.

    Supports JSON (machine-readable) and Markdown (human-readable)
    export formats for submission to regulatory authorities.
    """

    def export_json(self, entries: list[AIActLogEntry]) -> str:
        """Export entries as a JSON string.

        Args:
            entries: List of AIActLogEntry objects to export.

        Returns:
            Indented JSON string.
        """
        data = []
        for entry in entries:
            record: dict[str, Any] = {}
            for f in fields(AIActLogEntry):
                record[f.name] = getattr(entry, f.name)
            data.append(record)
        return json.dumps(data, indent=2)

    def export_markdown(self, entries: list[AIActLogEntry]) -> str:
        """Export entries as a human-readable Markdown table.

        Args:
            entries: List of AIActLogEntry objects to export.

        Returns:
            Markdown table string.
        """
        if not entries:
            return "No log entries to export."

        header_fields = [
            "entry_id", "system_id", "session_id", "event_timestamp_utc",
            "use_period_start", "use_period_end", "decision_type",
            "confidence_score", "risk_event", "anomaly_flag",
            "human_oversight_action",
        ]
        header = "| " + " | ".join(header_fields) + " |"
        separator = "| " + " | ".join("---" for _ in header_fields) + " |"

        lines = [header, separator]
        for entry in entries:
            row = []
            for f_name in header_fields:
                val = getattr(entry, f_name)
                val_str = str(val) if val is not None else ""
                if isinstance(val, bool):
                    if f_name == "risk_event" and val:
                        val_str = "RISK"
                    elif f_name == "anomaly_flag" and val:
                        val_str = "ANOMALY"
                    else:
                        val_str = str(val)
                row.append(val_str)
            lines.append("| " + " | ".join(row) + " |")

        lines.append("")
        lines.append(
            f"*Total entries: {len(entries)} | "
            f"Risk events: {sum(1 for e in entries if e.risk_event)} | "
            f"Anomalies: {sum(1 for e in entries if e.anomaly_flag)}*"
        )
        return "\n".join(lines)
