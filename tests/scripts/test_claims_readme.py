"""README 对外数字的守卫：只允许"下限"，不允许"无来源精确数"。

回归背景（2026-11-21 复盘）：
- README 写 "15,387 passing tests (CI, main@0f0c7632)"，而当前 main 实测 collect 17,137；
- 同一份 README 同时出现 "~87% test coverage" 与健康表 "76.6%"，STATE.yaml 记录的是 76.50%；
- 三个数没有一个能由命令复算，而 claims.yaml 自己的规则要求"公开数字必须登记"。

本文件锁死修法：README 只能写 `N,NNN+ test functions` 下限，覆盖率徽章必须等于
STATE.yaml 的实测值，`~NN% test coverage` 这类表述回归即报错。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_PATH = REPO_ROOT / "scripts" / "claims_probe.py"


def _load_probe():
    spec = importlib.util.spec_from_file_location("maref_claims_probe_readme", PROBE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


probe = _load_probe()


def test_readme_tests_floor_matches_ledger() -> None:
    assert probe.readme_tests_floor() == "16000"


def test_tests_floor_is_below_actual_function_count() -> None:
    # 下限声明必须仍然成立：函数数一旦低于 16000，claims 的 min 会先红。
    assert int(probe.count_tests()) >= int(probe.readme_tests_floor())


def test_readme_coverage_badge_matches_state() -> None:
    assert probe.coverage_readme_badge() == probe.coverage_state()


def test_state_coverage_is_two_decimals() -> None:
    value = probe.coverage_state()
    assert value.count(".") == 1
    assert len(value.split(".")[1]) == 2


def test_stale_aggregate_coverage_claim_is_rejected(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "README.md").write_text(
        "badge/coverage-76.5%25 ... Governance modules sit at ~87% test coverage.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(probe, "ROOT", tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        probe.coverage_readme_badge()

    assert "无来源聚合数" in str(excinfo.value)


def test_missing_coverage_badge_is_rejected(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "README.md").write_text("no badge here\n", encoding="utf-8")
    monkeypatch.setattr(probe, "ROOT", tmp_path)

    with pytest.raises(SystemExit):
        probe.coverage_readme_badge()


def test_missing_tests_phrase_is_rejected(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "README.md").write_text("15,387 passing tests\n", encoding="utf-8")
    monkeypatch.setattr(probe, "ROOT", tmp_path)

    with pytest.raises(SystemExit):
        probe.readme_tests_floor()


def test_missing_state_coverage_is_rejected(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "STATE.yaml").write_text("project:\n  version: 1\n", encoding="utf-8")
    monkeypatch.setattr(probe, "ROOT", tmp_path)

    with pytest.raises(SystemExit):
        probe.coverage_state()
