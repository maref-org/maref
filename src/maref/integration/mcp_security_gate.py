"""mcp_security_gate.py — MCP Security Gateway for MAREF open-source.

Per-agent, per-tool permission checks via configs/mcp_security_policy.json.
No dependencies on openclaw proprietary files or paths.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maref.integration.mcp_security import (
    MCPSecurityGate,
    MCPTrustLevel,
    SecurityVerdict,
    ZeroTrustContext,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentPermission:
    agent_id: str
    trust_level: str
    allowed_mcp_servers: list[str]
    max_response_size_bytes: int = 1048576
    rate_limit_rpm: int = 60
    blocked_operations: list[str] = field(default_factory=list)


class MCPSecurityGateV2:
    """Policy-driven MCP Security Gateway.

    Loads agent permissions and tool policies from configs/ directory.
    Integrates with base MCPSecurityGate for zero-trust evaluation.
    """

    def __init__(
        self,
        policy_path: Path | None = None,
        base_gate: MCPSecurityGate | None = None,
    ) -> None:
        repo_root = self._find_repo_root()
        self.policy_path = policy_path or repo_root / "configs" / "mcp_security_policy.json"
        self.base_gate = base_gate or MCPSecurityGate()
        self._policy: dict[str, Any] = {}
        self._load_policy()

    def check_call(
        self,
        agent_id: str,
        mcp_server: str,
        tool_name: str,
        args: dict[str, Any] | None = None,
    ) -> str:
        permissions = self._get_permissions(agent_id)
        if permissions is None:
            self._log_audit(tool_name, "agent_not_registered")
            return SecurityVerdict.DENY

        server_config = self._policy.get("mcp_servers", {}).get(mcp_server)
        if server_config is None:
            self._log_audit(tool_name, "unknown_mcp_server")
            return SecurityVerdict.DENY

        if mcp_server not in permissions.allowed_mcp_servers:
            self._log_audit(tool_name, "mcp_server_not_allowed")
            return SecurityVerdict.DENY

        if tool_name in permissions.blocked_operations:
            self._log_audit(tool_name, "operation_blocked")
            return SecurityVerdict.DENY

        dangerous = server_config.get("dangerous_tools", [])
        if tool_name in dangerous:
            self._log_audit(tool_name, "dangerous_tool")
            return SecurityVerdict.DENY

        trust_level = MCPTrustLevel(permissions.trust_level.lower())
        context = ZeroTrustContext(agent_id=agent_id)
        base_verdict = self.base_gate.check(tool_name, trust_level, args, context)

        self._log_audit(tool_name, f"verdict={base_verdict}")
        return base_verdict

    def _get_permissions(self, agent_id: str) -> AgentPermission | None:
        agents = self._policy.get("agents", {})
        config = agents.get(agent_id)
        if not config:
            return None
        return AgentPermission(
            agent_id=agent_id,
            trust_level=config.get("trust_level", "UNTRUSTED"),
            allowed_mcp_servers=config.get("allowed_mcp_servers", []),
            blocked_operations=config.get("blocked_operations", []),
        )

    def _log_audit(self, tool_name: str, reason: str) -> None:
        logger.debug(f"MCP security gate: {tool_name} — {reason}")

    def _load_policy(self) -> None:
        if self.policy_path.exists():
            try:
                self._policy = json.loads(self.policy_path.read_text())
                logger.info(f"Loaded MCP security policy from {self.policy_path}")
            except Exception as e:
                logger.warning(f"Failed to load MCP security policy: {e}")
                self._policy = {}

    @staticmethod
    def _find_repo_root() -> Path:
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
                return parent
        return current.parent.parent.parent


_security_gate: MCPSecurityGateV2 | None = None


def get_security_gate() -> MCPSecurityGateV2:
    global _security_gate
    if _security_gate is None:
        _security_gate = MCPSecurityGateV2()
    return _security_gate
