#!/usr/bin/env python3
"""
自动阈值优化器

基于 probe_readings + rule_effectiveness + agent_health_index
自动生成 probe_thresholds.json 和 governance 规则阈值调整建议

优化目标:
- 探针严重度分布均衡 (normal/warning/critical 各占合理比例)
- 规则 FP/FN 率最小化
- Agent 健康指数最大化

算法: 基于历史分布的分位数自适应 + 网格搜索微调
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False

from maref_config import config_path, PROBE_DB

LAKE_ROOT = Path(os.environ.get("MAREF_GOVERNANCE_LAKE", "/Volumes/1TB-M2/maref-governance-lake"))

# 当前默认阈值 (作为基线)
BASELINE_THRESHOLDS = {
    "oscillation": {"normal_max": 30.0, "critical_min": 60.0},
    "entropy": {"normal_max": 10.0, "critical_min": 25.0},
    "governance_health": {"normal_min": 80.0, "critical_min": 50.0},
    "agent_trust": {"normal_min": 70.0, "critical_min": 40.0},
}

# 目标分布 (理想状态下各严重级别占比)
TARGET_DISTRIBUTION = {
    "normal": 0.70,
    "warning": 0.20,
    "critical": 0.10,
}

# 探针类型配置
PROBE_CONFIG = {
    "oscillation": {"direction": "lower_better", "unit": "percent"},
    "entropy": {"direction": "lower_better", "unit": "percent"},
    "governance_health": {"direction": "higher_better", "unit": "percent"},
    "agent_trust": {"direction": "higher_better", "unit": "score"},
}


def _load_probe_history(days: int = 30) -> dict[str, list[float]]:
    """加载 probe_readings 历史值分布"""
    import sqlite3

    history = {k: [] for k in BASELINE_THRESHOLDS.keys()}

    if not os.path.exists(PROBE_DB):
        return history

    try:
        conn = sqlite3.connect(str(PROBE_DB))
        cur = conn.cursor()
        since_ts = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
        for probe in BASELINE_THRESHOLDS.keys():
            cur.execute(
                "SELECT value FROM probe_readings WHERE probe_name = ? AND timestamp >= ?",
                (probe, since_ts),
            )
            rows = cur.fetchall()
            history[probe] = [r[0] for r in rows]
        conn.close()
    except Exception as e:
        print(f"⚠️  加载 probe_readings 失败: {e}")

    return history


def _load_curated_probes(days: int = 30) -> dict[str, list[float]]:
    """从数据湖 curated/probe_readings 加载"""
    history = {k: [] for k in BASELINE_THRESHOLDS.keys()}

    if not DUCKDB_AVAILABLE:
        return history

    try:
        conn = duckdb.connect()
        date_cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
        df = conn.execute(f"""
            SELECT probe_name, value FROM read_parquet('{LAKE_ROOT}/curated/probe_readings/**/*.parquet')
            WHERE date >= '{date_cutoff}'
        """).fetchdf()
        for _, row in df.iterrows():
            name = row["probe_name"]
            if name in history:
                history[name].append(row["value"])
        conn.close()
    except Exception as e:
        print(f"⚠️  加载 curated probes 失败: {e}")

    return history


def _load_rule_effectiveness(days: int = 30) -> list[dict]:
    """加载规则有效度用于联动优化"""
    if not DUCKDB_AVAILABLE:
        return []

    try:
        conn = duckdb.connect()
        date_cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        df = conn.execute(f"""
            SELECT * FROM read_parquet('{LAKE_ROOT}/analytics/rule_effectiveness/**/*.parquet')
            WHERE date >= '{date_cutoff}'
        """).fetchdf()
        result = []
        for _, row in df.iterrows():
            result.append(row.to_dict())
        conn.close()
        return result
    except Exception:
        return []


def _load_agent_health(days: int = 30) -> list[dict]:
    """加载 Agent 健康指数"""
    if not DUCKDB_AVAILABLE:
        return []

    try:
        conn = duckdb.connect()
        date_cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        df = conn.execute(f"""
            SELECT * FROM read_parquet('{LAKE_ROOT}/analytics/agent_health_index/**/*.parquet')
            WHERE date >= '{date_cutoff}'
        """).fetchdf()
        result = []
        for _, row in df.iterrows():
            result.append(row.to_dict())
        conn.close()
        return result
    except Exception:
        return []


def _percentile(values: list[float], p: float) -> float:
    """计算百分位数"""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int(len(sorted_vals) * p)
    idx = min(idx, len(sorted_vals) - 1)
    return sorted_vals[idx]


def _compute_severity_distribution(values: list[float], thresholds: dict, probe_name: str) -> dict[str, float]:
    """计算当前阈值下的严重度分布"""
    if not values:
        return {"normal": 1.0, "warning": 0.0, "critical": 0.0}

    config = PROBE_CONFIG[probe_name]
    normal = 0
    warning = 0
    critical = 0

    if config["direction"] == "lower_better":
        n_max = thresholds.get("normal_max", 100)
        c_min = thresholds.get("critical_min", 100)
        for v in values:
            if v <= n_max:
                normal += 1
            elif v >= c_min:
                critical += 1
            else:
                warning += 1
    else:
        n_min = thresholds.get("normal_min", 0)
        c_min = thresholds.get("critical_min", 0)
        for v in values:
            if v >= n_min:
                normal += 1
            elif v <= c_min:
                critical += 1
            else:
                warning += 1

    total = len(values)
    return {
        "normal": normal / total,
        "warning": warning / total,
        "critical": critical / total,
    }


def _optimize_probe_threshold(probe_name: str, values: list[float], current: dict) -> dict:
    """单探针阈值优化"""
    if len(values) < 20:
        return current  # 样本太少，保持原值

    config = PROBE_CONFIG[probe_name]
    direction = config["direction"]

    # 计算分位数候选
    p10 = _percentile(values, 0.10)
    p25 = _percentile(values, 0.25)
    p50 = _percentile(values, 0.50)
    p75 = _percentile(values, 0.75)
    p90 = _percentile(values, 0.90)
    p95 = _percentile(values, 0.95)

    best = current
    best_score = float('inf')

    if direction == "lower_better":
        # normal_max: 目标 70% 以下为 normal
        # critical_min: 目标 10% 以上为 critical
        candidates_normal = [p50, p60 := _percentile(values, 0.60), p70 := _percentile(values, 0.70), p75]
        candidates_critical = [p85 := _percentile(values, 0.85), p90, p95]

        for n_max in candidates_normal:
            for c_min in candidates_critical:
                if n_max >= c_min:
                    continue
                thresholds = {"normal_max": n_max, "critical_min": c_min}
                dist = _compute_severity_distribution(values, thresholds, probe_name)
                # 评分: 与目标分布的 KL 散度近似
                score = sum((dist[k] - TARGET_DISTRIBUTION[k]) ** 2 for k in TARGET_DISTRIBUTION)
                if score < best_score:
                    best_score = score
                    best = {"normal_max": round(n_max, 1), "critical_min": round(c_min, 1)}

    else:  # higher_better
        # normal_min: 目标 70% 以上为 normal
        # critical_min: 目标 10% 以下为 critical
        candidates_normal = [p50, p40 := _percentile(values, 0.40), p30 := _percentile(values, 0.30), p25]
        candidates_critical = [p15 := _percentile(values, 0.15), p10, p05 := _percentile(values, 0.05)]

        for n_min in candidates_normal:
            for c_min in candidates_critical:
                if n_min <= c_min:
                    continue
                thresholds = {"normal_min": n_min, "critical_min": c_min}
                dist = _compute_severity_distribution(values, thresholds, probe_name)
                score = sum((dist[k] - TARGET_DISTRIBUTION[k]) ** 2 for k in TARGET_DISTRIBUTION)
                if score < best_score:
                    best_score = score
                    best = {"normal_min": round(n_min, 1), "critical_min": round(c_min, 1)}

    return best


def _optimize_rule_thresholds(rule_data: list[dict]) -> list[dict]:
    """基于规则有效度优化规则阈值 (生成建议)"""
    suggestions = []

    for r in rule_data:
        fp = r.get("false_positive_est", 0)
        drift = r.get("drift_score", 0)
        tier = r.get("effectiveness_tier", "medium")
        rule_id = r.get("rule_id", "")

        if fp > 0.3 and tier != "deprecated":
            suggestions.append({
                "type": "rule_threshold",
                "rule_id": rule_id,
                "action": "increase_threshold",  # 提高阈值减少误报
                "reason": f"高误报率 FP={fp:.1%}, 建议放宽触发条件",
                "priority": "P1",
                "current_fp": fp,
            })
        elif drift > 0.5:
            suggestions.append({
                "type": "rule_threshold",
                "rule_id": rule_id,
                "action": "recalibrate",
                "reason": f"高漂移 drift={drift:.2f}, 建议重新校准基线",
                "priority": "P2",
                "current_drift": drift,
            })

    return suggestions


def _optimize_agent_thresholds(health_data: list[dict]) -> list[dict]:
    """基于 Agent 健康指数优化阈值"""
    suggestions = []

    # 统计各 Agent 的违规/拦截分布
    for h in health_data:
        tier = h.get("health_tier", "excellent")
        agent = h.get("agent_id", "")
        viol = h.get("violation_rate", 0)
        intercept = h.get("interception_rate", 0)

        if tier in ("poor", "critical"):
            suggestions.append({
                "type": "agent_threshold",
                "agent_id": agent,
                "action": "increase_sensitivity",  # 增加敏感度，更早拦截
                "reason": f"Agent 健康差 ({tier}), violation={viol:.1%}, 建议提高拦截敏感度",
                "priority": "P1",
            })
        elif viol < 0.01 and intercept < 0.01 and tier == "excellent":
            suggestions.append({
                "type": "agent_threshold",
                "agent_id": agent,
                "action": "decrease_sensitivity",  # 降低敏感度，减少误拦截
                "reason": f"Agent 过度健康且低违规, 建议适当放宽阈值提高效率",
                "priority": "P3",
            })

    return suggestions


def main():
    parser = argparse.ArgumentParser(description="自动阈值优化器")
    parser.add_argument("--days", type=int, default=30, help="历史数据天数")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    parser.add_argument("--apply", action="store_true", help="直接应用到配置文件")
    args = parser.parse_args()

    print("=" * 60)
    print("自动阈值优化器")
    print("=" * 60)

    # 1. 加载数据
    print(f"\n📊 加载最近 {args.days} 天数据...")
    probe_hist = _load_probe_history(args.days)
    probe_curated = _load_curated_probes(args.days)
    rule_data = _load_rule_effectiveness(args.days)
    health_data = _load_agent_health(args.days)

    # 合并 probe 数据源
    for k in BASELINE_THRESHOLDS:
        probe_hist[k].extend(probe_curated.get(k, []))

    total_samples = sum(len(v) for v in probe_hist.values())
    print(f"   Probe 样本: {total_samples}")
    print(f"   规则有效度记录: {len(rule_data)}")
    print(f"   Agent 健康记录: {len(health_data)}")

    # 2. 优化 Probe 阈值
    print("\n🔧 优化 Probe 阈值...")
    new_thresholds = {}
    for probe_name, values in probe_hist.items():
        if len(values) < 20:
            print(f"  {probe_name}: 样本不足 ({len(values)}), 保持原值")
            new_thresholds[probe_name] = BASELINE_THRESHOLDS[probe_name]
            continue

        current = BASELINE_THRESHOLDS[probe_name]
        dist = _compute_severity_distribution(values, current, probe_name)
        print(f"  {probe_name}: 样本={len(values)} 当前分布={dist}")

        optimized = _optimize_probe_threshold(probe_name, values, current)
        new_dist = _compute_severity_distribution(values, optimized, probe_name)
        print(f"    优化后: {optimized} -> 分布={new_dist}")
        new_thresholds[probe_name] = optimized

    # 3. 生成规则阈值建议
    print("\n🔧 规则阈值调整建议...")
    rule_suggestions = _optimize_rule_thresholds(rule_data)
    for s in rule_suggestions[:5]:
        print(f"  {s['rule_id']}: {s['action']} ({s['reason']})")

    # 4. 生成 Agent 阈值建议
    print("\n🔧 Agent 阈值调整建议...")
    agent_suggestions = _optimize_agent_thresholds(health_data)
    for s in agent_suggestions[:5]:
        print(f"  {s['agent_id']}: {s['action']} ({s['reason']})")

    # 5. 输出结果
    result = {
        "optimized_at": datetime.now(timezone.utc).isoformat(),
        "data_window_days": args.days,
        "probe_thresholds": new_thresholds,
        "rule_suggestions": rule_suggestions,
        "agent_suggestions": agent_suggestions,
        "baseline": BASELINE_THRESHOLDS,
    }

    if args.dry_run:
        print("\n[dry-run] 结果预览:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    # 写入配置文件
    config_file = config_path("probe_thresholds.json")
    os.makedirs(os.path.dirname(config_file), exist_ok=True)

    output = {
        "version": "1.0",
        "optimized_at": result["optimized_at"],
        "data_window_days": args.days,
        "probes": new_thresholds,
    }

    with open(config_file, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Probe 阈值已写入: {config_file}")

    # 写入建议报告
    suggestions_file = config_path("threshold_suggestions.json")
    with open(suggestions_file, "w") as f:
        json.dump({
            "generated_at": result["optimized_at"],
            "rule_suggestions": rule_suggestions,
            "agent_suggestions": agent_suggestions,
        }, f, indent=2, ensure_ascii=False)
    print(f"📝 调整建议已写入: {suggestions_file}")

    if args.apply:
        print("\n⚠️  --apply 模式: 需重启 probe_sampler 生效")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())