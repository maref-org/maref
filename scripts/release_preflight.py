#!/usr/bin/env python3
"""Verify that a release tag can only be published from green checks.

Checks two things:
  1. the tagged commit (GITHUB_SHA) has successful `required_checks`
     (the MAREF CI jobs that run on every push to main);
  2. the pull request associated with that commit has successful
     `required_pr_checks` (Release Gate jobs, which only run on PRs).

Squash-merged commits do not carry Release Gate check-runs, so the PR head SHA
is queried instead of the merged SHA.

Usage:
    python scripts/release_preflight.py --repo owner/name --sha <commit>

Exit codes: 0 = pass, 1 = gate failed, 2 = API/tooling error.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


def gh_api(path: str) -> tuple[object | None, str | None]:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        return None, "GH_TOKEN or GITHUB_TOKEN must be set"
    env = dict(os.environ, GH_TOKEN=token)
    proc = subprocess.run(
        ["gh", "api", path],
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip()
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON from gh api: {exc}"


def latest_by_name(runs: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for run in runs:
        name = run.get("name") or ""
        if not name:
            continue
        key = run.get("started_at") or run.get("completed_at") or ""
        if name not in latest:
            latest[name] = run
            continue
        prev_key = latest[name].get("started_at") or latest[name].get("completed_at") or ""
        if key >= prev_key:
            latest[name] = run
    return latest


def evaluate(runs: list[dict], required: list[str], label: str) -> tuple[list[str], list[str]]:
    latest = latest_by_name(runs)
    problems: list[str] = []
    lines: list[str] = []
    for name in required:
        run = latest.get(name)
        if run is None:
            problems.append(f"{label}: missing check '{name}'")
            lines.append(f"  {name:<28} MISSING")
            continue
        status = run.get("status")
        conclusion = run.get("conclusion")
        lines.append(f"  {name:<28} {status}/{conclusion}")
        if status != "completed":
            problems.append(f"{label}: check '{name}' is {status}, not completed")
        elif conclusion != "success":
            problems.append(f"{label}: check '{name}' concluded {conclusion}")
    return problems, lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--sha", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--config", default="configs/release-gate.yaml")
    parser.add_argument(
        "--allow-direct",
        action="store_true",
        help="do not fail when the commit has no associated pull request",
    )
    args = parser.parse_args()

    if not args.repo or not args.sha:
        print("ERROR: --repo and --sha are required (or set GITHUB_REPOSITORY/GITHUB_SHA)")
        return 2

    config_path = Path(args.config)
    if not config_path.is_file():
        print(f"ERROR: config not found: {config_path}")
        return 2

    cfg = yaml.safe_load(config_path.read_text()) or {}
    required_push = list(cfg.get("required_checks") or [])
    required_pr = list(cfg.get("required_pr_checks") or [])
    if not required_push:
        print("ERROR: required_checks must not be empty")
        return 2

    problems: list[str] = []

    data, err = gh_api(f"repos/{args.repo}/commits/{args.sha}/check-runs?per_page=100")
    if data is None:
        print(f"ERROR: cannot query check-runs for {args.sha}: {err}")
        return 2

    print(f"tag sha: {args.sha}")
    print("push checks:")
    push_problems, push_lines = evaluate(data.get("check_runs", []), required_push, "tag sha")
    print("\n".join(push_lines))
    problems.extend(push_problems)

    if required_pr:
        prs, pr_err = gh_api(f"repos/{args.repo}/commits/{args.sha}/pulls")
        if prs is None:
            print(f"ERROR: cannot query pull requests for {args.sha}: {pr_err}")
            return 2
        if not prs:
            if args.allow_direct:
                print("PR checks: skipped (no associated PR, --allow-direct)")
            else:
                problems.append(
                    "no pull request associated with tag commit; Release Gate cannot be verified"
                )
        else:
            head_sha = prs[0].get("head", {}).get("sha")
            print(f"PR checks: {prs[0].get('number')} head {head_sha}")
            pr_data, pr_check_err = gh_api(
                f"repos/{args.repo}/commits/{head_sha}/check-runs?per_page=100"
            )
            if pr_data is None:
                print(f"ERROR: cannot query check-runs for PR head {head_sha}: {pr_check_err}")
                return 2
            pr_problems, pr_lines = evaluate(pr_data.get("check_runs", []), required_pr, "pr head")
            print("\n".join(pr_lines))
            problems.extend(pr_problems)

    if problems:
        print("\nPREFLIGHT FAILED:")
        for item in problems:
            print(f"  - {item}")
        return 1

    print("\nPREFLIGHT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
