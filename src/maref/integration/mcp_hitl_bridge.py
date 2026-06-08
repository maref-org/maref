#!/usr/bin/env python3
"""mcp_hitl_bridge.py — MCP Security Gate ↔ HITL Approval Bridge

Connects the MCP security gate's HITL requests with the existing HITLRouter
and HITL API infrastructure. Provides:

1. Automatic HITL event creation when MCP calls require human approval
2. Approval/denial propagation back to the security gate
3. Timeout handling with auto-approve/deny based on policy
4. REST API endpoints for MCP-specific HITL operations
5. Integration with the existing HITLView GUI component

Usage:
    from maref.integration.mcp_hitl_bridge import MCPHITLBridge
    bridge = MCPHITLBridge()

    # When security gate returns AUDIT:
    hitl_event = bridge.create_approval_request(
        agent_id="trae",
        mcp_server="mcp_GitHub",
        tool_name="create_issue",
        args={"title": "Bug report"}
    )

    # Human approves via API or GUI:
    bridge.approve(hitl_event.event_id)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from maref.integration.hitl import HITLRouter, HITLStatus, HITLTier

logger = logging.getLogger(__name__)


@dataclass
class MCPApprovalRequest:
    """An MCP-specific approval request that wraps a HITL event."""
    request_id: str
    hitl_event_id: str
    agent_id: str
    mcp_server: str
    tool_name: str
    args: dict[str, Any]
    risk_score: float
    tier: HITLTier
    created_at: float = field(default_factory=time.time)
    status: str = "pending"  # pending, approved, denied, timeout
    approved_by: str | None = None
    approved_at: float | None = None
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "hitl_event_id": self.hitl_event_id,
            "agent_id": self.agent_id,
            "mcp_server": self.mcp_server,
            "tool_name": self.tool_name,
            "args": self.args,
            "risk_score": self.risk_score,
            "tier": self.tier.value,
            "created_at": self.created_at,
            "status": self.status,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "rejection_reason": self.rejection_reason,
        }


class MCPHITLBridge:
    """Bridge between MCP Security Gate and HITL approval system.

    Responsibilities:
    - Create HITL events for MCP calls requiring approval
    - Map MCP risk scores to HITL tiers
    - Propagate approval/denial decisions
    - Handle timeouts based on HITL policy configuration
    - Provide query interface for pending/approved/denied requests
    """

    # Default timeout configuration (seconds)
    DEFAULT_TIMEOUTS = {
        HITLTier.P0_RESPONSE: 300,  # 5 minutes for critical
        HITLTier.P1_ESCALATE: 30,   # 30 seconds for warnings
        HITLTier.P2_LOG: 0,         # No timeout for log-only
        HITLTier.P3_OBSERVE: 0,     # No timeout for observe-only
    }

    # Auto-approve on timeout (true for P1, false for P0)
    DEFAULT_AUTO_APPROVE_ON_TIMEOUT = {
        HITLTier.P0_RESPONSE: False,
        HITLTier.P1_ESCALATE: True,
        HITLTier.P2_LOG: True,
        HITLTier.P3_OBSERVE: True,
    }

    def __init__(
        self,
        hitl_router: HITLRouter | None = None,
        timeouts: dict[HITLTier, float] | None = None,
        auto_approve_on_timeout: dict[HITLTier, bool] | None = None,
    ):
        self.hitl_router = hitl_router or HITLRouter()
        self.timeouts = timeouts or dict(self.DEFAULT_TIMEOUTS)
        self.auto_approve_on_timeout = auto_approve_on_timeout or dict(self.DEFAULT_AUTO_APPROVE_ON_TIMEOUT)

        self._requests: dict[str, MCPApprovalRequest] = {}
        self._hitl_to_mcp: dict[str, str] = {}  # hitl_event_id -> request_id

    def create_approval_request(
        self,
        agent_id: str,
        mcp_server: str,
        tool_name: str,
        args: dict[str, Any],
        risk_score: float = 0.0,
        hitl_type: str = "write",  # write, delete, execute
    ) -> MCPApprovalRequest:
        """Create a new MCP approval request and route to HITL.

        Args:
            agent_id: The agent requesting the MCP call
            mcp_server: The MCP server (e.g., "mcp_GitHub")
            tool_name: The tool being called (e.g., "create_issue")
            args: The tool arguments
            risk_score: Pre-calculated risk score [0, 1]
            hitl_type: Type of HITL required (write/delete/execute)

        Returns:
            MCPApprovalRequest with the HITL event information
        """
        # Map risk score to HITL tier
        tier = self._map_risk_to_tier(risk_score, hitl_type)

        # Create request ID
        request_id = f"mcp-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"

        # Create HITL event
        hitl_event = self.hitl_router.route(
            severity=self._tier_to_severity(tier),
            anomaly_type=f"mcp_{hitl_type}_approval",
            description=f"Agent '{agent_id}' requests {hitl_type} access to {mcp_server}/{tool_name}",
            session_id=agent_id,
            action=f"mcp:{mcp_server}:{tool_name}",
            parameters=args,
            agent_id=agent_id,
            mcp_server=mcp_server,
            tool_name=tool_name,
            risk_score=risk_score,
        )

        # Create MCP approval request
        request = MCPApprovalRequest(
            request_id=request_id,
            hitl_event_id=hitl_event.event_id,
            agent_id=agent_id,
            mcp_server=mcp_server,
            tool_name=tool_name,
            args=args,
            risk_score=risk_score,
            tier=tier,
        )

        self._requests[request_id] = request
        self._hitl_to_mcp[hitl_event.event_id] = request_id

        logger.info(
            f"MCP HITL request created: {request_id} "
            f"agent={agent_id} server={mcp_server} tool={tool_name} tier={tier.value}"
        )

        return request

    def approve(self, request_id: str, approver: str = "human") -> bool:
        """Approve an MCP request."""
        request = self._requests.get(request_id)
        if request is None:
            # Try to find by HITL event ID
            request = self._requests.get(self._hitl_to_mcp.get(request_id, ""))
            if request is None:
                return False

        if request.status != "pending":
            return False

        request.status = "approved"
        request.approved_by = approver
        request.approved_at = time.time()

        # Also approve the HITL event
        self.hitl_router.approve(request.hitl_event_id, reviewer=approver)

        logger.info(f"MCP HITL request approved: {request_id} by {approver}")
        return True

    def deny(self, request_id: str, reason: str = "") -> bool:
        """Deny an MCP request."""
        request = self._requests.get(request_id)
        if request is None:
            request = self._requests.get(self._hitl_to_mcp.get(request_id, ""))
            if request is None:
                return False

        if request.status != "pending":
            return False

        request.status = "denied"
        request.rejection_reason = reason

        # Also reject the HITL event
        self.hitl_router.reject(request.hitl_event_id, reason=reason or "Denied by human")

        logger.info(f"MCP HITL request denied: {request_id} reason={reason}")
        return True

    def check_timeout(self, request_id: str | None = None) -> list[MCPApprovalRequest]:
        """Check for timed-out requests and auto-approve/deny based on policy.

        If request_id is provided, checks only that request.
        Otherwise, checks all pending requests.

        Returns:
            List of requests that were auto-processed due to timeout.
        """
        auto_processed = []
        now = time.time()

        requests_to_check = (
            [self._requests[request_id]] if request_id and request_id in self._requests
            else [r for r in self._requests.values() if r.status == "pending"]
        )

        for request in requests_to_check:
            if request.status != "pending":
                continue

            timeout = self.timeouts.get(request.tier, 0)
            if timeout <= 0:
                continue

            elapsed = now - request.created_at
            if elapsed >= timeout:
                if self.auto_approve_on_timeout.get(request.tier, False):
                    request.status = "timeout_approved"
                    request.approved_by = "system_timeout"
                    request.approved_at = now
                    self.hitl_router.approve(request.hitl_event_id, reviewer="system")
                    logger.info(f"MCP HITL request auto-approved (timeout): {request.request_id}")
                else:
                    request.status = "timeout_denied"
                    request.rejection_reason = "Approval timeout - auto denied"
                    self.hitl_router.reject(request.hitl_event_id, reason="Timeout denied")
                    logger.info(f"MCP HITL request auto-denied (timeout): {request.request_id}")

                auto_processed.append(request)

        return auto_processed

    def get_pending_requests(
        self,
        agent_id: str | None = None,
        mcp_server: str | None = None,
        tier: HITLTier | None = None,
    ) -> list[MCPApprovalRequest]:
        """Get pending approval requests with optional filters."""
        results = []
        for request in self._requests.values():
            if request.status != "pending":
                continue
            if agent_id and request.agent_id != agent_id:
                continue
            if mcp_server and request.mcp_server != mcp_server:
                continue
            if tier and request.tier != tier:
                continue
            results.append(request)
        return results

    def get_request(self, request_id: str) -> MCPApprovalRequest | None:
        """Get a specific request by ID."""
        return self._requests.get(request_id)

    def get_request_by_hitl_event(self, hitl_event_id: str) -> MCPApprovalRequest | None:
        """Get a request by its associated HITL event ID."""
        mcp_id = self._hitl_to_mcp.get(hitl_event_id)
        return self._requests.get(mcp_id) if mcp_id else None

    def get_stats(self) -> dict[str, Any]:
        """Get MCP HITL statistics."""
        total = len(self._requests)
        by_status: dict[str, int] = {}
        by_tier: dict[str, int] = {}
        by_server: dict[str, int] = {}
        by_agent: dict[str, int] = {}

        for request in self._requests.values():
            by_status[request.status] = by_status.get(request.status, 0) + 1
            by_tier[request.tier.value] = by_tier.get(request.tier.value, 0) + 1
            by_server[request.mcp_server] = by_server.get(request.mcp_server, 0) + 1
            by_agent[request.agent_id] = by_agent.get(request.agent_id, 0) + 1

        return {
            "total_requests": total,
            "pending": by_status.get("pending", 0),
            "approved": by_status.get("approved", 0),
            "denied": by_status.get("denied", 0),
            "timeout_approved": by_status.get("timeout_approved", 0),
            "timeout_denied": by_status.get("timeout_denied", 0),
            "by_tier": by_tier,
            "by_server": by_server,
            "by_agent": by_agent,
        }

    def _map_risk_to_tier(self, risk_score: float, hitl_type: str) -> HITLTier:
        """Map MCP risk score to HITL tier.

        Higher risk scores map to more restrictive HITL tiers.
        """
        if risk_score >= 0.8 or hitl_type == "execute":
            return HITLTier.P0_RESPONSE
        if risk_score >= 0.5 or hitl_type == "delete":
            return HITLTier.P1_ESCALATE
        return HITLTier.P1_ESCALATE  # Default for write operations

    @staticmethod
    def _tier_to_severity(tier: HITLTier) -> str:
        """Map HITL tier to anomaly severity."""
        mapping = {
            HITLTier.P0_RESPONSE: "critical",
            HITLTier.P1_ESCALATE: "warning",
            HITLTier.P2_LOG: "info",
            HITLTier.P3_OBSERVE: "normal",
        }
        return mapping.get(tier, "info")


# Singleton
_mcp_hitl_bridge: MCPHITLBridge | None = None


def get_mcp_hitl_bridge() -> MCPHITLBridge:
    """Get or create the singleton MCP HITL bridge instance."""
    global _mcp_hitl_bridge
    if _mcp_hitl_bridge is None:
        _mcp_hitl_bridge = MCPHITLBridge()
    return _mcp_hitl_bridge


def request_mcp_approval(
    agent_id: str,
    mcp_server: str,
    tool_name: str,
    args: dict,
    risk_score: float = 0.0,
    hitl_type: str = "write",
) -> MCPApprovalRequest:
    """Convenience function to request MCP approval through the bridge.

    This is the function that mcp_security_gate should call when HITL is required.

    Returns:
        MCPApprovalRequest with the HITL event and request information.
    """
    bridge = get_mcp_hitl_bridge()
    return bridge.create_approval_request(agent_id, mcp_server, tool_name, args, risk_score, hitl_type)
