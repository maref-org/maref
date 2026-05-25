"""Human Decision API — standard interface for human-agent collaboration decisions.

Design principles:
- Sync blocking (wait for human button click) and async callback (Slack/WeChat reply)
- Timeout with default policies: high urgency auto-escalates, low urgency suspends
- Batch confirmation and intelligent aggregation to avoid "popup hell"
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class DecisionMode(Enum):
    """How the human receives and responds to the decision request."""

    SYNC = "sync"          # Block until human clicks a button
    ASYNC = "async"        # Human replies via Slack/WeChat/email callback


class UrgencyLevel(Enum):
    """Urgency determines timeout default policy."""

    LOW = "low"            # Timeout → suspend, wait indefinitely
    MEDIUM = "medium"      # Timeout → escalate to higher authority
    HIGH = "high"          # Timeout → auto-delegate to fallback agent


class DecisionStatus(Enum):
    """Lifecycle of a decision request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    TIMEOUT = "timeout"
    BATCHED = "batched"    # Merged into a batch confirmation


@dataclass
class DecisionContext:
    """Rich context for human to make an informed decision."""

    task_id: str
    agent_id: str
    action_description: str
    risk_score: float = 0.0          # 0.0-1.0, auto-calculated
    data_classification: str = ""     # PII, PUBLIC, INTERNAL, etc.
    estimated_cost: float = 0.0
    affected_resources: list[str] = field(default_factory=list)
    historical_precedent: str = ""    # "Similar action approved 3 times last week"


@dataclass
class DecisionRequest:
    """Standardized request for human decision."""

    task_id: str
    context: DecisionContext
    options: list[str] = field(default_factory=lambda: ["approve", "reject", "escalate"])
    timeout: float = 300.0            # seconds
    urgency: UrgencyLevel = UrgencyLevel.MEDIUM
    mode: DecisionMode = DecisionMode.SYNC
    batch_key: str | None = None      # For batch confirmation grouping
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "task_id": self.task_id,
            "options": self.options,
            "timeout": self.timeout,
            "urgency": self.urgency.value,
            "mode": self.mode.value,
            "batch_key": self.batch_key,
            "created_at": self.created_at,
            "context": {
                "task_id": self.context.task_id,
                "agent_id": self.context.agent_id,
                "action_description": self.context.action_description,
                "risk_score": self.context.risk_score,
                "data_classification": self.context.data_classification,
                "estimated_cost": self.context.estimated_cost,
                "affected_resources": self.context.affected_resources,
                "historical_precedent": self.context.historical_precedent,
            },
        }


@dataclass
class DecisionResponse:
    """Human's response to a decision request."""

    request_id: str
    decision: str                     # One of the options from the request
    reason: str = ""                  # Human's free-text explanation
    responded_by: str = ""            # User ID of the responder
    responded_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "decision": self.decision,
            "reason": self.reason,
            "responded_by": self.responded_by,
            "responded_at": self.responded_at,
        }


# Callback types
DecisionCallback = Callable[[DecisionResponse], None]
BatchFilter = Callable[[DecisionRequest], bool]


