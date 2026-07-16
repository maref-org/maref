"""GaaS AuditLog Service — immutable, tenant-scoped audit trail.

Every governance decision is logged with HMAC-SHA256 signature.
Supports querying by tenant with time/action/agent filters.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


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


class AuditLogService:
    """Tenant-scoped audit log service with HMAC signing.

    Production should use append-only storage (S3, Glacier, or blockchain anchor).
    """

    def __init__(self, secret: bytes | None = None) -> None:
        if secret is None:
            env_key = os.environ.get("MAREF_HMAC_SECRET_KEY")
            if env_key is None:
                raise ValueError(
                    "AuditLogService requires HMAC secret — set MAREF_HMAC_SECRET_KEY env var"
                )
            self._secret = env_key.encode("utf-8")
        else:
            self._secret = secret
        self._logs: list[GaaSAuditEntry] = []
        self._tenant_index: dict[str, list[int]] = {}

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
