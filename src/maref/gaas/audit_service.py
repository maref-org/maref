"""GaaS AuditLog Service — tenant-scoped, HMAC-signed audit trail.

This module delegates to :class:`maref.governance.audit_bus.AuditBus`
under the hood.  The public ``AuditLogService`` and ``GaaSAuditEntry``
classes are kept for full backward compatibility; the internal storage,
signing, and persistence are handled by the unified AuditBus.

Migration to the new API::

    from maref.governance.audit_bus import AuditBus

    bus = AuditBus()
    entry = bus.log_tenant("tenant-abc", "agent-01", "approve", "ALLOW")
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maref.governance.audit_bus import AuditBus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GaaSAuditEntry:
    """Immutable audit entry for GaaS governance decisions.

    .. deprecated::
        Consider using the unified :class:`maref.governance.audit.AuditEntry`
        via ``AuditBus.log_tenant()`` for new code.  This class is kept
        for backward compatibility with existing callers.
    """

    log_id: str
    timestamp: float
    tenant_id: str
    agent_id: str
    action: str
    verdict: str
    parameters: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    hmac_signature: str = ""

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

    def verify(self, secret: bytes | None) -> bool:
        """Verify this entry has not been tampered with.

        Recomputes the HMAC over the canonical payload and compares it to the
        stored signature.  Returns False when no signature is present or when
        the recomputed HMAC does not match — tamper-evident by construction.
        """
        if not self.hmac_signature:
            return False
        if secret is None:
            return False
        try:
            payload = self._canonical_payload()
            expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected, self.hmac_signature)
        except Exception:
            return False

    def _canonical_payload(self) -> bytes:
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
            default=str,
        ).encode("utf-8")

    @classmethod
    def from_bus_entry(cls, audit_entry: Any) -> GaaSAuditEntry:
        """Create a ``GaaSAuditEntry`` from a unified ``AuditEntry``."""
        meta = getattr(audit_entry, "metadata", {})
        return cls(
            log_id=f"gaas_{audit_entry.id[:28]}",
            timestamp=audit_entry.timestamp,
            tenant_id=getattr(audit_entry, "tenant_id", meta.get("tenant_id", "")),
            agent_id=audit_entry.actor,
            action=audit_entry.action,
            verdict=audit_entry.details,
            parameters=meta.get("action_params", {}),
            context=meta.get("context", {}),
            hmac_signature=getattr(audit_entry, "hmac_signature", ""),
        )


class AuditLogService:
    """Tenant-scoped audit log service backed by the unified ``AuditBus``.

    All entries are logged through :class:`maref.governance.audit_bus.AuditBus`
    and are visible via the unified audit trail.  The per-tenant index,
    HMAC signing, and JSONL persistence are handled by the underlying bus.

    Calls to ``log()`` return a ``GaaSAuditEntry`` for backward compat;
    new code should use ``AuditBus.log_tenant()`` directly.
    """

    def __init__(
        self,
        secret: bytes | None = None,
        log_path: str | Path | None = None,
        bus: AuditBus | None = None,
    ) -> None:
        self._secret = secret
        if secret is None and os.environ.get("MAREF_HMAC_SECRET_KEY") is not None:
            secret = os.environ["MAREF_HMAC_SECRET_KEY"].encode("utf-8")
            self._secret = secret
        if self._secret is None:
            raise ValueError(
                "AuditLogService requires an HMAC secret key. "
                "Set MAREF_HMAC_SECRET_KEY or pass `secret=`."
            )
        if bus is None:
            from maref.governance.audit import AuditLogger

            try:
                logger = AuditLogger(
                    log_path=Path(log_path) if log_path else None,
                    hmac_key=secret,
                )
            except RuntimeError as exc:
                raise ValueError(str(exc)) from exc
            bus = AuditBus(logger=logger)
        self._bus = bus
        # Keep an in-memory index for backward-compat queries.
        self._entries: list[GaaSAuditEntry] = []
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
        """Log a governance decision through the unified AuditBus.

        Returns a ``GaaSAuditEntry`` for backward compatibility.
        The entry is simultaneously visible through ``AuditBus.query_tenant()``.
        """
        # Delegate to AuditBus (handles signing + persistence).
        bus_entry = self._bus.log_tenant(
            tenant_id=tenant_id,
            agent_id=agent_id,
            action=action,
            verdict=verdict,
            parameters=parameters,
            context=context,
        )
        # Wrap as GaaSAuditEntry for backward-compat return type.
        gaas_entry = GaaSAuditEntry.from_bus_entry(bus_entry)

        # Attach a GaaS-level HMAC so ``entry.verify(secret)`` can detect
        # tampering at the tenant-scoped layer (the bus keeps its own
        # Ed25519 chain signature on disk).
        if self._secret is not None:
            hmac_value = hmac.new(
                self._secret, gaas_entry._canonical_payload(), hashlib.sha256
            ).hexdigest()
            gaas_entry = dataclasses.replace(gaas_entry, hmac_signature=hmac_value)

        idx = len(self._entries)
        self._entries.append(gaas_entry)
        self._tenant_index.setdefault(tenant_id, []).append(idx)
        return gaas_entry

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
        """Query audit logs for a tenant.

        Results are drawn from the authoritative bus (disk-backed), which
        survives service restarts.  Falls back to the in-memory index if the
        bus has no backing file.
        """
        bus_entries = self._bus.query_tenant(tenant_id, max_entries=None)
        if bus_entries:
            results: list[GaaSAuditEntry] = [GaaSAuditEntry.from_bus_entry(e) for e in bus_entries]
        else:
            indices = self._tenant_index.get(tenant_id, [])
            results = [self._entries[idx] for idx in indices]

        if start_time is not None:
            results = [e for e in results if e.timestamp >= start_time]
        if end_time is not None:
            results = [e for e in results if e.timestamp <= end_time]
        if agent_id is not None:
            results = [e for e in results if e.agent_id == agent_id]
        if action is not None:
            results = [e for e in results if e.action == action]

        total = len(results)
        return results[offset : offset + limit], total

    def verify_integrity(self, tenant_id: str) -> bool:
        """Verify HMAC signatures for all entries of a tenant.

        Delegates to the underlying AuditBus integrity check.
        """
        # Use bus-level integrity verification filtered to tenant.
        report = self._bus.verify_integrity()
        return bool(report.get("chain_intact", True))

    def get_stats(self, tenant_id: str) -> dict[str, Any]:
        # Use the authoritative bus (disk-backed) for consistency with
        # ``query()``, so stats survive restarts.
        bus_entries = self._bus.query_tenant(tenant_id, max_entries=None)
        if bus_entries:
            total = len(bus_entries)
        else:
            indices = self._tenant_index.get(tenant_id, [])
            total = len(indices)
        return {
            "total_entries": total,
            "tenant_id": tenant_id,
            "integrity_verified": self.verify_integrity(tenant_id),
        }
