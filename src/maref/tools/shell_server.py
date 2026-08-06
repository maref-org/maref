from __future__ import annotations

import os
import subprocess
from typing import Any

from maref.integration.mcp_server import MCPServer

WHITELISTED_COMMANDS = frozenset(
    {
        "ls",
        "cat",
        "head",
        "tail",
        "wc",
        "grep",
        "find",
        "echo",
        "date",
        "pwd",
        "which",
        "whoami",
        "uname",
        "sort",
        "cut",
        "tr",
        "mkdir",
    }
)

SHELL_METACHARACTER_PATTERNS = [
    "&&",
    "||",
]

SHELL_METACHARACTER_SINGLE = frozenset(";|$`(){}<>&\n\r")

MAX_OUTPUT_SIZE = 1048576
MAX_TIMEOUT = 300


class CommandWhitelist:
    def __init__(self) -> None:
        self._allowed = WHITELISTED_COMMANDS

    def is_allowed(self, command: str) -> bool:
        basename = os.path.basename(command)
        return basename in self._allowed

    def list_allowed(self) -> list[str]:
        return sorted(self._allowed)


def _has_shell_metacharacters(args: list[str]) -> bool:
    for arg in args:
        for pattern in SHELL_METACHARACTER_PATTERNS:
            if pattern in arg:
                return True
        for ch in arg:
            if ch in SHELL_METACHARACTER_SINGLE:
                return True
    return False


def _truncate_output(stdout: str, stderr: str) -> tuple[str, str]:
    combined = len(stdout.encode("utf-8")) + len(stderr.encode("utf-8"))
    if combined <= MAX_OUTPUT_SIZE:
        return stdout, stderr
    max_stdout = MAX_OUTPUT_SIZE // 2
    max_stderr = MAX_OUTPUT_SIZE - max_stdout
    stdout_bytes = stdout.encode("utf-8")[:max_stdout]
    stderr_bytes = stderr.encode("utf-8")[:max_stderr]
    return (
        stdout_bytes.decode("utf-8", errors="replace"),
        stderr_bytes.decode("utf-8", errors="replace"),
    )


def _run_command_impl(
    command: str, args: list[str] | None, timeout: int, cwd: str | None
) -> dict[str, Any]:
    whitelist = CommandWhitelist()
    if not whitelist.is_allowed(command):
        return {
            "stdout": "",
            "stderr": f"Command '{command}' is not in the whitelist",
            "exit_code": -1,
            "timed_out": False,
        }

    cmd_args = args or []

    if _has_shell_metacharacters(cmd_args):
        return {
            "stdout": "",
            "stderr": "Arguments contain shell metacharacters",
            "exit_code": -1,
            "timed_out": False,
        }

    if cwd is not None and not os.path.isabs(cwd):
        return {
            "stdout": "",
            "stderr": "cwd must be an absolute path",
            "exit_code": -1,
            "timed_out": False,
        }

    effective_timeout = min(timeout, MAX_TIMEOUT)
    full_args = [command] + cmd_args

    try:
        result = subprocess.run(
            full_args,
            capture_output=True,
            timeout=effective_timeout,
            cwd=cwd,
            text=True,
        )
        stdout, stderr = _truncate_output(result.stdout, result.stderr)
        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": result.returncode,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Command timed out after {effective_timeout} seconds",
            "exit_code": -1,
            "timed_out": True,
        }
    except FileNotFoundError:
        return {
            "stdout": "",
            "stderr": f"Command not found: {command}",
            "exit_code": -1,
            "timed_out": False,
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "timed_out": False,
        }


def create_shell_server() -> MCPServer:
    server = MCPServer(name="shell-server", version="0.25.0")
    whitelist = CommandWhitelist()

    def run_command_handler(args: dict[str, Any]) -> dict[str, Any]:
        command = args.get("command", "")
        cmd_args = args.get("args")
        timeout = args.get("timeout", 30)
        cwd = args.get("cwd")
        return _run_command_impl(command, cmd_args, timeout, cwd)

    server.register_tool(
        name="run_command",
        description="Run a whitelisted shell command",
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to run"},
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Command arguments",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds",
                    "default": 30,
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory (absolute path)",
                },
            },
            "required": ["command"],
        },
        handler=run_command_handler,
    )

    def get_shell_help_handler(args: dict[str, Any]) -> dict[str, Any]:
        return {
            "allowed_commands": whitelist.list_allowed(),
            "description": "Shell command execution server with whitelist-based security",
        }

    server.register_tool(
        name="get_shell_help",
        description="Get list of allowed shell commands",
        input_schema={
            "type": "object",
            "properties": {},
        },
        handler=get_shell_help_handler,
    )

    return server
