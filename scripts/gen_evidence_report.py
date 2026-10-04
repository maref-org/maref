#!/usr/bin/env python3
"""T2-4 单一自证明报告（三层合流）。

生成 reports/governance_evidence_report.json / .md：
  1. 遥测：探针行数+新鲜度 / sidecar 健康 / 端点可达
  2. 治理执行：各链行数、24h per-agent 裁决数、BLOCKED/DENY/HITL 计数、拦截率
  3. 自证明：报告数量、健康判定、哈希链验证通过率
  4. 覆盖：declared vs registry vs active 对账
  底部 evidence_hash = 所有引用文件 sha256 清单的 merkle 根
"""
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
from maref_config import (  # noqa: E402
    PROBE_DB,
    REPO_DIR,
    REPORTS_DIR,
    RUNTIME_DIR,
    sidecar_auth_headers,
    sidecar_url,
)

OUTPUT_JSON = REPORTS_DIR / "governance_evidence_report.json"
OUTPUT_MD = REPORTS_DIR / "governance_evidence_report.md"
HOOKS_CHAIN = Path.home() / ".claude" / "hooks" / "state" / "governance_audit.jsonl"
RT_CHAIN = Path(RUNTIME_DIR) / "governance_audit.jsonl"
MCP_DECISIONS = Path(RUNTIME_DIR) / ".governance" / "mcp_decisions.jsonl"
CHAINS = {
    "hooks_state": HOOKS_CHAIN,
    "audit_v2": REPO_DIR / "governance_audit_v2.jsonl",
    "audit_v1": REPO_DIR / "governance_audit.jsonl",
    "recursive_v2": REPO_DIR / "recursive_governance_audit_v2.jsonl",
    "openclaw_rt": RT_CHAIN,
    "mcp_decisions": MCP_DECISIONS,
}
PROOF_CHAINS = ["audit_v2", "audit_v1", "openclaw_rt"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def count_lines(path: Path) -> int:
    n = 0
    with open(path, "rb") as f:
        for _ in f:
            n += 1
    return n


def section_telemetry() -> dict:
    fresh = False
    rows = last_ts = age_h = None
    try:
        con = sqlite3.connect(str(PROBE_DB))
        rows = con.execute("select count(*) from probe_readings").fetchone()[0]
        last_ts = con.execute("select max(timestamp) from probe_readings").fetchone()[0]
        con.close()
        if last_ts:
            age_h = round((time.time() - float(last_ts)) / 3600, 2)
            fresh = age_h < 26
    except sqlite3.Error as e:
        age_h = f"error: {e}"

    sidecar_ok = ep_ok = False
    url = sidecar_url()
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=3) as r:
            body = r.read(512).decode("utf-8", "replace")
        sidecar_ok = "healthy" in body
    except OSError as e:
        body = str(e)
    try:
        req = urllib.request.Request(
            f"{url}/api/mcp/.well-known", headers=sidecar_auth_headers(content_type="")
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            ep_ok = r.status == 200
    except OSError:
        ep_ok = False

    return {
        "probe": {
            "db": str(PROBE_DB),
            "row_count": rows,
            "last_ts": last_ts,
            "age_hours": age_h,
            "fresh_26h": fresh,
        },
        "sidecar": {"url": url, "healthy": sidecar_ok, "health_body": body[:200]},
        "mcp_wellknown_reachable": ep_ok,
    }


def section_governance_execution() -> dict:
    chains = {}
    for name, path in CHAINS.items():
        if path.is_file():
            chains[name] = {
                "path": str(path),
                "rows": count_lines(path),
                "bytes": path.stat().st_size,
            }
        else:
            chains[name] = {"path": str(path), "rows": 0, "missing": True}

    verdicts_24h: Counter = Counter()
    verdicts_total: Counter = Counter()
    per_agent_24h: dict = {}
    cutoff = time.time() - 86400
    try:
        with open(HOOKS_CHAIN, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                v = str(d.get("verdict", "?"))
                verdicts_total[v] += 1
                if float(d.get("timestamp") or 0) >= cutoff:
                    verdicts_24h[v] += 1
                    aid = str(d.get("agent_id") or "unknown")
                    per_agent_24h.setdefault(aid, Counter())[v] += 1
    except OSError:
        pass

    status = load_json(REPORTS_DIR / "coding_agents_status.json") or {}
    gkpi = status.get("global_kpi") or {}
    per_agent_kpi = {
        a.get("agent_id", "?"): {
            "tool_calls_total": (a.get("runtime_kpi") or {}).get("tool_calls_total"),
            "allowed": (a.get("runtime_kpi") or {}).get("tool_calls_allowed"),
            "denied": (a.get("runtime_kpi") or {}).get("tool_calls_denied"),
            "hitl": (a.get("runtime_kpi") or {}).get("tool_calls_hitl"),
            "interception_rate": (a.get("runtime_kpi") or {}).get("interception_rate"),
            "telemetry_auth": a.get("telemetry_auth"),
        }
        for a in (status.get("agents") or [])
    }

    hooks_total = sum(verdicts_total.values())
    blocked = verdicts_total.get("BLOCKED", 0)
    deny = verdicts_total.get("DENY", 0)
    hitl = gkpi.get("tool_calls_hitl", 0)
    intercept_rate = round((blocked + deny) / hooks_total, 6) if hooks_total else 0.0

    return {
        "chains": chains,
        "hooks_verdicts_total": dict(verdicts_total),
        "hooks_verdicts_24h": dict(verdicts_24h),
        "per_agent_24h": {k: dict(v) for k, v in sorted(per_agent_24h.items())},
        "per_agent_kpi": per_agent_kpi,
        "global_kpi": gkpi,
        "counts": {
            "blocked": blocked,
            "deny": deny,
            "hitl": hitl,
            "hooks_rows": hooks_total,
        },
        "interception_rate": intercept_rate,
    }


def section_self_proof() -> dict:
    reports = sorted(REPORTS_DIR.glob("*.json"))
    health = load_json(REPORTS_DIR / "audit_health_check.json") or {}

    chain_verify = {}
    passed = 0
    for name in PROOF_CHAINS:
        path = CHAINS[name]
        if not path.is_file():
            chain_verify[name] = {"rc": -1, "ok": False, "reason": "missing"}
            continue
        r = subprocess.run(
            [sys.executable, str(REPO_DIR / "scripts" / "verify_audit_chain.py"),
             "--audit-file", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        ok = r.returncode == 0
        passed += int(ok)
        first = (r.stdout or "").splitlines()[:1]
        chain_verify[name] = {"rc": r.returncode, "ok": ok, "result": first[0] if first else ""}

    approval = load_json(REPORTS_DIR / "approval_tier_report.json") or {}
    acc = approval.get("t2_1_acceptance") or {}
    confidence = load_json(REPORTS_DIR / "confidence_audit.json") or {}
    sla = load_json(REPORTS_DIR / "backlog_sla_report.json") or {}
    loop = load_json(
        REPORTS_DIR / f"validation_{datetime.now(timezone.utc):%Y%m%d}.json"
    ) or {}

    return {
        "report_count": len(reports),
        "health": {
            "healthy": health.get("healthy"),
            "issues": health.get("issues"),
            "checked_at": health.get("checked_at"),
        },
        "chain_verify": {
            "checked": len(PROOF_CHAINS),
            "passed": passed,
            "pass_rate": round(passed / len(PROOF_CHAINS), 4) if PROOF_CHAINS else 0.0,
            "detail": chain_verify,
        },
        "verdicts": {
            "approval_tier_unknown_rate": acc.get("unknown_rate"),
            "approval_tier_deny_flag": acc.get("deny_flag_count"),
            "approval_tier_verdict": acc.get("verdict"),
            "confidence_critical": (confidence.get("stats") or {}).get("critical"),
            "confidence_30d": confidence.get("confidence_30d"),
            "medium_age_p95_days": sla.get("medium_age_p95"),
            "medium_sla_met": sla.get("medium_sla_met"),
            "loop_deployed_verified": (loop.get("summary") or {}).get("deployed_verified"),
            "loop_closed": (loop.get("loop_closed") or {}).get("recorded"),
        },
    }


def section_coverage() -> dict:
    cov = load_json(REPORTS_DIR / "agent_coverage_report.json") or {}
    declared = (cov.get("declared_180") or {}).get("count")
    registry = (cov.get("registry") or {}).get("count")
    active = cov.get("active_24h")
    gaps = cov.get("gaps") or []
    return {
        "declared": declared,
        "registry": registry,
        "active_24h": active,
        "internal_defs": (cov.get("internal_defs") or {}).get("count"),
        "coding_registry": (cov.get("coding_registry") or {}).get("count"),
        "gap_count": len(gaps),
        "gaps": gaps,
        "generated_at": cov.get("generated_at"),
        "reconciled": bool(cov) and not gaps,
    }


def merkle_root(hashes: list) -> str:
    hs = sorted(hashes)
    if not hs:
        return ""
    while len(hs) > 1:
        if len(hs) % 2:
            hs.append(hs[-1])
        hs = [hashlib.sha256((hs[i] + hs[i + 1]).encode()).hexdigest()
              for i in range(0, len(hs), 2)]
    return hs[0]


def build() -> dict:
    sections = {
        "telemetry": section_telemetry(),
        "governance_execution": section_governance_execution(),
        "self_proof": section_self_proof(),
        "coverage": section_coverage(),
    }

    evidence_paths = sorted(
        {p for p in CHAINS.values() if p.is_file()}
        | {PROBE_DB}
        | {p for p in REPORTS_DIR.glob("*.json") if p != OUTPUT_JSON}
    )
    evidence_files = []
    for p in evidence_paths:
        try:
            evidence_files.append({"path": str(p), "sha256": sha256_file(p)})
        except OSError:
            continue

    issues = []
    t = sections["telemetry"]
    if not t["probe"].get("fresh_26h"):
        issues.append("探针数据非新鲜 (<26h)")
    if not t["sidecar"].get("healthy"):
        issues.append("sidecar 不健康")
    if not t.get("mcp_wellknown_reachable"):
        issues.append("MCP 端点不可达")
    if sections["self_proof"]["health"].get("healthy") is not True:
        issues.append("审计健康检查未通过")
    if sections["self_proof"]["chain_verify"]["pass_rate"] < 1.0:
        issues.append("哈希链验证未全过")
    if sections["coverage"].get("gap_count"):
        issues.append(f"覆盖对账存在 {sections['coverage']['gap_count']} 个 gap")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "healthy" if not issues else "attention",
        "issues": issues,
        "sections": sections,
        "evidence_files": evidence_files,
        "evidence_hash": merkle_root([e["sha256"] for e in evidence_files]),
    }


def to_md(rep: dict) -> str:
    t, g, s, c = (
        rep["sections"]["telemetry"], rep["sections"]["governance_execution"],
        rep["sections"]["self_proof"], rep["sections"]["coverage"],
    )
    lines = [
        "# 治理证据报告（单一自证明）",
        "",
        f"- 生成时间: {rep['generated_at']}",
        f"- 状态: **{rep['status']}**"
        + (f" — {'; '.join(rep['issues'])}" if rep["issues"] else ""),
        "",
        "## 1. 遥测",
        f"- 探针库: {t['probe']['row_count']} 行, 距今 {t['probe']['age_hours']}h, "
        f"fresh={'PASS' if t['probe']['fresh_26h'] else 'FAIL'}",
        f"- sidecar: {t['sidecar']['url']} healthy={t['sidecar']['healthy']}",
        f"- MCP well-known: {'PASS' if t['mcp_wellknown_reachable'] else 'FAIL'}",
        "",
        "## 2. 治理执行",
    ]
    for name, info in g["chains"].items():
        lines.append(f"- {name}: {info['rows']} 行"
                     + (" (MISSING)" if info.get("missing") else ""))
    lines += [
        f"- 24h per-agent 裁决: {json.dumps(g['per_agent_24h'], ensure_ascii=False)}",
        f"- 计数: BLOCKED={g['counts']['blocked']} DENY={g['counts']['deny']} "
        f"HITL={g['counts']['hitl']} 拦截率={g['interception_rate']}",
        "",
        "## 3. 自证明",
        f"- 报告数量: {s['report_count']}",
        f"- 健康判定: {s['health'].get('healthy')} (checked_at={s['health'].get('checked_at')})",
        f"- 链验证通过率: {s['chain_verify']['passed']}/{s['chain_verify']['checked']} "
        f"({s['chain_verify']['pass_rate']})",
        f"- 关键裁决: {json.dumps(s['verdicts'], ensure_ascii=False)}",
        "",
        "## 4. 覆盖",
        f"- declared={c['declared']} registry={c['registry']} active_24h={c['active_24h']} "
        f"internal_defs={c['internal_defs']} coding_registry={c['coding_registry']} "
        f"gaps={c['gap_count']}",
        "",
        "## evidence_hash",
        f"- 文件数: {len(rep['evidence_files'])}",
        f"- merkle 根: `{rep['evidence_hash']}`",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    rep = build()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2, ensure_ascii=False)
    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write(to_md(rep))
    print(f"证据报告已生成: {OUTPUT_JSON}")
    print(f"status={rep['status']} evidence_hash={rep['evidence_hash'][:16]}... "
          f"files={len(rep['evidence_files'])}")
    if rep["issues"]:
        for i in rep["issues"]:
            print(f"  ⚠️ {i}")
    return 0 if rep["status"] == "healthy" else 1


if __name__ == "__main__":
    sys.exit(main())
