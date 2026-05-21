from __future__ import annotations

import os
import sys

from maref.integration.mcp_transport import InProcessTransport
from maref.tools.shell_server import (
    MAX_OUTPUT_SIZE,
    CommandWhitelist,
    _has_shell_metacharacters,
    _truncate_output,
    create_shell_server,
)


class TestCommandWhitelist:
    def test_allowed_commands(self):
        wl = CommandWhitelist()
        for cmd in ["ls", "echo", "pwd", "cat", "mkdir"]:
            assert wl.is_allowed(cmd)

    def test_blocked_commands(self):
        wl = CommandWhitelist()
        for cmd in ["rm", "rmdir", "chmod", "chown", "dd", "sudo", "su", "kill", "passwd", "shutdown", "reboot"]:
            assert not wl.is_allowed(cmd)

    def test_is_allowed_with_path(self):
        wl = CommandWhitelist()
        assert wl.is_allowed("/bin/ls")
        assert wl.is_allowed("/usr/bin/echo")
        assert not wl.is_allowed("/bin/rm")

    def test_list_allowed(self):
        wl = CommandWhitelist()
        allowed = wl.list_allowed()
        assert isinstance(allowed, list)
        assert "echo" in allowed
        assert "ls" in allowed
        assert sorted(allowed) == allowed


class TestHasShellMetacharacters:
    def test_semicolon(self):
        assert _has_shell_metacharacters(["hello;world"])

    def test_pipe(self):
        assert _has_shell_metacharacters(["ls", "|", "wc"])

    def test_and_and(self):
        assert _has_shell_metacharacters(["ls && wc"])

    def test_or_or(self):
        assert _has_shell_metacharacters(["ls || wc"])

    def test_dollar(self):
        assert _has_shell_metacharacters(["$HOME"])

    def test_backtick(self):
        assert _has_shell_metacharacters(["`ls`"])

    def test_parentheses(self):
        assert _has_shell_metacharacters(["$(pwd)"])

    def test_braces(self):
        assert _has_shell_metacharacters(["{a,b}"])

    def test_redirect(self):
        assert _has_shell_metacharacters([">file"])
        assert _has_shell_metacharacters(["<file"])

    def test_ampersand(self):
        assert _has_shell_metacharacters(["cmd &"])

    def test_newline(self):
        assert _has_shell_metacharacters(["hello\nworld"])

    def test_clean_args(self):
        assert not _has_shell_metacharacters(["hello", "world"])
        assert not _has_shell_metacharacters(["hello.txt"])
        assert not _has_shell_metacharacters(["--flag=value"])

    def test_empty_list(self):
        assert not _has_shell_metacharacters([])


