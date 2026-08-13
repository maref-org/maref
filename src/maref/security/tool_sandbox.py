"""v0.53 S2 — 工具执行沙箱：为外部进程提供运行时隔离（fail-closed）。

在命令级校验（BashValidator）之上增加进程运行时沙箱，堵住三个缺口：
1. 工作目录逃逸 — workdir 必须位于 workspace_root 下，锁死进程可写范围；
2. 敏感环境变量泄漏 — 子进程环境清洗，剔除 key 含敏感词的变量；
3. 资源无上限 — 超时/参数数量/输出大小一律限制，超限拒绝或截断。

安全级别最高：任意校验失败即拒绝执行（blocked），不静默放行。
"""

from __future__ import annotations

import os
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SandboxLimits:
    """沙箱资源上限（frozen，构造后不可改）。"""

    max_output_bytes: int = 64 * 1024
    max_runtime_seconds: int = 120
    max_args: int = 128
    allow_env_keys: tuple[str, ...] = (
        # 运行时必需且非敏感：SSH agent 转发、locale/终端
        "SSH_AUTH_SOCK",
        "SSH_AGENT_PID",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
    )
    deny_env_keys: tuple[str, ...] = (
        "KEY",
        "SECRET",
        "PASSWORD",
        "TOKEN",
        "CREDENTIAL",
        "AUTH",
    )


@dataclass
class SandboxResult:
    """沙箱校验结果。blocked=True 时 reason 说明拒绝原因。"""

    blocked: bool = False
    reason: str = ""
    workdir: str = ""
    timeout: int = 30
    max_output: int = 64 * 1024


class ToolSandbox:
    """外部命令进程沙箱：工作目录锁定 + env 清洗 + 资源上限。

    Usage:
        sandbox = ToolSandbox()
        result = sandbox.validate(workdir=wd, workspace_root=root, timeout=30, command=cmd)
        if result.blocked:
            raise SandboxError(result.reason)
        env = sandbox.clean_env()
        ...

    说明: 本实现为纯 Python 进程边界（路径/环境/参数约束）。
    容器级隔离（cgroup/seccomp/网络）由部署层 k8s admission 策略提供。
    """

    def __init__(self, limits: SandboxLimits | None = None) -> None:
        self.limits = limits if limits is not None else SandboxLimits()

    def validate(
        self,
        workdir: str | None,
        workspace_root: str,
        timeout: int,
        command: str,
    ) -> SandboxResult:
        """校验执行前约束，返回 resolved workdir / timeout / max_output。

        fail-closed: 任意一项违规即 blocked，reason 说明原因。
        """
        result = SandboxResult(max_output=self.limits.max_output_bytes)

        root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        if workdir is not None:
            workdir_path = Path(workdir)
            if not workdir_path.is_absolute():
                workdir_path = root / workdir_path
            wd = workdir_path.resolve()
            if wd != root and not wd.is_relative_to(root):
                result.blocked = True
                result.reason = (
                    f"Sandbox: workdir {wd} escapes workspace root {root}"
                )
                return result
            result.workdir = str(wd)
        else:
            result.workdir = str(root)

        if not (0 < timeout <= self.limits.max_runtime_seconds):
            result.blocked = True
            result.reason = (
                f"Sandbox: timeout {timeout}s exceeds limit "
                f"{self.limits.max_runtime_seconds}s"
            )
            return result
        result.timeout = timeout

        tokens = shlex.split(command)
        if not tokens:
            result.blocked = True
            result.reason = "Sandbox: empty command"
            return result
        if len(tokens) > self.limits.max_args:
            result.blocked = True
            result.reason = (
                f"Sandbox: argument count {len(tokens)} exceeds "
                f"limit {self.limits.max_args}"
            )
            return result

        return result

    def clean_env(
        self,
        source: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        """清洗环境变量：剔除含敏感词的变量，保留白名单 + 其余安全项。

        source 默认 os.environ；allow_env_keys 显式放行（即使含敏感词）。
        """
        env = dict(os.environ) if source is None else dict(source)
        denied: set[str] = set()
        for key in env:
            if key in self.limits.allow_env_keys:
                continue
            lowered = key.casefold()
            if any(
                needle.casefold() in lowered
                for needle in self.limits.deny_env_keys
            ):
                denied.add(key)
        for key in denied:
            env.pop(key, None)
        return env


class SandboxError(Exception):
    """沙箱校验不通过时抛出的异常（fail-closed）。"""
