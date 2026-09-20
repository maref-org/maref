#!/usr/bin/env python3
"""
规则有效度计算引擎

从 curated/governance_decisions 和 curated/tool_executions 计算每条治理规则的有效度指标:
- FP/FN 估计 (基于后验反馈 / HITL 结果 / 人工复核样本)
- 覆盖率 (命中该规则的工具调用占比)
- 平均延迟
- 漂移分数 (与基线版本偏离)
- 有效度分级 (high/medium/low/deprecated)
- 优化建议 (keep/tune/deprecate/replace)

输出: analytics/rule_effectiveness 分区表
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False

LAKE_ROOT = Path(os.environ.get("MAREF_GOVERNANCE_LAKE", "/Volumes/1TB-M2/maref-governance-lake"))


# 规则基线配置 (用于漂移检测)
RULE_BASELINES = {
    "mcp-rule-001": {"expected_allow_rate": 0.95, "expected_latency_ms": 1.0, "version": "1.0"},
    "mcp-rule-002": {"expected_allow_rate": 0.90, "expected_latency_ms": 2.0, "version": "1.0"},
    "mcp-rule-003": {"expected_deny_rate": 0.99, "expected_latency_ms": 5.0, "version": "1.0"},
    "mcp-rule-004": {"expected_deny_rate": 0.99, "expected_latency_ms": 3.0, "version": "1.0"},
    "mcp-rule-005": {"expected_hitl_rate": 0.80, "expected_latency_ms": 10.0, "version": "1.0"},
    "mcp-rule-006": {"expected_audit_rate": 0.70, "expected_latency_ms": 15.0, "version": "1.0"},
    "trust_boundary": {"expected_deny_rate": 0.95, "expected_latency_ms": 5.0, "version": "1.0"},
    "circuit_breaker": {"expected_deny_rate": 0.99, "expected_latency_ms": 2.0, "version": "1.0"},
    "budget_breaker": {"expected_deny_rate": 0.99, "expected_latency_ms": 3.0, "version": "1.0"},
    "destructive_gate": {"expected_hitl_rate": 0.85, "expected_latency_ms": 10.0, "version": "1.0"},
    "irreversible_hitl": {"expected_hitl_rate": 0.95, "expected_latency_ms": 5.0, "version": "1.0"},
    "intent_chain_halt": {"expected_deny_rate": 0.90, "expected_latency_ms": 20.0, "version": "1.0"},
    "intent_chain_escalate": {"expected_hitl_rate": 0.80, "expected_latency_ms": 20.0, "version": "1.0"},
    "permission_matrix": {"expected_deny_rate": 0.80, "expected_latency_ms": 2.0, "version": "1.0"},
    "circuit_breaker_depth": {"expected_deny_rate": 0.95, "expected_latency_ms": 2.0, "version": "1.0"},
    "circuit_breaker_monitor": {"expected_deny_rate": 0.90, "expected_latency_ms": 5.0, "version": "1.0"},
    "default": {"expected_allow_rate": 0.50, "expected_latency_ms": 10.0, "version": "1.0"},
}


def _load_curated_decisions(since_hours: int) -> list[dict]:
    """加载 curated/governance_decisions"""
    events = []
    since_ts = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp()

    # 优先从数据湖读取
    curated_dir = LAKE_ROOT / "curated" / "governance_decisions"
    if curated_dir.exists() and DUCKDB_AVAILABLE:
        try:
            conn = duckdb.connect()
            # 读取最近 since_hours 小时的分区
            date_cutoff = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).strftime("%Y%m%d")
            df = conn.execute(f"""
                SELECT * FROM read_parquet('{curated_dir}/**/*.parquet')
                WHERE date >= '{date_cutoff}' AND timestamp >= {since_ts}
            """).fetchdf()
            for _, row in df.iterrows():
                events.append(row.to_dict())
            conn.close()
            return events
        except Exception:
            pass

    # 回退: 从审计日志提取
    from maref_config import REPO_DIR
    audit_log = REPO_DIR / ".governance" / "governance_audit.jsonl"
    if audit_log.exists():
        try:
            with open(audit_log) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                        ts = ev.get("timestamp", 0)
                        if ts >= since_ts and ev.get("event_type") == "governance_decision":
                            meta = ev.get("metadata", {})
                            events.append({
                                "decision_id": ev.get("id", ""),
                                "timestamp": ts,
                                "agent_id": ev.get("actor", ""),
                                "tool_name": ev.get("action", ""),
                                "verdict": meta.get("verdict", "").lower(),
                                "matched_rule": meta.get("matched_rule", ""),
                                "risk_score": meta.get("risk_score", 0.0),
                                "hitl_triggered": meta.get("hitl_tier") != "",
                                "hitl_tier": meta.get("hitl_tier", ""),
                                "latency_ms": meta.get("latency_ms", 0),
                            })
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

    return events


def _load_tool_executions(since_hours: int) -> list[dict]:
    """加载 curated/tool_executions"""
    events = []
    since_ts = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp()

    curated_dir = LAKE_ROOT / "curated" / "tool_executions"
    if curated_dir.exists() and DUCKDB_AVAILABLE:
        try:
            conn = duckdb.connect()
            date_cutoff = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).strftime("%Y%m%d")
            df = conn.execute(f"""
                SELECT * FROM read_parquet('{curated_dir}/**/*.parquet')
                WHERE date >= '{date_cutoff}' AND timestamp >= {since_ts}
            """).fetchdf()
            for _, row in df.iterrows():
                events.append(row.to_dict())
            conn.close()
            return events
        except Exception:
            pass

    return events


def _load_hitl_results(since_hours: int) -> dict[str, str]:
    """加载 HITL 结果 (approved/rejected/auto_approved)"""
    results = {}
    since_ts = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp()

    # 从审计日志提取 HITL 结果
    from maref_config import REPO_DIR
    audit_log = REPO_DIR / ".governance" / "governance_audit.jsonl"
    if audit_log.exists():
        try:
            with open(audit_log) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                        ts = ev.get("timestamp", 0)
                        if ts >= since_ts and ev.get("event_type") == "hitl_resolved":
                            hitl_id = ev.get("action", "").replace("HITL_", "")
                            outcome = "approved" if "APPROVE" in ev.get("details", "") else "rejected"
                            results[hitl_id] = outcome
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

    return results


def compute_rule_effectiveness(since_hours: int = 24) -> list[dict]:
    """计算规则有效度"""
    print(f"📊 加载最近 {since_hours}h 决策数据...")

    decisions = _load_curated_decisions(since_hours)
    executions = _load_tool_executions(since_hours)
    hitl_results = _load_hitl_results(since_hours)

    print(f"   决策记录: {len(decisions)}")
    print(f"   工具执行: {len(executions)}")
    print(f"   HITL 结果: {len(hitl_results)}")

    # 按规则聚合
    by_rule: dict[str, dict] = defaultdict(lambda: {
        "total": 0,
        "allow": 0,
        "deny": 0,
        "ask_user": 0,
        "latencies": [],
        "hitl_triggered": 0,
        "hitl_resolved": {"approved": 0, "rejected": 0, "auto_approved": 0, "pending": 0},
        "tools": set(),
        "agents": set(),
    })

    for d in decisions:
        rule = d.get("matched_rule", "unknown")
        stats = by_rule[rule]
        stats["total"] += 1
        stats["tools"].add(d.get("tool_name", ""))
        stats["agents"].add(d.get("agent_id", ""))
        lat = d.get("latency_ms", 0)
        if lat:
            stats["latencies"].append(lat)

        verdict = d.get("verdict", "").lower()
        if verdict == "allow":
            stats["allow"] += 1
        elif verdict == "deny":
            stats["deny"] += 1
        elif verdict == "ask_user":
            stats["ask_user"] += 1
            stats["hitl_triggered"] += 1
            hitl_id = d.get("hitl_event_id", "")
            if hitl_id in hitl_results:
                outcome = hitl_results[hitl_id]
                stats["hitl_resolved"][outcome] = stats["hitl_resolved"].get(outcome, 0) + 1
            else:
                stats["hitl_resolved"]["pending"] = stats["hitl_resolved"].get("pending", 0) + 1

    # 计算覆盖率 (基于工具执行)
    rule_coverage: dict[str, int] = defaultdict(int)
    total_executions = len(executions)
    for ex in executions:
        rule = ex.get("matched_rule", "unknown")
        rule_coverage[rule] += 1

    # 生成报告
    now = datetime.now(timezone.utc).isoformat()
    reports = []

    for rule_id, stats in by_rule.items():
        if stats["total"] == 0:
            continue

        total = stats["total"]
        baseline = RULE_BASELINES.get(rule_id, RULE_BASELINES["default"])

        # 基础指标
        allow_rate = stats["allow"] / total
        deny_rate = stats["deny"] / total
        ask_user_rate = stats["ask_user"] / total
        avg_latency = sum(stats["latencies"]) / len(stats["latencies"]) if stats["latencies"] else 0

        # FP/FN 估计 (基于 HITL 结果)
        # FP: 规则拦截 (deny/ask_user) 但 HITL 通过 (approved) -> 可能是误报
        # FN: 规则放行 (allow) 但实际应该拦截 (无法直接观测，用启发式)
        hitl_total = stats["hitl_resolved"]["approved"] + stats["hitl_resolved"]["rejected"] + stats["hitl_resolved"]["auto_approved"]
        fp_est = 0.0
        if stats["ask_user"] > 0 and hitl_total > 0:
            fp_est = stats["hitl_resolved"]["approved"] / hitl_total  # HITL 通过率作为 FP 代理

        fn_est = 0.0  # 需要红队/人工标注数据，暂时为 0

        # 覆盖率
        coverage = rule_coverage.get(rule_id, 0) / max(total_executions, 1)

        # 漂移分数 (与基线偏离)
        drift = 0.0
        if "expected_allow_rate" in baseline:
            drift += abs(allow_rate - baseline["expected_allow_rate"])
        if "expected_deny_rate" in baseline:
            drift += abs(deny_rate - baseline["expected_deny_rate"])
        if "expected_hitl_rate" in baseline:
            drift += abs(ask_user_rate - baseline["expected_hitl_rate"])
        if "expected_latency_ms" in baseline and avg_latency > 0:
            drift += abs(avg_latency - baseline["expected_latency_ms"]) / baseline["expected_latency_ms"] * 0.1
        drift = min(1.0, drift)  # 归一化到 0-1

        # 有效度分级
        if drift < 0.1 and fp_est < 0.1 and coverage > 0.01:
            effectiveness = "high"
            recommendation = "keep"
        elif drift < 0.3 and fp_est < 0.3:
            effectiveness = "medium"
            recommendation = "tune"
        elif drift > 0.5 or fp_est > 0.5:
            effectiveness = "low"
            recommendation = "deprecate"
        else:
            effectiveness = "medium"
            recommendation = "tune"

        # 最后触发时间
        last_triggered = max(
            (d.get("timestamp", 0) for d in decisions if d.get("matched_rule") == rule_id),
            default=0
        )

        reports.append({
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "rule_id": rule_id,
            "rule_version": baseline.get("version", "1.0"),
            "total_evaluations": total,
            "allow_count": stats["allow"],
            "deny_count": stats["deny"],
            "ask_user_count": stats["ask_user"],
            "false_positive_est": round(fp_est, 4),
            "false_negative_est": round(fn_est, 4),
            "coverage_rate": round(coverage, 6),
            "avg_latency_ms": round(avg_latency, 2),
            "drift_score": round(drift, 4),
            "last_triggered": last_triggered,
            "effectiveness_tier": effectiveness,
            "recommendation": recommendation,
        })

    return reports


def write_reports(reports: list[dict], date_str: str) -> None:
    """写入 analytics/rule_effectiveness"""
    if not reports:
        print("⚠️  无规则有效度数据")
        return

    analytics_dir = LAKE_ROOT / "analytics" / "rule_effectiveness"
    analytics_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_file = analytics_dir / f"rule_effectiveness_{date_str}.json"
    with open(json_file, "w") as f:
        json.dump(reports, f, indent=2, ensure_ascii=False)
    print(f"📝 JSON 输出: {json_file}")

    # Parquet
    if DUCKDB_AVAILABLE:
        try:
            parquet_file = analytics_dir / f"rule_effectiveness_{date_str}.parquet"
            conn = duckdb.connect()
            conn.execute(f"""
                COPY (
                    SELECT * FROM read_json_auto('{json.dumps(reports)}')
                ) TO '{parquet_file}' (FORMAT PARQUET, PARTITION BY (rule_id))
            """)
            conn.close()
            print(f"📊 Parquet 输出: {parquet_file}")
        except Exception as e:
            print(f"⚠️  Parquet 写入失败: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="规则有效度计算引擎")
    parser.add_argument("--since", default="24h", help="时间范围: 1h, 6h, 24h, 7d, 30d")
    parser.add_argument("--date", help="指定日期 YYYYMMDD")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    args = parser.parse_args()

    since_map = {"1h": 1, "6h": 6, "24h": 24, "7d": 168, "30d": 720}
    since_hours = since_map.get(args.since, 24)
    date_str = args.date or datetime.now(timezone.utc).strftime("%Y%m%d")

    print("=" * 60)
    print("规则有效度计算引擎")
    print("=" * 60)
    print(f"时间范围: 最近 {since_hours} 小时")
    print()

    reports = compute_rule_effectiveness(since_hours)

    if args.dry_run:
        print("\n[dry-run] 结果预览:")
        for r in reports:
            print(f"  {r['rule_id']}: total={r['total_evaluations']} FP={r['false_positive_est']:.2%} "
                  f"drift={r['drift_score']:.2f} tier={r['effectiveness_tier']} rec={r['recommendation']}")
        return 0

    write_reports(reports, date_str)

    print(f"\n✅ 完成: {len(reports)} 条规则有效度报告")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())