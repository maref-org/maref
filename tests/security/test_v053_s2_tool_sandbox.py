"""v0.53 S2 — 工具执行沙箱（ToolSandbox）验收测试。

缺口: 工具执行只有命令级校验（BashValidator），无进程运行时沙箱——
工作目录可逃逸到工作区外、敏感环境变量随子进程继承泄漏、输出/时限无上限。
本套件验证: 工作目录锁定、env 清洗、资源上限 fail-closed、BashTool 生产接线。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maref.codegen.tool import ToolContext, ToolResultStatus
from maref.security.tool_sandbox import SandboxLimits, ToolSandbox
from maref.tools.bash_tool import BashInput, BashTool


class TestSandboxValidate:
    def test_workdir_outside_workspace_blocked(self, tmp_path: Path) -> None:
        sandbox = ToolSandbox()
        result = sandbox.validate(
            workdir="/etc", workspace_root=str(tmp_path), timeout=10, command="ls"
        )
        assert result.blocked
        assert "workdir" in result.reason

    def test_workdir_inside_workspace_allowed(self, tmp_path: Path) -> None:
        sandbox = ToolSandbox()
        result = sandbox.validate(
            workdir=str(tmp_path), workspace_root=str(tmp_path), timeout=10, command="ls"
        )
        assert not result.blocked
        assert Path(result.workdir or "") == Path(str(tmp_path)).resolve()

    def test_timeout_exceeds_limit_blocked(self, tmp_path: Path) -> None:
        sandbox = ToolSandbox(limits=SandboxLimits(max_runtime_seconds=10))
        result = sandbox.validate(
            workdir=None, workspace_root=str(tmp_path), timeout=30, command="ls"
        )
        assert result.blocked
        assert "timeout" in result.reason

    def test_empty_command_blocked(self, tmp_path: Path) -> None:
        sandbox = ToolSandbox()
        result = sandbox.validate(
            workdir=None, workspace_root=str(tmp_path), timeout=10, command=""
        )
        assert result.blocked

    def test_too_many_args_blocked(self, tmp_path: Path) -> None:
        sandbox = ToolSandbox(limits=SandboxLimits(max_args=2))
        result = sandbox.validate(
            workdir=None, workspace_root=str(tmp_path), timeout=10, command="echo a b c"
        )
        assert result.blocked


class TestSandboxEnv:
    def test_clean_env_strips_sensitive_keys(self) -> None:
        sandbox = ToolSandbox()
        env = {
            "PATH": "/usr/bin",
            "OPENAI_API_KEY": "sk-secret",
            "HOME": "/Users/x",
            "DATABASE_PASSWORD": "pw",
            "TZ": "UTC",
        }
        cleaned = sandbox.clean_env(env)
        assert "OPENAI_API_KEY" not in cleaned
        assert "DATABASE_PASSWORD" not in cleaned
        assert cleaned["PATH"] == "/usr/bin"
        assert cleaned["TZ"] == "UTC"

    def test_clean_env_custom_deny_keys(self) -> None:
        sandbox = ToolSandbox(limits=SandboxLimits(deny_env_keys=("SECRET",)))
        cleaned = sandbox.clean_env({"MYTOKEN": "x", "SAFE": "1"})
        assert "MYTOKEN" in cleaned
        assert cleaned["SAFE"] == "1"

    def test_clean_env_preserves_runtime_essentials(self) -> None:
        sandbox = ToolSandbox()
        cleaned = sandbox.clean_env(
            {
                "PATH": "/usr/bin",
                "SSH_AUTH_SOCK": "/tmp/ssh-agent",
                "LANG": "en_US.UTF-8",
                "OPENAI_API_KEY": "sk-secret",
            }
        )
        assert cleaned["SSH_AUTH_SOCK"] == "/tmp/ssh-agent"
        assert cleaned["LANG"] == "en_US.UTF-8"
        assert "OPENAI_API_KEY" not in cleaned

    def test_relative_workdir_resolves_against_root(self, tmp_path: Path) -> None:
        sandbox = ToolSandbox()
        sub = tmp_path / "sub"
        sub.mkdir()
        result = sandbox.validate(
            workdir="sub", workspace_root=str(tmp_path), timeout=10, command="ls"
        )
        assert not result.blocked
        assert Path(result.workdir or "") == sub.resolve()

    def test_relative_workdir_escape_against_root_blocked(self, tmp_path: Path) -> None:
        sandbox = ToolSandbox()
        result = sandbox.validate(
            workdir="../..", workspace_root=str(tmp_path), timeout=10, command="ls"
        )
        assert result.blocked


class TestBashToolIntegration:
    async def test_runs_normal_command(self, tmp_path: Path) -> None:
        tool = BashTool(sandbox=ToolSandbox())
        ctx = ToolContext(workspace_root=str(tmp_path))
        result = await tool.call(BashInput(command="echo hello"), ctx)
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data is not None
        assert "hello" in result.data.stdout

    async def test_workdir_escape_blocked_fail_closed(self, tmp_path: Path) -> None:
        tool = BashTool(sandbox=ToolSandbox())
        ctx = ToolContext(workspace_root=str(tmp_path))
        result = await tool.call(
            BashInput(command="pwd", workdir="/etc"),
            ctx,
        )
        assert result.status == ToolResultStatus.ERROR
        assert "Sandbox" in result.error

    async def test_sensitive_env_not_leaked_to_subprocess(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "supersecret")
        tool = BashTool(sandbox=ToolSandbox())
        ctx = ToolContext(workspace_root=str(tmp_path))
        result = await tool.call(
            BashInput(command="printenv AWS_SECRET_ACCESS_KEY"),
            ctx,
        )
        assert result.data is not None
        assert "supersecret" not in result.data.stdout

    async def test_large_output_truncated(self, tmp_path: Path) -> None:
        sandbox = ToolSandbox(limits=SandboxLimits(max_output_bytes=32))
        tool = BashTool(sandbox=sandbox)
        ctx = ToolContext(workspace_root=str(tmp_path))
        result = await tool.call(
            BashInput(command="python3 -c \"print('x' * 100)\""),
            ctx,
        )
        assert result.data is not None
        assert result.data.stdout.count("x") <= 32
        assert result.truncated is True

    async def test_output_within_limit_not_truncated(self, tmp_path: Path) -> None:
        tool = BashTool(sandbox=ToolSandbox())
        ctx = ToolContext(workspace_root=str(tmp_path))
        result = await tool.call(
            BashInput(command="echo short"),
            ctx,
        )
        assert result.truncated is False

    async def test_execute_path_runs_validate_and_call(self, tmp_path: Path) -> None:
        tool = BashTool(sandbox=ToolSandbox())
        ctx = ToolContext(workspace_root=str(tmp_path))
        result = await tool.execute(BashInput(command="echo via-execute"), ctx)
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data is not None
        assert "via-execute" in result.data.stdout

    async def test_execute_blocked_when_bash_validator_rejects(self, tmp_path: Path) -> None:
        tool = BashTool(sandbox=ToolSandbox())
        ctx = ToolContext(workspace_root=str(tmp_path))
        result = await tool.execute(
            BashInput(command="sudo rm -rf /"),
            ctx,
        )
        assert result.status == ToolResultStatus.BLOCKED

    async def test_timeout_covers_sandbox_validate_violation(self, tmp_path: Path) -> None:
        sandbox = ToolSandbox(limits=SandboxLimits(max_runtime_seconds=10))
        tool = BashTool(sandbox=sandbox)
        ctx = ToolContext(workspace_root=str(tmp_path))
        result = await tool.execute(
            BashInput(command="echo hi", timeout=30),
            ctx,
        )
        assert result.status == ToolResultStatus.ERROR
        assert "Sandbox" in result.error
