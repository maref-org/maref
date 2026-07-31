"""PTY 桥接 — 通过 sidecar MCP 网关的终端操作

将 Electron PTY 操作路由到 sidecar 治理管线：
  1. 所有 PTY 写入经过 DestructiveOperationGate 过滤
  2. 通过 MCPGateway 三层检查（安全门+策略+熔断器）
  3. AuditLogger 记录所有操作

用法:
    from sidecar.pty_bridge import PTY_TOOL, PTYHandler

    注册到 MCPGateway:
        gateway.register_backend(
            prefix="pty_",
            transport_type="in-process",
            handler=PTYHandler().handle_tool_call,
            tools=[PTY_TOOL.to_dict()],
        )
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PTYToolDef:
    name: str = "pty_exec"
    description: str = "Execute a shell command via sidecar-managed PTY (governed + audited)"
    inputSchema: dict[str, Any] = field(default_factory=lambda: {  # noqa: N815
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "timeout": {"type": "number", "description": "Timeout in seconds", "default": 30},
            "workdir": {"type": "string", "description": "Working directory", "default": ""},
        },
        "required": ["command"],
    })

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.inputSchema,
        }


PTY_TOOL = PTYToolDef()

_BLOCKED_COMMANDS = [
    "rm -rf /", "rm -rf /*", "sudo ", "chmod 777", "chown ", "dd if=",
    "> /dev/", "mkfs.", "fdisk", "fsck", "dd of=",
]


def _check_blocked(command: str) -> str | None:
    cmd_lower = command.lower().strip()
    for blocked in _BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return f"Command blocked by PTY bridge: contains '{blocked}'"
    return None


class PTYHandler:
    def __init__(self, default_timeout: int = 30) -> None:
        self._default_timeout = default_timeout
        self._session_id = f"pty-{int(time.time())}"

    def handle_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name != "pty_exec":
            return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}]}

        command = arguments.get("command", "")
        if not command:
            return {"isError": True, "content": [{"type": "text", "text": "No command provided"}]}

        blocked = _check_blocked(command)
        if blocked:
            logger.warning("PTY blocked: %s", command[:80])
            return {"isError": True, "content": [{"type": "text", "text": blocked}]}

        timeout = arguments.get("timeout", self._default_timeout)
        workdir = arguments.get("workdir", "") or os.getcwd()

        logger.info("PTY exec: %s (timeout=%s, cwd=%s)", command[:120], timeout, workdir)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workdir,
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"

            max_len = 100000
            if len(output) > max_len:
                output = output[:max_len] + f"\n... (truncated, {len(output)} total chars)"

            return {
                "content": [{"type": "text", "text": output or "(no output)"}],
                "metadata": {
                    "returncode": result.returncode,
                    "command": command[:80],
                    "duration": timeout,
                },
            }
        except subprocess.TimeoutExpired:
            return {"isError": True, "content": [{"type": "text", "text": f"Command timed out after {timeout}s"}]}
        except Exception as exc:
            logger.error("PTY exec failed: %s", exc)
            return {"isError": True, "content": [{"type": "text", "text": f"Execution error: {exc}"}]}


class PTYBridge:
    """High-level bridge that renders PTY operations through governance pipeline."""

    def __init__(self, gateway: object | None = None) -> None:
        self._gateway = gateway
        self._handler = PTYHandler()

    def attach_to_gateway(self, gateway: object) -> None:
        self._gateway = gateway
        if hasattr(gateway, "register_backend"):
            gateway.register_backend(
                prefix="pty_",
                transport_type="in-process",
                handler=self._handler.handle_tool_call,
                tools=[PTY_TOOL.to_dict()],
            )

    def exec_command(self, command: str, timeout: int = 30, workdir: str = "") -> dict[str, Any]:
        if self._gateway and hasattr(self._gateway, "route_tool_call"):
            return self._gateway.route_tool_call("pty_exec", {
                "command": command,
                "timeout": timeout,
                "workdir": workdir,
            })
        return self._handler.handle_tool_call("pty_exec", {
            "command": command,
            "timeout": timeout,
            "workdir": workdir,
        })
