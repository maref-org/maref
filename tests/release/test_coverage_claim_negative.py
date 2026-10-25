"""覆盖率声称对账负向测试：偏差、unverified、缺 run id、run 不匹配必须非 0 退出。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK = REPO_ROOT / "scripts" / "coverage_claim_check.py"


def _write_inputs(
    tmp_path: Path,
    *,
    claimed: float,
    actual: float,
    source_run_id: str | None = "123456",
) -> tuple[Path, Path]:
    state = {
        "version": 19,
        "governance": {
            "coverage": {
                "value": claimed,
                "source_run_id": source_run_id,
                "verified_at": "2026-10-26T00:00:00Z",
            }
        },
    }
    coverage = {
        "totals": {"percent_covered": actual},
        "files": {
            "src/maref/example.py": {"summary": {"covered_lines": 80, "num_statements": 100}}
        },
    }
    state_path = tmp_path / "STATE.yaml"
    coverage_path = tmp_path / "coverage.json"
    state_path.write_text(yaml.safe_dump(state, sort_keys=False))
    coverage_path.write_text(json.dumps(coverage))
    return state_path, coverage_path


def _run(state: Path, coverage: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK), "--state", str(state), "--coverage", str(coverage), *extra],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_within_tolerance_passes(tmp_path: Path) -> None:
    state, coverage = _write_inputs(tmp_path, claimed=76.36, actual=76.40)
    proc = _run(state, coverage)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CLAIM CHECK OK" in proc.stdout


def test_delta_over_tolerance_fails(tmp_path: Path) -> None:
    state, coverage = _write_inputs(tmp_path, claimed=76.36, actual=76.50)
    proc = _run(state, coverage)
    assert proc.returncode == 1
    assert "!= artifact" in proc.stdout


def test_unverified_claim_fails(tmp_path: Path) -> None:
    state, coverage = _write_inputs(tmp_path, claimed=76.36, actual=76.36)
    data = yaml.safe_load(state.read_text())
    data["governance"]["coverage"]["value"] = "unverified"
    state.write_text(yaml.safe_dump(data, sort_keys=False))
    proc = _run(state, coverage)
    assert proc.returncode == 1
    assert "unverified" in proc.stdout


def test_numeric_claim_without_source_run_id_fails(tmp_path: Path) -> None:
    state, coverage = _write_inputs(tmp_path, claimed=76.36, actual=76.36, source_run_id=None)
    proc = _run(state, coverage)
    assert proc.returncode == 1
    assert "source_run_id" in proc.stdout


def test_run_id_mismatch_fails(tmp_path: Path) -> None:
    state, coverage = _write_inputs(tmp_path, claimed=76.36, actual=76.36, source_run_id="111")
    proc = _run(state, coverage, "--run-id", "222")
    assert proc.returncode == 1
    assert "!= checked run" in proc.stdout


def test_run_id_match_passes(tmp_path: Path) -> None:
    state, coverage = _write_inputs(tmp_path, claimed=76.36, actual=76.36, source_run_id="111")
    proc = _run(state, coverage, "--run-id", "111")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_missing_artifact_is_tooling_error(tmp_path: Path) -> None:
    state, _ = _write_inputs(tmp_path, claimed=76.36, actual=76.36)
    proc = _run(state, tmp_path / "absent.json")
    assert proc.returncode == 2
