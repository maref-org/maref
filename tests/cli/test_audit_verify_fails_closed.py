"""`maref audit verify` 的输入语义：区分"不可解释"（exit 2）与"被篡改"（exit 1）。

回归背景（2026-11-21）：
- v0.55.2：空文件 / 非 JSON 文件都输出 ``Integrity intact ✅ Yes`` + exit 0（fail-open）；
- v0.55.3 第一版：全部压成 ``FAILED`` + exit 1 —— 不再 fail-open，但调用方无法区分
  "没有事件"与"被攻击"，也不能把 exit 1 当作"证据被破坏"的稳定信号。

现在的契约：
- 0 = 完好（至少一条签名验证通过，链连续）；
- 1 = 有内容但验证失败（篡改 / 未签名 / 缺公钥导致不可验证）；
- 2 = 输入不可用（文件不存在 / 空日志 / 行不是 JSON 对象）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from maref.governance.audit import AuditLogger
from maref_lite.cli import app

runner = CliRunner()


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("empty.jsonl", ""),
        ("blank_lines.jsonl", "\n\n\n"),
    ],
)
def test_verify_reports_empty_log_as_exit_2(tmp_path: Path, name: str, content: str) -> None:
    log = tmp_path / name
    log.write_text(content, encoding="utf-8")

    result = runner.invoke(app, ["audit", "verify", "-f", str(log)])
    output = _plain(result.output)

    assert result.exit_code == 2, output
    assert "EMPTY" in output
    assert "✅" not in output


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("garbage.jsonl", "not json at all\n"),
        ("mixed.jsonl", '{"id": "ok"}\n<<<<<<< HEAD\n'),
    ],
)
def test_verify_reports_unparsable_lines_as_exit_2(tmp_path: Path, name: str, content: str) -> None:
    log = tmp_path / name
    log.write_text(content, encoding="utf-8")

    result = runner.invoke(app, ["audit", "verify", "-f", str(log)])
    output = _plain(result.output)

    assert result.exit_code == 2, output
    assert "UNREADABLE" in output
    # 格式错误不该被计成"被篡改"
    assert "tampered or unverifiable" not in output


def test_verify_still_reports_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.jsonl"

    result = runner.invoke(app, ["audit", "verify", "-f", str(missing)])
    output = _plain(result.output)

    assert result.exit_code == 2, output
    assert "AUDIT LOG NOT FOUND" in output


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
    assert result.exit_code == 2


def _write_signed_log(tmp_path: Path, entries: int = 3) -> Path:
    log = tmp_path / ".governance" / "audit.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    # CLI 以 hmac_key="" 构造 logger；验证时回落到磁盘 key 文件。
    (tmp_path / ".maraf_hmac_key").write_text("k", encoding="utf-8")
    logger = AuditLogger(log, hmac_key="k")
    for index in range(entries):
        logger.log("governance", f"agent-{index}", "tool_call", details="demo")
    return log


def test_verify_intact_log_exits_0(tmp_path: Path) -> None:
    log = _write_signed_log(tmp_path)

    result = runner.invoke(app, ["audit", "verify", "-f", str(log)])
    output = _plain(result.output)

    assert result.exit_code == 0, output
    assert "VERIFIED" in output
    assert "3/3" in output


def test_verify_tampered_log_exits_1(tmp_path: Path) -> None:
    log = _write_signed_log(tmp_path)
    lines = log.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace('"demo"', '"tampered"')
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = runner.invoke(app, ["audit", "verify", "-f", str(log)])
    output = _plain(result.output)

    assert result.exit_code == 1, output
    assert "FAILED" in output
    assert "tampered" in output.lower()
