#!/usr/bin/env python3
"""生成单一自证明治理证据报告。

输出 reports/governance_evidence_report.json / .md，内容覆盖：
  1. 遥测：探针行数与新鲜度、sidecar 健康、MCP well-known
  2. 治理执行：各审计链行数、24h 裁决分布、拦截计数
  3. 自证明：审计健康、必需链验证、可选链验证
  4. 覆盖：Agent 覆盖对账
  5. 链范围：声明每条链是 in_scope / legacy / foreign / auxiliary，避免盲区
  6. evidence_hash：引用文件 sha256 清单的 Merkle 根

`--check` 只校验已有报告的引用文件哈希与 Merkle 根，不重新生成。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from audit_health_check import _parse_timestamp  # noqa: E402
from maref_config import (  # noqa: E402
    AUDIT_LOG_V2,
    PROBE_DB,
    RECURSIVE_AUDIT_LOG,
    REPO_DIR,
    REPORTS_DIR,
    audit_base,
    sidecar_auth_headers,
    sidecar_url,
)

OUTPUT_JSON = REPORTS_DIR / "governance_evidence_report.json"
OUTPUT_MD = REPORTS_DIR / "governance_evidence_report.md"
HOOKS_CHAIN = Path.home() / ".claude" / "hooks" / "state" / "governance_audit.jsonl"
PRIMARY_CHAIN = audit_base() / "governance_audit.jsonl"
MCP_DECISIONS = audit_base() / "mcp_decisions.jsonl"

CHAINS = {
    "audit_primary": PRIMARY_CHAIN,
    "audit_v2": AUDIT_LOG_V2,
    "hooks_agent": HOOKS_CHAIN,
    "recursive_primary": RECURSIVE_AUDIT_LOG,
    "mcp_decisions": MCP_DECISIONS,
}
REQUIRED_PROOF_CHAINS = ("audit_primary",)
OPTIONAL_PROOF_CHAINS = ("audit_v2", "recursive_primary")

# 链范围声明：不把「无法验证」伪装成「已验证」，也不静默忽略外部链。
CHAIN_SCOPE = {
    "audit_primary": ("in_scope", "发布证据主链，必须通过链验证"),
    "audit_v2": ("in_scope", "审计 v2 链，必须通过链验证"),
    "recursive_primary": ("legacy", "递归审计历史链，schema 与通用 verifier 不兼容"),
    "hooks_agent": ("foreign", "外部 Claude hooks 链，遗留哈希格式，MAREF verifier 不可验证"),
    "mcp_decisions": ("auxiliary", "MCP 决策辅助链，不参与发布签名主链"),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_prefix(path: Path, size: int) -> str:
    digest = hashlib.sha256()
    remaining = size
    with open(path, "rb") as f:
        while remaining > 0:
            chunk = f.read(min(1 << 20, remaining))
            if not chunk:
                break
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def count_lines(path: Path) -> int:
    with open(path, "rb") as f:
        return sum(1 for _ in f)


def merkle_root(hashes: list[str]) -> str:
    nodes = sorted(hashes)
    if not nodes:
        return ""
    while len(nodes) > 1:
        if len(nodes) % 2:
            nodes.append(nodes[-1])
        nodes = [
            hashlib.sha256((nodes[i] + nodes[i + 1]).encode()).hexdigest()
            for i in range(0, len(nodes), 2)
        ]
    return nodes[0]


def _age_hours(value: object) -> float | None:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return None
    return round((datetime.now(timezone.utc) - parsed).total_seconds() / 3600, 2)


def _refresh_audit_health() -> int:
    try:
        result = subprocess.run(
            [sys.executable, str(REPO_DIR / "scripts" / "audit_health_check.py")],
            cwd=str(REPO_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1
    return result.returncode


def section_telemetry() -> dict:
    rows = last_ts = age_h = None
    fresh = False
    if PROBE_DB.is_file():
        try:
            con = sqlite3.connect(str(PROBE_DB))
            rows = con.execute("select count(*) from probe_readings").fetchone()[0]
            last_ts = con.execute("select max(timestamp) from probe_readings").fetchone()[0]
            con.close()
            if last_ts is not None:
                age_h = round((time.time() - float(last_ts)) / 3600, 2)
                fresh = age_h < 26
        except (sqlite3.Error, TypeError, ValueError) as exc:
            age_h = f"error: {exc}"

    sidecar_ok = False
    health_body = ""
    url = sidecar_url()
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=3) as response:
            health_body = response.read(512).decode("utf-8", "replace")
        sidecar_ok = "healthy" in health_body.lower()
    except OSError as exc:
        health_body = str(exc)

    endpoint_ok = False
    try:
        request = urllib.request.Request(
            f"{url}/api/mcp/.well-known",
            headers=sidecar_auth_headers(content_type=""),
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            endpoint_ok = response.status == 200
    except OSError:
        endpoint_ok = False

    return {
        "probe": {
            "db": str(PROBE_DB),
            "row_count": rows,
            "last_ts": last_ts,
            "age_hours": age_h,
            "fresh_26h": fresh,
        },
        "sidecar": {"url": url, "healthy": sidecar_ok, "health_body": health_body[:200]},
        "mcp_wellknown_reachable": endpoint_ok,
    }


def section_governance_execution() -> dict:
    chains: dict[str, dict] = {}
    for name, path in CHAINS.items():
        if path.is_file():
            chains[name] = {
                "path": str(path),
                "rows": count_lines(path),
                "bytes": path.stat().st_size,
            }
        else:
            chains[name] = {"path": str(path), "rows": 0, "missing": True}

    verdicts_24h: Counter[str] = Counter()
    verdicts_total: Counter[str] = Counter()
    per_agent_24h: dict[str, dict[str, int]] = {}
    cutoff = time.time() - 86400
    try:
        with open(HOOKS_CHAIN, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                verdict = str(entry.get("verdict", "?"))
                verdicts_total[verdict] += 1
                ts = _parse_timestamp(entry.get("timestamp"))
                if ts is not None and ts.timestamp() >= cutoff:
                    verdicts_24h[verdict] += 1
                    agent = str(entry.get("agent_id") or "unknown")
                    per_agent_24h.setdefault(agent, {})
                    per_agent_24h[agent][verdict] = (
                        per_agent_24h[agent].get(verdict, 0) + 1
                    )
    except OSError:
        pass

    status = load_json(REPORTS_DIR / "coding_agents_status.json") or {}
    global_kpi = status.get("global_kpi") or {}
    per_agent_kpi = {
        str(agent.get("agent_id", "?")): {
            "tool_calls_total": (agent.get("runtime_kpi") or {}).get("tool_calls_total"),
            "allowed": (agent.get("runtime_kpi") or {}).get("tool_calls_allowed"),
            "denied": (agent.get("runtime_kpi") or {}).get("tool_calls_denied"),
            "hitl": (agent.get("runtime_kpi") or {}).get("tool_calls_hitl"),
            "interception_rate": (agent.get("runtime_kpi") or {}).get("interception_rate"),
            "telemetry_auth": agent.get("telemetry_auth"),
        }
        for agent in (status.get("agents") or [])
        if isinstance(agent, dict)
    }

    hooks_total = sum(verdicts_total.values())
    blocked = verdicts_total.get("BLOCKED", 0)
    deny = verdicts_total.get("DENY", 0)
    hitl = global_kpi.get("tool_calls_hitl", 0)
    interception_rate = round((blocked + deny) / hooks_total, 6) if hooks_total else 0.0

    return {
        "chains": chains,
        "hooks_verdicts_total": dict(verdicts_total),
        "hooks_verdicts_24h": dict(verdicts_24h),
        "per_agent_24h": per_agent_24h,
        "per_agent_kpi": per_agent_kpi,
        "global_kpi": global_kpi,
        "counts": {
            "blocked": blocked,
            "deny": deny,
            "hitl": hitl,
            "hooks_rows": hooks_total,
        },
        "interception_rate": interception_rate,
    }


def _verify_chain(path: Path) -> dict:
    if not path.is_file():
        return {"ok": False, "rc": -1, "result": "missing"}
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_DIR / "scripts" / "verify_audit_chain.py"),
                "--audit-file",
                str(path),
            ],
            cwd=str(REPO_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "rc": -1, "result": str(exc)}
    first_line = (result.stdout or "").splitlines()[:1]
    return {
        "ok": result.returncode == 0,
        "rc": result.returncode,
        "result": first_line[0] if first_line else "",
    }


def _chain_scope() -> dict:
    """声明每条链的验证范围，避免外部/遗留链成为证据盲区。"""
    scope: dict[str, dict] = {}
    for name, path in CHAINS.items():
        kind, reason = CHAIN_SCOPE.get(name, ("unknown", "未分类链"))
        try:
            records = count_lines(path) if path.is_file() else 0
        except OSError:
            records = 0
        scope[name] = {
            "path": str(path),
            "records": records,
            "scope": kind,
            "reason": reason,
        }
    complete = bool(scope) and all(
        item.get("scope") not in (None, "", "unknown") and item.get("reason")
        for item in scope.values()
    )
    return {"chains": scope, "complete": complete}


def section_self_proof() -> dict:
    health_rc = _refresh_audit_health()
    health = load_json(REPORTS_DIR / "audit_health_check.json") or {}
    required = {name: _verify_chain(CHAINS[name]) for name in REQUIRED_PROOF_CHAINS}
    optional = {name: _verify_chain(CHAINS[name]) for name in OPTIONAL_PROOF_CHAINS}
    required_passed = sum(1 for item in required.values() if item["ok"])

    approval = load_json(REPORTS_DIR / "approval_tier_report.json") or {}
    verdict_dist = approval.get("verdict_distribution") or {}
    approval_total = approval.get("total_decisions") or sum(verdict_dist.values())
    unknown = verdict_dist.get("unknown", 0)
    unknown_rate = round(unknown / approval_total, 4) if approval_total else None

    confidence = load_json(REPORTS_DIR / "confidence_audit.json") or {}
    confidence_stats = confidence.get("stats") or {}
    confidence_total = confidence_stats.get("total")
    confidence_critical = confidence_stats.get("critical")
    critical_rate = (
        round(confidence_critical / confidence_total, 4)
        if confidence_total and confidence_critical is not None
        else None
    )

    sla = load_json(REPORTS_DIR / "backlog_sla_report.json") or {}
    loop = load_json(REPORTS_DIR / f"validation_{datetime.now(timezone.utc):%Y%m%d}.json") or {}

    return {
        "audit_health": {"rc": health_rc, "healthy": health.get("healthy")},
        "health": {
            "healthy": health.get("healthy"),
            "issues": health.get("issues"),
            "checked_at": health.get("checked_at"),
        },
        "chain_verify": {
            "required": required,
            "optional": optional,
            "required_total": len(required),
            "required_passed": required_passed,
            "required_ok": required_passed == len(required),
        },
        "chain_scope": _chain_scope(),
        "verdicts": {
            "approval_tier_unknown_rate": unknown_rate,
            "approval_tier_total": approval_total,
            "approval_tier_unknown": unknown,
            "approval_tier_deny_flag": verdict_dist.get("deny", 0) + verdict_dist.get("flag", 0),
            "confidence_critical": confidence_critical,
            "confidence_total": confidence_total,
            "confidence_critical_rate": critical_rate,
            "confidence_30d": confidence.get("confidence_30d"),
            "backlog_sla_met": sla.get("sla_met"),
            "backlog_total": sla.get("total_backlog"),
            "loop_deployed_verified": (loop.get("summary") or {}).get("deployed_verified"),
            "loop_closed": (loop.get("loop_closed") or {}).get("recorded"),
        },
    }


def section_coverage() -> dict:
    coverage = load_json(REPORTS_DIR / "agent_coverage_report.json") or {}
    declared = (coverage.get("declared_180") or {}).get("count")
    registry = (coverage.get("registry") or {}).get("count")
    active = coverage.get("active_24h")
    gaps = coverage.get("gaps") or []
    generated_at = coverage.get("generated_at")
    return {
        "declared": declared,
        "registry": registry,
        "active_24h": active,
        "internal_defs": (coverage.get("internal_defs") or {}).get("count"),
        "coding_registry": (coverage.get("coding_registry") or {}).get("count"),
        "gap_count": len(gaps),
        "gaps": gaps,
        "generated_at": generated_at,
        "age_hours": _age_hours(generated_at),
        "reconciled": bool(coverage) and not gaps,
    }


def _evidence_paths() -> list[tuple[Path, str]]:
    paths: dict[Path, str] = {
        path: "append" for path in CHAINS.values() if path.is_file()
    }
    if PROBE_DB.is_file():
        paths[PROBE_DB] = "volatile"
    paths.update(
        {
            path: "exact"
            for path in REPORTS_DIR.glob("*.json")
            if path != OUTPUT_JSON and path.is_file()
        }
    )
    return sorted(paths.items(), key=lambda item: str(item[0]))


def build() -> dict:
    sections = {
        "telemetry": section_telemetry(),
        "governance_execution": section_governance_execution(),
        "self_proof": section_self_proof(),
        "coverage": section_coverage(),
    }

    evidence_files = []
    for path, mode in _evidence_paths():
        try:
            evidence_files.append(
                {
                    "path": str(path),
                    "sha256": sha256_file(path),
                    "size": path.stat().st_size,
                    "mode": mode,
                }
            )
        except OSError:
            continue

    issues: list[str] = []
    warnings: list[str] = []
    telemetry = sections["telemetry"]
    proof = sections["self_proof"]
    coverage = sections["coverage"]

    if not telemetry["probe"].get("fresh_26h"):
        issues.append("探针数据非新鲜 (<26h)")
    if not telemetry["sidecar"].get("healthy"):
        issues.append("sidecar 不健康")
    if not telemetry.get("mcp_wellknown_reachable"):
        issues.append("MCP well-known 端点不可达")
    if proof["audit_health"]["rc"] != 0:
        issues.append(f"审计健康检查退出码 {proof['audit_health']['rc']}")
    if proof["health"].get("healthy") is not True:
        issues.append("审计健康检查未通过")
    if not proof["chain_verify"]["required_ok"]:
        issues.append(
            f"必需链验证未全过 ({proof['chain_verify']['required_passed']}/"
            f"{proof['chain_verify']['required_total']})"
        )
    if coverage.get("gap_count"):
        issues.append(f"覆盖对账存在 {coverage['gap_count']} 个 gap")

    if coverage.get("age_hours") is None or coverage["age_hours"] > 168:
        warnings.append("Agent 覆盖报告超过 7 天或缺失 generated_at")
    if proof["verdicts"].get("approval_tier_unknown_rate") is None:
        warnings.append("审批分层报告缺少裁决分布")
    elif proof["verdicts"]["approval_tier_unknown_rate"] > 0.30:
        warnings.append(
            f"审批 unknown 占比 {proof['verdicts']['approval_tier_unknown_rate']:.1%} > 30%"
        )
    if proof["verdicts"].get("confidence_critical_rate") is not None:
        rate = proof["verdicts"]["confidence_critical_rate"]
        if rate < 0.05 or rate > 0.15:
            warnings.append(f"置信度 critical 占比 {rate:.1%} 不在 5%-15%")
    if proof["verdicts"].get("backlog_sla_met") is False:
        warnings.append("backlog SLA 未达标")
    if not (sections["governance_execution"].get("global_kpi") or {}).get("tool_calls_total"):
        warnings.append("coding agent 24h tool_calls_total 为 0")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "healthy" if not issues else "attention",
        "status_scope": "evidence_integrity",
        "quality_status": "healthy" if not warnings else "attention",
        "issues": issues,
        "warnings": warnings,
        "sections": sections,
        "evidence_files": evidence_files,
        "evidence_hash": merkle_root([item["sha256"] for item in evidence_files]),
    }


def verify_report(path: Path = OUTPUT_JSON) -> list[str]:
    report = load_json(path)
    if report is None:
        return [f"report missing or invalid: {path}"]

    issues: list[str] = []
    hashes: list[str] = []
    for item in report.get("evidence_files") or []:
        if not isinstance(item, dict):
            issues.append("invalid evidence entry")
            continue
        raw_path = item.get("path")
        expected = item.get("sha256")
        if not isinstance(raw_path, str) or not isinstance(expected, str):
            issues.append("invalid evidence entry fields")
            continue
        evidence_path = Path(raw_path)
        if not evidence_path.is_file():
            issues.append(f"evidence file missing: {evidence_path}")
            continue

        mode = item.get("mode", "exact")
        if mode == "volatile":
            hashes.append(expected)
            continue

        if mode == "append":
            recorded_size = item.get("size")
            if not isinstance(recorded_size, int) or recorded_size < 0:
                issues.append(f"invalid evidence size: {evidence_path}")
                continue
            if evidence_path.stat().st_size < recorded_size:
                issues.append(f"evidence file truncated: {evidence_path}")
                continue
            actual = sha256_prefix(evidence_path, recorded_size)
        else:
            actual = sha256_file(evidence_path)

        if actual != expected:
            issues.append(f"evidence hash mismatch: {evidence_path}")
        hashes.append(expected)

    expected_root = report.get("evidence_hash")
    actual_root = merkle_root(hashes)
    if expected_root != actual_root:
        issues.append("evidence merkle root mismatch")
    return issues


def to_md(report: dict) -> str:
    telemetry = report["sections"]["telemetry"]
    execution = report["sections"]["governance_execution"]
    proof = report["sections"]["self_proof"]
    coverage = report["sections"]["coverage"]

    lines = [
        "# 治理证据报告（单一自证明）",
        "",
        f"- 生成时间: {report['generated_at']}",
        f"- 证据完整性: **{report['status']}**",
        f"- 治理质量: **{report.get('quality_status', 'unknown')}**",
    ]
    if report.get("issues"):
        lines.append(f"- 阻断问题: {'; '.join(report['issues'])}")
    if report.get("warnings"):
        lines.append(f"- 非阻断警告: {'; '.join(report['warnings'])}")

    lines += [
        "",
        "## 1. 遥测",
        f"- 探针库: {telemetry['probe']['row_count']} 行, "
        f"距今 {telemetry['probe']['age_hours']}h, "
        f"fresh={'PASS' if telemetry['probe']['fresh_26h'] else 'FAIL'}",
        f"- sidecar: {telemetry['sidecar']['url']} healthy={telemetry['sidecar']['healthy']}",
        f"- MCP well-known: {'PASS' if telemetry['mcp_wellknown_reachable'] else 'FAIL'}",
        "",
        "## 2. 治理执行",
    ]
    for name, info in execution["chains"].items():
        lines.append(
            f"- {name}: {info['rows']} 行" + (" (MISSING)" if info.get("missing") else "")
        )
    lines += [
        f"- 24h per-agent 裁决: {json.dumps(execution['per_agent_24h'], ensure_ascii=False)}",
        f"- 计数: BLOCKED={execution['counts']['blocked']} "
        f"DENY={execution['counts']['deny']} HITL={execution['counts']['hitl']} "
        f"拦截率={execution['interception_rate']}",
        "",
        "## 3. 自证明",
        f"- 审计健康退出码: {proof['audit_health']['rc']}",
        f"- 健康判定: {proof['health'].get('healthy')} "
        f"(checked_at={proof['health'].get('checked_at')})",
        f"- 必需链验证: {proof['chain_verify']['required_passed']}/"
        f"{proof['chain_verify']['required_total']}",
        f"- 可选链验证: {json.dumps(proof['chain_verify']['optional'], ensure_ascii=False)}",
        f"- 关键裁决: {json.dumps(proof['verdicts'], ensure_ascii=False)}",
        "",
        "## 4. 覆盖",
        f"- declared={coverage['declared']} registry={coverage['registry']} "
        f"active_24h={coverage['active_24h']} internal_defs={coverage['internal_defs']} "
        f"coding_registry={coverage['coding_registry']} gaps={coverage['gap_count']}",
        f"- generated_at={coverage['generated_at']} age_hours={coverage['age_hours']}",
        "",
        "## evidence_hash",
        f"- 文件数: {len(report['evidence_files'])}",
        f"- merkle 根: `{report['evidence_hash']}`",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="校验已有报告的哈希与 Merkle 根")
    args = parser.parse_args()

    if args.check:
        issues = verify_report()
        for issue in issues:
            print(f"FAIL: {issue}")
        if issues:
            return 1
        print(f"evidence report verified: {OUTPUT_JSON}")
        return 0

    report = build()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write(to_md(report))

    print(f"证据报告已生成: {OUTPUT_JSON}")
    print(
        f"status={report['status']} evidence_hash={report['evidence_hash'][:16]}... "
        f"files={len(report['evidence_files'])}"
    )
    for issue in report["issues"]:
        print(f"  ❌ {issue}")
    for warning in report["warnings"]:
        print(f"  ⚠️ {warning}")
    return 0 if report["status"] == "healthy" else 1


if __name__ == "__main__":
    sys.exit(main())
