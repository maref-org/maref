"""MAREF Cross-Organization HITL (Human-in-the-Loop)

Routes human approval requests across organizational boundaries.
When a task in org A requires review by someone in org B (e.g., because
org B's data is involved, or the action affects org B's agents), the
cross-org HITL engine manages the approval lifecycle with timeout and
escalation support.

Extends the tenant-scoped :class:`maref.integration.hitl.HITLRouter`
pattern to the federation layer, where the requester and reviewer may
belong to different organisations.

References:
    - Plan §7 Phase 3: CrossOrgHITL ``hitl.py``
    - Plan §4.2 workflow step 11: 联邦审计链记录
    - Existing pattern: :mod:`maref.integration.hitl`
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CrossOrgApprovalStatus(str, Enum):
    """Lifecycle status of a cross-org approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    ESCALATED = "escalated"


@dataclass
class CrossOrgApprovalRequest:
    """A cross-organization human approval request.

    ``requesting_org`` is the org that needs approval; ``reviewing_org``
    is the org that must approve.  If the request times out, it is
    escalated to ``escalation_org`` (if set).
    """

    request_id: str
    action: str
    description: str
    requesting_org: str
    reviewing_org: str
    agent_did: str
    task_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    status: CrossOrgApprovalStatus = CrossOrgApprovalStatus.PENDING
    created_at: float = field(default_factory=time.time)
    resolved_at: float | None = None
    reviewer: str = ""
    reason: str = ""
    timeout_seconds: float = 300.0  # 5 min default
    escalation_org: str | None = None
    escalated_to: str | None = None
    # Timestamp when the request was escalated to escalation_org. Set on
    # escalation; ``created_at`` remains immutable for audit-trail integrity.
    escalated_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action": self.action,
            "description": self.description,
            "requesting_org": self.requesting_org,
            "reviewing_org": self.reviewing_org,
            "agent_did": self.agent_did,
            "task_id": self.task_id,
            "parameters": dict(self.parameters),
            "status": self.status.value,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "reviewer": self.reviewer,
            "reason": self.reason,
            "timeout_seconds": self.timeout_seconds,
            "escalation_org": self.escalation_org,
            "escalated_to": self.escalated_to,
            "escalated_at": self.escalated_at,
        }

    @property
    def is_resolved(self) -> bool:
        return self.status in (
            CrossOrgApprovalStatus.APPROVED,
            CrossOrgApprovalStatus.REJECTED,
            CrossOrgApprovalStatus.EXPIRED,
        )

    @property
    def is_pending(self) -> bool:
        return self.status in (
            CrossOrgApprovalStatus.PENDING,
            CrossOrgApprovalStatus.ESCALATED,
        )


