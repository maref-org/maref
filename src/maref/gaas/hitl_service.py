"""GaaS HITL Service — multi-tenant human-in-the-loop approval system.

Wraps the existing HITLRouter with tenant-scoped event isolation.
Each tenant has independent approval queues and history.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HITLStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"
    EXPIRED = "expired"


class HITLTier(str, Enum):
    P0 = "p0"
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"


@dataclass
class HITLEvent:
    """A tenant-scoped HITL event."""

    event_id: str
    tenant_id: str
    agent_id: str
    action: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    tier: HITLTier = HITLTier.P0
    status: HITLStatus = HITLStatus.PENDING
    created_at: float = field(default_factory=time.time)
    resolved_at: float | None = None
    reviewer: str = ""
    reason: str = ""
    auto_approve_seconds: float = 30.0


class HITLService:
    """Multi-tenant HITL approval service.

    Isolates events by tenant_id. Supports auto-approval timeouts.
    """

    def __init__(self) -> None:
        self._events: dict[str, HITLEvent] = {}
        self._tenant_index: dict[str, list[str]] = {}
        self._pending_by_tier: dict[str, dict[HITLTier, list[str]]] = {}

    def request(
        self,
        tenant_id: str,
        agent_id: str,
        action: str,
        description: str,
        parameters: dict[str, Any] | None = None,
        tier: HITLTier = HITLTier.P0,
        auto_approve_seconds: float = 30.0,
    ) -> HITLEvent:
        """Create a new HITL approval request."""
        event = HITLEvent(
            event_id=f"hitl_{uuid.uuid4().hex}",
            tenant_id=tenant_id,
            agent_id=agent_id,
            action=action,
            description=description,
            parameters=parameters or {},
            tier=tier,
            auto_approve_seconds=auto_approve_seconds,
        )
        self._events[event.event_id] = event
        self._tenant_index.setdefault(tenant_id, []).append(event.event_id)
        self._pending_by_tier.setdefault(tenant_id, {}).setdefault(tier, []).append(event.event_id)
        return event

    def approve(self, tenant_id: str, event_id: str, reviewer: str = "human") -> HITLStatus:
        """Approve a pending event."""
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

    def reject(self, tenant_id: str, event_id: str, reason: str = "") -> HITLStatus:
        """Reject a pending event."""
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

    def get_pending(
        self,
        tenant_id: str,
        tier: HITLTier | None = None,
    ) -> list[HITLEvent]:
        """Get pending events for a tenant, optionally filtered by tier."""
        event_ids = self._tenant_index.get(tenant_id, [])
        events = [
            self._events[eid] for eid in event_ids if self._events[eid].status == HITLStatus.PENDING
        ]
        if tier:
            events = [e for e in events if e.tier == tier]
        return events

    def get_history(
        self,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[HITLEvent]:
        """Get resolved events for a tenant."""
        event_ids = self._tenant_index.get(tenant_id, [])
        resolved = [
            self._events[eid] for eid in event_ids if self._events[eid].status != HITLStatus.PENDING
        ]
        resolved.sort(key=lambda e: e.created_at, reverse=True)
        return resolved[offset : offset + limit]

    def process_auto_approvals(self) -> list[str]:
        """Auto-approve expired events. Returns list of auto-approved event IDs."""
        now = time.time()
        auto_approved: list[str] = []
        for event in list(self._events.values()):
            if event.status == HITLStatus.PENDING:
                elapsed = now - event.created_at
                if elapsed >= event.auto_approve_seconds:
                    event.status = HITLStatus.AUTO_APPROVED
                    event.resolved_at = now
                    event.reviewer = "auto"
                    self._remove_from_pending(event)
                    auto_approved.append(event.event_id)
        return auto_approved

    def _remove_from_pending(self, event: HITLEvent) -> None:
        tenant_pending = self._pending_by_tier.get(event.tenant_id, {})
        tier_list = tenant_pending.get(event.tier, [])
        if event.event_id in tier_list:
            tier_list.remove(event.event_id)

    def get_stats(self, tenant_id: str) -> dict[str, Any]:
        event_ids = self._tenant_index.get(tenant_id, [])
        pending = sum(1 for eid in event_ids if self._events[eid].status == HITLStatus.PENDING)
        approved = sum(1 for eid in event_ids if self._events[eid].status == HITLStatus.APPROVED)
        rejected = sum(1 for eid in event_ids if self._events[eid].status == HITLStatus.REJECTED)
        auto_approved = sum(
            1 for eid in event_ids if self._events[eid].status == HITLStatus.AUTO_APPROVED
        )
        return {
            "tenant_id": tenant_id,
            "total_events": len(event_ids),
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "auto_approved": auto_approved,
        }
