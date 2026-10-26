"""Meta 门禁负向测试：all_passed=false 必须以非 0 退出。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "scripts" / "meta_audit_gate.py"


def _run(report: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), "--report", str(report), *extra],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _summary(all_passed: bool, m2: bool = True) -> dict:
    return {
        "summary": {
            "m0_passed": True,
            "m1_passed": True,
            "m2_passed": m2,
            "m3_passed": True,
            "m4_passed": True,
            "all_passed": all_passed,
        }
    }


def test_all_true_report_passes(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_summary(all_passed=True)))
    proc = _run(report, "--all")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_false_check_fails(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_summary(all_passed=False, m2=False)))
    proc = _run(report, "--all")
    assert proc.returncode == 1
    assert "m2" in proc.stderr


def test_all_passed_false_cannot_be_masked_by_narrow_require(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_summary(all_passed=False, m2=False)))
    proc = _run(report, "--require", "m0")
    assert proc.returncode == 1
    assert "all_passed" in proc.stderr


def test_report_without_summary_is_tooling_error(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"m0": {}}))
    proc = _run(report)
    assert proc.returncode == 2


def test_missing_report_file_is_tooling_error(tmp_path: Path) -> None:
    proc = _run(tmp_path / "missing.json")
    assert proc.returncode == 2
