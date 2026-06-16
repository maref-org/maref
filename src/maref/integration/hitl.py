"""
MAREF ↔ HITL (Human-in-the-Loop) Approval Bridge

M6.3: Maps MAREF anomaly severities to Athena's HITL approval tiers.
Every anomaly flows through a configurable routing decision:

Mapping:
  anomaly.critical → P0_RESPONSE (synchronous, blocking)
  anomaly.warning  → P1_ESCALATE (30s auto-approve if no human response)
  anomaly.info     → P2_LOG (passive, audit-only)
  finding          → P3_OBSERVE (to knowledge graph, no action)
"""

from __future__ import annotations

import time
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
    timestamp: float = field(default_factory=time.time)
    status: HITLStatus = HITLStatus.PENDING
    auto_approve_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "tier": self.tier.value,
            "severity": self.severity,
            "anomaly_type": self.anomaly_type,
            "description": self.description,
            "timestamp": self.timestamp,
            "status": self.status.value,
            "auto_approve_seconds": self.auto_approve_seconds,
            "metadata": self.metadata,
        }


class HITLRouter:
    """
    Routes MAREF anomalies to HITL approval tiers.

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
        self._events: list[HITLEvent] = []

    def route(self, severity: str, anomaly_type: str, description: str, **meta: Any) -> HITLEvent:
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
        self._events.append(event)
        return event

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

    def approve(self, event_id: str, reviewer: str = "human") -> HITLStatus:
        for event in self._events:
            if event.event_id == event_id:
                event.status = HITLStatus.APPROVED
                return event.status
        return HITLStatus.PENDING

    def reject(self, event_id: str, reason: str = "") -> HITLStatus:
        for event in self._events:
            if event.event_id == event_id:
                event.status = HITLStatus.REJECTED
                event.metadata["reject_reason"] = reason
                return event.status
        return HITLStatus.PENDING

    def get_pending(self, tier: HITLTier | None = None) -> list[HITLEvent]:
        result = [e for e in self._events if e.status == HITLStatus.PENDING]
        if tier:
            result = [e for e in result if e.tier == tier]
        return result

    def get_history(self, limit: int = 50, offset: int = 0) -> list[HITLEvent]:
        completed = [
            e
            for e in self._events
            if e.status
            in (
                HITLStatus.APPROVED,
                HITLStatus.REJECTED,
                HITLStatus.AUTO_APPROVED,
                HITLStatus.EXPIRED,
            )
        ]
        return completed[offset : offset + limit]

    def get_all(self) -> list[HITLEvent]:
        return list(self._events)

    def get_stats(self) -> dict[str, Any]:
        tier_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        for event in self._events:
            t = event.tier.value
            tier_counts[t] = tier_counts.get(t, 0) + 1
            s = event.status.value
            status_counts[s] = status_counts.get(s, 0) + 1

        return {
            "total_events": len(self._events),
            "pending_count": len(self.get_pending()),
            "by_tier": tier_counts,
            "by_status": status_counts,
            "tier_map": {k: v.value for k, v in self._tier_map.items()},
        }

    def update_tier_mapping(self, severity: str, tier: HITLTier) -> None:
        self._tier_map[severity] = tier
