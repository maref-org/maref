"""Smoke tests for maref.integration.mcp_security_gate."""
from __future__ import annotations

import pytest

from maref.integration.mcp_security_gate import AgentPermission, MCPSecurityGateV2


class TestAgentPermission:
    def test_init_minimal(self) -> None:
        perm = AgentPermission(
            agent_id="test_agent", trust_level="TRUSTED",
            allowed_mcp_servers=["mcp_GitHub", "mcp_Filesystem"],
        )
        assert perm.agent_id == "test_agent"
        assert perm.trust_level == "TRUSTED"
        assert "mcp_GitHub" in perm.allowed_mcp_servers
        assert perm.max_response_size_bytes == 1048576
        assert perm.rate_limit_rpm == 60
        assert perm.blocked_operations == []

    def test_init_custom(self) -> None:
        perm = AgentPermission(
            agent_id="admin_agent", trust_level="ADMIN",
            allowed_mcp_servers=["mcp_GitHub"],
            max_response_size_bytes=2097152,
            rate_limit_rpm=120,
            blocked_operations=["delete_repo"],
        )
        assert perm.max_response_size_bytes == 2097152
        assert perm.rate_limit_rpm == 120
        assert "delete_repo" in perm.blocked_operations


class TestMCPSecurityGateV2:
    def test_init_default(self) -> None:
        gate = MCPSecurityGateV2()
        assert gate is not None
        assert gate.policy_path is not None

    def test_check_call_unknown_agent(self) -> None:
        gate = MCPSecurityGateV2()
        result = gate.check_call(
            agent_id="nonexistent",
            mcp_server="mcp_GitHub",
            tool_name="create_issue",
        )
        assert result == "DENY"

    def test_find_repo_root(self) -> None:
        root = MCPSecurityGateV2._find_repo_root()
        assert root is not None
        assert root.exists()
