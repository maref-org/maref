"""D1 Pre-Flight 负向测试：门禁必须能被注入的故障证伪。

每个用例在临时目录里放一份脚本 + 配置 + fake `gh`，通过 FAKE_GH_SCENARIO
控制 GitHub 响应。若某条故障不能使 exit code 变非 0，门禁即视为失效。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "d1_preflight_check.py"
SHA = "a" * 40

FAKE_GH = (
    textwrap.dedent(
        """\
    #!/usr/bin/env python3
    import json
    import os
    import sys

    path = sys.argv[-1]
    scenario = os.environ.get("FAKE_GH_SCENARIO", "all_green")
    sha = os.environ.get("FAKE_SHA", "%s")

    def emit(payload):
        print(json.dumps(payload))
        sys.exit(0)

    if "/branches/" in path and path.endswith("/protection"):
        contexts = [] if scenario in {"protection_empty", "state_claims_true"} else [
            "lint", "test", "gate-quality"
        ]
        emit({"required_status_checks": {"contexts": contexts, "checks": []}})

    if "/check-runs" in path:
        conclusion = "failure" if scenario == "check_failed" else "success"
        emit({
            "check_runs": [
                {"name": "lint", "status": "completed", "conclusion": "success", "started_at": "2026-10-25T10:00:00Z"},
                {"name": "test", "status": "completed", "conclusion": conclusion, "started_at": "2026-10-25T10:00:00Z"},
            ]
        })

    if "/actions/workflows/" in path:
        if scenario == "security_missing":
            emit({"workflow_runs": []})
        conclusion = "failure" if scenario == "security_failed" else "success"
        emit({
            "workflow_runs": [
                {"id": 1, "status": "completed", "conclusion": conclusion, "created_at": "2026-10-25T10:00:00Z", "head_sha": sha}
            ]
        })

    print("unexpected gh api call: " + path, file=sys.stderr)
    sys.exit(1)
    """
    )
    % SHA
)


def make_repo(
    tmp_path: Path,
    scenario: str,
    *,
    state_yaml: str | None = None,
    index_files: tuple[str, ...] = (),
) -> Path:
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "configs").mkdir()
    (root / "bin").mkdir()

    shutil.copy2(SCRIPT, root / "scripts" / "d1_preflight_check.py")
    (root / "configs" / "release-gate.yaml").write_text(
        textwrap.dedent(
            """\
            repository: maref-org/maref
            branch: main
            required_checks: [lint, test]
            required_pr_checks: [gate-quality]
            """
        )
    )
    gh = root / "bin" / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)

    if state_yaml is not None:
        (root / "STATE.yaml").write_text(state_yaml)

    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    for name in index_files:
        (root / name).write_text("dummy")
        subprocess.run(["git", "add", "-f", name], cwd=root, check=True)

    return root


def run_script(root: Path, scenario: str, *extra: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = f"{root / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    env["FAKE_GH_SCENARIO"] = scenario
    env["FAKE_SHA"] = SHA
    return subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "d1_preflight_check.py"),
            "--sha",
            SHA,
            "--json",
            *extra,
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def test_all_green_passes(tmp_path: Path) -> None:
    root = make_repo(tmp_path, "all_green")
    proc = run_script(root, "all_green")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["gate_passed"] is True


def test_state_claim_true_cannot_override_live_protection(tmp_path: Path) -> None:
    root = make_repo(
        tmp_path,
        "state_claims_true",
        state_yaml=textwrap.dedent(
            """\
            d1_gate:
              branch_protection: true
              ci_green: true
              security_scan: true
            """
        ),
    )
    proc = run_script(root, "state_claims_true")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["gate_passed"] is False


def test_empty_protection_contexts_fail(tmp_path: Path) -> None:
    root = make_repo(tmp_path, "protection_empty")
    proc = run_script(root, "protection_empty")
    assert proc.returncode == 1
    gates = {gate["id"]: gate for gate in json.loads(proc.stdout)["gates"]}
    assert gates["G1"]["pass"] is False


def test_failed_check_run_fails(tmp_path: Path) -> None:
    root = make_repo(tmp_path, "check_failed")
    proc = run_script(root, "check_failed")
    assert proc.returncode == 1
    gates = {gate["id"]: gate for gate in json.loads(proc.stdout)["gates"]}
    assert gates["G2"]["pass"] is False
    assert "test" in gates["G2"]["detail"]


def test_failed_security_scan_fails(tmp_path: Path) -> None:
    root = make_repo(tmp_path, "security_failed")
    proc = run_script(root, "security_failed")
    assert proc.returncode == 1
    gates = {gate["id"]: gate for gate in json.loads(proc.stdout)["gates"]}
    assert gates["G3"]["pass"] is False


def test_missing_security_scan_run_fails(tmp_path: Path) -> None:
    root = make_repo(tmp_path, "security_missing")
    proc = run_script(root, "security_missing")
    assert proc.returncode == 1
    gates = {gate["id"]: gate for gate in json.loads(proc.stdout)["gates"]}
    assert gates["G3"]["pass"] is False


def test_secret_in_index_fails(tmp_path: Path) -> None:
    root = make_repo(tmp_path, "all_green", index_files=("server.pem",))
    proc = run_script(root, "all_green")
    assert proc.returncode == 1
    gates = {gate["id"]: gate for gate in json.loads(proc.stdout)["gates"]}
    assert gates["G4"]["pass"] is False
    assert "server.pem" in gates["G4"]["artifacts"]


def test_missing_config_is_tooling_error(tmp_path: Path) -> None:
    root = make_repo(tmp_path, "all_green")
    (root / "configs" / "release-gate.yaml").unlink()
    proc = run_script(root, "all_green")
    assert proc.returncode == 2
    assert "release-gate config not found" in json.loads(proc.stdout)["error"]
