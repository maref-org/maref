"""EU AI Act Record-Keeping — Article 12.

Implements Art.12 requirements for automatic event logging, retention
policy configuration, regulatory log export (JSON/Markdown),
and Merkle audit chain integration for tamper-evident audit trails.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4


class AuditChainBridge(Protocol):
    """Duck-typed protocol for AuditChainIntegrator.

    Avoids hard cross-layer import from eivl/merkle_auditor.
    """

    def record_audit_entry(self, entry: Any) -> str: ...


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


class _AIActToAuditAdapter:
    """Adapts AIActLogEntry to governance AuditEntry protocol.

    Allows AIActLogEntry to be pushed through AuditChainIntegrator.
    Satisfies field access required by AuditEvidence.from_audit_entry().
    """

    def __init__(self, entry: AIActLogEntry, system_id: str) -> None:
        self.id = entry.entry_id
        self.timestamp = (
            time.mktime(datetime.fromisoformat(entry.event_timestamp_utc).timetuple())
            if "T" in entry.event_timestamp_utc
            else time.time()
        )
        self.event_type = "ai_act_log"
        self.actor = system_id
        self.action = entry.decision_type or "log_event"
        self.details = (
            f"Session {entry.session_id} | "
            f"confidence={entry.confidence_score} | "
            f"risk={entry.risk_event} | "
            f"anomaly={entry.anomaly_flag}"
        )
        self.metadata: dict[str, Any] = {
            "entry_id": entry.entry_id,
            "session_id": entry.session_id,
            "risk_event": entry.risk_event,
            "anomaly_flag": entry.anomaly_flag,
            "input_data_hash": entry.input_data_hash,
            "system_id": system_id,
        }
        self.chain_hash: str = ""

    @property
    def signature_type(self) -> str:
        return "unsigned"


class AIActLogger:
    """Art.12 automatic event logger.

    Wraps the AIActLogEntry schema with in-memory storage.
    Provides log_event creation with SHA-256 input hashing,
    query filtering, retention status reporting, and optional
    Merkle audit chain anchoring for tamper-evident audit trails.
    """

    def __init__(
        self,
        system_id: str,
        system_version: str = "1.0.0",
        retention: RetentionPolicy | None = None,
        chain_integrator: Any | None = None,
    ) -> None:
        self.system_id = system_id
        self.system_version = system_version
        self.retention = retention if retention is not None else RetentionPolicy()
        self._chain_integrator = chain_integrator
        self._entries: dict[str, AIActLogEntry] = {}
        self._merkle_hashes: dict[str, str] = {}

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
            "entry_id",
            "system_id",
            "system_version",
            "session_id",
            "event_timestamp_utc",
            "use_period_start",
            "use_period_end",
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
        if self._chain_integrator is not None:
            adapter = _AIActToAuditAdapter(entry, self.system_id)
            try:
                merkle_hash = self._chain_integrator.record_audit_entry(adapter)
                self._merkle_hashes[entry.entry_id] = merkle_hash
            except (TypeError, ValueError, AttributeError):
                pass
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

        valid_query_fields = {
            "risk_event",
            "anomaly_flag",
            "session_id",
            "entry_id",
            "decision_type",
        }
        for key, value in filters.items():
            if key not in valid_query_fields:
                raise ValueError(f"Unknown query filter field: {key}")
            results = [e for e in results if getattr(e, key, None) == value]

        return results

    def get_retention_status(self) -> dict[str, Any]:
        """Return current retention policy status summary.

        Returns:
            Dict with retention_days, apply_to_public_authority,
            total_events, system_id, system_version, and
            merkle_chain status if chain_integrator is configured.
        """
        result: dict[str, Any] = {
            "retention_days": self.retention.duration_days,
            "apply_to_public_authority": self.retention.apply_to_public_authority,
            "total_events": len(self._entries),
            "system_id": self.system_id,
            "system_version": self.system_version,
        }
        if self._chain_integrator is not None:
            result["merkle_chain_enabled"] = True
            result["merkle_anchored_events"] = len(self._merkle_hashes)
        return result

    def get_merkle_hash(self, entry_id: str) -> str | None:
        """Return the Merkle leaf hash for a given entry, if anchored."""
        return self._merkle_hashes.get(entry_id)

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
            "entry_id",
            "system_id",
            "session_id",
            "event_timestamp_utc",
            "use_period_start",
            "use_period_end",
            "decision_type",
            "confidence_score",
            "risk_event",
            "anomaly_flag",
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
