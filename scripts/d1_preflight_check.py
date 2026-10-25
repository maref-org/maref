#!/usr/bin/env python3
"""D1 Pre-Flight Gate — live evidence only.

Every gate queries GitHub (or the local git index). STATE.yaml booleans are
never consulted: a state file claiming `d1_gate: true` cannot make this pass.

  G1  Branch protection exists and its required contexts cover the declared
      release-gate policy (configs/release-gate.yaml).
  G2  Every `required_checks` context is completed/success on the SHA being
      pushed. There is deliberately no "fresh main" fallback.
  G3  The latest Security Scan workflow run bound to the same SHA succeeded.
  G4  No secrets/credentials/runtime artifacts in the git index.

Usage:
  python3 scripts/d1_preflight_check.py [--sha <commit>] [--json]

Exit codes: 0 = all gates pass, 1 = a gate failed, 2 = config/tooling error.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "configs" / "release-gate.yaml"
DEFAULT_REPO = "maref-org/maref"
DEFAULT_BRANCH = "main"
SECURITY_WORKFLOW = "security-scan.yml"


def _gh_api(path: str) -> tuple[object | None, str | None]:
    try:
        proc = subprocess.run(
            ["gh", "api", path],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return None, str(exc)
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip()
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON from gh api: {exc}"


def _current_sha() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=PROJECT_ROOT,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def _load_config() -> dict:
    if not CONFIG_PATH.is_file():
        raise RuntimeError(f"release-gate config not found: {CONFIG_PATH}")
    config = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    if not config.get("required_checks"):
        raise RuntimeError("required_checks must not be empty")
    return config


def _protection_contexts(data: dict) -> set[str]:
    rsc = data.get("required_status_checks") or {}
    contexts = set(rsc.get("contexts") or [])
    for item in rsc.get("checks") or []:
        if item.get("context"):
            contexts.add(item["context"])
    return contexts


def _latest_by_name(runs: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for run in runs:
        name = run.get("name") or ""
        if not name:
            continue
        key = run.get("started_at") or run.get("completed_at") or ""
        previous = latest.get(name)
        if previous is None:
            latest[name] = run
            continue
        previous_key = previous.get("started_at") or previous.get("completed_at") or ""
        if key >= previous_key:
            latest[name] = run
    return latest


def check_g1(repo: str, branch: str, config: dict) -> dict:
    data, error = _gh_api(f"repos/{repo}/branches/{branch}/protection")
    if data is None:
        if "404" in (error or ""):
            return {
                "id": "G1",
                "name": "Branch Protection",
                "pass": False,
                "detail": f"branch protection is not configured for {repo}@{branch}",
            }
        return {
            "id": "G1",
            "name": "Branch Protection",
            "pass": False,
            "detail": f"cannot query branch protection: {error}",
        }

    configured = _protection_contexts(data)
    required = set(config.get("required_checks") or []) | set(
        config.get("required_pr_checks") or []
    )
    missing = sorted(required - configured)
    if missing:
        return {
            "id": "G1",
            "name": "Branch Protection",
            "pass": False,
            "detail": f"missing required contexts: {', '.join(missing)}",
            "action": "bash scripts/configure_branch_protection.sh --apply",
        }
    return {
        "id": "G1",
        "name": "Branch Protection",
        "pass": True,
        "detail": f"OK ({len(configured)} contexts, {len(required)} required)",
    }


def check_g2(repo: str, sha: str, required: list[str]) -> dict:
    data, error = _gh_api(f"repos/{repo}/commits/{sha}/check-runs?per_page=100")
    if data is None:
        return {
            "id": "G2",
            "name": "CI Status",
            "pass": False,
            "detail": f"cannot query check-runs for {sha[:12]}: {error}",
        }

    latest = _latest_by_name(data.get("check_runs") or [])
    missing: list[str] = []
    failed: list[str] = []
    for name in required:
        run = latest.get(name)
        if run is None or run.get("status") != "completed":
            missing.append(name)
        elif run.get("conclusion") != "success":
            failed.append(f"{name}={run.get('conclusion')}")

    if missing or failed:
        parts = []
        if missing:
            parts.append(f"missing/pending: {', '.join(missing)}")
        if failed:
            parts.append(f"not successful: {', '.join(failed)}")
        return {
            "id": "G2",
            "name": "CI Status",
            "pass": False,
            "detail": f"{sha[:12]}: " + "; ".join(parts),
        }
    return {
        "id": "G2",
        "name": "CI Status",
        "pass": True,
        "detail": f"{sha[:12]}: {len(required)} required checks successful",
    }


def check_g3(repo: str, sha: str) -> dict:
    data, error = _gh_api(
        f"repos/{repo}/actions/workflows/{SECURITY_WORKFLOW}/runs?head_sha={sha}&per_page=20"
    )
    if data is None:
        return {
            "id": "G3",
            "name": "Security Scan",
            "pass": False,
            "detail": f"cannot query Security Scan runs for {sha[:12]}: {error}",
        }

    runs = data.get("workflow_runs") or []
    if not runs:
        return {
            "id": "G3",
            "name": "Security Scan",
            "pass": False,
            "detail": f"no Security Scan run is bound to {sha[:12]}",
        }

    latest = sorted(runs, key=lambda run: run.get("created_at") or "", reverse=True)[0]
    status = latest.get("status")
    conclusion = latest.get("conclusion")
    if status != "completed" or conclusion != "success":
        return {
            "id": "G3",
            "name": "Security Scan",
            "pass": False,
            "detail": f"latest run {latest.get('id')} is {status}/{conclusion}",
        }
    return {
        "id": "G3",
        "name": "Security Scan",
        "pass": True,
        "detail": f"run {latest.get('id')} successful for {sha[:12]}",
    }


def check_g4() -> dict:
    patterns = [".env", "*.key", "*.pem", "credentials*", "secrets*"]
    if "public/maref" in str(PROJECT_ROOT):
        patterns.append(".openclaw/")
    artifacts: list[str] = []
    for pattern in patterns:
        try:
            proc = subprocess.run(
                ["git", "ls-files", "--", pattern],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=PROJECT_ROOT,
            )
        except (subprocess.TimeoutExpired, OSError):
            return {
                "id": "G4",
                "name": "No Runtime Artifacts",
                "pass": False,
                "detail": "cannot inspect git index",
            }
        if proc.stdout.strip():
            artifacts.extend(proc.stdout.strip().splitlines())

    if artifacts:
        return {
            "id": "G4",
            "name": "No Runtime Artifacts",
            "pass": False,
            "detail": f"found {len(artifacts)} artifact(s) in index",
            "artifacts": artifacts[:10],
        }
    return {
        "id": "G4",
        "name": "No Runtime Artifacts",
        "pass": True,
        "detail": "no runtime artifacts in index",
    }


def check_gates(sha: str | None = None) -> tuple[int, dict]:
    try:
        config = _load_config()
    except (RuntimeError, yaml.YAMLError) as exc:
        return 2, {
            "gate_passed": False,
            "error": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    repo = str(config.get("repository") or DEFAULT_REPO)
    branch = str(config.get("branch") or DEFAULT_BRANCH)
    target_sha = sha or _current_sha()
    if not target_sha:
        return 2, {
            "gate_passed": False,
            "error": "cannot resolve target SHA (pass --sha or run inside git)",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    gates = [
        check_g1(repo, branch, config),
        check_g2(repo, target_sha, list(config.get("required_checks") or [])),
        check_g3(repo, target_sha),
        check_g4(),
    ]
    all_pass = all(gate["pass"] for gate in gates)
    return (0 if all_pass else 1), {
        "gate_passed": all_pass,
        "sha": target_sha,
        "repo": repo,
        "branch": branch,
        "gates": gates,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    args = sys.argv[1:]
    json_output = "--json" in args
    sha = None
    if "--sha" in args:
        index = args.index("--sha")
        if index + 1 >= len(args):
            print("--sha requires a value", file=sys.stderr)
            return 2
        sha = args[index + 1]

    exit_code, result = check_gates(sha=sha)

    if json_output:
        print(json.dumps(result, indent=2))
        return exit_code

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"\n{'=' * 50}")
    print(f"  D1 Pre-Flight 闸门检查 — {now}")
    print(f"{'=' * 50}\n")

    if "error" in result:
        print(f"  ❌ CONFIG ERROR: {result['error']}")
        return exit_code

    print(f"  target: {result['repo']}@{result['branch']}  sha={result['sha'][:12]}\n")
    for gate in result["gates"]:
        icon = "✅" if gate["pass"] else "❌"
        print(f"  {icon} [{gate['id']}] {gate['name']}")
        print(f"       {gate['detail']}")
        if not gate["pass"] and gate.get("action"):
            print(f"       → {gate['action']}")

    print(f"\n{'─' * 50}")
    if result["gate_passed"]:
        print("  结果: ✅ 全部通过 — 允许 push")
    else:
        blocked = [gate["id"] for gate in result["gates"] if not gate["pass"]]
        print("  结果: ❌ 闸门未通过 — 禁止 push")
        print(f"  阻塞项: {', '.join(blocked)}")
    print(f"{'=' * 50}\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
