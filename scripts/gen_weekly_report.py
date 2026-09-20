#!/usr/bin/env python3
"""
周报/月报生成器

聚合 analytics 层数据，生成结构化治理报告:
- 周报: 每周一生成，覆盖过去 7 天趋势、异常、规则演进建议
- 月报: 每月 1 号生成，覆盖过去 30 天战略视图、ROI、演进路线图

输出: reports/weekly-governance-W##.json, reports/monthly-governance-YYYYMM.json
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
REPORTS_DIR = Path(os.environ.get("MAREF_REPORTS_DIR", "/Volumes/1TB-M2/public/maref/reports"))
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _load_analytics_table(table: str, days: int) -> list[dict]:
    """从 analytics 加载指定天数的数据"""
    events = []
    since_ts = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()

    analytics_dir = LAKE_ROOT / "analytics" / table
    if not analytics_dir.exists() or not DUCKDB_AVAILABLE:
        return events

    try:
        conn = duckdb.connect()
        date_cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
        df = conn.execute(f"""
            SELECT * FROM read_parquet('{analytics_dir}/**/*.parquet')
            WHERE date >= '{date_cutoff}'
        """).fetchdf()
        for _, row in df.iterrows():
            events.append(row.to_dict())
        conn.close()
    except Exception as e:
        print(f"⚠️  加载 {table} 失败: {e}")

    return events


def _load_probe_readings(days: int) -> list[dict]:
    """加载 curated/probe_readings"""
    events = []
    since_ts = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()

    curated_dir = LAKE_ROOT / "curated" / "probe_readings"
    if curated_dir.exists() and DUCKDB_AVAILABLE:
        try:
            conn = duckdb.connect()
            date_cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
            df = conn.execute(f"""
                SELECT * FROM read_parquet('{curated_dir}/**/*.parquet')
                WHERE date >= '{date_cutoff}'
            """).fetchdf()
            for _, row in df.iterrows():
                events.append(row.to_dict())
            conn.close()
        except Exception as e:
            print(f"⚠️  加载 probe_readings 失败: {e}")

    return events


def generate_weekly_report() -> dict:
    """生成周报"""
    print("📊 生成周报 (过去 7 天)...")

    # 加载数据
    kpi_data = _load_analytics_table("daily_governance_kpi", 7)
    health_data = _load_analytics_table("agent_health_index", 7)
    rule_data = _load_analytics_table("rule_effectiveness", 7)
    probe_data = _load_probe_readings(7)
    fuel_data = _load_analytics_table("evolution_fuel", 7)

    # 聚合 KPI
    total_calls = sum(d.get("total_tool_calls", 0) for d in kpi_data)
    total_intercepted = sum(d.get("intercepted_calls", 0) for d in kpi_data)
    total_denied = sum(d.get("denied_calls", 0) for d in kpi_data)
    total_hitl = sum(d.get("hitl_calls", 0) for d in kpi_data)
    avg_latency = sum(d.get("avg_latency_ms", 0) for d in kpi_data) / max(len(kpi_data), 1)
    total_cost = sum(d.get("total_cost_usd", 0) for d in kpi_data)

    # Agent 健康趋势
    by_agent: dict[str, list[float]] = defaultdict(list)
    for h in health_data:
        by_agent[h.get("agent_id", "")].append(h.get("composite_health", 0))

    agent_trends = {}
    for aid, scores in by_agent.items():
        if len(scores) >= 2:
            trend = scores[-1] - scores[0]
            agent_trends[aid] = {
                "current": scores[-1],
                "start": scores[0],
                "trend": round(trend, 1),
                "data_points": len(scores),
            }

    # 规则有效度摘要
    rule_summary = defaultdict(lambda: {"total": 0, "fp": 0.0, "drift": 0.0, "tier": "unknown"})
    for r in rule_data:
        rid = r.get("rule_id", "")
        rule_summary[rid]["total"] += r.get("total_evaluations", 0)
        rule_summary[rid]["fp"] = max(rule_summary[rid]["fp"], r.get("false_positive_est", 0))
        rule_summary[rid]["drift"] = max(rule_summary[rid]["drift"], r.get("drift_score", 0))
        rule_summary[rid]["tier"] = r.get("effectiveness_tier", "unknown")

    # 探针趋势
    probe_trends = defaultdict(list)
    for p in probe_data:
        probe_trends[p.get("probe_name", "")].append(p.get("value", 0))

    # 迭代燃料
    fuel_by_type = defaultdict(int)
    fuel_by_status = defaultdict(int)
    for f in fuel_data:
        fuel_by_type[f.get("fuel_type", "")] += 1
        fuel_by_status[f.get("status", "")] += 1

    # 异常检测
    anomalies = []
    for d in kpi_data:
        if d.get("interception_rate", 0) > 50:
            anomalies.append(f"高拦截率: {d.get('interception_rate', 0):.1f}% on {d.get('date')}")
        if d.get("hitl_rate", 0) > 30:
            anomalies.append(f"高 HITL 率: {d.get('hitl_rate', 0):.1f}% on {d.get('date')}")
        if d.get("avg_latency_ms", 0) > 1000:
            anomalies.append(f"高延迟: {d.get('avg_latency_ms', 0):.0f}ms on {d.get('date')}")

    for p in probe_data:
        if p.get("severity") == "critical":
            anomalies.append(f"探针告警: {p.get('probe_name')} = {p.get('value'):.1f} (critical)")

    # Agent 健康告警
    for aid, trend in agent_trends.items():
        if trend["trend"] < -10:
            anomalies.append(f"Agent 健康下降: {aid} 趋势 {trend['trend']:.1f}")

    now = datetime.now(timezone.utc)
    week_num = now.isocalendar()[1]
    year = now.isocalendar()[0]

    report = {
        "report_id": f"WEEKLY-GOV-{year}-W{week_num:02d}",
        "generated_at": now.isoformat(),
        "period": {
            "start": (now - timedelta(days=7)).strftime("%Y-%m-%d"),
            "end": now.strftime("%Y-%m-%d"),
            "days": 7,
        },
        "summary": {
            "total_tool_calls": total_calls,
            "interception_rate": round(total_intercepted / max(total_calls, 1) * 100, 2),
            "denial_rate": round(total_denied / max(total_calls, 1) * 100, 2),
            "hitl_rate": round(total_hitl / max(total_calls, 1) * 100, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "total_cost_usd": round(total_cost, 6),
            "active_agents": len(set(d.get("agent_id") for d in health_data if d.get("agent_id"))),
            "anomalies_count": len(anomalies),
        },
        "kpi_trends": {
            "daily_calls": [d.get("total_tool_calls", 0) for d in kpi_data],
            "daily_interception_rate": [d.get("interception_rate", 0) for d in kpi_data],
            "daily_hitl_rate": [d.get("hitl_rate", 0) for d in kpi_data],
            "daily_latency": [d.get("avg_latency_ms", 0) for d in kpi_data],
        },
        "agent_health": {
            "trends": agent_trends,
            "current_status": {
                aid: {
                    "health": scores[-1] if scores else 0,
                    "trend": agent_trends.get(aid, {}).get("trend", 0),
                }
                for aid, scores in by_agent.items()
            },
        },
        "rule_effectiveness": {
            rid: {
                "total_evals": v["total"],
                "fp_est": v["fp"],
                "drift": v["drift"],
                "tier": v["tier"],
            }
            for rid, v in rule_summary.items()
        },
        "probe_trends": {
            name: {
                "current": vals[-1] if vals else 0,
                "avg": sum(vals) / len(vals) if vals else 0,
                "max": max(vals) if vals else 0,
                "data_points": len(vals),
            }
            for name, vals in probe_trends.items()
        },
        "evolution_fuel": {
            "by_type": dict(fuel_by_type),
            "by_status": dict(fuel_by_status),
            "total_proposals": sum(fuel_by_type.values()),
        },
        "anomalies": anomalies[:20],  # 限制数量
        "recommendations": _generate_recommendations(anomalies, agent_trends, rule_summary, probe_trends),
    }

    return report


def generate_monthly_report() -> dict:
    """生成月报"""
    print("📊 生成月报 (过去 30 天)...")

    # 加载数据 (复用周报逻辑但扩展到 30 天)
    kpi_data = _load_analytics_table("daily_governance_kpi", 30)
    health_data = _load_analytics_table("agent_health_index", 30)
    rule_data = _load_analytics_table("rule_effectiveness", 30)
    probe_data = _load_probe_readings(30)
    fuel_data = _load_analytics_table("evolution_fuel", 30)

    # 战略指标
    total_calls = sum(d.get("total_tool_calls", 0) for d in kpi_data)
    total_cost = sum(d.get("total_cost_usd", 0) for d in kpi_data)
    avg_interception = sum(d.get("interception_rate", 0) for d in kpi_data) / max(len(kpi_data), 1)
    avg_hitl = sum(d.get("hitl_rate", 0) for d in kpi_data) / max(len(kpi_data), 1)

    # Agent 表现排名
    by_agent_calls: dict[str, int] = defaultdict(int)
    by_agent_cost: dict[str, float] = defaultdict(float)
    by_agent_health: dict[str, list[float]] = defaultdict(list)

    for d in kpi_data:
        # kpi_data 没有按 agent 分解，从 health_data 获取
        pass

    for h in health_data:
        aid = h.get("agent_id", "")
        by_agent_health[aid].append(h.get("composite_health", 0))

    agent_ranking = []
    for aid, scores in by_agent_health.items():
        if scores:
            agent_ranking.append({
                "agent_id": aid,
                "avg_health": round(sum(scores) / len(scores), 1),
                "min_health": min(scores),
                "max_health": max(scores),
                "volatility": round(max(scores) - min(scores), 1),
            })
    agent_ranking.sort(key=lambda x: x["avg_health"], reverse=True)

    # 规则演进建议
    rule_evolution = []
    rule_summary = defaultdict(lambda: {"total": 0, "fp": 0.0, "drift": 0.0, "rec": "keep"})
    for r in rule_data:
        rid = r.get("rule_id", "")
        rule_summary[rid]["total"] += r.get("total_evaluations", 0)
        rule_summary[rid]["fp"] = max(rule_summary[rid]["fp"], r.get("false_positive_est", 0))
        rule_summary[rid]["drift"] = max(rule_summary[rid]["drift"], r.get("drift_score", 0))
        rule_summary[rid]["rec"] = r.get("recommendation", "keep")

    for rid, v in rule_summary.items():
        if v["total"] > 100:  # 只有足够样本的规则
            if v["rec"] in ("deprecate", "replace"):
                rule_evolution.append({
                    "rule_id": rid,
                    "action": v["rec"],
                    "reason": f"FP={v['fp']:.1%}, drift={v['drift']:.2f}",
                    "priority": "P1" if v["fp"] > 0.3 else "P2",
                })

    # ROI 估算
    # 成本节约 = (拦截的恶意调用 * 单次事故成本) - 治理系统运行成本
    prevented_incidents = total_calls * avg_interception / 100 * 0.1  # 假设 10% 拦截是真阳性
    incident_cost = 10000  # 单次事故成本估算 $10k
    governance_cost = total_cost * 30  # 月度运行成本
    roi = (prevented_incidents * incident_cost - governance_cost) / max(governance_cost, 1) * 100

    now = datetime.now(timezone.utc)
    month_str = now.strftime("%Y%m")

    report = {
        "report_id": f"MONTHLY-GOV-{month_str}",
        "generated_at": now.isoformat(),
        "period": {
            "month": month_str,
            "days": 30,
        },
        "strategic_kpis": {
            "total_tool_calls": total_calls,
            "total_cost_usd": round(total_cost, 2),
            "avg_interception_rate": round(avg_interception, 2),
            "avg_hitl_rate": round(avg_hitl, 2),
            "prevented_incidents_est": round(prevented_incidents, 1),
            "roi_percent": round(roi, 1),
        },
        "agent_ranking": agent_ranking[:10],  # Top 10
        "rule_evolution": rule_evolution,
        "governance_maturity": _assess_maturity(kpi_data, health_data, rule_data),
        "roadmap": _generate_roadmap(rule_evolution, agent_ranking, probe_data),
    }

    return report


def _generate_recommendations(anomalies, agent_trends, rule_summary, probe_trends) -> list[str]:
    """基于数据生成建议"""
    recs = []

    if any("高拦截率" in a for a in anomalies):
        recs.append("调整拦截规则阈值，减少误报 (建议: 降低 mcp-rule-005/006 敏感度)")

    if any("高 HITL" in a for a in anomalies):
        recs.append("优化 HITL 路由，引入自动批准策略降低人工负载")

    if any("高延迟" in a for a in anomalies):
        recs.append("排查治理管线瓶颈，考虑并行化规则评估")

    for aid, trend in agent_trends.items():
        if trend["trend"] < -10:
            recs.append(f"关注 {aid} 健康下降，建议检查其集成状态")

    for rid, v in rule_summary.items():
        if v["fp"] > 0.3 and v["total"] > 50:
            recs.append(f"规则 {rid} 高误报 (FP={v['fp']:.1%})，建议降级或重写")

    for name, vals in probe_trends.items():
        if vals and max(vals) > 50:
            recs.append(f"探针 {name} 持续偏高，建议调整阈值或扩容")

    return list(dict.fromkeys(recs))[:10]  # 去重并限制


def _assess_maturity(kpi_data, health_data, rule_data) -> dict:
    """评估治理成熟度 (0-5 级)"""
    score = 0

    # 覆盖度
    if kpi_data:
        avg_intercept = sum(d.get("interception_rate", 0) for d in kpi_data) / len(kpi_data)
        if 10 <= avg_intercept <= 40:
            score += 1

    # 规则质量
    if rule_data:
        high_quality = sum(1 for r in rule_data if r.get("effectiveness_tier") == "high")
        if high_quality / len(rule_data) > 0.5:
            score += 1

    # Agent 健康
    if health_data:
        healthy = sum(1 for h in health_data if h.get("health_tier") in ("excellent", "good"))
        if healthy / len(health_data) > 0.6:
            score += 1

    # 迭代能力
    fuel_data = _load_analytics_table("evolution_fuel", 30)
    if fuel_data:
        deployed = sum(1 for f in fuel_data if f.get("status") == "deployed")
        if deployed > 0:
            score += 1

    # 可观测性
    if kpi_data and len(kpi_data) >= 7:
        score += 1

    maturity_levels = ["初始", "发展", "定义", "管理", "优化"]
    return {
        "score": score,
        "level": maturity_levels[min(score, 4)],
        "max_score": 5,
    }


def _generate_roadmap(rule_evolution, agent_ranking, probe_data) -> list[dict]:
    """生成演进路线图"""
    roadmap = []

    # 规则优化
    for r in rule_evolution[:3]:
        roadmap.append({
            "area": "规则优化",
            "action": f"{r['action']} 规则 {r['rule_id']}",
            "reason": r["reason"],
            "priority": r["priority"],
            "timeline": "2 weeks",
        })

    # Agent 改进
    for a in agent_ranking[:3]:
        if a["avg_health"] < 60:
            roadmap.append({
                "area": "Agent 治理",
                "action": f"改进 {a['agent_id']} 集成健康度",
                "reason": f"平均健康度 {a['avg_health']}, 波动 {a['volatility']}",
                "priority": "P1",
                "timeline": "1 month",
            })

    # 基础设施
    roadmap.append({
        "area": "基础设施",
        "action": "部署 DuckDB + Parquet 数据湖生产环境",
        "reason": "当前开发环境，需生产化",
        "priority": "P2",
        "timeline": "2 weeks",
    })

    return roadmap


def write_report(report: dict, report_type: str) -> None:
    """写入报告文件"""
    if report_type == "weekly":
        week_num = datetime.now(timezone.utc).isocalendar()[1]
        year = datetime.now(timezone.utc).isocalendar()[0]
        filename = f"weekly-governance-W{week_num:02d}-{year}.json"
    else:
        month_str = datetime.now(timezone.utc).strftime("%Y%m")
        filename = f"monthly-governance-{month_str}.json"

    out_file = REPORTS_DIR / filename
    with open(out_file, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"📝 报告已保存: {out_file}")


def main() -> int:
    parser = argparse.ArgumentParser(description="周报/月报生成器")
    parser.add_argument("--type", choices=["weekly", "monthly", "both"], default="weekly", help="报告类型")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    args = parser.parse_args()

    print("=" * 60)
    print(f"{args.type.capitalize()} 报告生成器")
    print("=" * 60)

    if args.type in ("weekly", "both"):
        weekly = generate_weekly_report()
        if args.dry_run:
            print(json.dumps(weekly, indent=2, ensure_ascii=False))
        else:
            write_report(weekly, "weekly")

    if args.type in ("monthly", "both"):
        monthly = generate_monthly_report()
        if args.dry_run:
            print(json.dumps(monthly, indent=2, ensure_ascii=False))
        else:
            write_report(monthly, "monthly")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())