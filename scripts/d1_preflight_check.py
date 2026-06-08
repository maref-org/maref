#!/usr/bin/env python3
"""D1 Pre-Flight Checklist — 所有 Code Agent 的统一闸门验证入口

所有外部 Code Agent 在执行 D1 push 前必须运行本脚本。
输出 PASS/FAIL 矩阵，任一 FAIL 则阻断 push。

用法:
    python3 scripts/d1_preflight_check.py

返回码:
    0 — 全部通过
    1 — 任一 FAIL
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = REPO_ROOT / "STATE.yaml"

GATES = [
    {
        "id": "G1",
        "name": "arXiv ID 已获取",
        "check": lambda: _arxiv_id_obtained(),
    },
    {
        "id": "G2",
        "name": "Branch protection 已启用",
        "check": lambda: _gh_api_check(
            "repos/maref-org/maref/branches/main/protection"
        ),
    },
    {
        "id": "G3",
        "name": "CI 全绿",
        "check": lambda: _gh_run_check("ci"),
    },
    {
        "id": "G4",
        "name": "安全扫描通过",
        "check": lambda: _gh_run_check("security-scan"),
    },
    {
        "id": "G5",
        "name": "发布源无运行产物污染",
        "check": lambda: _no_artifacts(),
    },
]


def _arxiv_id_obtained() -> bool:
    """从 STATE.yaml 读取 arxive.id，检查是否已获取"""
    if not STATE_FILE.exists():
        return False
    content = STATE_FILE.read_text()
    m = re.search(r"^\s*id:\s*(\S+)", content, re.MULTILINE)
    if not m:
        return False
    val = m.group(1)
    return val != "null" and val != "~" and val != ""


def _gh_api_check(endpoint: str) -> bool:
    try:
        r = subprocess.run(
            ["gh", "api", endpoint],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _gh_run_check(workflow: str) -> bool:
    try:
        r = subprocess.run(
            ["gh", "run", "list", "--workflow", workflow,
             "--limit", "3", "--json", "conclusion"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return False
        runs = json.loads(r.stdout)
        return all(run.get("conclusion") == "success" for run in runs)
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        return False


def _no_artifacts() -> bool:
    patterns = [
        "coverage.json", "governance_observations.db",
        "*.coverage", "bandit_report.json",
        "*.db",
    ]
    for p in patterns:
        result = list(REPO_ROOT.glob(p))
        if result:
            return False
    return True


def _update_results(results: list):
    """原子更新 STATE.yaml 的 last_updated 和各闸门状态

    使用行级替换而非字符串替换，避免累积追加旧值。
    """
    if not STATE_FILE.exists():
        return

    lines = STATE_FILE.read_text().splitlines()
    key_map = {
        "G1": "G1_arxiv_id",
        "G2": "G2_branch_protection",
        "G3": "G3_ci_green",
        "G4": "G4_security_clean",
        "G5": "G5_no_runtime_artifacts",
    }
    now = time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    new_lines = []

    for line in lines:
        stripped = line.strip()

        # Update last_updated
        if stripped.startswith("last_updated:"):
            new_lines.append(f'last_updated: "{now}"')
            continue

        # Update each gate key
        updated = False
        for gid, passed in results:
            key = key_map.get(gid)
            if key and stripped.startswith(f"{key}:"):
                new_lines.append(f"  {key}: {'true' if passed else 'false'}  # updated by d1_preflight_check")
                updated = True
                break

        if not updated:
            new_lines.append(line)

    STATE_FILE.write_text("\n".join(new_lines) + "\n")


def main():
    results = []
    all_pass = True

    print("=" * 60)
    print("  D1 Pre-Flight Checklist — MAREF 发布闸门验证")
    print("=" * 60)
    print()

    for gate in GATES:
        try:
            passed = gate["check"]()
        except Exception as e:
            passed = False
            print(f"  ⚠️  {gate['id']} 检查异常: {e}")

        label = "✅ PASS" if passed else "❌ FAIL"
        results.append((gate["id"], passed))
        print(f"  {label}  {gate['id']}: {gate['name']}")
        if not passed:
            all_pass = False

    # 原子更新状态（一次写入，而非每闸门依次更新）
    _update_results(results)

    print()
    print("-" * 60)

    if all_pass:
        print("  结果: ✅ 全部通过 — 可以 push")
        print()
        print("  执行: touch .push_allow && git push origin main")
        sys.exit(0)
    else:
        print("  结果: ❌ 闸门未通过 — push 已阻断")
        print()
        for gid, passed in results:
            if not passed:
                print(f"    {gid} — 请修复后重试")
        print()
        print("  执行: python3 scripts/d1_preflight_check.py")
        sys.exit(1)


if __name__ == "__main__":
    main()