class TestTruncateOutput:
    def test_no_truncation_needed(self):
        stdout = "hello"
        stderr = ""
        result = _truncate_output(stdout, stderr)
        assert result == (stdout, stderr)

    def test_truncation(self):
        large = "x" * (MAX_OUTPUT_SIZE + 100)
        stdout, stderr = _truncate_output(large, "")
        assert len(stdout.encode("utf-8")) <= MAX_OUTPUT_SIZE // 2

    def test_both_streams_truncated(self):
        large = "x" * (MAX_OUTPUT_SIZE // 2 + 1000)
        stdout, stderr = _truncate_output(large, large)
        combined = len(stdout.encode("utf-8")) + len(stderr.encode("utf-8"))
        assert combined <= MAX_OUTPUT_SIZE


class TestShellServerRunCommand:
    def setup_method(self):
        self.server = create_shell_server()
        self.transport = self.server.get_inprocess_transport()
        self.transport.connect()

    def test_echo_success(self):
        resp = self.transport.send_tool_call("run_command", {"command": "echo", "args": ["hello world"]})
        assert not resp.is_error
        assert resp.result["stdout"].strip() == "hello world"
        assert resp.result["exit_code"] == 0
        assert not resp.result["timed_out"]

    def test_pwd(self):
        resp = self.transport.send_tool_call("run_command", {"command": "pwd"})
        assert not resp.is_error
        assert resp.result["stdout"].strip() == os.getcwd()
        assert resp.result["exit_code"] == 0

    def test_ls(self):
        resp = self.transport.send_tool_call("run_command", {"command": "ls"})
        assert not resp.is_error
        assert resp.result["exit_code"] == 0
        assert len(resp.result["stdout"]) > 0

    def test_echo_with_multiple_args(self):
        resp = self.transport.send_tool_call("run_command", {"command": "echo", "args": ["hello", "world"]})
        assert not resp.is_error
        assert resp.result["stdout"].strip() == "hello world"
        assert resp.result["exit_code"] == 0

    def test_command_not_in_whitelist(self):
        resp = self.transport.send_tool_call("run_command", {"command": "rm", "args": ["-rf", "/"]})
        assert not resp.is_error
        assert resp.result["exit_code"] == -1
        assert "not in the whitelist" in resp.result["stderr"]

    def test_shell_metacharacters_semicolon(self):
        resp = self.transport.send_tool_call("run_command", {"command": "echo", "args": ["hello;world"]})
        assert not resp.is_error
        assert resp.result["exit_code"] == -1
        assert "metacharacters" in resp.result["stderr"]

    def test_shell_metacharacters_pipe(self):
        resp = self.transport.send_tool_call("run_command", {"command": "echo", "args": ["hello", "|", "wc"]})
        assert not resp.is_error
        assert resp.result["exit_code"] == -1
        assert "metacharacters" in resp.result["stderr"]

    def test_shell_metacharacters_dollar(self):
        resp = self.transport.send_tool_call("run_command", {"command": "echo", "args": ["$HOME"]})
        assert not resp.is_error
        assert resp.result["exit_code"] == -1
        assert "metacharacters" in resp.result["stderr"]

    def test_shell_metacharacters_and_and(self):
        resp = self.transport.send_tool_call("run_command", {"command": "echo", "args": ["ls && pwd"]})
        assert not resp.is_error
        assert resp.result["exit_code"] == -1
        assert "metacharacters" in resp.result["stderr"]

    def test_timeout_enforcement(self):
        resp = self.transport.send_tool_call("run_command", {"command": "echo", "args": ["test"]})
        assert not resp.is_error
        assert not resp.result["timed_out"]

    def test_cwd_relative_path_rejected(self):
        resp = self.transport.send_tool_call("run_command", {"command": "pwd", "cwd": "relative/path"})
        assert not resp.is_error
        assert resp.result["exit_code"] == -1
        assert "absolute path" in resp.result["stderr"]

    def test_cwd_absolute_path(self):
        resp = self.transport.send_tool_call("run_command", {"command": "pwd", "cwd": "/tmp"})
        assert not resp.is_error
        assert resp.result["stdout"].strip() == os.path.realpath("/tmp")
        assert resp.result["exit_code"] == 0

    def test_unknown_tool(self):
        resp = self.transport.send_tool_call("nonexistent_tool", {})
        assert resp.is_error

    def test_get_shell_help(self):
        resp = self.transport.send_tool_call("get_shell_help", {})
        assert not resp.is_error
        assert "allowed_commands" in resp.result
        assert "description" in resp.result
        assert resp.result["description"] != ""

    def test_get_shell_help_commands_list(self):
        resp = self.transport.send_tool_call("get_shell_help", {})
        assert not resp.is_error
        commands = resp.result["allowed_commands"]
        for cmd in ["ls", "echo", "pwd", "cat", "mkdir"]:
            assert cmd in commands

    def test_output_truncation(self):
        large_output = "A" * (MAX_OUTPUT_SIZE + 1000)
        resp = self.transport.send_tool_call(
            "run_command",
            {"command": sys.executable, "args": ["-c", f"print('{large_output}')"]},
        )
        assert not resp.is_error
        stdout_size = len(resp.result["stdout"].encode("utf-8"))
        stderr_size = len(resp.result["stderr"].encode("utf-8"))
        total_size = stdout_size + stderr_size
        assert total_size <= MAX_OUTPUT_SIZE

    def test_whitelist_contains_all_specified_commands(self):
        wl = CommandWhitelist()
        expected = {"ls", "cat", "head", "tail", "wc", "grep", "find",
                    "echo", "date", "pwd", "which", "whoami", "uname",
                    "sort", "cut", "tr", "mkdir"}
        for cmd in expected:
            assert wl.is_allowed(cmd), f"{cmd} should be whitelisted"

    def test_whitelist_excludes_dangerous_commands(self):
        wl = CommandWhitelist()
        forbidden = {"rm", "rmdir", "chmod", "chown", "dd", "sudo", "su", "kill", "passwd", "shutdown", "reboot"}
        for cmd in forbidden:
            assert not wl.is_allowed(cmd), f"{cmd} should not be whitelisted"


class TestShellServerInProcessTransport:
    def test_create_shell_server_returns_mcp_server(self):
        server = create_shell_server()
        assert server.name == "shell-server"
        assert server.version == "0.25.0"

    def test_inprocess_transport_initialization(self):
        server = create_shell_server()
        transport = server.get_inprocess_transport()
        assert isinstance(transport, InProcessTransport)

    def test_transport_connect_disconnect(self):
        server = create_shell_server()
        transport = server.get_inprocess_transport()
        transport.connect()
        assert transport.state.value == "connected"
        transport.disconnect()
        assert transport.state.value == "disconnected"

    def test_transport_disconnected_returns_error(self):
        server = create_shell_server()
        transport = server.get_inprocess_transport()
        resp = transport.send_tool_call("run_command", {"command": "echo", "args": ["test"]})
        assert resp.is_error
        assert "not connected" in resp.error["message"]

    def test_tools_list(self):
        server = create_shell_server()
        transport = server.get_inprocess_transport()
        transport.connect()
        resp = transport.send_tools_list()
        assert not resp.is_error
        tool_names = [t["name"] for t in resp.result["tools"]]
        assert "run_command" in tool_names
        assert "get_shell_help" in tool_names

    def test_initialize(self):
        server = create_shell_server()
        transport = server.get_inprocess_transport()
        transport.connect()
        resp = transport.send_initialize()
        assert not resp.is_error
        assert resp.result["serverInfo"]["name"] == "shell-server"


class TestShellServerEdgeCases:
    def setup_method(self):
        self.server = create_shell_server()
        self.transport = self.server.get_inprocess_transport()
        self.transport.connect()

    def test_missing_command_param(self):
        resp = self.transport.send_tool_call("run_command", {})
        assert not resp.is_error
        assert resp.result["exit_code"] == -1
        assert "not in the whitelist" in resp.result["stderr"]

    def test_empty_args(self):
        resp = self.transport.send_tool_call("run_command", {"command": "echo", "args": []})
        assert not resp.is_error
        assert resp.result["stdout"].strip() == ""
        assert resp.result["exit_code"] == 0

    def test_which_command(self):
        resp = self.transport.send_tool_call("run_command", {"command": "which", "args": ["echo"]})
        assert not resp.is_error
        assert resp.result["exit_code"] == 0
        assert len(resp.result["stdout"].strip()) > 0

    def test_whoami(self):
        resp = self.transport.send_tool_call("run_command", {"command": "whoami"})
        assert not resp.is_error
        assert resp.result["exit_code"] == 0
        assert len(resp.result["stdout"].strip()) > 0

    def test_date(self):
        resp = self.transport.send_tool_call("run_command", {"command": "date"})
        assert not resp.is_error
        assert resp.result["exit_code"] == 0
        assert len(resp.result["stdout"].strip()) > 0

    def test_uname(self):
        resp = self.transport.send_tool_call("run_command", {"command": "uname", "args": ["-a"]})
        assert not resp.is_error
        assert resp.result["exit_code"] == 0
        assert len(resp.result["stdout"].strip()) > 0


class TestShellServerTimeout:
    def setup_method(self):
        self.server = create_shell_server()
        self.transport = self.server.get_inprocess_transport()
        self.transport.connect()

    def test_timeout_triggers(self):
        resp = self.transport.send_tool_call(
            "run_command",
            {"command": "find", "args": ["/"], "timeout": 1},
        )
        assert not resp.is_error
        assert resp.result["timed_out"]
        assert resp.result["exit_code"] == -1
        assert "timed out" in resp.result["stderr"].lower()

    def test_max_timeout_capped(self):
        resp = self.transport.send_tool_call(
            "run_command",
            {"command": "echo", "args": ["test"], "timeout": 500},
        )
        assert not resp.is_error
        assert resp.result["stdout"].strip() == "test"
        assert resp.result["exit_code"] == 0
