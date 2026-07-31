#!/usr/bin/env python3
"""D1 Pre-Flight Gate — MAREF 开源发布前置闸门检查。

宪法第四-A条 / 开源执行规范 §2.1A 要求。
由 pre-push hook 自动调用，所有 5 项通过后允许推送到 maref-org/maref。

Usage:
  python3 d1_preflight_check.py          # 检查所有闸门
  python3 d1_preflight_check.py --json   # JSON 格式输出

Returns 0 if ALL GATES PASS, 1 if ANY FAILS.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

_STATE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "STATE.yaml")
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_state() -> dict | None:
    """Parse STATE.yaml."""
    if not os.path.isfile(_STATE_PATH):
        alt = "$PROJECT_ROOT/STATE.yaml"
        if os.path.isfile(alt):
            with open(alt) as f:
                return _parse_yaml(f.read())
        return None
    try:
        with open(_STATE_PATH) as f:
            return _parse_yaml(f.read())
    except OSError:
        return None


def _parse_yaml(text: str) -> dict:
    """Parse YAML using yaml module if available, otherwise fallback."""
    if HAS_YAML:
        try:
            return yaml.safe_load(text) or {}
        except yaml.YAMLError:
            pass
    return _parse_yaml_simple(text)


def _parse_yaml_simple(text: str) -> dict:
    """Minimal YAML parser for flat nested dicts (fallback)."""
    result: dict = {}
    path: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        while path and path[-1][1] >= indent:
            path.pop()
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "":
                new_dict: dict = {}
                if path:
                    parent = result
                    for p in path:
                        parent = parent[p[0]]
                    parent[key] = new_dict
                else:
                    result[key] = new_dict
                path.append((key, indent))
            else:
                if value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
                elif value.lower() == "null" or value == "~":
                    value = None
                    try:
                        value = float(value) if "." in value else int(value)
                    except (ValueError, TypeError):
                        pass
                if path:
                    parent = result
                    for p in path:
                        parent = parent[p[0]]
                    parent[key] = value
                else:
                    result[key] = value
    return result


def _check_github_gate(name: str, check_cmd: list[str], expected: bool, label: str) -> tuple[bool, str]:
    """Run a GitHub CLI check, return (pass, detail)."""
    try:
        result = subprocess.run(check_cmd, capture_output=True, text=True, timeout=30)
        actual = result.returncode == 0 and result.stdout.strip().lower() == "true"
    except (subprocess.TimeoutExpired, OSError):
        actual = False
    if actual == expected:
        return True, f"✅ {name}: {label}"
    state = "enabled" if expected else "clean"
    return False, f"❌ {name}: expected {state}, got {actual}. {label}"


def check_gates(json_output: bool = False) -> tuple[bool, list[dict]]:
    """Run all D1 gates. Returns (all_pass, gate_results)."""
    state = _read_state()
    gates: list[dict] = []
    all_pass = True

    d1 = (state or {}).get("d1_gate", {})

    # G1: Branch Protection
    g1 = d1.get("G1_branch_protection", False)
    if g1:
        gates.append({"id": "G1", "name": "Branch Protection", "pass": True, "detail": "✅ Branch protection enabled on main"})
    else:
        live_pass, detail = _check_github_gate("G1", ["gh", "api", "/repos/maref-org/maref/branches/main/protection", "--jq", ".required_status_checks.enabled"], True, "Branch protection enabled on main")
        g1 = live_pass
        gates.append({"id": "G1", "name": "Branch Protection", "pass": live_pass, "detail": detail})
        if not live_pass:
            all_pass = False

    # G2: CI Green
    g2 = d1.get("G2_ci_green", False)
    if g2:
        gates.append({"id": "G2", "name": "CI Status", "pass": True, "detail": "✅ All CI checks passing"})
    else:
        try:
            ci_result = subprocess.run(
                ["gh", "run", "list", "--repo", "maref-org/maref", "--branch", "main", "--limit", "5",
                 "--json", "conclusion,workflowName"],
                capture_output=True, text=True, timeout=30,
            )
            if ci_result.returncode == 0:
                runs = json.loads(ci_result.stdout) if ci_result.stdout.strip() else []
                failures = [r for r in runs if r.get("conclusion") == "failure"]
                g2 = len(failures) == 0
            else:
                g2 = False
        except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError):
            g2 = False
        gates.append({
            "id": "G2", "name": "CI Status", "pass": g2,
            "detail": "✅ All CI checks passing" if g2 else "❌ CI has failures",
        })
        if not g2:
            all_pass = False

    # G3: Security Scan Clean
    g3 = d1.get("G3_security_clean", False)
    gates.append({
        "id": "G3", "name": "Security Scan", "pass": g3,
        "detail": "✅ Security scan passed" if g3 else "❌ Security scan has findings",
    })
    if not g3:
        all_pass = False

    # G4: No Runtime Artifacts (context-aware: public/maref checks .openclaw/; openclaw doesn't)
    is_public_maref = "public/maref" in os.getcwd() or "public/maref" in _STATE_PATH
    g4_patterns = [".env", "*.key", "*.pem", "credentials*", "secrets*"]
    if is_public_maref:
        g4_patterns.append(".openclaw/")
    artifacts = []
    for pattern in g4_patterns:
        try:
            result = subprocess.run(
                ["git", "ls-files", "--", pattern],
                capture_output=True, text=True, timeout=10, cwd=_PROJECT_ROOT,
            )
            if result.stdout.strip():
                artifacts.extend(result.stdout.strip().splitlines())
        except (subprocess.TimeoutExpired, OSError):
            pass
    if artifacts:
        gates.append({
            "id": "G4", "name": "No Runtime Artifacts", "pass": False,
            "detail": f"❌ Found {len(artifacts)} artifact(s) in index",
            "artifacts": artifacts[:10],
        })
        all_pass = False
    else:
        gates.append({
            "id": "G4", "name": "No Runtime Artifacts", "pass": True,
            "detail": "✅ No runtime artifacts in index",
        })

    return all_pass, gates


def main() -> int:
    json_output = "--json" in sys.argv
    all_pass, gates = check_gates(json_output=json_output)

    if json_output:
        print(json.dumps({"gate_passed": all_pass, "gates": gates, "timestamp": datetime.now(timezone.utc).isoformat()}, indent=2))
    else:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"\n{'=' * 50}")
        print(f"  D1 Pre-Flight 闸门检查 — {now}")
        print(f"{'=' * 50}\n")
        for g in gates:
            icon = "✅" if g["pass"] else "❌"
            print(f"  {icon} [{g['id']}] {g['name']}")
            print(f"       {g['detail']}")
            if not g["pass"] and g.get("action"):
                print(f"       → {g['action']}")
        print(f"\n{'─' * 50}")
        if all_pass:
            print("  结果: ✅ 全部通过 — 允许 push")
            print("  执行: touch .push_allow && git push origin main")
        else:
            print("  结果: ❌ 闸门未通过 — 禁止 push")
            blocked = [g["id"] for g in gates if not g["pass"]]
            print(f"  阻塞项: {', '.join(blocked)}")
        print(f"{'=' * 50}\n")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
