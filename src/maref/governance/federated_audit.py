"""
MAREF Federated Audit Log

Cross-instance audit trail that records all synchronization
events, consensus decisions, and detected poisoning attempts.
Each entry is HMAC-signed for tamper-evident verification.
"""

from __future__ import annotations

import hashlib
import hmac as hmac_lib
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AuditEventType(Enum):
    SYNC_STARTED = "sync_started"
    SYNC_COMPLETED = "sync_completed"
    SYNC_FAILED = "sync_failed"
    CONSENSUS_REACHED = "consensus_reached"
    CONSENSUS_FAILED = "consensus_failed"
    WEIGHT_POISON_DETECTED = "weight_poison_detected"
    CONFLICT_DETECTED = "conflict_detected"
    CONFLICT_RESOLVED = "conflict_resolved"
    INSTANCE_JOINED = "instance_joined"
    INSTANCE_LEFT = "instance_left"
    POLICY_VIOLATION = "policy_violation"
    UNAUTHORIZED_SYNC = "unauthorized_sync"


_HMAC_KEY: bytes | None = None


def _ensure_hmac_key() -> bytes:
    global _HMAC_KEY
    if _HMAC_KEY is not None:
        return _HMAC_KEY
    key = os.environ.get("MAREF_FEDERATED_AUDIT_KEY")
    if key:
        _HMAC_KEY = key.encode("utf-8")
        return _HMAC_KEY
    try:
        import keyring

        stored = keyring.get_password("system", "maref-federated-audit-key")
        if stored:
            _HMAC_KEY = stored.encode("utf-8")
            return _HMAC_KEY
    except ImportError:
        pass
    raise RuntimeError(
        "MAREF_FEDERATED_AUDIT_KEY environment variable not set. "
        "Use keyring_store.py to store it, or set the env var before "
        "using federated audit."
    )


@dataclass
class FederatedAuditEntry:
    entry_id: str
    event_type: AuditEventType
    source_instance: str
    target_instance: str
    data_type: str
    details: str
    severity: str = "info"
    timestamp: float = field(default_factory=time.time)
    blob_hash: str = ""
    hmac_signature: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "event_type": self.event_type.value,
            "source_instance": self.source_instance,
            "target_instance": self.target_instance,
            "data_type": self.data_type,
            "details": self.details,
            "severity": self.severity,
            "timestamp": self.timestamp,
            "blob_hash": self.blob_hash,
            "hmac_signature": self.hmac_signature,
        }

    def sign(self, key: bytes | None = None) -> str:
        if key is None:
            key = _ensure_hmac_key()
        payload = (
            f"{self.entry_id}:{self.event_type.value}:{self.source_instance}:"
            f"{self.target_instance}:{self.data_type}:{self.details}:{self.timestamp}"
        ).encode()
        self.hmac_signature = hmac_lib.new(key, payload, hashlib.sha256).hexdigest()
        return self.hmac_signature

    def verify(self, key: bytes | None = None) -> bool:
        if not self.hmac_signature:
            return False
        if key is None:
            key = _ensure_hmac_key()
        payload = (
            f"{self.entry_id}:{self.event_type.value}:{self.source_instance}:"
            f"{self.target_instance}:{self.data_type}:{self.details}:{self.timestamp}"
        ).encode()
        expected = hmac_lib.new(key, payload, hashlib.sha256).hexdigest()
        return hmac_lib.compare_digest(self.hmac_signature, expected)


class FederatedAuditLog:
    def __init__(self) -> None:
        self._entries: list[FederatedAuditEntry] = []

    def record(
        self,
        event_type: AuditEventType,
        source_instance: str,
        target_instance: str,
        data_type: str,
        details: str = "",
        severity: str = "info",
    ) -> FederatedAuditEntry:
        entry = FederatedAuditEntry(
            entry_id=str(uuid.uuid4()),
            event_type=event_type,
            source_instance=source_instance,
            target_instance=target_instance,
            data_type=data_type,
            details=details,
            severity=severity,
        )
        entry.sign()
        self._entries.append(entry)
        return entry

    def query(
        self,
        event_type: AuditEventType | None = None,
        source: str | None = None,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[FederatedAuditEntry]:
        results = list(self._entries)
        if event_type:
            results = [e for e in results if e.event_type == event_type]
        if source:
            results = [e for e in results if e.source_instance == source]
        if severity:
            results = [e for e in results if e.severity == severity]
        return sorted(results, key=lambda e: e.timestamp, reverse=True)[:limit]

    def verify_all(self) -> list[FederatedAuditEntry]:
        return [e for e in self._entries if not e.verify()]

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def get_entries(self) -> list[FederatedAuditEntry]:
        return list(self._entries)
