"""
v0.50 W5-S1 — pty_exec 去 shell=True（I5）

覆盖：
- 命令用 shlex.split 拆分，subprocess.run(cmd_list, shell=False)
- 空命令拒绝
- 命令注入（; 分隔的第二条命令）不执行 —— shell=False 语义
- 引号参数正确拆分
- 超时语义保留
- 静态断言源码不含 pty_exec 的 shell=True
"""

from __future__ import annotations

from pathlib import Path

from src.sidecar.pty_bridge import PTYHandler


class TestPTYNoShell:
    def test_simple_command_runs(self) -> None:
        handler = PTYHandler()
        result = handler.handle_tool_call("pty_exec", {"command": "echo hello"})
        assert result.get("isError") is not True
        text = result["content"][0]["text"]
        assert "hello" in text

    def test_empty_command_rejected(self) -> None:
        handler = PTYHandler()
        result = handler.handle_tool_call("pty_exec", {"command": ""})
        assert result.get("isError") is True

    def test_blank_command_rejected(self) -> None:
        handler = PTYHandler()
        result = handler.handle_tool_call("pty_exec", {"command": "   "})
        assert result.get("isError") is True

    def test_injection_not_executed(self) -> None:
        handler = PTYHandler()
        # `;` 注入：shlex 拆分后 `;` 是普通参数传给 `echo`，
        # 不作为 shell 命令分隔符，因此不会独立执行第二个命令。
        result = handler.handle_tool_call(
            "pty_exec",
            {"command": "echo injected > /tmp/maref_w5_injected_out"},
        )
        assert result.get("isError") is not True
        text = result["content"][0]["text"]
        # `>` 也是普通参数：echo 输出原始内容，不产生重定向文件。
        assert "/tmp/maref_w5_injected_out" in text or "injected" in text
        import os

        assert not os.path.exists("/tmp/maref_w5_injected_out")

    def test_quoted_argument_split(self) -> None:
        handler = PTYHandler()
        result = handler.handle_tool_call(
            "pty_exec", {"command": 'python3 -c "print(\'quoted ok\')"'}
        )
        assert result.get("isError") is not True
        text = result["content"][0]["text"]
        assert "quoted ok" in text

    def test_timeout_semantics(self) -> None:
        handler = PTYHandler(default_timeout=1)
        result = handler.handle_tool_call(
            "pty_exec", {"command": "sleep 5", "timeout": 1}
        )
        assert result.get("isError") is True
        assert "timed out" in result["content"][0]["text"]


class TestSourceNoShellTrue:
    def test_pty_bridge_has_no_shell_true(self) -> None:
        src = Path(__file__).resolve().parents[2] / "src" / "sidecar" / "pty_bridge.py"
        text = src.read_text(encoding="utf-8")
        assert "shell=True" not in text

    def test_mcp_bridge_has_no_shell_true(self) -> None:
        src = Path(__file__).resolve().parents[2] / "src" / "sidecar" / "mcp_bridge.py"
        text = src.read_text(encoding="utf-8")
        assert "shell=True" not in text


class TestSidecarMCPBridgePtyExec:
    """I5 生产路径：sidecar mcp_bridge._handle_pty_exec 去 shell=True。"""

    def test_injection_not_executed(self, tmp_path: Path) -> None:
        from sidecar.mcp_bridge import SidecarMCPBridge

        bridge = SidecarMCPBridge()
        # `;` 注入：shlex 拆分后 `;` 是普通参数，第二条命令不被独立执行。
        result = bridge._handle_pty_exec(
            {"command": "echo hi; touch injected", "cwd": str(tmp_path)}
        )
        assert result.get("isError") is not True
        assert not (tmp_path / "injected").exists()
        assert "hi" in result["content"][0]["text"]

    def test_empty_command_rejected(self) -> None:
        from sidecar.mcp_bridge import SidecarMCPBridge

        bridge = SidecarMCPBridge()
        result = bridge._handle_pty_exec({"command": "   "})
        assert result.get("isError") is True

    def test_unparseable_command_rejected(self) -> None:
        from sidecar.mcp_bridge import SidecarMCPBridge

        bridge = SidecarMCPBridge()
        result = bridge._handle_pty_exec({"command": 'echo "unclosed'})
        assert result.get("isError") is True

    def test_simple_command_runs(self, tmp_path: Path) -> None:
        from sidecar.mcp_bridge import SidecarMCPBridge

        bridge = SidecarMCPBridge()
        result = bridge._handle_pty_exec(
            {"command": "echo hello", "cwd": str(tmp_path)}
        )
        assert result.get("isError") is not True
        text = result["content"][0]["text"]
        assert "hello" in text
