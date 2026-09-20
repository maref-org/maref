#!/usr/bin/env python3
"""
MAREF 治理数据湖初始化脚本

创建统一的治理数据湖目录结构、Parquet Schema 注册、分区策略。
数据湖位于外置盘 /Volumes/1TB-M2/maref-governance-lake/

用法:
    python scripts/init_governance_lake.py          # 完整初始化
    python scripts/init_governance_lake.py --dry-run # 仅打印计划
    python scripts/init_governance_lake.py --verify  # 验证现有结构
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False

LAKE_ROOT = Path(os.environ.get("MAREF_GOVERNANCE_LAKE", "/Volumes/1TB-M2/maref-governance-lake"))

# =============================================================================
# Schema 定义 (Apache Arrow / DuckDB 兼容)
# =============================================================================

SCHEMAS: dict[str, dict[str, Any]] = {
    # ---------------------------------------------------------
    # Raw Layer: 原始不可变数据 (按源分区，保持原始格式)
    # ---------------------------------------------------------
    "raw/coding_agents": {
        "description": "Coding Agent 注册状态历史快照",
        "partition_by": ["date", "agent_id"],
        "schema": {
            "checked_at": "TIMESTAMP",
            "agent_id": "VARCHAR",
            "display_name": "VARCHAR",
            "kind": "VARCHAR",
            "did": "VARCHAR",
            "domain_weight": "INTEGER",
            "integration_kind": "VARCHAR",
            "declared_status": "VARCHAR",
            "effective_status": "VARCHAR",
            "entry_exists": "BOOLEAN",
            "config_exists": "BOOLEAN",
            "sidecar_reachable": "BOOLEAN",
            "degraded_reason": "VARCHAR",
            "tool_calls_total": "INTEGER",
            "tool_calls_intercepted": "INTEGER",
            "avg_latency_ms": "DOUBLE",
            "trust_score": "DOUBLE",
        },
    },
    "raw/obs_events": {
        "description": "MarefObsClient 行为事件 ndjson 原始导入",
        "partition_by": ["date", "event_type", "agent_id"],
        "schema": {
            "session_id": "VARCHAR",
            "event_type": "VARCHAR",
            "version": "VARCHAR",
            "timestamp": "TIMESTAMP",
            "event_sequence": "BIGINT",
            "metadata": "JSON",
            "source_agent": "VARCHAR",
        },
    },
    "raw/audit_logs": {
        "description": "治理审计日志 governance_audit.jsonl 等",
        "partition_by": ["date", "event_type", "actor"],
        "schema": {
            "id": "VARCHAR",
            "timestamp": "TIMESTAMP",
            "event_type": "VARCHAR",
            "actor": "VARCHAR",
            "action": "VARCHAR",
            "details": "VARCHAR",
            "metadata": "JSON",
            "previous_hash": "VARCHAR",
            "chain_hash": "VARCHAR",
        },
    },
    "raw/telemetry": {
        "description": "OpenClaw 遥测推送 data/telemetry/",
        "partition_by": ["date", "source", "telemetry_type"],
        "schema": {
            "source": "VARCHAR",
            "telemetry_type": "VARCHAR",
            "timestamp": "TIMESTAMP",
            "data": "JSON",
            "ingested_at": "TIMESTAMP",
            "signature": "VARCHAR",
            "dedup_key": "VARCHAR",
        },
    },
    "raw/probe_readings": {
        "description": "Probe Sampler 探针读数 SQLite 导出",
        "partition_by": ["date", "probe_name"],
        "schema": {
            "probe_name": "VARCHAR",
            "severity": "VARCHAR",
            "value": "DOUBLE",
            "threshold": "DOUBLE",
            "timestamp": "TIMESTAMP",
            "context_json": "JSON",
        },
    },
    "raw/mcp_governance": {
        "description": "MCP 治理决策/审计日志导出",
        "partition_by": ["date", "agent_id", "verdict"],
        "schema": {
            "timestamp": "TIMESTAMP",
            "agent_id": "VARCHAR",
            "tool_name": "VARCHAR",
            "trust_level": "VARCHAR",
            "verdict": "VARCHAR",
            "risk_score": "DOUBLE",
            "matched_rule": "VARCHAR",
            "reason": "VARCHAR",
            "hitl_event_id": "VARCHAR",
            "chain_id": "VARCHAR",
            "delegation_depth": "INTEGER",
            "latency_ms": "INTEGER",
            "args_hash": "VARCHAR",
        },
    },

    # ---------------------------------------------------------
    # Curated Layer: 清洗后表 (Parquet, 分区: date+agent)
    # ---------------------------------------------------------
    "curated/agent_sessions": {
        "description": "Agent 会话级汇总 (关联 correlation_id + chain_id)",
        "partition_by": ["date", "agent_id"],
        "schema": {
            "session_id": "VARCHAR",
            "correlation_id": "VARCHAR",
            "chain_id": "VARCHAR",
            "agent_id": "VARCHAR",
            "start_time": "TIMESTAMP",
            "end_time": "TIMESTAMP",
            "duration_ms": "BIGINT",
            "tool_calls_count": "INTEGER",
            "intercepted_count": "INTEGER",
            "hitl_count": "INTEGER",
            "total_tokens": "BIGINT",
            "total_cost_usd": "DOUBLE",
            "max_context_window": "INTEGER",
            "final_verdict": "VARCHAR",
            "delegation_depth_max": "INTEGER",
            "delegation_count": "INTEGER",
        },
    },
    "curated/tool_executions": {
        "description": "工具调用全链路 (含参数脱敏、治理决策)",
        "partition_by": ["date", "agent_id", "tool_name"],
        "schema": {
            "execution_id": "VARCHAR",
            "correlation_id": "VARCHAR",
            "chain_id": "VARCHAR",
            "delegation_depth": "INTEGER",
            "agent_id": "VARCHAR",
            "tool_name": "VARCHAR",
            "args_hash": "VARCHAR",
            "args_redacted": "JSON",
            "start_time": "TIMESTAMP",
            "end_time": "TIMESTAMP",
            "latency_ms": "INTEGER",
            "verdict": "VARCHAR",
            "matched_rule": "VARCHAR",
            "risk_score": "DOUBLE",
            "hitl_event_id": "VARCHAR",
            "hitl_tier": "VARCHAR",
            "tokens_input": "INTEGER",
            "tokens_output": "INTEGER",
            "cost_usd": "DOUBLE",
            "error": "VARCHAR",
        },
    },
    "curated/governance_decisions": {
        "description": "治理裁决明细 (verdict, rule, risk, 延迟)",
        "partition_by": ["date", "agent_id", "verdict"],
        "schema": {
            "decision_id": "VARCHAR",
            "correlation_id": "VARCHAR",
            "chain_id": "VARCHAR",
            "agent_id": "VARCHAR",
            "tool_name": "VARCHAR",
            "timestamp": "TIMESTAMP",
            "verdict": "VARCHAR",
            "matched_rule": "VARCHAR",
            "risk_score": "DOUBLE",
            "reason": "VARCHAR",
            "policy_version": "VARCHAR",
            "latency_ms": "INTEGER",
            "hitl_triggered": "BOOLEAN",
            "hitl_tier": "VARCHAR",
            "hitl_resolved": "BOOLEAN",
            "hitl_resolution_time_ms": "BIGINT",
        },
    },
    "curated/cross_agent_flows": {
        "description": "多 Agent 协作流 DAG (chain_id 关联)",
        "partition_by": ["date", "correlation_id"],
        "schema": {
            "correlation_id": "VARCHAR",
            "chain_id": "VARCHAR",
            "root_agent_id": "VARCHAR",
            "start_time": "TIMESTAMP",
            "end_time": "TIMESTAMP",
            "total_duration_ms": "BIGINT",
            "agent_sequence": "VARCHAR",  # JSON array of agent_ids
            "delegation_edges": "JSON",   # [{"from": "a", "to": "b", "tool": "x", "depth": 1}, ...]
            "total_tool_calls": "INTEGER",
            "total_interceptions": "INTEGER",
            "total_hitl": "INTEGER",
            "final_outcome": "VARCHAR",
            "bottleneck_agent": "VARCHAR",
            "bottleneck_tool": "VARCHAR",
        },
    },
    "curated/violation_patterns": {
        "description": "违规模式聚类 (频次、演变、关联)",
        "partition_by": ["date", "pattern_type"],
        "schema": {
            "pattern_id": "VARCHAR",
            "pattern_type": "VARCHAR",  # bypass, injection, escalation, privilege, etc.
            "signature": "VARCHAR",     # 规则化特征签名
            "first_seen": "TIMESTAMP",
            "last_seen": "TIMESTAMP",
            "occurrence_count": "INTEGER",
            "affected_agents": "VARCHAR",  # JSON array
            "affected_tools": "VARCHAR",   # JSON array
            "matched_rules": "VARCHAR",    # JSON array
            "severity_distribution": "JSON",
            "evolution_stage": "VARCHAR",  # new, growing, stable, declining
            "related_cves": "VARCHAR",     # JSON array
            "vaccine_candidate": "BOOLEAN",
        },
    },

    # ---------------------------------------------------------
    # Analytics Layer: 分析就绪数据集 (物化视图)
    # ---------------------------------------------------------
    "analytics/daily_governance_kpi": {
        "description": "每日治理 KPI (覆盖率、拦截率、延迟、吞吐)",
        "partition_by": ["date"],
        "schema": {
            "date": "DATE",
            "total_agents": "INTEGER",
            "active_agents": "INTEGER",
            "total_tool_calls": "BIGINT",
            "allowed_calls": "BIGINT",
            "intercepted_calls": "BIGINT",
            "denied_calls": "BIGINT",
            "hitl_calls": "BIGINT",
            "interception_rate": "DOUBLE",
            "hitl_rate": "DOUBLE",
            "avg_latency_ms": "DOUBLE",
            "p95_latency_ms": "DOUBLE",
            "total_tokens": "BIGINT",
            "total_cost_usd": "DOUBLE",
            "unique_correlations": "BIGINT",
            "cross_agent_sessions": "INTEGER",
            "violations_detected": "INTEGER",
            "new_patterns": "INTEGER",
        },
    },
    "analytics/agent_health_index": {
        "description": "Agent 健康指数 (信任分、违规率、活跃度、协作质量)",
        "partition_by": ["date", "agent_id"],
        "schema": {
            "date": "DATE",
            "agent_id": "VARCHAR",
            "trust_score": "DOUBLE",
            "violation_rate": "DOUBLE",
            "interception_rate": "DOUBLE",
            "activity_score": "DOUBLE",      # 调用频次归一化
            "collaboration_score": "DOUBLE", # 跨 Agent 协作质量
            "latency_score": "DOUBLE",       # 延迟表现
            "cost_efficiency_score": "DOUBLE",
            "composite_health": "DOUBLE",    # 0-100 加权合成
            "health_tier": "VARCHAR",        # excellent/good/fair/poor/critical
            "trend_7d": "DOUBLE",            # 7日趋势
            "trend_30d": "DOUBLE",
            "alerts": "VARCHAR",             # JSON array
        },
    },
    "analytics/rule_effectiveness": {
        "description": "规则有效度 (FP/FN、覆盖率、偏漂、版本对比)",
        "partition_by": ["date", "rule_id"],
        "schema": {
            "date": "DATE",
            "rule_id": "VARCHAR",
            "rule_version": "VARCHAR",
            "total_evaluations": "BIGINT",
            "allow_count": "BIGINT",
            "deny_count": "BIGINT",
            "ask_user_count": "BIGINT",
            "false_positive_est": "DOUBLE",  # 经人工复核/后验估计
            "false_negative_est": "DOUBLE",
            "coverage_rate": "DOUBLE",       # 命中该规则的工具调用占比
            "avg_latency_ms": "DOUBLE",
            "drift_score": "DOUBLE",         # 与基线版本偏离度
            "last_triggered": "TIMESTAMP",
            "effectiveness_tier": "VARCHAR", # high/medium/low/deprecated
            "recommendation": "VARCHAR",     # keep/tune/deprecate/replace
        },
    },
    "analytics/evolution_fuel": {
        "description": "迭代燃料 (候选规则、阈值建议、疫苗、红线候选)",
        "partition_by": ["date", "fuel_type"],
        "schema": {
            "fuel_id": "VARCHAR",
            "fuel_type": "VARCHAR",  # threshold_adjustment, new_rule, redline_candidate, vaccine, policy_proposal
            "source": "VARCHAR",     # probe_sampler, rule_effectiveness, pattern_miner, vaccine_pipeline
            "priority": "INTEGER",   # 1=P0, 2=P1, 3=P2
            "title": "VARCHAR",
            "description": "VARCHAR",
            "evidence": "JSON",      # 支撑数据引用
            "proposed_change": "JSON", # 具体变更内容
            "impact_estimate": "JSON", # 预估影响
            "status": "VARCHAR",     # proposed, reviewing, approved, deployed, rejected
            "created_at": "TIMESTAMP",
            "reviewed_at": "TIMESTAMP",
            "deployed_at": "TIMESTAMP",
        },
    },
}

# =============================================================================
# 目录结构
# =============================================================================

DIRS = [
    # Raw
    "raw/coding_agents",
    "raw/obs_events",
    "raw/audit_logs",
    "raw/telemetry",
    "raw/probe_readings",
    "raw/mcp_governance",
    # Curated
    "curated/agent_sessions",
    "curated/tool_executions",
    "curated/governance_decisions",
    "curated/cross_agent_flows",
    "curated/violation_patterns",
    # Analytics
    "analytics/daily_governance_kpi",
    "analytics/agent_health_index",
    "analytics/rule_effectiveness",
    "analytics/evolution_fuel",
    # Meta
    "meta/schemas",
    "meta/checkpoints",
    "meta/lineage",
]

# =============================================================================
# 实现
# =============================================================================

def create_directories(dry_run: bool = False) -> list[Path]:
    """创建数据湖目录结构"""
    created = []
    for d in DIRS:
        p = LAKE_ROOT / d
        if dry_run:
            print(f"[DRY-RUN] mkdir -p {p}")
        else:
            p.mkdir(parents=True, exist_ok=True)
            created.append(p)
    return created


def write_schemas(dry_run: bool = False) -> None:
    """写入 Schema 注册文件"""
    meta_dir = LAKE_ROOT / "meta" / "schemas"
    if not dry_run:
        meta_dir.mkdir(parents=True, exist_ok=True)

    for table_name, spec in SCHEMAS.items():
        schema_file = meta_dir / f"{table_name.replace('/', '_')}.json"
        content = {
            "table": table_name,
            "description": spec["description"],
            "partition_by": spec["partition_by"],
            "schema": spec["schema"],
            "created_at": datetime.utcnow().isoformat() + "Z",
            "version": "1.0",
        }
        if dry_run:
            print(f"[DRY-RUN] write schema: {schema_file}")
        else:
            with open(schema_file, "w") as f:
                json.dump(content, f, indent=2, ensure_ascii=False)

    # 写入汇总清单
    manifest = {
        "lake_root": str(LAKE_ROOT),
        "initialized_at": datetime.utcnow().isoformat() + "Z",
        "tables": list(SCHEMAS.keys()),
        "total_tables": len(SCHEMAS),
    }
    manifest_file = LAKE_ROOT / "meta" / "lake_manifest.json"
    if dry_run:
        print(f"[DRY-RUN] write manifest: {manifest_file}")
    else:
        with open(manifest_file, "w") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)


def create_duckdb_views(dry_run: bool = False) -> None:
    """在 DuckDB 中创建视图以便 SQL 查询"""
    if not DUCKDB_AVAILABLE:
        print("⚠️  duckdb 未安装，跳过视图创建 (pip install duckdb)")
        return

    db_path = LAKE_ROOT / "meta" / "governance_lake.duckdb"
    if dry_run:
        print(f"[DRY-RUN] create duckdb views: {db_path}")
        return

    conn = duckdb.connect(str(db_path))
    try:
        # 为每个 curated/analytics 表创建视图，自动发现最新分区
        for table_name, spec in SCHEMAS.items():
            if not (table_name.startswith("curated/") or table_name.startswith("analytics/")):
                continue
            view_name = table_name.replace("/", "_")
            glob_path = str(LAKE_ROOT / table_name / "**" / "*.parquet")
            # 检查是否有文件匹配
            try:
                conn.execute(f"SELECT 1 FROM read_parquet('{glob_path}') LIMIT 1")
                conn.execute(f"""
                    CREATE OR REPLACE VIEW {view_name} AS
                    SELECT * FROM read_parquet('{glob_path}', hive_partitioning=1)
                """)
                print(f"  ✅ View created: {view_name}")
            except Exception:
                # 无数据时创建空视图（基于 schema 推断）
                cols = ", ".join(f"CAST(NULL AS {dtype}) AS {col}" for col, dtype in spec["schema"].items())
                conn.execute(f"CREATE OR REPLACE VIEW {view_name} AS SELECT {cols} WHERE false")
                print(f"  ⚪ View created (empty): {view_name}")
    finally:
        conn.close()


def verify_structure() -> bool:
    """验证数据湖结构完整性"""
    ok = True
    print(f"🔍 验证数据湖: {LAKE_ROOT}")
    print()

    # 检查目录
    for d in DIRS:
        p = LAKE_ROOT / d
        if p.exists():
            parquet_count = len(list(p.glob("**/*.parquet")))
            print(f"  ✅ {d} (parquet files: {parquet_count})")
        else:
            print(f"  ❌ {d} (缺失)")
            ok = False

    # 检查 Schema 注册
    meta_dir = LAKE_ROOT / "meta" / "schemas"
    if meta_dir.exists():
        schema_files = list(meta_dir.glob("*.json"))
        print(f"\n  📋 Schema 注册: {len(schema_files)} 个")
        for sf in schema_files:
            try:
                with open(sf) as f:
                    data = json.load(f)
                print(f"    ✅ {data['table']} v{data.get('version', '?')}")
            except Exception as e:
                print(f"    ❌ {sf.name}: {e}")
                ok = False
    else:
        print("  ❌ meta/schemas 目录缺失")
        ok = False

    # 检查 Manifest
    manifest = LAKE_ROOT / "meta" / "lake_manifest.json"
    if manifest.exists():
        with open(manifest) as f:
            m = json.load(f)
        print(f"\n  📦 Manifest: {m['total_tables']} 表, 初始化于 {m['initialized_at']}")
    else:
        print("\n  ❌ Manifest 缺失")
        ok = False

    # 检查 DuckDB
    db = LAKE_ROOT / "meta" / "governance_lake.duckdb"
    if db.exists():
        print(f"  🦆 DuckDB: {db} ({db.stat().st_size / 1024:.1f} KB)")
    else:
        print("  ⚠️  DuckDB 未创建")

    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="MAREF 治理数据湖初始化")
    parser.add_argument("--dry-run", action="store_true", help="仅打印计划不执行")
    parser.add_argument("--verify", action="store_true", help="验证现有结构")
    args = parser.parse_args()

    print("=" * 60)
    print("MAREF 治理数据湖初始化")
    print("=" * 60)
    print(f"湖根目录: {LAKE_ROOT}")
    print()

    if args.verify:
        success = verify_structure()
        print()
        print("=" * 60)
        print("验证" + ("通过" if success else "失败"))
        print("=" * 60)
        return 0 if success else 1

    if args.dry_run:
        print("🔍 DRY-RUN 模式，仅打印计划")
        print()

    # 1. 创建目录
    print("📁 创建目录结构...")
    created = create_directories(args.dry_run)
    if not args.dry_run:
        print(f"  创建 {len(created)} 个目录")
    print()

    # 2. 写入 Schema
    print("📋 写入 Schema 注册...")
    write_schemas(args.dry_run)
    if not args.dry_run:
        print(f"  注册 {len(SCHEMAS)} 个表 Schema")
    print()

    # 3. 创建 DuckDB 视图
    print("🦆 创建 DuckDB 视图...")
    create_duckdb_views(args.dry_run)
    print()

    if not args.dry_run:
        # 4. 验证
        print("🔍 验证初始化结果...")
        verify_structure()

    print()
    print("=" * 60)
    print("初始化完成" if not args.dry_run else "DRY-RUN 完成")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())