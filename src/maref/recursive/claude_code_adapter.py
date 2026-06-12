from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from maref.integration.mcp_client import MCPClient, MCPConnection, MCPServerConfig
from maref.integration.mcp_governance import MCPGovernance
from maref.integration.mcp_security import MCPTrustLevel


@dataclass
class AdapterConfig:
    agent_id: str = "claude-code"
    mcp_server_name: str = "claude-code-mcp"
    auto_reconnect: bool = True
    request_timeout: float = 120.0


@dataclass
class TaskResult:
    task_id: str
    success: bool
    output: str = ""
    error: str = ""
    tool_name: str = ""
    duration: float = 0.0


class ClaudeCodeAdapter:
    def __init__(
        self,
        config: AdapterConfig | None = None,
        mcp_client: MCPClient | None = None,
        governance: MCPGovernance | None = None,
    ) -> None:
        self.config = config or AdapterConfig()
        self._mcp_client = mcp_client or MCPClient()
        self._governance = governance or MCPGovernance()
        self._connection: MCPConnection | None = None
        self._task_results: dict[str, TaskResult] = {}

    @property
    def is_connected(self) -> bool:
        return self._connection is not None

    def connect(self, server_config: MCPServerConfig | None = None) -> bool:
        if self._connection is not None:
            return True
        self._mcp_client.register_governance(self._governance)
        cfg = server_config or MCPServerConfig(
            command=["npx", "-y", "@anthropic-ai/claude-code"],
            transport_type="stdio",
            server_name=self.config.mcp_server_name,
        )
        try:
            self._connection = self._mcp_client.register_server(cfg)
            return self._connection is not None
        except Exception:
            self._connection = None
            return False

    def set_connection(self, connection: MCPConnection) -> None:
        self._connection = connection

    def disconnect(self) -> None:
        self._connection = None

    def submit_task(self, tool_name: str, args: dict[str, Any]) -> str | None:
        if self._connection is None and not self.connect():
            return None
        if self._connection is None:
            return None
        start = time.time()
        try:
            resp = self._mcp_client.call_tool(
                conn=self._connection,
                tool_name=tool_name,
                args=args,
                trust_level=MCPTrustLevel.SEMI_TRUSTED,
                agent_id=self.config.agent_id,
            )
        except Exception as e:
            task_id = str(uuid.uuid4())[:8]
            self._task_results[task_id] = TaskResult(
                task_id=task_id,
                success=False,
                error=f"connection_error: {e}",
                tool_name=tool_name,
                duration=time.time() - start,
            )
            return None
        task_id = str(uuid.uuid4())[:8]
        elapsed = time.time() - start
        if resp.is_error:
            self._task_results[task_id] = TaskResult(
                task_id=task_id,
                success=False,
                error=str(resp.error),
                tool_name=tool_name,
                duration=elapsed,
            )
            return None
        self._task_results[task_id] = TaskResult(
            task_id=task_id,
            success=True,
            output=str(resp.result),
            tool_name=tool_name,
            duration=elapsed,
        )
        return task_id

    def get_result(self, task_id: str) -> TaskResult | None:
        return self._task_results.get(task_id)

    def recent_results(self, limit: int = 10) -> list[TaskResult]:
        return list(self._task_results.values())[-limit:]
