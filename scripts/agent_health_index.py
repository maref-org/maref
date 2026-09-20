#!/usr/bin/env python3
"""
Agent 健康指数模型

多维度评分 (0-100):
- trust_score (25%): 信任分 (基于治理决策历史、违规率)
- violation_rate (20%): 违规率 (越低越好)
- interception_rate (15%): 拦截率 (适中最好，过高/过低都异常)
- activity_score (15%): 活跃度 (调用频次归一化)
- collaboration_score (10%): 协作质量 (跨 Agent 协作成功率)
- latency_score (10%): 延迟表现 (P95 延迟)
- cost_efficiency_score (5%): 成本效率

输出: analytics/agent_health_index 分区表
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

# 权重配置
WEIGHTS = {
    "trust": 0.25,
    "violation": 0.20,
    "interception": 0.15,
    "activity": 0.15,
    "collaboration": 0.10,
    "latency": 0.10,
    "cost": 0.05,
}

# 健康等级阈值
HEALTH_TIERS = [
    (90, "excellent"),
    (75, "good"),
    (60, "fair"),
    (40, "poor"),
    (0, "critical"),
]


def _load_agent_sessions(since_hours: int) -> list[dict]:
    """加载 curated/agent_sessions"""
    events = []
    since_ts = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp()

    curated_dir = LAKE_ROOT / "curated" / "agent_sessions"
    if curated_dir.exists() and DUCKDB_AVAILABLE:
        try:
            conn = duckdb.connect()
            date_cutoff = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).strftime("%Y%m%d")
            df = conn.execute(f"""
                SELECT * FROM read_parquet('{curated_dir}/**/*.parquet')
                WHERE date >= '{date_cutoff}' AND start_time >= {since_ts}
            """).fetchdf()
            for _, row in df.iterrows():
                events.append(row.to_dict())
            conn.close()
            return events
        except Exception:
            pass
    return []


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
    return []


def _load_cross_agent_flows(since_hours: int) -> list[dict]:
    """加载 curated/cross_agent_flows"""
    events = []
    since_ts = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp()

    curated_dir = LAKE_ROOT / "curated" / "cross_agent_flows"
    if curated_dir.exists() and DUCKDB_AVAILABLE:
        try:
            conn = duckdb.connect()
            date_cutoff = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).strftime("%Y%m%d")
            df = conn.execute(f"""
                SELECT * FROM read_parquet('{curated_dir}/**/*.parquet')
                WHERE date >= '{date_cutoff}' AND start_time >= {since_ts}
            """).fetchdf()
            for _, row in df.iterrows():
                events.append(row.to_dict())
            conn.close()
            return events
        except Exception:
            pass
    return []


def _load_coding_agent_status() -> dict[str, dict]:
    """加载 coding_agent_status.json (信任分基线)"""
    try:
        from maref_config import REPORTS_DIR
        status_file = REPORTS_DIR / "coding_agents_status.json"
        if status_file.exists():
            with open(status_file) as f:
                data = json.load(f)
                return {a["agent_id"]: a for a in data.get("agents", [])}
    except Exception:
        pass
    return {}


def compute_health_index(since_hours: int = 24) -> list[dict]:
    """计算 Agent 健康指数"""
    print(f"📊 加载最近 {since_hours}h 数据...")

    sessions = _load_agent_sessions(since_hours)
    executions = _load_tool_executions(since_hours)
    flows = _load_cross_agent_flows(since_hours)
    agent_status = _load_coding_agent_status()

    print(f"   会话: {len(sessions)} | 执行: {len(executions)} | 协作流: {len(flows)}")
    print(f"   注册 Agent: {list(agent_status.keys())}")

    # 按 agent 聚合
    by_agent: dict[str, dict] = defaultdict(lambda: {
        "sessions": [],
        "executions": [],
        "flows_as_root": [],
        "flows_as_participant": [],
        "trust_baseline": 50.0,
    })

    # 注册表基线信任分
    for aid, info in agent_status.items():
        by_agent[aid]["trust_baseline"] = info.get("runtime_kpi", {}).get("trust_score", 50.0)
        by_agent[aid]["domain_weight"] = info.get("domain_weight", 1)
        by_agent[aid]["integration_kind"] = info.get("integration_kind", "unknown")

    for s in sessions:
        aid = s.get("agent_id")
        if aid:
            by_agent[aid]["sessions"].append(s)

    for ex in executions:
        aid = ex.get("agent_id")
        if aid:
            by_agent[aid]["executions"].append(ex)

    for f in flows:
        root = f.get("root_agent_id")
        if root:
            by_agent[root]["flows_as_root"].append(f)
        # 参与者
        try:
            seq = json.loads(f.get("agent_sequence", "[]"))
            for aid in seq:
                if aid != root:
                    by_agent[aid]["flows_as_participant"].append(f)
        except Exception:
            pass

    # 计算各维度得分
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    reports = []

    for aid, data in by_agent.items():
        if not data["executions"] and not data["sessions"]:
            continue

        execs = data["executions"]
        sess = data["sessions"]

        # 1. trust_score (25%)
        trust = data["trust_baseline"]

        # 2. violation_rate (20%) - 越低越好
        total_calls = len(execs)
        violations = sum(1 for e in execs if e.get("verdict") in ("deny", "ask_user"))
        violation_rate = violations / max(total_calls, 1)
        violation_score = max(0, 100 - violation_rate * 200)  # 50%违规率=0分

        # 3. interception_rate (15%) - 适中最好 (10-30% 为佳)
        intercepted = sum(1 for e in execs if e.get("verdict") == "ask_user")
        interception_rate = intercepted / max(total_calls, 1)
        if 0.1 <= interception_rate <= 0.3:
            interception_score = 100
        elif interception_rate < 0.1:
            interception_score = 50 + interception_rate * 500  # 太低可能漏报
        else:
            interception_score = max(0, 100 - (interception_rate - 0.3) * 300)

        # 4. activity_score (15%) - 基于调用频次归一化
        # 使用对数缩放: log10(calls+1) * 20, 上限 100
        import math
        activity_raw = math.log10(total_calls + 1) * 20
        activity_score = min(100, activity_raw)

        # 5. collaboration_score (10%) - 跨 Agent 协作成功率
        total_flows = len(data["flows_as_root"]) + len(data["flows_as_participant"])
        successful_flows = sum(1 for f in data["flows_as_root"] if f.get("final_outcome") == "success")
        successful_flows += sum(1 for f in data["flows_as_participant"] if f.get("final_outcome") == "success")
        collaboration_score = (successful_flows / max(total_flows, 1)) * 100 if total_flows > 0 else 50

        # 6. latency_score (10%) - P95 延迟
        latencies = [e.get("latency_ms", 0) for e in execs if e.get("latency_ms", 0) > 0]
        if latencies:
            latencies.sort()
            p95 = latencies[int(len(latencies) * 0.95)]
            # P95 < 100ms = 100, P95 > 5000ms = 0
            latency_score = max(0, 100 - (p95 / 50))
        else:
            latency_score = 50

        # 7. cost_efficiency_score (5%) - 成本/调用
        total_cost = sum(e.get("cost_usd", 0) for e in execs)
        cost_per_call = total_cost / max(total_calls, 1)
        # 成本越低越好，假设 $0.01/调用为基准
        cost_score = max(0, 100 - cost_per_call * 10000)

        # 加权合成
        composite = (
            trust * WEIGHTS["trust"] +
            violation_score * WEIGHTS["violation"] +
            interception_score * WEIGHTS["interception"] +
            activity_score * WEIGHTS["activity"] +
            collaboration_score * WEIGHTS["collaboration"] +
            latency_score * WEIGHTS["latency"] +
            cost_score * WEIGHTS["cost"]
        )

        # 健康等级
        health_tier = "critical"
        for threshold, tier in HEALTH_TIERS:
            if composite >= threshold:
                health_tier = tier
                break

        # 趋势 (简化: 与 7d/30d 前对比，这里用 placeholder)
        trend_7d = 0.0
        trend_30d = 0.0

        # 告警
        alerts = []
        if violation_rate > 0.5:
            alerts.append("高违规率")
        if interception_rate > 0.5:
            alerts.append("过度拦截")
        if total_calls == 0:
            alerts.append("无活动")
        if latency_score < 30:
            alerts.append("高延迟")

        reports.append({
            "date": date_str,
            "agent_id": aid,
            "trust_score": round(trust, 1),
            "violation_rate": round(violation_rate, 4),
            "interception_rate": round(interception_rate, 4),
            "activity_score": round(activity_score, 1),
            "collaboration_score": round(collaboration_score, 1),
            "latency_score": round(latency_score, 1),
            "cost_efficiency_score": round(cost_score, 1),
            "composite_health": round(composite, 1),
            "health_tier": health_tier,
            "trend_7d": trend_7d,
            "trend_30d": trend_30d,
            "alerts": json.dumps(alerts),
        })

    return reports


def write_reports(reports: list[dict], date_str: str) -> None:
    """写入 analytics/agent_health_index"""
    if not reports:
        print("⚠️  无 Agent 健康数据")
        return

    analytics_dir = LAKE_ROOT / "analytics" / "agent_health_index"
    analytics_dir.mkdir(parents=True, exist_ok=True)

    json_file = analytics_dir / f"agent_health_index_{date_str}.json"
    with open(json_file, "w") as f:
        json.dump(reports, f, indent=2, ensure_ascii=False)
    print(f"📝 JSON 输出: {json_file}")

    if DUCKDB_AVAILABLE:
        try:
            parquet_file = analytics_dir / f"agent_health_index_{date_str}.parquet"
            conn = duckdb.connect()
            conn.execute(f"""
                COPY (
                    SELECT * FROM read_json_auto('{json.dumps(reports)}')
                ) TO '{parquet_file}' (FORMAT PARQUET, PARTITION BY (agent_id))
            """)
            conn.close()
            print(f"📊 Parquet 输出: {parquet_file}")
        except Exception as e:
            print(f"⚠️  Parquet 写入失败: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent 健康指数模型")
    parser.add_argument("--since", default="24h", help="时间范围: 1h, 6h, 24h, 7d, 30d")
    parser.add_argument("--date", help="指定日期 YYYYMMDD")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    args = parser.parse_args()

    since_map = {"1h": 1, "6h": 6, "24h": 24, "7d": 168, "30d": 720}
    since_hours = since_map.get(args.since, 24)
    date_str = args.date or datetime.now(timezone.utc).strftime("%Y%m%d")

    print("=" * 60)
    print("Agent 健康指数模型")
    print("=" * 60)
    print(f"时间范围: 最近 {since_hours} 小时")
    print()

    reports = compute_health_index(since_hours)

    if args.dry_run:
        print("\n[dry-run] 结果预览:")
        for r in reports:
            print(f"  {r['agent_id']}: health={r['composite_health']} tier={r['health_tier']} "
                  f"trust={r['trust_score']} viol={r['violation_rate']:.1%} "
                  f"intercept={r['interception_rate']:.1%} act={r['activity_score']:.0f}")
        return 0

    write_reports(reports, date_str)

    print(f"\n✅ 完成: {len(reports)} 个 Agent 健康指数")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())