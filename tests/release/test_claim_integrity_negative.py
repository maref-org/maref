"""声称完整性门禁负向测试：证据指针不可解析必须以非 0 退出。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAIM = REPO_ROOT / "scripts" / "claim_integrity_gate.py"
SHA = "27978a4fcac9f638eeadc9870f3c7dff3bbfa396"

FAKE_GH = """#!/usr/bin/env python3
import json
import os
import sys

scenario = os.environ.get("FAKE_GH_SCENARIO", "ok")
if scenario == "not_found":
    print("gh: Not Found (HTTP 404)", file=sys.stderr)
    sys.exit(1)
data = {
    "id": 1,
    "head_sha": os.environ.get("FAKE_GH_SHA", "@SHA@"),
    "conclusion": os.environ.get("FAKE_GH_CONCLUSION", "success"),
    "status": "completed",
}
print(json.dumps(data))
""".replace("@SHA@", SHA)


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        },
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout.strip()


def _root(tmp_path: Path, *, d1_sha: str | None = None) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nversion = "0.54.3"\n')
    (root / "CHANGELOG.md").write_text("## [0.54.3] - test\n")
    (root / "docs").mkdir()
    (root / "docs" / "CONSTITUTION.md").write_text("# MAREF 宪法 v1.8\n")
    (root / ".githooks").mkdir()
    (root / ".githooks" / "pre-push").write_text("#!/bin/sh\n")

    _git(root, "init", "-q")
    _git(root, "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "init")
    head = _git(root, "rev-parse", "HEAD")

    state = {
        "version": 19,
        "project": {
            "name": "MAREF",
            "current_release": "0.54.3",
            "public_repo": "https://github.com/maref-org/maref",
            "constitution_version": "v1.8",
            "rsi_level": {"value": "conditional", "verified_at": "2026-10-19"},
        },
        "track_b": {
            "pre_push_hook": "present",
            "ci_status": {
                "value": "green",
                "run_id": 40197782331,
                "sha": SHA,
                "verified_at": "2026-10-25T13:28:43Z",
            },
            "security_scan": {
                "value": "green",
                "run_id": 40197782006,
                "sha": SHA,
                "verified_at": "2026-10-25T13:28:42Z",
            },
        },
        "governance": {"coverage": {"value": "unverified", "overall": None}},
        "d1_gate": {
            "value": "failed",
            "sha": d1_sha or head,
            "verified_at": "2026-10-25T14:07:59Z",
        },
    }
    (root / "STATE.yaml").write_text(yaml.safe_dump(state, sort_keys=False))

    bindir = tmp_path / "bin"
    bindir.mkdir()
    gh = bindir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    return root


def _run(root: Path, *extra: str, scenario: str = "ok", **env: str):
    bindir = root.parent / "bin"
    proc_env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ.get('PATH', '')}",
        "FAKE_GH_SCENARIO": scenario,
        **env,
    }
    return subprocess.run(
        [sys.executable, str(CLAIM), "--root", str(root), "--json", *extra],
        capture_output=True,
        text=True,
        timeout=120,
        env=proc_env,
    )


def test_resolvable_pointers_pass(tmp_path: Path) -> None:
    proc = _run(_root(tmp_path))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["errors"] == 0


def test_missing_run_fails(tmp_path: Path) -> None:
    proc = _run(_root(tmp_path), scenario="not_found")
    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    assert report["errors"] >= 1
    assert any("不可解析" in f["detail"] for f in report["findings"])


def test_sha_mismatch_fails(tmp_path: Path) -> None:
    proc = _run(_root(tmp_path), FAKE_GH_SHA="f" * 40)
    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    assert any("SHA 不匹配" in f["detail"] for f in report["findings"])


def test_green_claim_with_failed_run_fails(tmp_path: Path) -> None:
    proc = _run(_root(tmp_path), FAKE_GH_CONCLUSION="failure")
    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    assert any("conclusion=failure" in f["detail"] for f in report["findings"])


def test_unknown_d1_sha_fails(tmp_path: Path) -> None:
    proc = _run(_root(tmp_path, d1_sha="0" * 40))
    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    assert any("不在本地仓库" in f["detail"] for f in report["findings"])


def test_advisory_reports_but_exits_zero(tmp_path: Path) -> None:
    proc = _run(_root(tmp_path), "--advisory", scenario="not_found")
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["errors"] >= 1
