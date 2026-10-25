#!/usr/bin/env python3
"""claim_integrity_gate — 声称完整性门禁（claim vs evidence）。

对 STATE.yaml 等自声称面做自动对账，防止「装饰性合规」：
纸面声称 implemented / 版本号 / 路径引用 与仓库真实状态脱节。

检查项:
  C1 版本三角   STATE.project.current_release ↔ pyproject.toml ↔ CHANGELOG 头
                （git 最新 tag 不一致记 WARNING，tag 可先于文档更新）
  C2 引用存在性 STATE.yaml 内所有仓库相对路径引用 → 文件必须存在
  C3 声明级联   status: implemented 的 sidecar 工具名 → src/ 下须有符号引用
  C4 宪法版本   STATE.project.constitution_version ↔ docs/CONSTITUTION.md 标题版本
                （设 OPENCLAW_ROOT 时对 Track A 宪法做跨仓 Advisory 比对）
  C5 钩子声称   track_b.pre_push_hook=present → .githooks/pre-push 存在
  C6 证据指针   ci_status / security_scan / coverage / d1_gate 的
                run_id + sha + verified_at 必须可解析（run 存在、SHA 匹配、
                绿色声称与 conclusion 一致）；非结构化旧值为 WARNING

退出码: 0=通过 1=存在 ERROR 级漂移 2=用法/环境错误
--advisory 模式下恒 0（影子运行，仅报告），供上线初期低误报验证。

用法:
  python3 scripts/claim_integrity_gate.py            # 全量检查
  python3 scripts/claim_integrity_gate.py --json     # 机器可读输出
  python3 scripts/claim_integrity_gate.py --advisory # 影子模式
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("ERROR: 需要 pyyaml（pip install pyyaml）", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent

SEV_ERROR = "ERROR"
SEV_WARN = "WARNING"


def _rel(path_str: str) -> bool:
    """判断字符串是否像仓库相对路径引用（排除 URL / home / 命令行）。"""
    if not path_str or path_str.startswith(("http://", "https://", "~", "/", "$")):
        return False
    if "|" in path_str or " " in path_str.strip():
        return False
    return bool(re.search(r"\.(md|yaml|yml|json|py|toml|sh)$", path_str))


def load_state(root: Path) -> dict:
    p = root / "STATE.yaml"
    if not p.exists():
        raise FileNotFoundError("STATE.yaml 不存在")
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def check_version_triangle(state: dict, root: Path) -> list[dict]:
    findings: list[dict] = []
    claimed = str(state.get("project", {}).get("current_release", ""))

    # pyproject.toml
    pyproject = root / "pyproject.toml"
    m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.M) if pyproject.exists() else None
    actual_py = m.group(1) if m else None
    if actual_py is None:
        findings.append({"check": "C1", "severity": SEV_ERROR, "detail": "pyproject.toml version 缺失"})
    elif actual_py != claimed:
        findings.append({"check": "C1", "severity": SEV_ERROR,
                         "detail": f"版本三角: STATE={claimed} ↔ pyproject={actual_py}"})

    # CHANGELOG 头
    changelog = root / "CHANGELOG.md"
    m2 = re.search(r"^##\s*\[v?([0-9][^\]]*)\]", changelog.read_text(encoding="utf-8"), re.M) if changelog.exists() else None
    if m2 is None:
        findings.append({"check": "C1", "severity": SEV_WARN, "detail": "CHANGELOG.md 头部版本无法解析"})
    elif m2.group(1) != claimed.lstrip("v"):
        findings.append({"check": "C1", "severity": SEV_ERROR,
                         "detail": f"版本三角: STATE={claimed} ↔ CHANGELOG头=v{m2.group(1)}"})

    # git tag（WARNING：tag 可先于 STATE/CHANGELOG 更新）
    try:
        tags = subprocess.run(
            ["git", "tag", "--sort=-v:refname"],
            cwd=root, capture_output=True, text=True, timeout=10,
        ).stdout.strip().splitlines()
        if tags:
            latest = tags[0].lstrip("v")
            if latest != claimed.lstrip("v"):
                findings.append({"check": "C1", "severity": SEV_WARN,
                                 "detail": f"git 最新 tag=v{latest} 领先/偏离 STATE={claimed}（若为 patch 发布请同步 STATE/CHANGELOG/pyproject）"})
    except (OSError, subprocess.TimeoutExpired):
        pass

    return findings


def check_referenced_paths(state: dict, root: Path) -> list[dict]:
    findings: list[dict] = []
    seen: set[str] = set()

    def walk(node, trail="STATE"):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{trail}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{trail}[{i}]")
        elif isinstance(node, str) and _rel(node) and node not in seen:
            seen.add(node)
            if not (root / node).exists():
                findings.append({"check": "C2", "severity": SEV_ERROR,
                                 "detail": f"引用不存在: {trail} → {node}"})

    walk(state)
    return findings


def check_implemented_symbols(state: dict, root: Path) -> list[dict]:
    """status: implemented 的具名工具 → 须在 src/ 下有代码引用。"""
    findings: list[dict] = []
    src_dir = root / "src"
    if not src_dir.exists():
        findings.append({"check": "C3", "severity": SEV_WARN, "detail": "src/ 不存在，跳过符号核验"})
        return findings

    # 预扫 src 下全部 .py 文本（数量级可控）
    corpus = []
    for p in src_dir.rglob("*.py"):
        try:
            corpus.append(p.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    haystack = "\n".join(corpus)

    def walk(node, trail="STATE"):
        if isinstance(node, dict):
            if node.get("status") == "implemented" and isinstance(node.get("name"), str):
                name = node["name"]
                if name not in haystack:
                    findings.append({"check": "C3", "severity": SEV_ERROR,
                                     "detail": f"声称 implemented 但 src/ 无符号引用: {trail}.name={name}"})
            for k, v in node.items():
                walk(v, f"{trail}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{trail}[{i}]")

    walk(state)
    return findings


def check_constitution_version(state: dict, root: Path) -> list[dict]:
    findings: list[dict] = []
    claimed = str(state.get("project", {}).get("constitution_version", ""))
    if not claimed:
        return findings

    local = root / "docs" / "CONSTITUTION.md"
    if local.exists():
        m = re.search(r"v(\d+\.\d+)", local.read_text(encoding="utf-8")[:500])
        if m and f"v{m.group(1)}" != claimed:
            findings.append({"check": "C4", "severity": SEV_ERROR,
                             "detail": f"宪法版本: STATE={claimed} ↔ docs/CONSTITUTION.md=v{m.group(1)}"})
    else:
        findings.append({"check": "C4", "severity": SEV_WARN, "detail": "docs/CONSTITUTION.md 不存在"})

    # 跨仓 Track A Advisory（仅本机双仓环境）
    oc_root = os.environ.get("OPENCLAW_ROOT")
    if oc_root:
        oc_const = Path(oc_root) / "CONSTITUTION.md"
        if oc_const.exists():
            m2 = re.search(r"v(\d+\.\d+)", oc_const.read_text(encoding="utf-8")[:500])
            if m2 and f"v{m2.group(1)}" != claimed:
                findings.append({"check": "C4", "severity": SEV_WARN,
                                 "detail": f"跨仓宪法版本: 公开仓 STATE={claimed} ↔ Track A=v{m2.group(1)}（Track B 独立演进则忽略）"})
    return findings


def check_hook_claims(state: dict, root: Path) -> list[dict]:
    findings: list[dict] = []
    claim = str(state.get("track_b", {}).get("pre_push_hook", "")).lower()
    if claim == "present" and not (root / ".githooks" / "pre-push").exists():
        findings.append({"check": "C5", "severity": SEV_ERROR,
                         "detail": "track_b.pre_push_hook=present 但 .githooks/pre-push 不存在"})
    return findings


def _repo_slug(state: dict) -> str:
    url = str(state.get("project", {}).get("public_repo", ""))
    m = re.search(r"github\.com[/:]([^/\s]+/[^/\s.#]+)", url)
    return m.group(1) if m else ""


def _gh_api(path: str) -> tuple[dict | None, str | None]:
    """Call ``gh api``; return (json, error). Never raises."""
    try:
        proc = subprocess.run(
            ["gh", "api", path], capture_output=True, text=True, timeout=20
        )
    except FileNotFoundError:
        return None, "gh CLI 不存在"
    except subprocess.TimeoutExpired:
        return None, "gh api 超时"
    if proc.returncode != 0:
        lines = (proc.stderr or proc.stdout).strip().splitlines()
        return None, lines[-1][:200] if lines else f"gh exit {proc.returncode}"
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"gh 输出非 JSON: {exc}"


def _iso_ok(value) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return False
    return True


def _err(check: str, detail: str) -> dict:
    return {"check": check, "severity": SEV_ERROR, "detail": detail}


def _warn(check: str, detail: str) -> dict:
    return {"check": check, "severity": SEV_WARN, "detail": detail}


def _check_run_pointer(trail: str, node: dict, repo: str) -> list[dict]:
    """A green claim must resolve to a real successful run with the same SHA."""
    findings: list[dict] = []
    value = str(node.get("value", "")).lower()
    run_id = str(node.get("run_id") or "")
    claimed_sha = str(node.get("sha") or "")
    claims_green = value in ("green", "success", "passed")

    if not run_id:
        if claims_green:
            findings.append(_err("C6", f"{trail} 声称 {value} 但缺少 run_id"))
        return findings
    if not repo:
        findings.append(_err("C6", f"{trail}.run_id 存在但 project.public_repo 无法解析"))
        return findings

    data, err = _gh_api(f"repos/{repo}/actions/runs/{run_id}")
    if data is None:
        findings.append(_err("C6", f"{trail}.run_id={run_id} 不可解析: {err}"))
        return findings

    head = str(data.get("head_sha") or "")
    if claimed_sha and not head.startswith(claimed_sha):
        findings.append(
            _err(
                "C6",
                f"{trail} SHA 不匹配: run={head[:12] or '?'} claimed={claimed_sha[:12]}",
            )
        )
    conclusion = data.get("conclusion")
    if claims_green and conclusion != "success":
        findings.append(
            _err("C6", f"{trail} 声称 {value} 但 run conclusion={conclusion}")
        )
    if not _iso_ok(node.get("verified_at")):
        findings.append(_err("C6", f"{trail}.verified_at 缺失或不可解析"))
    return findings


def _check_coverage_pointer(state: dict, repo: str) -> list[dict]:
    node = state.get("governance", {}).get("coverage")
    if not isinstance(node, dict):
        return [
            _warn(
                "C6",
                "governance.coverage 未指针化（需 value/source_run_id/verified_at）",
            )
        ]

    value = node.get("value")
    text = str(value).strip().lower() if value is not None else ""
    if text in ("unverified", "unknown", "none"):
        if node.get("overall") not in (None, ""):
            return [_err("C6", "governance.coverage 标记 unverified 却保留 overall 数值")]
        return []

    try:
        float(text.rstrip("%"))
    except ValueError:
        return [_err("C6", f"governance.coverage.value 非数值也非 unverified: {value!r}")]

    findings: list[dict] = []
    run_id = str(node.get("source_run_id") or "")
    if not run_id:
        findings.append(_err("C6", "governance.coverage 数值声称缺少 source_run_id"))
        return findings
    if not repo:
        findings.append(_err("C6", "coverage.source_run_id 存在但 public_repo 无法解析"))
        return findings
    data, err = _gh_api(f"repos/{repo}/actions/runs/{run_id}")
    if data is None:
        findings.append(_err("C6", f"coverage.source_run_id={run_id} 不可解析: {err}"))
    elif data.get("conclusion") != "success":
        findings.append(
            _err("C6", f"coverage run conclusion={data.get('conclusion')}，产物不可信")
        )
    if not _iso_ok(node.get("verified_at")):
        findings.append(_err("C6", "coverage.verified_at 缺失或不可解析"))
    return findings


def _check_d1_pointer(state: dict, root: Path) -> list[dict]:
    node = state.get("d1_gate")
    if not isinstance(node, dict):
        return [_warn("C6", "d1_gate 未指针化（需 value/sha/verified_at）")]

    findings: list[dict] = []
    value = str(node.get("value", "")).lower()
    if value not in ("passed", "failed", "blocked"):
        findings.append(_err("C6", f"d1_gate.value 非法: {node.get('value')!r}"))

    sha = str(node.get("sha") or "")
    if not sha:
        findings.append(_err("C6", "d1_gate.sha 缺失"))
    else:
        proc = subprocess.run(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            findings.append(_err("C6", f"d1_gate.sha 不在本地仓库: {sha}"))

    if not _iso_ok(node.get("verified_at")):
        findings.append(_err("C6", "d1_gate.verified_at 缺失或不可解析"))

    if value == "passed":
        evidence = str(node.get("evidence") or "")
        if not evidence:
            findings.append(_err("C6", "d1_gate=passed 但缺少 evidence 路径"))
        elif not (root / evidence).exists():
            findings.append(_err("C6", f"d1_gate.evidence 不存在: {evidence}"))
    return findings


def _check_rsi_pointer(state: dict) -> list[dict]:
    node = state.get("project", {}).get("rsi_level")
    if not isinstance(node, dict):
        return [_warn("C6", "project.rsi_level 未指针化（需 value/verified_at）")]

    value = str(node.get("value", "")).lower()
    if value not in ("conditional", "full_pass", "failed"):
        return [_err("C6", f"project.rsi_level.value 非法: {node.get('value')!r}")]
    if value == "full_pass" and not node.get("evidence"):
        return [_err("C6", "rsi_level=full_pass 但缺少 evidence（E1–E9 未全过时须保持 conditional）")]
    return []


def check_evidence_pointers(state: dict, root: Path) -> list[dict]:
    repo = _repo_slug(state)
    findings: list[dict] = []
    for key in ("ci_status", "security_scan", "dependency_audit"):
        node = state.get("track_b", {}).get(key)
        if isinstance(node, dict):
            findings += _check_run_pointer(f"track_b.{key}", node, repo)
        else:
            findings.append(_warn("C6", f"track_b.{key} 未指针化（需 value/run_id/sha/verified_at）"))
    findings += _check_coverage_pointer(state, repo)
    findings += _check_d1_pointer(state, root)
    findings += _check_rsi_pointer(state)
    return findings


def run_all(root: Path) -> dict:
    state = load_state(root)
    findings: list[dict] = []
    findings += check_version_triangle(state, root)
    findings += check_referenced_paths(state, root)
    findings += check_implemented_symbols(state, root)
    findings += check_constitution_version(state, root)
    findings += check_hook_claims(state, root)
    findings += check_evidence_pointers(state, root)

    errors = [f for f in findings if f["severity"] == SEV_ERROR]
    warns = [f for f in findings if f["severity"] == SEV_WARN]
    return {
        "ok": not errors,
        "errors": len(errors),
        "warnings": len(warns),
        "findings": findings,
        "state_version": state.get("version"),
        "claimed_release": state.get("project", {}).get("current_release"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="声称完整性门禁（claim vs evidence）")
    ap.add_argument("--root", default=str(ROOT), help="仓库根目录（默认本脚本所在仓）")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--advisory", action="store_true", help="影子模式：恒 exit 0，仅报告")
    args = ap.parse_args()

    try:
        result = run_all(Path(args.root))
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"=== 声称完整性门禁 (STATE v{result['state_version']}, release {result['claimed_release']}) ===")
        if not result["findings"]:
            print("✅ 全部声称与仓库实证一致")
        for f in result["findings"]:
            icon = "❌" if f["severity"] == SEV_ERROR else "⚠️"
            print(f"{icon} [{f['check']}][{f['severity']}] {f['detail']}")
        print(f"— ERROR {result['errors']} / WARNING {result['warnings']}")

    if args.advisory:
        return 0
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