class HumanDecisionAPI:
    """Central API for all human-agent collaboration decisions.

    Usage:
        api = HumanDecisionAPI()
        req = DecisionRequest(
            task_id="transfer-001",
            context=DecisionContext(...),
            urgency=UrgencyLevel.HIGH,
            mode=DecisionMode.SYNC,
        )
        resp = api.request_decision(req)
        if resp.decision == "approve":
            proceed()
    """

    DEFAULT_TIMEOUT = 300.0
    HIGH_URGENCY_TIMEOUT = 60.0
    LOW_URGENCY_TIMEOUT = 3600.0

    def __init__(self) -> None:
        self._pending: dict[str, DecisionRequest] = {}
        self._responses: dict[str, DecisionResponse] = {}
        self._callbacks: dict[str, DecisionCallback] = {}
        self._batch_queues: dict[str, list[DecisionRequest]] = {}
        self._batch_filters: list[BatchFilter] = []

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def request_decision(self, request: DecisionRequest, callback: DecisionCallback | None = None) -> DecisionResponse | None:
        """Request a human decision.

        SYNC mode: blocks until human responds or timeout.
        ASYNC mode: returns None immediately, callback invoked later.
        """
        # Auto-adjust timeout by urgency
        if request.timeout == self.DEFAULT_TIMEOUT:
            request.timeout = self._default_timeout(request.urgency)

        # Batch detection
        batch_key = self._detect_batch(request)
        if batch_key:
            request.batch_key = batch_key
            self._batch_queues.setdefault(batch_key, []).append(request)
            # If batch threshold reached, flush
            if len(self._batch_queues[batch_key]) >= 5:
                return self._flush_batch(batch_key)
            # Otherwise return batched status
            return DecisionResponse(
                request_id=request.request_id,
                decision="batched",
                reason=f"Queued in batch '{batch_key}'",
            )

        self._pending[request.request_id] = request
        if callback:
            self._callbacks[request.request_id] = callback

        if request.mode == DecisionMode.ASYNC:
            return None

        # SYNC mode: poll with timeout
        return self._poll_sync(request)

    def submit_response(self, response: DecisionResponse) -> None:
        """Submit a human response (called by GUI/Slack/WeChat adapters)."""
        self._responses[response.request_id] = response
        if response.request_id in self._callbacks:
            self._callbacks[response.request_id](response)
            del self._callbacks[response.request_id]
        if response.request_id in self._pending:
            del self._pending[response.request_id]

    def get_pending(self) -> list[DecisionRequest]:
        """List all pending decision requests."""
        return list(self._pending.values())

    def get_batch_queue(self, batch_key: str) -> list[DecisionRequest]:
        """Get all requests in a batch queue."""
        return list(self._batch_queues.get(batch_key, []))

    def flush_batch(self, batch_key: str) -> DecisionResponse:
        """Force flush a batch for human confirmation."""
        return self._flush_batch(batch_key)

    # ------------------------------------------------------------------ #
    # Timeout policies
    # ------------------------------------------------------------------ #
    def _default_timeout(self, urgency: UrgencyLevel) -> float:
        return {
            UrgencyLevel.LOW: self.LOW_URGENCY_TIMEOUT,
            UrgencyLevel.MEDIUM: self.DEFAULT_TIMEOUT,
            UrgencyLevel.HIGH: self.HIGH_URGENCY_TIMEOUT,
        }[urgency]

    def _on_timeout(self, request: DecisionRequest) -> DecisionResponse:
        """Generate default response on timeout based on urgency."""
        if request.urgency == UrgencyLevel.HIGH:
            return DecisionResponse(
                request_id=request.request_id,
                decision="escalated",
                reason="Timeout: high urgency auto-escalated to fallback agent",
            )
        if request.urgency == UrgencyLevel.LOW:
            return DecisionResponse(
                request_id=request.request_id,
                decision="suspended",
                reason="Timeout: low urgency task suspended indefinitely",
            )
        return DecisionResponse(
            request_id=request.request_id,
            decision="escalated",
            reason="Timeout: medium urgency escalated to supervisor",
        )

    # ------------------------------------------------------------------ #
    # Batch confirmation (anti popup-hell)
    # ------------------------------------------------------------------ #
    def register_batch_filter(self, filter_fn: BatchFilter) -> None:
        """Register a filter to group similar requests into batches."""
        self._batch_filters.append(filter_fn)

    def _detect_batch(self, request: DecisionRequest) -> str | None:
        """Detect if request should be batched. Returns batch key or None."""
        for filter_fn in self._batch_filters:
            if filter_fn(request):
                # Use a simple grouping key based on agent + action type
                return f"{request.context.agent_id}:{request.context.action_description.split()[0]}"
        return None

    def _flush_batch(self, batch_key: str) -> DecisionResponse:
        """Flush a batch: present all queued requests as a single decision."""
        queue = self._batch_queues.get(batch_key, [])
        if not queue:
            return DecisionResponse(
                request_id="batch_empty",
                decision="approved",
                reason="Batch queue empty",
            )
        # Clear the queue
        del self._batch_queues[batch_key]
        # Return a batch decision (in production, this would present a UI)
        return DecisionResponse(
            request_id=f"batch:{batch_key}",
            decision="batch_approved",
            reason=f"Batch approved: {len(queue)} requests",
        )

    # ------------------------------------------------------------------ #
    # SYNC polling
    # ------------------------------------------------------------------ #
    def _poll_sync(self, request: DecisionRequest) -> DecisionResponse:
        """Poll for response with timeout. Production: use condition variable."""
        deadline = time.time() + request.timeout
        while time.time() < deadline:
            if request.request_id in self._responses:
                return self._responses.pop(request.request_id)
            time.sleep(0.1)
        # Timeout
        return self._on_timeout(request)
