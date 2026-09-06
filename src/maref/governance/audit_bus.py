"""MAREF AuditBus — unified audit interface over AuditLogger.

The AuditBus is the single point of entry for all audit logging in MAREF:
- Governance decisions (via ``governance/audit.py`` AuditLogger)
- GaaS tenant-scoped decisions (replaces ``gaas/audit_service.py``)
- Recursive evolution (replaces ``recursive/unified_audit.py``)
- Integration-layer MCP audit (replaces ``integration/audit_logger.py``)

Usage::

    from maref.governance.audit_bus import AuditBus, AuditEntry

    bus = AuditBus()
    entry = bus.log("policy_enforced", "agent-01", "deny", "...")
    bus.log_tenant("tenant-abc", "agent-02", "approve", "ok")

    # pub/sub for real-time monitoring
    bus.subscribe("anomaly", my_callback)
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from maref.governance.audit import AuditEntry, AuditLogger

if TYPE_CHECKING:
    from maref.recursive.unified_audit import UnifiedAuditRecord

SubscriberFn = Callable[[AuditEntry], Any]

_WILDCARD = "*"


class AuditBus:
    """Unified audit bus — single entry point for all MAREF audit logging.

    Combines governance :class:`AuditLogger`, GaaS tenant logging,
    and recursive-evolution logging into one interface.
    """

    def __init__(
        self,
        logger: AuditLogger | None = None,
        hmac_key: bytes | str | None = None,
        ed25519_keypair: Any | None = None,
    ) -> None:
        self._logger = logger or AuditLogger(
            hmac_key=hmac_key,
            ed25519_keypair=ed25519_keypair,
        )
        self._subscribers: dict[str, list[SubscriberFn]] = defaultdict(list)

    # ── Core logging ──────────────────────────────────────────────────

    def log(
        self,
        event_type: str,
        actor: str,
        action: str,
        details: str = "",
        metadata: dict[str, Any] | None = None,
        parent_action_id: str = "",
        tenant_id: str = "",
        layer: str = "governance",
        round: int = 0,
    ) -> AuditEntry:
        """Log an audit entry through the unified AuditBus.

        All optional fields default to sensible zero values, making this
        a drop-in replacement for ``AuditLogger.log()``.
        """
        entry = self._logger.log(
            event_type=event_type,
            actor=actor,
            action=action,
            details=details,
            metadata=metadata or {},
            parent_action_id=parent_action_id,
            tenant_id=tenant_id,
            layer=layer,
            round=round,
        )
        self._publish(entry)
        return entry

    def log_decision(
        self,
        actor: str,
        action: str,
        reason: str = "",
        tenant_id: str = "",
        **extra: Any,
    ) -> AuditEntry:
        """Log a governance decision (convenience shortcut)."""
        return self.log(
            event_type="governance_decision",
            actor=actor,
            action=action,
            details=reason,
            tenant_id=tenant_id,
            metadata=extra,
        )

    def log_anomaly(
        self,
        actor: str,
        anomaly_type: str,
        severity: str,
        description: str = "",
        tenant_id: str = "",
    ) -> AuditEntry:
        """Log an anomaly event."""
        return self.log(
            event_type="anomaly_detected",
            actor=actor,
            action="handle_anomaly",
            details=description,
            tenant_id=tenant_id,
            metadata={
                "anomaly_type": anomaly_type,
                "severity": severity,
            },
        )

    def log_tenant(
        self,
        tenant_id: str,
        agent_id: str,
        action: str,
        verdict: str,
        parameters: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Tenant-scoped audit log — replaces ``gaas.audit_service.AuditLogService.log()``.

        Args:
            tenant_id: The tenant scope for this entry.
            agent_id: The agent that performed the action.
            action: The action performed.
            verdict: ALLOW / DENY / ASK (or custom).
            parameters: Action parameters (optional).
            context: Additional context (optional).
        """
        metadata = {
            "action_params": parameters or {},
            "context": context or {},
        }
        return self.log(
            event_type="tenant_governance",
            actor=agent_id,
            action=action,
            details=verdict,
            tenant_id=tenant_id,
            metadata=metadata,
        )

    def log_from_unified(
        self,
        record: UnifiedAuditRecord,
    ) -> AuditEntry:
        """Log from a recursive-evolution ``UnifiedAuditRecord``."""
        return self.log(
            event_type=record.event_type,
            actor=record.source_module,
            action=record.decision,
            details=record.justification,
            tenant_id=record.tenant_id,
            layer=record.layer,
            round=record.round,
            metadata={
                "target_module": record.target_module,
                "outcome": record.outcome,
                "context_refs": record.context_refs,
            },
        )

    # ── Pub/sub ───────────────────────────────────────────────────────

    def subscribe(self, topic: str, callback: SubscriberFn) -> None:
        self._subscribers[topic].append(callback)

    def unsubscribe(self, topic: str, callback: SubscriberFn) -> None:
        try:
            self._subscribers[topic].remove(callback)
        except ValueError:
            pass

    def _publish(self, entry: AuditEntry) -> None:
        for cb in self._subscribers.get(entry.event_type, []):
            cb(entry)
        for cb in self._subscribers.get(_WILDCARD, []):
            cb(entry)

    # ── Query helpers ─────────────────────────────────────────────────

    def query_tenant(
        self,
        tenant_id: str,
        max_entries: int | None = 1000,
    ) -> list[AuditEntry]:
        """Query audit entries scoped to a specific tenant.

        Queries the underlying AuditLogger and filters in-memory.
        For large datasets, prefer a database-backed audit store.
        """
        all_entries = self._logger.read_all(max_entries=None)
        filtered = [e for e in all_entries if getattr(e, "tenant_id", "") == tenant_id]
        return filtered if max_entries is None else filtered[-max_entries:]

    def query_recent(self, n: int = 100) -> list[AuditEntry]:
        return self._logger.read_recent(n)

    def verify_integrity(
        self,
        ed25519_public_key_pem: str | None = None,
    ) -> dict[str, Any]:
        return self._logger.verify_integrity(ed25519_public_key_pem)

    # ── Access to underlying logger ───────────────────────────────────

    @property
    def logger(self) -> AuditLogger:
        return self._logger
