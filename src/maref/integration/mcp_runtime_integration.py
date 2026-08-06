"""mcp_runtime_integration.py — MCP Security Runtime for MAREF open-source.

Wires MCPSecurityGateV2 + AuditLogger for secure MCP tool execution.
HITL is not included (open-source context — AUDIT verdicts are denied).

Usage:
    executor = SecureMCPExecutor(agent_id="claude-code")
    result = executor.execute("mcp_Filesystem", "read_file", {"path": "/tmp/test"})
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from maref.integration.audit_logger import AuditLogger, get_audit_logger
from maref.integration.mcp_security import SecurityVerdict
from maref.integration.mcp_security_gate import MCPSecurityGateV2, get_security_gate

logger = logging.getLogger(__name__)


@dataclass
class MCPExecutionResult:
    verdict: str  # ALLOW, DENY
    data: dict[str, Any] | None = None
    reason: str = ""
    duration_ms: float = 0.0
    risk_score: float = 0.0


class _MetricsCollector:
    """Minimal inline metrics collector (no external dependency)."""

    def __init__(self) -> None:
        self._calls: list[dict[str, Any]] = []

    def record(self, agent_id: str, mcp_server: str, tool_name: str, verdict: str, duration_ms: float) -> None:
        self._calls.append({
            "agent_id": agent_id,
            "mcp_server": mcp_server,
            "tool_name": tool_name,
            "verdict": verdict,
            "duration_ms": duration_ms,
            "timestamp": time.time(),
        })

    def get_summary(self, window_hours: float = 1.0) -> dict[str, Any]:
        cutoff = time.time() - (window_hours * 3600)
        recent = [c for c in self._calls if c["timestamp"] >= cutoff]
        return {
            "total": len(recent),
            "allowed": sum(1 for c in recent if c["verdict"] == SecurityVerdict.ALLOW),
            "denied": sum(1 for c in recent if c["verdict"] == SecurityVerdict.DENY),
        }


class SecureMCPExecutor:
    """Execute MCP tools with security gate and audit logging.

    Open-source variant: AUDIT verdict → DENY (no HITL available).
    """

    def __init__(
        self,
        agent_id: str,
        security_gate: MCPSecurityGateV2 | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.security_gate = security_gate or get_security_gate()
        self.audit_logger = audit_logger or get_audit_logger()
        self._metrics = _MetricsCollector()
        self._tool_executor: Any = None

    def execute(
        self,
        mcp_server: str,
        tool_name: str,
        args: dict[str, Any] | None = None,
    ) -> MCPExecutionResult:
        args = args or {}
        start = time.time()

        verdict = self.security_gate.check_call(
            agent_id=self.agent_id,
            mcp_server=mcp_server,
            tool_name=tool_name,
            args=args,
        )

        duration_ms = (time.time() - start) * 1000

        # AUDIT → DENY in open-source (no HITL)
        if verdict == SecurityVerdict.AUDIT:
            verdict = SecurityVerdict.DENY
            reason = "AUDIT verdict denied (HITL not available in open-source)"

        if verdict == SecurityVerdict.DENY:
            self.audit_logger.log_call(
                agent_id=self.agent_id,
                mcp_server=mcp_server,
                tool_name=tool_name,
                verdict=verdict,
                args=args,
                risk_score=0.8,
                latency_ms=duration_ms,
            )
            self._metrics.record(self.agent_id, mcp_server, tool_name, verdict, duration_ms)
            return MCPExecutionResult(
                verdict=verdict,
                reason=reason if verdict == SecurityVerdict.DENY else "",
                duration_ms=duration_ms,
                risk_score=0.8 if verdict == SecurityVerdict.DENY else 0.0,
            )

        # ALLOW — execute the tool
        result_data = self._execute_tool(mcp_server, tool_name, args)
        self.audit_logger.log_call(
            agent_id=self.agent_id,
            mcp_server=mcp_server,
            tool_name=tool_name,
            verdict=verdict,
            args=args,
            latency_ms=duration_ms,
        )
        self._metrics.record(self.agent_id, mcp_server, tool_name, verdict, duration_ms)

        return MCPExecutionResult(
            verdict=verdict,
            data=result_data,
            duration_ms=duration_ms,
        )

    def set_tool_executor(self, executor: Any) -> None:
        self._tool_executor = executor

    def get_metrics(self) -> dict[str, Any]:
        return self._metrics.get_summary()

    def _execute_tool(self, mcp_server: str, tool_name: str, args: dict[str, Any]) -> dict[str, Any] | None:
        if self._tool_executor is None:
            return {"ok": True, "tool": f"{mcp_server}/{tool_name}", "args": args}
        try:
            return self._tool_executor(mcp_server, tool_name, args)
        except Exception as e:
            logger.error(f"MCP execution failed: {mcp_server}/{tool_name}: {e}")
            return {"ok": False, "error": str(e)}


_METRICS = _MetricsCollector()


def create_secure_executor(agent_id: str) -> SecureMCPExecutor:
    return SecureMCPExecutor(agent_id=agent_id)
