"""Smoke tests for maref.integration.mcp_hitl_bridge."""
from __future__ import annotations

import pytest

from maref.integration.hitl import HITLTier
from maref.integration.mcp_hitl_bridge import MCPApprovalRequest, MCPHITLBridge


class TestMCPApprovalRequest:
    def test_init_minimal(self) -> None:
        req = MCPApprovalRequest(
            request_id="r1", hitl_event_id="e1", agent_id="a1",
            mcp_server="mcp_GitHub", tool_name="create_issue",
            args={}, risk_score=0.5, tier=HITLTier.P1_ESCALATE,
        )
        assert req.request_id == "r1"
        assert req.agent_id == "a1"
        assert req.status == "pending"
        assert req.approved_by is None

    def test_init_custom(self) -> None:
        req = MCPApprovalRequest(
            request_id="r2", hitl_event_id="e2", agent_id="a2",
            mcp_server="mcp_Filesystem", tool_name="write_file",
            args={"path": "/tmp/test.txt"}, risk_score=0.9,
            tier=HITLTier.P0_RESPONSE, status="approved",
            approved_by="admin", approved_at=1000.0,
        )
        assert req.status == "approved"
        assert req.approved_by == "admin"

    def test_to_dict(self) -> None:
        req = MCPApprovalRequest(
            request_id="r1", hitl_event_id="e1", agent_id="a1",
            mcp_server="mcp_GitHub", tool_name="create_issue",
            args={}, risk_score=0.5, tier=HITLTier.P2_LOG,
        )
        d = req.to_dict()
        assert d["request_id"] == "r1"
        assert d["tier"] == "p2_log"
        assert d["status"] == "pending"


class TestMCPHITLBridge:
    def test_init_default(self) -> None:
        bridge = MCPHITLBridge()
        assert bridge is not None
        assert len(bridge._requests) == 0

    def test_init_with_router(self) -> None:
        bridge = MCPHITLBridge(hitl_router=None)
        assert bridge is not None

    def test_create_approval_request(self) -> None:
        bridge = MCPHITLBridge()
        req = bridge.create_approval_request(
            agent_id="test_agent",
            mcp_server="mcp_GitHub",
            tool_name="create_issue",
            args={"title": "Test"},
            risk_score=0.3,
        )
        assert req.agent_id == "test_agent"
        assert req.mcp_server == "mcp_GitHub"
        assert req.tool_name == "create_issue"
        assert req.status == "pending"
