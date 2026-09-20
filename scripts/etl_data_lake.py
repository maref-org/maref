#!/usr/bin/env python3
"""
数据湖 ETL: raw -> curated (Parquet) -> analytics

三层管线:
1. Raw Layer: 原始不可变数据 (JSONL/NDJSON) - 已由各组件直接写入
2. Curated Layer: 清洗、去重、标准化、分区的 Parquet 表
3. Analytics Layer: 物化视图、聚合指标、分析就绪数据集

用法:
    python scripts/etl_data_lake.py --layer raw          # 仅导入 raw
    python scripts/etl_data_lake.py --layer curated      # raw -> curated
    python scripts/etl_data_lake.py --layer analytics    # curated -> analytics
    python scripts/etl_data_lake.py --layer all          # 全链路
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    print("⚠️  duckdb 未安装，ETL 功能受限 (pip install duckdb)")

LAKE_ROOT = Path(os.environ.get("MAREF_GOVERNANCE_LAKE", "/Volumes/1TB-M2/maref-governance-lake"))


TABLE_CONFIGS = {
    # Curated Layer Tables
    "agent_sessions": {
        "source": "raw/obs_events",
        "partition_by": ["date", "agent_id"],
        "transform": "build_agent_sessions",
    },
    "tool_executions": {
        "source": ["raw/obs_events", "raw/mcp_governance", "raw/telemetry"],
        "partition_by": ["date", "agent_id", "tool_name"],
        "transform": "build_tool_executions",
    },
    "governance_decisions": {
        "source": ["raw/audit_logs", "raw/mcp_governance"],
        "partition_by": ["date", "agent_id", "verdict"],
        "transform": "build_governance_decisions",
    },
    "cross_agent_flows": {
        "source": "curated/tool_executions",
        "partition_by": ["date", "correlation_id"],
        "transform": "build_cross_agent_flows",
    },
    "violation_patterns": {
        "source": ["curated/governance_decisions", "curated/tool_executions"],
        "partition_by": ["date", "pattern_type"],
        "transform": "build_violation_patterns",
    },
    # Analytics Layer Tables
    "daily_governance_kpi": {
        "source": ["curated/tool_executions", "curated/governance_decisions", "curated/agent_sessions"],
        "partition_by": ["date"],
        "transform": "build_daily_kpi",
    },
    "agent_health_index": {
        "source": ["curated/agent_sessions", "curated/tool_executions", "curated/cross_agent_flows"],
        "partition_by": ["date", "agent_id"],
        "transform": "build_agent_health",
    },
    "rule_effectiveness": {
        "source": "curated/governance_decisions",
        "partition_by": ["date", "rule_id"],
        "transform": "build_rule_effectiveness",
    },
    "evolution_fuel": {
        "source": ["analytics/rule_effectiveness", "analytics/agent_health_index", "curated/violation_patterns"],
        "partition_by": ["date", "fuel_type"],
        "transform": "build_evolution_fuel",
    },
}


def run_duckdb_sql(sql: str) -> bool:
    """执行 DuckDB SQL"""
    if not DUCKDB_AVAILABLE:
        return False
    try:
        conn = duckdb.connect()
        conn.execute(sql)
        conn.close()
        return True
    except Exception as e:
        print(f"❌ DuckDB 执行失败: {e}")
        return False


def etl_raw_to_curated(date_str: str | None = None) -> bool:
    """Raw -> Curated ETL"""
    print("🔄 ETL: Raw -> Curated")
    print("=" * 50)

    if not DUCKDB_AVAILABLE:
        print("❌ 需要 duckdb")
        return False

    date_filter = ""
    if date_str:
        date_filter = f"AND date = '{date_str}'"

    success = True

    # 1. agent_sessions: 从 ObsEvent 重建会话
    print("  📦 构建 agent_sessions...")
    sql = f"""
        COPY (
            WITH normalized AS (
                SELECT
                    metadata->>'correlation_id' as correlation_id,
                    metadata->>'chain_id' as chain_id,
                    metadata->>'agent_id' as agent_id,
                    timestamp as start_time,
                    metadata->>'tool_name' as tool_name,
                    metadata->>'verdict' as verdict,
                    metadata->>'latency_ms' as latency_ms,
                    metadata->>'hitl_event_id' as hitl_event_id,
                    metadata->>'tokens_input' as tokens_input,
                    metadata->>'tokens_output' as tokens_output,
                    metadata->>'cost_usd' as cost_usd,
                    metadata->>'delegation_depth' as delegation_depth,
                    date_trunc('day', to_timestamp(timestamp))::DATE as date
                FROM read_parquet('{LAKE_ROOT}/raw/obs_events/**/*.parquet')
                WHERE metadata->>'correlation_id' IS NOT NULL
            ),
            sessions AS (
                SELECT
                    correlation_id,
                    chain_id,
                    agent_id,
                    MIN(start_time) as start_time,
                    MAX(start_time) as end_time,
                    COUNT(*) as tool_calls_count,
                    SUM(CASE WHEN verdict IN ('deny','ask_user') THEN 1 ELSE 0 END) as intercepted_count,
                    SUM(CASE WHEN verdict = 'ask_user' THEN 1 ELSE 0 END) as hitl_count,
                    SUM(COALESCE(tokens_input,0) + COALESCE(tokens_output,0)) as total_tokens,
                    SUM(COALESCE(cost_usd,0)) as total_cost_usd,
                    MAX(COALESCE(latency_ms,0)) as max_latency_ms,
                    MAX(CASE WHEN verdict IN ('deny','ask_user') THEN 1 ELSE 0 END) as final_verdict_flag,
                    MAX(delegation_depth) as delegation_depth_max,
                    SUM(CASE WHEN delegation_depth > 0 THEN 1 ELSE 0 END) as delegation_count,
                    date
                FROM normalized
                GROUP BY correlation_id, chain_id, agent_id, date
            )
            SELECT * FROM sessions
        ) TO '{LAKE_ROOT}/curated/agent_sessions/agent_sessions_{date_str or datetime.now(timezone.utc).strftime("%Y%m%d")}.parquet' (FORMAT PARQUET, PARTITION_BY (date, agent_id))
    """
    if run_duckdb_sql(sql):
        print("    ✅ agent_sessions")
    else:
        success = False

    # 2. tool_executions: 标准化工具执行记录
    print("  📦 构建 tool_executions...")
    sql = f"""
        COPY (
            WITH normalized AS (
                SELECT
                    metadata->>'correlation_id' as correlation_id,
                    metadata->>'chain_id' as chain_id,
                    metadata->>'delegation_depth' as delegation_depth,
                    metadata->>'agent_id' as agent_id,
                    metadata->>'tool_name' as tool_name,
                    md5(COALESCE(metadata->>'args_hash','') || COALESCE(timestamp,'')) as execution_id,
                    metadata->>'args_hash' as args_hash,
                    '{{}}'::JSON as args_redacted,
                    timestamp as start_time,
                    timestamp + COALESCE(metadata->>'latency_ms',0)/1000.0 as end_time,
                    metadata->>'latency_ms' as latency_ms,
                    metadata->>'verdict' as verdict,
                    metadata->>'matched_rule' as matched_rule,
                    metadata->>'risk_score' as risk_score,
                    metadata->>'hitl_event_id' as hitl_event_id,
                    metadata->>'hitl_tier' as hitl_tier,
                    metadata->>'tokens_input' as tokens_input,
                    metadata->>'tokens_output' as tokens_output,
                    metadata->>'cost_usd' as cost_usd,
                    metadata->>'error' as error,
                    date_trunc('day', to_timestamp(timestamp))::DATE as date
                FROM read_parquet('{LAKE_ROOT}/raw/obs_events/**/*.parquet')
                WHERE metadata->>'event_type' IN ('tool_call_start','tool_call_end','tool_call_intercepted')
                UNION ALL
                SELECT
                    metadata->>'correlation_id' as correlation_id,
                    metadata->>'chain_id' as chain_id,
                    metadata->>'delegation_depth' as delegation_depth,
                    metadata->>'agent_id' as agent_id,
                    metadata->>'tool_name' as tool_name,
                    md5(COALESCE(metadata->>'args_hash','') || COALESCE(timestamp,'')) as execution_id,
                    metadata->>'args_hash' as args_hash,
                    '{{}}'::JSON as args_redacted,
                    timestamp as start_time,
                    timestamp + COALESCE(metadata->>'latency_ms',0)/1000.0 as end_time,
                    metadata->>'latency_ms' as latency_ms,
                    metadata->>'verdict' as verdict,
                    metadata->>'matched_rule' as matched_rule,
                    metadata->>'risk_score' as risk_score,
                    metadata->>'hitl_event_id' as hitl_event_id,
                    metadata->>'hitl_tier' as hitl_tier,
                    0 as tokens_input,
                    0 as tokens_output,
                    0 as cost_usd,
                    metadata->>'error' as error,
                    date_trunc('day', to_timestamp(timestamp))::DATE as date
                FROM read_parquet('{LAKE_ROOT}/raw/mcp_governance/**/*.parquet')
            )
            SELECT * FROM normalized
        ) TO '{LAKE_ROOT}/curated/tool_executions/tool_executions_{date_str or datetime.now(timezone.utc).strftime("%Y%m%d")}.parquet' (FORMAT PARQUET, PARTITION_BY (date, agent_id, tool_name))
    """
    if run_duckdb_sql(sql):
        print("    ✅ tool_executions")
    else:
        success = False

    # 3. governance_decisions: 标准化治理裁决
    print("  📦 构建 governance_decisions...")
    sql = f"""
        COPY (
            WITH audit_decisions AS (
                SELECT
                    id as decision_id,
                    metadata->>'correlation_id' as correlation_id,
                    metadata->>'chain_id' as chain_id,
                    actor as agent_id,
                    action as tool_name,
                    timestamp,
                    metadata->>'verdict' as verdict,
                    metadata->>'matched_rule' as matched_rule,
                    metadata->>'risk_score' as risk_score,
                    metadata->>'reason' as reason,
                    '1.0' as policy_version,
                    metadata->>'latency_ms' as latency_ms,
                    CASE WHEN metadata->>'hitl_tier' != '' THEN true ELSE false END as hitl_triggered,
                    metadata->>'hitl_tier' as hitl_tier,
                    false as hitl_resolved,
                    0 as hitl_resolution_time_ms,
                    date_trunc('day', to_timestamp(timestamp))::DATE as date
                FROM read_parquet('{LAKE_ROOT}/raw/audit_logs/**/*.parquet')
                WHERE event_type = 'governance_decision'
            ),
            mcp_decisions AS (
                SELECT
                    md5(COALESCE(timestamp,'') || COALESCE(actor,'') || COALESCE(action,'')) as decision_id,
                    metadata->>'correlation_id' as correlation_id,
                    metadata->>'chain_id' as chain_id,
                    actor as agent_id,
                    action as tool_name,
                    timestamp,
                    metadata->>'verdict' as verdict,
                    metadata->>'matched_rule' as matched_rule,
                    metadata->>'risk_score' as risk_score,
                    metadata->>'reason' as reason,
                    '1.0' as policy_version,
                    metadata->>'latency_ms' as latency_ms,
                    CASE WHEN metadata->>'hitl_tier' != '' THEN true ELSE false END as hitl_triggered,
                    metadata->>'hitl_tier' as hitl_tier,
                    false as hitl_resolved,
                    0 as hitl_resolution_time_ms,
                    date_trunc('day', to_timestamp(timestamp))::DATE as date
                FROM read_parquet('{LAKE_ROOT}/raw/mcp_governance/**/*.parquet')
            )
            SELECT * FROM audit_decisions
            UNION ALL
            SELECT * FROM mcp_decisions
        ) TO '{LAKE_ROOT}/curated/governance_decisions/governance_decisions_{date_str or datetime.now(timezone.utc).strftime("%Y%m%d")}.parquet' (FORMAT PARQUET, PARTITION_BY (date, agent_id, verdict))
    """
    if run_duckdb_sql(sql):
        print("    ✅ governance_decisions")
    else:
        success = False

    return success


def etl_curated_to_analytics(date_str: str | None = None) -> bool:
    """Curated -> Analytics ETL"""
    print("🔄 ETL: Curated -> Analytics")
    print("=" * 50)

    if not DUCKDB_AVAILABLE:
        print("❌ 需要 duckdb")
        return False

    success = True

    # 1. daily_governance_kpi
    print("  📊 构建 daily_governance_kpi...")
    sql = f"""
        COPY (
            SELECT
                date,
                COUNT(DISTINCT agent_id) as total_agents,
                COUNT(DISTINCT CASE WHEN tool_calls_count > 0 THEN agent_id END) as active_agents,
                SUM(tool_calls_count) as total_tool_calls,
                SUM(CASE WHEN verdict = 'allow' THEN 1 ELSE 0 END) as allowed_calls,
                SUM(CASE WHEN verdict IN ('deny','ask_user') THEN 1 ELSE 0 END) as intercepted_calls,
                SUM(CASE WHEN verdict = 'deny' THEN 1 ELSE 0 END) as denied_calls,
                SUM(CASE WHEN verdict = 'ask_user' THEN 1 ELSE 0 END) as hitl_calls,
                SUM(CASE WHEN verdict IN ('deny','ask_user') THEN 1 ELSE 0 END) * 100.0 / NULLIF(SUM(tool_calls_count),0) as interception_rate,
                SUM(CASE WHEN verdict = 'ask_user' THEN 1 ELSE 0 END) * 100.0 / NULLIF(SUM(tool_calls_count),0) as hitl_rate,
                AVG(latency_ms) as avg_latency_ms,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95_latency_ms,
                SUM(total_tokens) as total_tokens,
                SUM(total_cost_usd) as total_cost_usd,
                COUNT(DISTINCT correlation_id) as unique_correlations,
                SUM(CASE WHEN delegation_count > 0 THEN 1 ELSE 0 END) as cross_agent_sessions,
                0 as violations_detected,
                0 as new_patterns
            FROM read_parquet('{LAKE_ROOT}/curated/tool_executions/**/*.parquet')
            GROUP BY date
        ) TO '{LAKE_ROOT}/analytics/daily_governance_kpi/daily_kpi_{date_str or datetime.now(timezone.utc).strftime("%Y%m%d")}.parquet' (FORMAT PARQUET, PARTITION_BY (date))
    """
    if run_duckdb_sql(sql):
        print("    ✅ daily_governance_kpi")
    else:
        success = False

    # 2. agent_health_index
    print("  📊 构建 agent_health_index...")
    sql = f"""
        COPY (
            WITH agent_stats AS (
                SELECT
                    agent_id,
                    date,
                    AVG(trust_score) as trust_score,
                    AVG(violation_rate) as violation_rate,
                    AVG(interception_rate) as interception_rate,
                    AVG(activity_score) as activity_score,
                    AVG(collaboration_score) as collaboration_score,
                    AVG(latency_score) as latency_score,
                    AVG(cost_efficiency_score) as cost_efficiency_score,
                    AVG(composite_health) as composite_health,
                    MAX(health_tier) as health_tier,
                    0 as trend_7d,
                    0 as trend_30d,
                    '[]' as alerts
                FROM (
                    SELECT
                        agent_id,
                        date,
                        50.0 as trust_score,
                        CASE WHEN tool_calls_count > 0 THEN intercepted_count * 1.0 / tool_calls_count ELSE 0 END as violation_rate,
                        CASE WHEN tool_calls_count > 0 THEN hitl_count * 1.0 / tool_calls_count ELSE 0 END as interception_rate,
                        LOG10(tool_calls_count + 1) * 20 as activity_score,
                        50.0 as collaboration_score,
                        CASE WHEN max_latency_ms > 0 THEN GREATEST(0, 100 - max_latency_ms / 50) ELSE 50 END as latency_score,
                        50.0 as cost_efficiency_score,
                        (50.0 * 0.25 +
                         (100 - CASE WHEN tool_calls_count > 0 THEN intercepted_count * 100.0 / tool_calls_count ELSE 0 END) * 0.20 +
                         100 * 0.15 +
                         LOG10(tool_calls_count + 1) * 20 * 0.15 +
                         50.0 * 0.10 +
                         GREATEST(0, 100 - max_latency_ms / 50) * 0.10 +
                         50.0 * 0.05) as composite_health,
                        CASE
                            WHEN (50.0 * 0.25 + ...) >= 90 THEN 'excellent'
                            WHEN (50.0 * 0.25 + ...) >= 75 THEN 'good'
                            WHEN (50.0 * 0.25 + ...) >= 60 THEN 'fair'
                            WHEN (50.0 * 0.25 + ...) >= 40 THEN 'poor'
                            ELSE 'critical'
                        END as health_tier
                    FROM read_parquet('{LAKE_ROOT}/curated/agent_sessions/**/*.parquet')
                )
                GROUP BY agent_id, date
            )
            SELECT * FROM agent_stats
        ) TO '{LAKE_ROOT}/analytics/agent_health_index/agent_health_{date_str or datetime.now(timezone.utc).strftime("%Y%m%d")}.parquet' (FORMAT PARQUET, PARTITION_BY (date, agent_id))
    """
    # 简化版：使用外部脚本计算
    print("    ⚠️  使用外部脚本 agent_health_index.py 计算")
    try:
        subprocess.run([sys.executable, "scripts/agent_health_index.py"], check=True, capture_output=True)
        print("    ✅ agent_health_index (via external script)")
    except Exception:
        success = False

    # 3. rule_effectiveness
    print("  📊 构建 rule_effectiveness...")
    print("    ⚠️  使用外部脚本 rule_effectiveness.py 计算")
    try:
        subprocess.run([sys.executable, "scripts/rule_effectiveness.py"], check=True, capture_output=True)
        print("    ✅ rule_effectiveness (via external script)")
    except Exception:
        success = False

    # 4. evolution_fuel
    print("  📊 构建 evolution_fuel...")
    print("    ⚠️  待实现: 基于规则有效度 + Agent 健康 + 违规模式生成燃料")

    return success


def etl_full_pipeline(date_str: str | None = None) -> bool:
    """全链路 ETL"""
    print("🚀 启动全链路 ETL")
    print("=" * 60)

    ok = True
    ok &= etl_raw_to_curated(date_str)
    print()
    ok &= etl_curated_to_analytics(date_str)
    print()

    if ok:
        print("✅ 全链路 ETL 完成")
    else:
        print("❌ ETL 存在失败")

    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="数据湖 ETL 管线")
    parser.add_argument("--layer", choices=["raw", "curated", "analytics", "all"], default="all", help="ETL 层级")
    parser.add_argument("--date", help="指定日期 YYYYMMDD (默认今天)")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划")
    args = parser.parse_args()

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y%m%d")

    if args.dry_run:
        print(f"[DRY-RUN] ETL 计划: layer={args.layer}, date={date_str}")
        return 0

    if args.layer == "raw":
        print("⚠️  Raw 层由各组件直接写入，无需单独 ETL")
        return 0
    elif args.layer == "curated":
        return 0 if etl_raw_to_curated(date_str) else 1
    elif args.layer == "analytics":
        return 0 if etl_curated_to_analytics(date_str) else 1
    elif args.layer == "all":
        return 0 if etl_full_pipeline(date_str) else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())