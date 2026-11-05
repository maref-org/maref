"""tool 层审计留痕（第 5 项第二步，2026-11-05）。

验证 ToolSandbox 与 BashValidator 在注入 AuditLogger 后：
- DENY 必留痕
- ALLOW 仅在 audit_all=True 时留痕（默认关闭，避免审计洪水）
- 命令/参数只记 digest，原文不落盘
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maref.codegen.permissions import BashValidator
from maref.governance.audit import AuditLogger
from maref.security.tool_sandbox import ToolSandbox


@pytest.fixture()
def audit_log(tmp_path: Path) -> tuple[AuditLogger, Path]:
    path = tmp_path / "audit.jsonl"
    return AuditLogger(path, hmac_key="test-key"), path


def _entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class TestToolSandboxAudit:
    def test_deny_is_recorded(self, audit_log, tmp_path: Path) -> None:
        logger, path = audit_log
        sandbox = ToolSandbox(audit_logger=logger)
        result = sandbox.validate("/etc/evil", str(tmp_path), 30, "ls")
        assert result.blocked
        entries = _entries(path)
        assert len(entries) == 1
        assert entries[0]["actor"] == "tool_sandbox"
        assert entries[0]["action"] == "SANDBOX_DENY"

    def test_allow_not_recorded_by_default(self, audit_log, tmp_path: Path) -> None:
        logger, path = audit_log
        sandbox = ToolSandbox(audit_logger=logger)
        assert not sandbox.validate(None, str(tmp_path), 30, "echo hi").blocked
        assert _entries(path) == []

    def test_allow_recorded_when_audit_all(self, audit_log, tmp_path: Path) -> None:
        logger, path = audit_log
        sandbox = ToolSandbox(audit_logger=logger, audit_all=True)
        assert not sandbox.validate(None, str(tmp_path), 30, "echo hi").blocked
        entries = _entries(path)
        assert len(entries) == 1
        assert entries[0]["action"] == "SANDBOX_ALLOW"

    def test_command_text_not_stored(self, audit_log, tmp_path: Path) -> None:
        logger, path = audit_log
        secret = "echo super-secret-token-value"
        sandbox = ToolSandbox(audit_logger=logger, audit_all=True)
        sandbox.validate(None, str(tmp_path), 30, secret)
        raw = path.read_text()
        assert secret not in raw
        assert "super-secret-token-value" not in raw

    def test_no_logger_keeps_pure_semantics(self, tmp_path: Path) -> None:
        sandbox = ToolSandbox()
        assert sandbox.validate("/etc/evil", str(tmp_path), 30, "ls").blocked


class TestBashValidatorAudit:
    def test_deny_is_recorded(self, audit_log) -> None:
        logger, path = audit_log
        validator = BashValidator(audit_logger=logger)
        ok, reason, _ = validator.validate("sudo rm -rf /")
        assert not ok
        entries = _entries(path)
        assert len(entries) == 1
        assert entries[0]["actor"] == "bash_validator"
        assert entries[0]["action"] == "BASH_DENY"

    def test_allow_not_recorded_by_default(self, audit_log) -> None:
        logger, path = audit_log
        validator = BashValidator(audit_logger=logger)
        assert validator.validate("echo hi")[0]
        assert _entries(path) == []

    def test_allow_recorded_when_audit_all(self, audit_log) -> None:
        logger, path = audit_log
        validator = BashValidator(audit_logger=logger, audit_all=True)
        assert validator.validate("echo hi")[0]
        assert _entries(path)[0]["action"] == "BASH_ALLOW"

    def test_command_text_not_stored(self, audit_log) -> None:
        logger, path = audit_log
        validator = BashValidator(audit_logger=logger, audit_all=True)
        validator.validate("echo my-password-is-hunter2")
        assert "hunter2" not in path.read_text()
