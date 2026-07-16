"""MAREF ↔ HITL (Human-in-the-Loop) Approval Bridge

M6.3: Maps MAREF anomaly severities to Athena's HITL approval tiers.
Every anomaly flows through a configurable routing decision:

Mapping:
  anomaly.critical → P0_RESPONSE (synchronous, blocking)
  anomaly.warning  → P1_ESCALATE (30s auto-approve if no human response)
  anomaly.info     → P2_LOG (passive, audit-only)
  finding          → P3_OBSERVE (to knowledge graph, no action)

This is the UNIFIED HITL implementation for both GaaS and MCP governance paths.
HITL was previously duplicated in gaas/hitl_service.py — all functionality
has been merged here. See governance_router.py for GaaS integration.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HITLTier(Enum):
    P0_RESPONSE = "p0_response"
    P1_ESCALATE = "p1_escalate"
    P2_LOG = "p2_log"
    P3_OBSERVE = "p3_observe"


class HITLStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"
    EXPIRED = "expired"


@dataclass
class HITLEvent:
    event_id: str
    tier: HITLTier
    severity: str
    anomaly_type: str
    description: str
    tenant_id: str = ""
    agent_id: str = ""
    action: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    status: HITLStatus = HITLStatus.PENDING
    auto_approve_seconds: float = 0.0
    resolved_at: float | None = None
    reviewer: str = ""
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "tier": self.tier.value,
            "severity": self.severity,
            "anomaly_type": self.anomaly_type,
            "description": self.description,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "action": self.action,
            "parameters": dict(self.parameters),
            "timestamp": self.timestamp,
            "status": self.status.value,
            "auto_approve_seconds": self.auto_approve_seconds,
            "resolved_at": self.resolved_at,
            "reviewer": self.reviewer,
            "reason": self.reason,
            "metadata": self.metadata,
        }


class HITLRouter:
    """
    Routes MAREF anomalies to HITL approval tiers.

    Supports both anomaly-severity routing (integration/observe path)
    and GaaS tenant-scoped approval (gaas governance path).

    Default tier mapping:
    - critical → P0 (synchronous block, requires human)
    - warning  → P1 (30s auto-approve window)
    - info     → P2 (log only, no human interaction)
    - normal   → P3 (observe only, to knowledge graph)
    """

    DEFAULT_TIER_MAP: dict[str, HITLTier] = {
        "critical": HITLTier.P0_RESPONSE,
        "warning": HITLTier.P1_ESCALATE,
        "info": HITLTier.P2_LOG,
        "normal": HITLTier.P3_OBSERVE,
    }

    DEFAULT_AUTO_APPROVE: dict[HITLTier, float] = {
        HITLTier.P0_RESPONSE: 0.0,
        HITLTier.P1_ESCALATE: 30.0,
        HITLTier.P2_LOG: 0.0,
        HITLTier.P3_OBSERVE: 0.0,
    }

    def __init__(
        self,
        tier_map: dict[str, HITLTier] | None = None,
        auto_approve_seconds: dict[HITLTier, float] | None = None,
        event_counter: int = 0,
    ) -> None:
        self._tier_map = tier_map or dict(self.DEFAULT_TIER_MAP)
        self._auto_approve = auto_approve_seconds or dict(self.DEFAULT_AUTO_APPROVE)
        self._event_counter = event_counter
        self._events: dict[str, HITLEvent] = {}
        # GaaS tenant-scoped index: tenant_id -> [event_id, ...]
        self._tenant_index: dict[str, list[str]] = {}
        # GaaS pending-by-tier index: tenant_id -> {tier -> [event_id, ...]}
        self._pending_by_tier: dict[str, dict[HITLTier, list[str]]] = {}

    # ------------------------------------------------------------------
    # Create / route
    # ------------------------------------------------------------------

    def route(self, severity: str, anomaly_type: str, description: str, **meta: Any) -> HITLEvent:
        """Route an anomaly event to the appropriate HITL tier (integration path)."""
        tier = self._tier_map.get(severity, HITLTier.P2_LOG)
        auto_sec = self._auto_approve.get(tier, 0.0)

        self._event_counter += 1
        event = HITLEvent(
            event_id=f"hitl-{self._event_counter:06d}",
            tier=tier,
            severity=severity,
            anomaly_type=anomaly_type,
            description=description,
            auto_approve_seconds=auto_sec,
            metadata=meta,
        )
        self._events[event.event_id] = event
        return event

    def request(
        self,
        tenant_id: str,
        agent_id: str,
        action: str,
        description: str,
        parameters: dict[str, Any] | None = None,
        tier: HITLTier = HITLTier.P0_RESPONSE,
        auto_approve_seconds: float = 30.0,
    ) -> HITLEvent:
        """Create a new HITL approval request (GaaS path)."""
        event = HITLEvent(
            event_id=f"hitl_{uuid.uuid4().hex}",
            tier=tier,
            severity="",
            anomaly_type="governance",
            description=description,
            tenant_id=tenant_id,
            agent_id=agent_id,
            action=action,
            parameters=parameters or {},
            auto_approve_seconds=auto_approve_seconds,
        )
        self._events[event.event_id] = event
        self._tenant_index.setdefault(tenant_id, []).append(event.event_id)
        self._pending_by_tier.setdefault(tenant_id, {}).setdefault(tier, []).append(event.event_id)
        return event

    # ------------------------------------------------------------------
    # Approve / reject
    # ------------------------------------------------------------------

    def approve(self, event_id: str, reviewer: str = "human") -> HITLStatus:
        event = self._events.get(event_id)
        if not event or event.status != HITLStatus.PENDING:
            return HITLStatus.PENDING if not event else event.status
        event.status = HITLStatus.APPROVED
        event.resolved_at = time.time()
        event.reviewer = reviewer
        self._remove_from_pending(event)
        return event.status

    def gaas_approve(self, tenant_id: str, event_id: str, reviewer: str = "human") -> HITLStatus:
        """Approve a pending event with tenant-id verification (GaaS path)."""
        event = self._events.get(event_id)
        if not event or event.tenant_id != tenant_id:
            return HITLStatus.REJECTED
        if event.status != HITLStatus.PENDING:
            return event.status
        event.status = HITLStatus.APPROVED
        event.resolved_at = time.time()
        event.reviewer = reviewer
        self._remove_from_pending(event)
        return event.status

    def reject(self, event_id: str, reason: str = "") -> HITLStatus:
        event = self._events.get(event_id)
        if not event or event.status != HITLStatus.PENDING:
            return HITLStatus.PENDING if not event else event.status
        event.status = HITLStatus.REJECTED
        event.resolved_at = time.time()
        event.reason = reason
        event.metadata["reject_reason"] = reason
        self._remove_from_pending(event)
        return event.status

    def gaas_reject(self, tenant_id: str, event_id: str, reason: str = "") -> HITLStatus:
        """Reject a pending event with tenant-id verification (GaaS path)."""
        event = self._events.get(event_id)
        if not event or event.tenant_id != tenant_id:
            return HITLStatus.REJECTED
        if event.status != HITLStatus.PENDING:
            return event.status
        event.status = HITLStatus.REJECTED
        event.resolved_at = time.time()
        event.reason = reason
        self._remove_from_pending(event)
        return event.status

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def is_blocking(self, tier: HITLTier) -> bool:
        return tier == HITLTier.P0_RESPONSE

    def can_auto_approve(self, event: HITLEvent) -> bool:
        return event.tier in (
            HITLTier.P1_ESCALATE,
            HITLTier.P2_LOG,
            HITLTier.P3_OBSERVE,
        )

    def check_timeout(self, event: HITLEvent) -> bool:
        if event.auto_approve_seconds <= 0:
            return False
        elapsed = time.time() - event.timestamp
        return elapsed >= event.auto_approve_seconds

    def get_pending(self, tier: HITLTier | None = None) -> list[HITLEvent]:
        result = [e for e in self._events.values() if e.status == HITLStatus.PENDING]
        if tier:
            result = [e for e in result if e.tier == tier]
        return result

    def get_tenant_pending(
        self,
        tenant_id: str,
        tier: HITLTier | None = None,
    ) -> list[HITLEvent]:
        """Get pending events for a tenant, optionally filtered by tier (GaaS path)."""
        event_ids = self._tenant_index.get(tenant_id, [])
        events = [
            self._events[eid] for eid in event_ids
            if self._events[eid].status == HITLStatus.PENDING
        ]
        if tier:
            events = [e for e in events if e.tier == tier]
        return events

    def get_history(self, limit: int = 50, offset: int = 0) -> list[HITLEvent]:
        completed = [
            e for e in self._events.values()
            if e.status in (
                HITLStatus.APPROVED,
                HITLStatus.REJECTED,
                HITLStatus.AUTO_APPROVED,
                HITLStatus.EXPIRED,
            )
        ]
        return completed[offset : offset + limit]

    def get_tenant_history(
        self,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[HITLEvent]:
        """Get resolved events for a tenant (GaaS path)."""
        event_ids = self._tenant_index.get(tenant_id, [])
        resolved = [
            self._events[eid] for eid in event_ids
            if self._events[eid].status != HITLStatus.PENDING
        ]
        resolved.sort(key=lambda e: e.timestamp, reverse=True)
        return resolved[offset : offset + limit]

    def get_all(self) -> list[HITLEvent]:
        return list(self._events.values())

    # ------------------------------------------------------------------
    # Auto-approval processing
    # ------------------------------------------------------------------

    def process_auto_approvals(self) -> list[str]:
        """Auto-approve expired events. Returns list of auto-approved event IDs."""
        now = time.time()
        auto_approved: list[str] = []
        for event in list(self._events.values()):
            if event.status == HITLStatus.PENDING and event.auto_approve_seconds >= 0:
                elapsed = now - event.timestamp
                if elapsed >= event.auto_approve_seconds:
                    event.status = HITLStatus.AUTO_APPROVED
                    event.resolved_at = now
                    event.reviewer = "auto"
                    self._remove_from_pending(event)
                    auto_approved.append(event.event_id)
        return auto_approved

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self, tenant_id: str | None = None) -> dict[str, Any]:
        if tenant_id:
            event_ids = self._tenant_index.get(tenant_id, [])
            events = [self._events[eid] for eid in event_ids if eid in self._events]
            prefix = f"tenant_{tenant_id}_"
        else:
            events = list(self._events.values())
            prefix = ""

        tier_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        for event in events:
            t = event.tier.value
            tier_counts[t] = tier_counts.get(t, 0) + 1
            s = event.status.value
            status_counts[s] = status_counts.get(s, 0) + 1

        return {
            f"{prefix}total_events": len(events),
            f"{prefix}pending_count": sum(1 for e in events if e.status == HITLStatus.PENDING),
            f"{prefix}approved_count": sum(1 for e in events if e.status == HITLStatus.APPROVED),
            f"{prefix}rejected_count": sum(1 for e in events if e.status == HITLStatus.REJECTED),
            f"{prefix}auto_approved_count": sum(
                1 for e in events if e.status == HITLStatus.AUTO_APPROVED
            ),
            f"{prefix}by_tier": tier_counts,
            f"{prefix}by_status": status_counts,
        }

    def update_tier_mapping(self, severity: str, tier: HITLTier) -> None:
        self._tier_map[severity] = tier

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _remove_from_pending(self, event: HITLEvent) -> None:
        """Remove event from all pending indexes."""
        if event.tenant_id:
            tenant_pending = self._pending_by_tier.get(event.tenant_id, {})
            tier_list = tenant_pending.get(event.tier, [])
            if event.event_id in tier_list:
                tier_list.remove(event.event_id)
