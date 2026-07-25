"""GaaS AuditLog Service - immutable, tenant-scoped audit trail.

Every governance decision is logged with HMAC-SHA256 signature.
Supports querying by tenant with time/action/agent filters.

Optional append-only JSONL persistence: pass ``log_path`` to
:class:`AuditLogService` to persist entries across process restarts.
Each line is a self-contained signed JSON record (append-only, never
mutated), matching the tamper-evident pattern of
:class:`maref.governance.audit.AuditLogger`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GaaSAuditEntry:
    """Immutable audit entry for GaaS governance decisions."""

    log_id: str
    timestamp: float
    tenant_id: str
    agent_id: str
    action: str
    verdict: str
    parameters: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    hmac_signature: str = ""

    def _payload_for_signing(self) -> str:
        return json.dumps(
            {
                "log_id": self.log_id,
                "timestamp": self.timestamp,
                "tenant_id": self.tenant_id,
                "agent_id": self.agent_id,
                "action": self.action,
                "verdict": self.verdict,
                "parameters": self.parameters,
                "context": self.context,
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )

    def verify(self, secret: bytes) -> bool:
        if not self.hmac_signature:
            return False
        expected = hmac.new(
            secret,
            self._payload_for_signing().encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, self.hmac_signature)

    def to_dict(self) -> dict[str, Any]:
        return {
            "log_id": self.log_id,
            "timestamp": self.timestamp,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "action": self.action,
            "verdict": self.verdict,
            "parameters": self.parameters,
            "context": self.context,
            "hmac_signature": self.hmac_signature,
        }


class AuditLogService:
    """Tenant-scoped audit log service with HMAC signing.

    By default operates in-memory.  Pass ``log_path`` to enable
    append-only JSONL persistence; existing entries are loaded on
    construction and new entries are appended atomically.
    """

    def __init__(
        self,
        secret: bytes | None = None,
        log_path: str | Path | None = None,
    ) -> None:
        if secret is None:
            env_key = os.environ.get("MAREF_HMAC_SECRET_KEY")
            if env_key is None:
                raise ValueError(
                    "AuditLogService requires HMAC secret - set MAREF_HMAC_SECRET_KEY env var"
                )
            self._secret = env_key.encode("utf-8")
        else:
            self._secret = secret
        self._logs: list[GaaSAuditEntry] = []
        self._tenant_index: dict[str, list[int]] = {}
        self._log_path: Path | None = Path(log_path) if log_path else None
        if self._log_path is not None:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Load existing entries from the JSONL log file (append-only)."""
        assert self._log_path is not None
        if not self._log_path.exists():
            return
        with open(self._log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                entry = GaaSAuditEntry(
                    log_id=data["log_id"],
                    timestamp=data["timestamp"],
                    tenant_id=data["tenant_id"],
                    agent_id=data["agent_id"],
                    action=data["action"],
                    verdict=data["verdict"],
                    parameters=data.get("parameters", {}),
                    context=data.get("context", {}),
                    hmac_signature=data.get("hmac_signature", ""),
                )
                if not entry.verify(self._secret):
                    logger.warning(
                        "HMAC verification failed for audit entry %s, skipping",
                        entry.log_id,
                    )
                    continue
                idx = len(self._logs)
                self._logs.append(entry)
                self._tenant_index.setdefault(entry.tenant_id, []).append(idx)

    def _append_to_disk(self, entry: GaaSAuditEntry) -> None:
        """Append a single signed entry to the JSONL log file."""
        assert self._log_path is not None
        record = entry.to_dict()
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def log(
        self,
        tenant_id: str,
        agent_id: str,
        action: str,
        verdict: str,
        parameters: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> GaaSAuditEntry:
        """Log a governance decision and return the signed entry."""
        entry = GaaSAuditEntry(
            log_id=f"log_{uuid.uuid4().hex}",
            timestamp=time.time(),
            tenant_id=tenant_id,
            agent_id=agent_id,
            action=action,
            verdict=verdict,
            parameters=parameters or {},
            context=context or {},
        )
        # Sign
        payload = entry._payload_for_signing()
        signature = hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()
        object.__setattr__(entry, "hmac_signature", signature)

        if self._log_path is not None:
            self._append_to_disk(entry)
        idx = len(self._logs)
        self._logs.append(entry)
        self._tenant_index.setdefault(tenant_id, []).append(idx)
        return entry

    def query(
        self,
        tenant_id: str,
        start_time: float | None = None,
        end_time: float | None = None,
        agent_id: str | None = None,
        action: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[GaaSAuditEntry], int]:
        """Query audit logs for a tenant."""
        indices = self._tenant_index.get(tenant_id, [])
        results: list[GaaSAuditEntry] = []

        for idx in indices:
            entry = self._logs[idx]
            if start_time is not None and entry.timestamp < start_time:
                continue
            if end_time is not None and entry.timestamp > end_time:
                continue
            if agent_id is not None and entry.agent_id != agent_id:
                continue
            if action is not None and entry.action != action:
                continue
            results.append(entry)

        total = len(results)
        return results[offset : offset + limit], total

    def verify_integrity(self, tenant_id: str) -> bool:
        """Verify HMAC signatures for all entries of a tenant."""
        indices = self._tenant_index.get(tenant_id, [])
        return all(self._logs[idx].verify(self._secret) for idx in indices)

    def get_stats(self, tenant_id: str) -> dict[str, Any]:
        indices = self._tenant_index.get(tenant_id, [])
        return {
            "total_entries": len(indices),
            "tenant_id": tenant_id,
            "integrity_verified": self.verify_integrity(tenant_id),
        }
