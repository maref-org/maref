#!/usr/bin/env python3
"""第 5 项（第二步）：ToolSandbox 写审计；BashValidator 写审计。

背景（2026-11-05 命令注入审计）：
    审计矩阵只看到 inbound.gate 的记录，tool 层（tool_sandbox / BashValidator）
    是否真的在工作无法从审计验证。用户要求"请求经过的每一层都留痕"。

改动：
    1. ToolSandbox：
       - __init__ 新增 audit_logger / audit_all（默认 None/False，保持纯校验语义）
       - _audit() 写 log_decision；命令只记 sha256 前 16 位（不落原文）
       - validate() 的 4 个 DENY 分支 + 1 个 ALLOW 出口调用
    2. BashValidator：
       - 同样可选 audit_logger；validate() 在 DENY/ALLOW 时留痕

用法：
    python3 scripts/apply_tool_layer_audit.py --check | --revert | (默认应用)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = ROOT / "src/maref/security/tool_sandbox.py"
BASH = ROOT / "src/maref/codegen/permissions.py"

# ---------------- ToolSandbox ----------------
SB_IMPORT_OLD = "import os\nimport shlex"
SB_IMPORT_NEW = "import hashlib\nimport os\nimport shlex"

SB_INIT_OLD = '''    def __init__(self, limits: SandboxLimits | None = None) -> None:
        self.limits = limits if limits is not None else SandboxLimits()'''

SB_INIT_NEW = '''    def __init__(
        self,
        limits: SandboxLimits | None = None,
        *,
        audit_logger: object | None = None,
        audit_all: bool = False,
    ) -> None:
        self.limits = limits if limits is not None else SandboxLimits()
        self._audit_logger = audit_logger
        self._audit_all = audit_all

    def _audit(self, decision: str, reason: str, command: str) -> None:
        """本层裁决留痕。命令只记 digest，不落原文（防 secret/PII 入审计链）。"""
        logger = self._audit_logger
        if logger is None:
            return
        if decision == "ALLOW" and not self._audit_all:
            return
        logger.log_decision(  # type: ignore[attr-defined]
            actor="tool_sandbox",
            action=f"SANDBOX_{decision}",
            reason=reason,
            command_digest=hashlib.sha256(command.encode("utf-8", "ignore")).hexdigest()[:16],
        )'''

# 4 个 DENY 分支 + 1 个 ALLOW 出口
DENY_BLOCKS = [
    (
        '''                result.blocked = True
                result.reason = f"Sandbox: workdir {wd} escapes workspace root {root}"
                return result''',
        '''                result.blocked = True
                result.reason = f"Sandbox: workdir {wd} escapes workspace root {root}"
                self._audit("DENY", result.reason, command)
                return result''',
    ),
    (
        '''            result.blocked = True
            result.reason = (
                f"Sandbox: timeout {timeout}s exceeds limit {self.limits.max_runtime_seconds}s"
            )
            return result''',
        '''            result.blocked = True
            result.reason = (
                f"Sandbox: timeout {timeout}s exceeds limit {self.limits.max_runtime_seconds}s"
            )
            self._audit("DENY", result.reason, command)
            return result''',
    ),
    (
        '''        if not tokens:
            result.blocked = True
            result.reason = "Sandbox: empty command"
            return result''',
        '''        if not tokens:
            result.blocked = True
            result.reason = "Sandbox: empty command"
            self._audit("DENY", result.reason, command)
            return result''',
    ),
    (
        '''        if len(tokens) > self.limits.max_args:
            result.blocked = True
            result.reason = (
                f"Sandbox: argument count {len(tokens)} exceeds limit {self.limits.max_args}"
            )
            return result

        return result''',
        '''        if len(tokens) > self.limits.max_args:
            result.blocked = True
            result.reason = (
                f"Sandbox: argument count {len(tokens)} exceeds limit {self.limits.max_args}"
            )
            self._audit("DENY", result.reason, command)
            return result

        self._audit("ALLOW", "", command)
        return result''',
    ),
]

# ---------------- BashValidator ----------------
BASH_INIT_OLD = '''    BLOCKED_COMMANDS: set[str] = {"sudo", "su", "doas", "pkexec"}
    BLOCKED_PATHS: set[str] = {"/etc", "/proc", "/sys", "/dev"}

    def validate(self, command: str) -> tuple[bool, str, list[str]]:
        warnings: list[str] = []'''

BASH_INIT_NEW = '''    BLOCKED_COMMANDS: set[str] = {"sudo", "su", "doas", "pkexec"}
    BLOCKED_PATHS: set[str] = {"/etc", "/proc", "/sys", "/dev"}

    def __init__(
        self,
        *,
        audit_logger: object | None = None,
        audit_all: bool = False,
    ) -> None:
        self._audit_logger = audit_logger
        self._audit_all = audit_all

    def _audit(self, decision: str, reason: str, command: str) -> None:
        """本层裁决留痕（命令只记 digest）。"""
        logger = self._audit_logger
        if logger is None:
            return
        if decision == "ALLOW" and not self._audit_all:
            return
        logger.log_decision(  # type: ignore[attr-defined]
            actor="bash_validator",
            action=f"BASH_{decision}",
            reason=reason,
            command_digest=hashlib.sha256(command.encode("utf-8", "ignore")).hexdigest()[:16],
        )

    def validate(self, command: str) -> tuple[bool, str, list[str]]:
        warnings: list[str] = []'''

BASH_DENY_OLD = '''        if self.PROC_ENVIRON_PATTERN.search(command):
            return False, "Access to process environment is blocked", warnings

        tokens = command.split()
        if tokens and tokens[0] in self.BLOCKED_COMMANDS:
            return False, f"Command '{tokens[0]}' is blocked", warnings'''

BASH_DENY_NEW = '''        if self.PROC_ENVIRON_PATTERN.search(command):
            reason = "Access to process environment is blocked"
            self._audit("DENY", reason, command)
            return False, reason, warnings

        tokens = command.split()
        if tokens and tokens[0] in self.BLOCKED_COMMANDS:
            reason = f"Command '{tokens[0]}' is blocked"
            self._audit("DENY", reason, command)
            return False, reason, warnings'''

BASH_ALLOW_OLD = '''        if not tokens:
            return False, "Empty command", warnings

        return True, "", warnings'''

BASH_ALLOW_NEW = '''        if not tokens:
            self._audit("DENY", "Empty command", command)
            return False, "Empty command", warnings

        self._audit("ALLOW", "", command)
        return True, "", warnings'''

PAIRS = [
    (SANDBOX, SB_IMPORT_OLD, SB_IMPORT_NEW),
    (SANDBOX, SB_INIT_OLD, SB_INIT_NEW),
    *[(SANDBOX, old, new) for old, new in DENY_BLOCKS],
    (BASH, BASH_INIT_OLD, BASH_INIT_NEW),
    (BASH, BASH_DENY_OLD, BASH_DENY_NEW),
    (BASH, BASH_ALLOW_OLD, BASH_ALLOW_NEW),
]

# BashValidator 的 _audit 需要 hashlib
BASH_HASHLIB_OLD = "import re\n"
BASH_HASHLIB_NEW = "import hashlib\nimport re\n"


def main() -> int:
    if not SANDBOX.exists() or not BASH.exists():
        print("ERROR: target file missing")
        return 1

    check = "--check" in sys.argv
    revert = "--revert" in sys.argv

    if revert:
        for path in {p for p, _, _ in PAIRS}:
            text = path.read_text(encoding="utf-8")
            for p, old, new in PAIRS:
                if p == path and new in text:
                    text = text.replace(new, old, 1)
            text = text.replace(BASH_HASHLIB_NEW, BASH_HASHLIB_OLD, 1) if path == BASH else text
            path.write_text(text, encoding="utf-8")
        print("reverted")
        return 0

    # 检查 BashValidator 是否需要 hashlib
    bash_text = BASH.read_text(encoding="utf-8")
    need_hash = BASH_INIT_NEW not in bash_text

    pending = []
    for path, old, new in PAIRS:
        text = path.read_text(encoding="utf-8")
        if new not in text:
            if old not in text:
                raise SystemExit(f"ERROR: anchor not found in {path.name}: {old[:60]!r}")
            pending.append((path, old, new))

    if not pending:
        print("already applied")
        return 0

    if check:
        print(f"NOT applied ({len(pending)} block(s) pending)")
        return 2

    for path, old, new in pending:
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    if need_hash and "import hashlib" not in BASH.read_text(encoding="utf-8"):
        t = BASH.read_text(encoding="utf-8")
        BASH.write_text(t.replace(BASH_HASHLIB_OLD, BASH_HASHLIB_NEW, 1), encoding="utf-8")

    print(f"applied {len(pending)} block(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
