"""
MAREF Audit Logger

Append-only, structured audit log for all governance decisions.
Every entry is timestamped, immutable after write, and includes
the full decision context for post-mortem analysis.

Compliance: ISO 27001 audit trail requirements (C.5.33).
Features HMAC-SHA256 signing for tamper-evident audit chain.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from maref.recursive.unified_audit import UnifiedAuditRecord

_HMAC_KEY_ENV = "MAREF_HMAC_SECRET_KEY"


@dataclass(frozen=True)
class AuditEntry:
    """An immutable audit log entry with optional HMAC signature."""

    id: str
    timestamp: float
    event_type: str
    actor: str
    action: str
    details: str
    metadata: dict[str, Any] = field(default_factory=dict)
    previous_hash: str = ""
    chain_hash: str = ""
    hmac_signature: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = {
            "id": self.id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "actor": self.actor,
            "action": self.action,
            "details": self.details,
            "metadata": self.metadata,
        }
        if self.previous_hash:
            result["previous_hash"] = self.previous_hash
        if self.chain_hash:
            result["chain_hash"] = self.chain_hash
        if self.hmac_signature:
            result["hmac_signature"] = self.hmac_signature
        return result

    def _payload_for_signing(self) -> str:
        return json.dumps(
            {
                "id": self.id,
                "timestamp": self.timestamp,
                "event_type": self.event_type,
                "actor": self.actor,
                "action": self.action,
                "details": self.details,
                "metadata": self.metadata,
                "previous_hash": self.previous_hash,
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )

    def to_unified(self, layer: str = "governance", round_num: int = 0) -> UnifiedAuditRecord:
        from maref.recursive.unified_audit import UnifiedAuditRecord

        outcome: str | None = None
        if "success" in self.details.lower() or "recovery" in self.event_type:
            outcome = "success"
        elif "trip" in self.event_type or "failure" in self.details.lower():
            outcome = "failure"

        return UnifiedAuditRecord(
            record_id=self.id,
            timestamp=self.timestamp,
            layer=layer,
            round=round_num,
            event_type=self.event_type,
            source_module=self.actor,
            target_module=self.metadata.get("target_module", ""),
            decision=self.action,
            justification=self.details,
            outcome=outcome,
            context_refs=[],
        )


class AuditLogger:
    """
    Append-only audit logger.

    Writes structured JSON lines to a log file. Each entry is
    a single JSON object per line for easy parsing and streaming.

    Usage:
        logger = AuditLogger(Path("audit.jsonl"))
        logger.log_decision(
            event_type="state_transition",
            actor="GovernanceOverlay",
            action="force_stabilize",
            details="dual_threshold_primary:entropy=4",
            metadata={"from_state": "ACT", "to_state": "STABILIZE"},
        )
    """

    def __init__(
        self,
        log_path: Path | str | None = None,
        hmac_key: bytes | str | None = None,
        max_file_size_mb: int = 50,
    ) -> None:
        if log_path is None:
            self._path: Path | None = None
            self._memory_entries: list[AuditEntry] = []
        else:
            self._path = Path(log_path) if not isinstance(log_path, Path) else log_path
            self._memory_entries = []
        self._write_lock: Any = __import__("threading").Lock()
        self._max_file_size = max_file_size_mb * 1024 * 1024
        env_key = os.environ.get(_HMAC_KEY_ENV)
        resolved_key = hmac_key if hmac_key is not None else env_key
        if resolved_key is None:
            for key_path in (".maraf_hmac_key", ".gaas_api_key"):
                try:
                    with open(key_path) as f:
                        resolved_key = f.read().strip()
                        logger.info("HMAC key loaded from %s", key_path)
                        break
                except (FileNotFoundError, OSError):
                    continue
        if resolved_key:
            self._hmac_key: bytes | None = (
                resolved_key.encode("utf-8") if isinstance(resolved_key, str) else resolved_key
            )
        else:
            self._hmac_key = None
            logger.warning("No HMAC key configured — audit trail tamper protection disabled")

    def _sign_entry(self, entry: AuditEntry) -> str:
        if self._hmac_key is None:
            return ""
        payload = entry._payload_for_signing().encode("utf-8")
        return hmac.new(self._hmac_key, payload, hashlib.sha256).hexdigest()

    def _entry_with_signature(self, entry: AuditEntry) -> AuditEntry:
        sig = self._sign_entry(entry)
        if sig:
            return AuditEntry(
                id=entry.id,
                timestamp=entry.timestamp,
                event_type=entry.event_type,
                actor=entry.actor,
                action=entry.action,
                details=entry.details,
                metadata=entry.metadata,
                previous_hash=entry.previous_hash,
                chain_hash=entry.chain_hash,
                hmac_signature=sig,
            )
        return entry

    def _compute_chain_hash(self, entry: AuditEntry) -> str:
        payload = entry._payload_for_signing().encode("utf-8")
        return hashlib.sha256(entry.previous_hash.encode("utf-8") + payload).hexdigest()

    def verify_integrity(self) -> dict[str, Any]:
        entries = self.read_all()
        total = len(entries)
        signed = sum(1 for e in entries if e.hmac_signature)
        valid = 0
        issues: list[str] = []
        previous_chain_hash = ""

        for entry in entries:
            if entry.previous_hash != previous_chain_hash:
                issues.append(entry.id)

            if not entry.hmac_signature:
                issues.append(entry.id)
                previous_chain_hash = entry.chain_hash
                continue

            expected = self._sign_entry(
                AuditEntry(
                    id=entry.id,
                    timestamp=entry.timestamp,
                    event_type=entry.event_type,
                    actor=entry.actor,
                    action=entry.action,
                    details=entry.details,
                    metadata=entry.metadata,
                    previous_hash=entry.previous_hash,
                )
            )
            if hmac.compare_digest(expected, entry.hmac_signature):
                valid += 1
            else:
                issues.append(entry.id)

            if entry.chain_hash:
                expected_chain = self._compute_chain_hash(entry)
                if not hmac.compare_digest(expected_chain, entry.chain_hash):
                    issues.append(entry.id)
            else:
                issues.append(entry.id)

            previous_chain_hash = entry.chain_hash

        unique_issues = sorted(set(issues))
        return {
            "total_entries": total,
            "signed_entries": signed,
            "valid_signatures": valid,
            "tampered_entries": unique_issues,
            "integrity_intact": len(unique_issues) == 0,
        }

    def log(
        self,
        event_type: str,
        actor: str,
        action: str,
        details: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> AuditEntry:
        import uuid

        now = time.time()
        previous_hash = self._memory_entries[-1].chain_hash if self._memory_entries else ""
        if self._path is not None and self._path.exists() and not self._memory_entries:
            existing = self.read_all(max_entries=None)
            if existing:
                previous_hash = existing[-1].chain_hash
        entry = AuditEntry(
            id=uuid.uuid4().hex[:8],
            timestamp=now,
            event_type=event_type,
            actor=actor,
            action=action,
            details=details,
            metadata=metadata or {},
            previous_hash=previous_hash,
        )
        signed_entry = self._write(entry)
        return signed_entry

    def log_decision(
        self,
        actor: str,
        action: str,
        reason: str = "",
        from_state: str = "",
        to_state: str = "",
        **extra: Any,
    ) -> AuditEntry:
        return self.log(
            event_type="governance_decision",
            actor=actor,
            action=action,
            details=reason,
            metadata={
                "from_state": from_state,
                "to_state": to_state,
                **extra,
            },
        )

    def log_anomaly(
        self,
        actor: str,
        anomaly_type: str,
        severity: str,
        description: str = "",
    ) -> AuditEntry:
        return self.log(
            event_type="anomaly_detected",
            actor=actor,
            action="handle_anomaly",
            details=description,
            metadata={
                "anomaly_type": anomaly_type,
                "severity": severity,
            },
        )

    def _write(self, entry: AuditEntry) -> AuditEntry:
        signed_entry = self._entry_with_signature(entry)
        chain_hash = self._compute_chain_hash(signed_entry)
        final_entry = AuditEntry(
            id=signed_entry.id,
            timestamp=signed_entry.timestamp,
            event_type=signed_entry.event_type,
            actor=signed_entry.actor,
            action=signed_entry.action,
            details=signed_entry.details,
            metadata=signed_entry.metadata,
            previous_hash=signed_entry.previous_hash,
            chain_hash=chain_hash,
            hmac_signature=signed_entry.hmac_signature,
        )
        if self._path is None:
            self._memory_entries.append(final_entry)
            return final_entry
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists() and self._path.stat().st_size >= self._max_file_size:
            self._rotate()
        line = json.dumps(final_entry.to_dict(), ensure_ascii=False, default=str)
        with self._write_lock, open(self._path, "a") as f:
            f.write(line + "\n")
        return final_entry

    def _rotate(self) -> None:
        """Rotate audit log: rename current file, start a new one."""
        assert self._path is not None
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        rotated = self._path.with_name(f"{self._path.stem}_{timestamp}{self._path.suffix}")
        self._path.rename(rotated)

    def read_all(self, max_entries: int | None = 1000) -> list[AuditEntry]:
        if max_entries is None:
            logging.warning("read_all without limit — may cause OOM on large audit logs")
        if self._path is None:
            return list(
                self._memory_entries[-max_entries:] if max_entries else self._memory_entries
            )
        if not self._path.exists():
            return []
        entries: list[AuditEntry] = []
        with open(self._path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        entries.append(
                            AuditEntry(
                                id=data["id"],
                                timestamp=data["timestamp"],
                                event_type=data["event_type"],
                                actor=data["actor"],
                                action=data["action"],
                                details=data["details"],
                                metadata=data.get("metadata", {}),
                                previous_hash=data.get("previous_hash", ""),
                                chain_hash=data.get("chain_hash", ""),
                                hmac_signature=data.get("hmac_signature", ""),
                            )
                        )
                    except (json.JSONDecodeError, KeyError):
                        continue
                if max_entries and len(entries) >= max_entries:
                    break
        return entries[-max_entries:] if max_entries else entries

    def read_recent(self, n: int = 100) -> list[AuditEntry]:
        return self.read_all(max_entries=n)

    def read_filtered(
        self,
        event_type: str | None = None,
        actor: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        max_entries: int | None = 1000,
    ) -> list[AuditEntry]:
        if self._path is None:
            filtered = []
            for entry in self._memory_entries:
                if event_type and entry.event_type != event_type:
                    continue
                if actor and entry.actor != actor:
                    continue
                if start_time and entry.timestamp < start_time:
                    continue
                if end_time and entry.timestamp > end_time:
                    continue
                filtered.append(entry)
        elif not self._path.exists():
            return []
        else:
            filtered = []
            with open(self._path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except (json.JSONDecodeError, KeyError):
                        continue
                    if event_type and data.get("event_type") != event_type:
                        continue
                    if actor and data.get("actor") != actor:
                        continue
                    if start_time and data.get("timestamp", 0) < start_time:
                        continue
                    if end_time and data.get("timestamp", float("inf")) > end_time:
                        continue
                    filtered.append(
                        AuditEntry(
                            id=data["id"],
                            timestamp=data["timestamp"],
                            event_type=data["event_type"],
                            actor=data["actor"],
                            action=data["action"],
                            details=data["details"],
                            metadata=data.get("metadata", {}),
                            previous_hash=data.get("previous_hash", ""),
                            chain_hash=data.get("chain_hash", ""),
                            hmac_signature=data.get("hmac_signature", ""),
                        )
                    )
                    if max_entries and len(filtered) >= max_entries:
                        break
        return filtered[-max_entries:] if max_entries else filtered

    def export_syslog(self, max_entries: int | None = 1000) -> str:
        """Export audit entries in RFC 5424 syslog format."""
        entries = self.read_all(max_entries=max_entries)
        lines: list[str] = []
        for entry in entries:
            priority = 14 * 8 + 6
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(entry.timestamp))
            lines.append(
                f"<{priority}>1 {timestamp} maref MAREF - - "
                f'[audit@32473 event="{entry.event_type}" actor="{entry.actor}" action="{entry.action}"] '
                f"{entry.details}"
            )
        return "\n".join(lines)

    def export_json(
        self,
        event_type: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        max_entries: int | None = 1000,
    ) -> list[dict[str, Any]]:
        """Export audit entries as JSON list with optional filtering."""
        entries = self.read_filtered(
            event_type=event_type,
            start_time=start_time,
            end_time=end_time,
            max_entries=max_entries,
        )
        return [entry.to_dict() for entry in entries]

    def get_audit_trail(self, max_entries: int | None = 1000) -> list[AuditEntry]:
        """Return the audit trail with optional limit."""
        return self.read_all(max_entries=max_entries)

    def count(self) -> int:
        return len(self._memory_entries)
