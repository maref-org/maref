"""审计日志路径语义：显式路径必须被尊重，沙箱前缀不得叠加两次。

回归背景（2026-11-21，公开仓 v0.55.2 实测）：
- `AuditLogger("audit.jsonl")` → `.governance/audit.jsonl`（沙箱，符合设计）；
- `AuditLogger(".governance/audit.jsonl")` → `.governance/.governance/audit.jsonl`（前缀叠加）；
- 于是 `maref audit verify -f .governance/audit.jsonl` 读到的是空文件，
  旧版 CLI 还把它报成 "Integrity intact ✅ Yes"。
"""

from __future__ import annotations

from pathlib import Path

from maref.governance.audit import AuditLogger


def _write_three(logger: AuditLogger) -> None:
    for index in range(3):
        logger.log("governance", f"agent-{index}", "tool_call", details="demo")


def test_bare_filename_goes_to_sandbox(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MAREF_AUDIT_PATH", raising=False)

    logger = AuditLogger("audit.jsonl", hmac_key="k")
    _write_three(logger)

    assert (tmp_path / ".governance" / "audit.jsonl").is_file()


def test_sandbox_prefix_is_not_doubled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MAREF_AUDIT_PATH", raising=False)

    logger = AuditLogger(".governance/audit.jsonl", hmac_key="k")
    _write_three(logger)

    assert logger._path == Path(".governance/audit.jsonl")
    assert (tmp_path / ".governance" / "audit.jsonl").is_file()
    assert not (tmp_path / ".governance" / ".governance").exists()


def test_absolute_path_is_used_verbatim(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "audit.jsonl"
    target.parent.mkdir(parents=True)

    logger = AuditLogger(target, hmac_key="k")

    assert logger._path == target


def test_roundtrip_verify_reads_what_was_written(tmp_path: Path, monkeypatch) -> None:
    """写 `.governance/x.jsonl` 后，用同一路径验签必须看到 3 条。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MAREF_AUDIT_PATH", raising=False)

    _write_three(AuditLogger(".governance/audit.jsonl", hmac_key="k"))
    result = AuditLogger(".governance/audit.jsonl", hmac_key="k").verify_integrity()

    assert result["total_entries"] == 3
    assert result["valid_signatures"] == 3
    assert result["integrity_intact"] is True


def test_marf_audit_path_env_is_respected(tmp_path: Path, monkeypatch) -> None:
    sandbox = tmp_path / "elsewhere"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MAREF_AUDIT_PATH", str(sandbox))

    logger = AuditLogger("audit.jsonl", hmac_key="k")
    _write_three(logger)

    assert logger._path == sandbox / "audit.jsonl"
    assert (sandbox / "audit.jsonl").is_file()
