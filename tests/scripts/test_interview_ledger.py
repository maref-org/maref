"""访谈账本（scripts/interview_ledger.py）的结构校验与判定门槛回归。

背景（2026-11-21）：产物层诊断的结论是「能力已够、缺外部验证」。访谈账本是把
「聊过了」变成可核验证据的最小载体，因此它必须 fail-closed：

- 结构不合法（缺 consent / 缺金额 / 有 PII）→ 拒绝评估，不能把脏数据算成「没需求」；
- 达到门槛且 0 硬/强信号、0 真实切换 → 判定 kill（exit 3），且不允许改数据救它。

测试只覆盖判定逻辑本身；它不判断访谈内容是否为真，那需要人工核对原件（见 EVIDENCE.md）。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "interview_ledger.py"


def _load_ledger_module():
    spec = importlib.util.spec_from_file_location("maref_interview_ledger", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # 必须注册进 sys.modules：脚本用 dataclass，类创建时 dataclasses 会按
    # `cls.__module__` 回查 sys.modules（Python 3.14 会因此抛 AttributeError）。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ledger = _load_ledger_module()


def _entry(**overrides):
    base = {
        "id": "INT-20261125-01",
        "date": "2026-11-25",
        "persona": "integrator",
        "consent": True,
        "spend_cny": 0,
        "hours_wasted": 0,
        "would_buy": {"signal": "none"},
    }
    base.update(overrides)
    return base


def _write(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "ledger.yaml"
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return path


# ---------------------------------------------------------------- 结构校验


def test_valid_entry_has_no_findings() -> None:
    findings = ledger.validate_ledger({"schema": 1, "interviews": [_entry()]})
    assert findings == []


def test_repository_ledger_is_valid() -> None:
    """仓库里的真实账本必须始终通过校验（空账本也算有效）。"""
    data = yaml.safe_load(
        (REPO_ROOT / "docs/research/interviews/ledger.yaml").read_text(encoding="utf-8")
    )
    assert ledger.validate_ledger(data) == []


def test_pii_fields_are_rejected() -> None:
    findings = ledger.validate_ledger({"interviews": [_entry(name="张总", phone="13800000000")]})
    errors = [f for f in findings if f.level == "ERROR"]
    assert errors, "个人信息字段必须导致 ERROR"
    assert "禁止记录个人信息字段" in errors[0].detail


def test_consent_must_be_explicit_true() -> None:
    findings = ledger.validate_ledger({"interviews": [_entry(consent=None)]})
    assert any("consent" in f.detail for f in findings if f.level == "ERROR")


def test_strong_signal_requires_amount() -> None:
    findings = ledger.validate_ledger(
        {"interviews": [_entry(would_buy={"signal": "quote_requested"})]}
    )
    assert any("amount_cny" in f.detail for f in findings if f.level == "ERROR")


def test_paid_signal_requires_amount() -> None:
    findings = ledger.validate_ledger(
        {"interviews": [_entry(would_buy={"signal": "paid", "amount_cny": 0})]}
    )
    assert any("amount_cny" in f.detail for f in findings if f.level == "ERROR")


def test_missing_artifact_is_error(tmp_path: Path) -> None:
    findings = ledger.validate_ledger(
        {"interviews": [_entry(artifacts=["docs/research/interviews/artifacts/nope.md"])]}
    )
    assert any("证据文件不存在" in f.detail for f in findings if f.level == "ERROR")


def test_existing_artifact_is_ok() -> None:
    findings = ledger.validate_ledger(
        {"interviews": [_entry(artifacts=["docs/research/interviews/EVIDENCE.md"])]}
    )
    assert findings == []


def test_duplicate_ids_rejected() -> None:
    findings = ledger.validate_ledger({"interviews": [_entry(), _entry()]})
    assert any("id 重复" in f.detail for f in findings if f.level == "ERROR")


def test_bad_persona_and_date_rejected() -> None:
    findings = ledger.validate_ledger({"interviews": [_entry(persona="ceo", date="2026/11/25")]})
    details = " ".join(f.detail for f in findings if f.level == "ERROR")
    assert "persona 非法" in details
    assert "date 无法解析" in details


# ---------------------------------------------------------------- 判定门槛


def _summary(entries: list[dict], kill_min: int = 5) -> dict:
    return ledger.evaluate({"interviews": entries}, kill_min)


def test_empty_ledger_is_insufficient_evidence() -> None:
    summary = _summary([])
    assert summary["interviews"] == 0
    assert summary["kill"] is False
    assert "证据不足" in summary["verdict"]


def test_below_threshold_is_not_kill() -> None:
    summary = _summary([_entry() for _ in range(4)], kill_min=5)
    assert summary["kill"] is False
    assert "未到判定门槛" in summary["verdict"]


def test_threshold_without_signals_is_kill() -> None:
    summary = _summary([_entry(id=f"INT-20261125-{i:02d}") for i in range(5)], kill_min=5)
    assert summary["kill"] is True
    assert summary["hard"] == summary["strong"] == summary["switched"] == 0


def test_real_spend_prevents_kill() -> None:
    entries = [_entry(id=f"INT-20261125-{i:02d}") for i in range(4)]
    entries.append(_entry(id="INT-20261125-05", spend_cny=180000))
    summary = _summary(entries, kill_min=5)

    assert summary["spend_cny"] == 180000
    assert summary["switched"] == 1
    assert summary["kill"] is False


def test_overtime_counts_as_switched() -> None:
    entries = [_entry(id=f"INT-20261125-{i:02d}") for i in range(4)]
    entries.append(_entry(id="INT-20261125-05", hours_wasted=240))
    summary = _summary(entries, kill_min=5)

    assert summary["hours_wasted"] == 240
    assert summary["switched"] == 1
    assert summary["kill"] is False


def test_hard_signal_dominates_verdict() -> None:
    entries = [_entry(id=f"INT-20261125-{i:02d}") for i in range(4)]
    entries.append(_entry(id="INT-20261125-05", would_buy={"signal": "paid", "amount_cny": 80000}))
    summary = _summary(entries, kill_min=5)

    assert summary["hard"] == 1
    assert summary["kill"] is False
    assert "硬信号" in summary["verdict"]


def test_signal_counts_are_per_entry() -> None:
    entries = [
        _entry(id="INT-20261125-01", would_buy={"signal": "interest"}),
        _entry(id="INT-20261125-02", would_buy={"signal": "trial", "amount_cny": 10000}),
        _entry(id="INT-20261125-03", would_buy={"signal": "quote_requested", "amount_cny": 30000}),
    ]
    summary = _summary(entries, kill_min=3)

    assert summary["signals"] == {"interest": 1, "trial": 1, "quote_requested": 1}
    assert summary["strong"] == 2
    assert summary["hard"] == 0
    assert "强信号" in summary["verdict"]


# ---------------------------------------------------------------- CLI 行为


def test_cli_invalid_ledger_exits_1(tmp_path: Path) -> None:
    path = _write(tmp_path, {"interviews": [_entry(consent=False)]})
    assert ledger.main(["--file", str(path), "--check"]) == ledger._EXIT_INVALID


def test_cli_missing_file_exits_2(tmp_path: Path) -> None:
    assert ledger.main(["--file", str(tmp_path / "absent.yaml"), "--check"]) == ledger._EXIT_USAGE


def test_cli_kill_exits_3(tmp_path: Path) -> None:
    entries = [_entry(id=f"INT-20261125-{i:02d}") for i in range(5)]
    path = _write(tmp_path, {"interviews": entries})
    assert ledger.main(["--file", str(path), "--eval", "--kill-min", "5"]) == ledger._EXIT_KILL


def test_cli_json_output_is_machine_readable(tmp_path: Path, capsys) -> None:
    entries = [_entry(id=f"INT-20261125-{i:02d}") for i in range(2)]
    path = _write(tmp_path, {"interviews": entries})

    assert ledger.main(["--file", str(path), "--eval", "--json"]) == ledger._EXIT_OK
    out = capsys.readouterr().out
    payload = json.loads(out[out.index("{") :])
    assert payload["interviews"] == 2


def test_cli_report_has_table_and_no_person_names(tmp_path: Path, capsys) -> None:
    path = _write(tmp_path, {"interviews": [_entry(spend_cny=180000)]})

    assert ledger.main(["--file", str(path), "--report"]) == ledger._EXIT_OK
    out = capsys.readouterr().out
    assert "| id | 日期 | 角色 | 信号 |" in out
    assert "180000" in out
    assert "访谈账本摘要" in out


@pytest.mark.parametrize("flag", ["--check", "--eval", "--report"])
def test_cli_default_ledger_path_works(flag: str, capsys) -> None:
    """默认路径指向真实账本；无论哪个子命令都不能因路径写错而崩。"""
    assert ledger.main([flag]) in (0, 1, 3)
    capsys.readouterr()
