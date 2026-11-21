"""`maref audit verify` 必须 fail-closed：解析不出条目时不得报 "intact".

回归背景（2026-11-21 实测，干净安装）：
- 空文件 → ``Total entries 0`` + ``Integrity intact ✅ Yes`` + exit 0
- 内容为 ``not json at all`` → 同上
对于以"可验证审计链"为差异化的治理产品，这是最危险的一类缺陷：
攻击者只需给一个空文件，就能拿到一张"完整"的回执。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from maref_lite.cli import app

runner = CliRunner()


def _plain(text: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("empty.jsonl", ""),
        ("garbage.jsonl", "not json at all\n"),
        ("blank_lines.jsonl", "\n\n\n"),
    ],
)
def test_verify_refuses_zero_parseable_entries(tmp_path: Path, name: str, content: str) -> None:
    log = tmp_path / name
    log.write_text(content, encoding="utf-8")

    result = runner.invoke(app, ["audit", "verify", "-f", str(log)])
    output = _plain(result.output)

    assert result.exit_code == 1, output
    assert "integrity intact" in output.lower()
    assert "❌ No" in output
    assert "✅" not in output


def test_verify_still_reports_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.jsonl"

    result = runner.invoke(app, ["audit", "verify", "-f", str(missing)])
    output = _plain(result.output)

    assert result.exit_code == 1, output
    assert "Audit log not found" in output


def test_verify_prints_resolved_path(tmp_path: Path, monkeypatch) -> None:
    """裸文件名会被沙箱重定向；必须把真实读取路径打出来，否则用户以为读的是 ./x.jsonl。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MAREF_AUDIT_PATH", raising=False)
    (tmp_path / ".governance").mkdir()
    (tmp_path / ".governance" / "audit.jsonl").write_text("", encoding="utf-8")

    result = runner.invoke(app, ["audit", "verify", "-f", "audit.jsonl"])
    output = _plain(result.output)

    assert "Resolved:" in output, output
    assert ".governance/audit.jsonl" in output
    assert result.exit_code == 1