class CrossOrgHITL:
    """Cross-organization human-in-the-loop approval engine.

    Manages approval requests where the requesting and reviewing
    parties belong to different organisations.  Supports timeout-based
    escalation to a designated third org.
    """

    def __init__(self) -> None:
        self._requests: dict[str, CrossOrgApprovalRequest] = {}
        # Index: reviewing_org -> {request_id} for pending lookups.
        self._pending_by_org: dict[str, set[str]] = {}
        # Index: requesting_org -> {request_id} for history lookups.
        self._by_requesting_org: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # Request lifecycle
    # ------------------------------------------------------------------

    def request_approval(
        self,
        action: str,
        description: str,
        requesting_org: str,
        reviewing_org: str,
        agent_did: str,
        task_id: str,
        parameters: dict[str, Any] | None = None,
        timeout_seconds: float = 300.0,
        escalation_org: str | None = None,
    ) -> CrossOrgApprovalRequest:
        """Create a new cross-org approval request.

        If ``reviewing_org`` equals ``requesting_org``, the request is
        auto-approved (it's an intra-org approval, not cross-org).
        """
        request = CrossOrgApprovalRequest(
            request_id=f"xhitl_{uuid.uuid4().hex}",
            action=action,
            description=description,
            requesting_org=requesting_org,
            reviewing_org=reviewing_org,
            agent_did=agent_did,
            task_id=task_id,
            parameters=parameters or {},
            timeout_seconds=timeout_seconds,
            escalation_org=escalation_org,
        )

        # Intra-org requests are auto-approved.
        if requesting_org == reviewing_org:
            request.status = CrossOrgApprovalStatus.APPROVED
            request.resolved_at = time.time()
            request.reviewer = "auto"
        else:
            self._pending_by_org.setdefault(reviewing_org, set()).add(request.request_id)

        self._requests[request.request_id] = request
        self._by_requesting_org.setdefault(requesting_org, []).append(request.request_id)
        return request

    def approve(
        self, request_id: str, reviewer: str = "human"
    ) -> bool:
        """Approve a pending or escalated request."""
        request = self._requests.get(request_id)
        if request is None or not request.is_pending:
            return False
        request.status = CrossOrgApprovalStatus.APPROVED
        request.resolved_at = time.time()
        request.reviewer = reviewer
        self._remove_from_pending(request)
        return True

    def reject(
        self, request_id: str, reason: str = ""
    ) -> bool:
        """Reject a pending or escalated request."""
        request = self._requests.get(request_id)
        if request is None or not request.is_pending:
            return False
        request.status = CrossOrgApprovalStatus.REJECTED
        request.resolved_at = time.time()
        request.reason = reason
        self._remove_from_pending(request)
        return True

    # ------------------------------------------------------------------
    # Timeout & escalation
    # ------------------------------------------------------------------

    def process_timeouts(self, now: float | None = None) -> list[str]:
        """Expire or escalate timed-out requests.

        If ``escalation_org`` is set, the request is escalated (re-routed
        to the escalation org).  Otherwise, it is marked as expired.

        Returns the list of request IDs that were escalated or expired.
        """
        current = now if now is not None else time.time()
        affected: list[str] = []

        for request in list(self._requests.values()):
            if not request.is_pending:
                continue
            # Use escalated_at as the clock base once escalated, so the
            # escalation org gets the full timeout window. created_at is
            # immutable and preserves the original submission time.
            clock_base = request.escalated_at if request.escalated_at is not None else request.created_at
            elapsed = current - clock_base
            if elapsed < request.timeout_seconds:
                continue

            if request.escalation_org is not None and request.status == CrossOrgApprovalStatus.PENDING:
                # Escalate: re-route to escalation org.
                self._remove_from_pending(request)
                request.status = CrossOrgApprovalStatus.ESCALATED
                request.escalated_to = request.escalation_org
                self._pending_by_org.setdefault(request.escalation_org, set()).add(
                    request.request_id
                )
                # Start a fresh timeout window for the escalation org.
                request.escalated_at = current
                affected.append(request.request_id)
            elif request.status == CrossOrgApprovalStatus.ESCALATED:
                # Already escalated and timed out again → expire.
                request.status = CrossOrgApprovalStatus.EXPIRED
                request.resolved_at = current
                self._remove_from_pending(request)
                affected.append(request.request_id)
            else:
                # No escalation org → expire directly.
                request.status = CrossOrgApprovalStatus.EXPIRED
                request.resolved_at = current
                self._remove_from_pending(request)
                affected.append(request.request_id)

        return affected

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_request(self, request_id: str) -> CrossOrgApprovalRequest | None:
        return self._requests.get(request_id)

    def get_pending(
        self, reviewing_org: str | None = None
    ) -> list[CrossOrgApprovalRequest]:
        """Get pending (and escalated) requests.

        If ``reviewing_org`` is given, only requests routed to that org
        (including escalations) are returned.
        """
        if reviewing_org is not None:
            ids = self._pending_by_org.get(reviewing_org, set())
            return [self._requests[i] for i in ids if self._requests[i].is_pending]

        return [
            r for r in self._requests.values() if r.is_pending
        ]

    def get_history(
        self,
        org: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CrossOrgApprovalRequest]:
        """Get resolved requests, optionally filtered by org.

        ``org`` matches either requesting_org or reviewing_org.
        """
        if org is not None:
            requests = [
                r for r in self._requests.values()
                if r.requesting_org == org or r.reviewing_org == org
            ]
        else:
            requests = list(self._requests.values())
        resolved = [r for r in requests if r.is_resolved]
        resolved.sort(key=lambda r: r.created_at, reverse=True)
        return resolved[offset : offset + limit]

    def get_pending_count(self, reviewing_org: str | None = None) -> int:
        return len(self.get_pending(reviewing_org))

    @property
    def request_count(self) -> int:
        return len(self._requests)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def hitl_summary(self) -> dict[str, Any]:
        """Return a global summary of the cross-org HITL engine."""
        requests = list(self._requests.values())
        status_counts: dict[str, int] = {}
        for r in requests:
            status_counts[r.status.value] = status_counts.get(r.status.value, 0) + 1

        orgs = set()
        for r in requests:
            orgs.add(r.requesting_org)
            orgs.add(r.reviewing_org)

        return {
            "total_requests": len(requests),
            "status_counts": status_counts,
            "total_orgs": len(orgs),
            "pending_count": sum(
                1 for r in requests if r.is_pending
            ),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _remove_from_pending(self, request: CrossOrgApprovalRequest) -> None:
        """Remove a request from all pending indexes."""
        # Remove from the original reviewing_org's pending set.
        original = self._pending_by_org.get(request.reviewing_org, set())
        original.discard(request.request_id)
        # Remove from escalation_org's pending set if escalated.
        if request.escalated_to is not None:
            escalated = self._pending_by_org.get(request.escalated_to, set())
            escalated.discard(request.request_id)
