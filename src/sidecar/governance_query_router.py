#!/usr/bin/env python3
"""
统一治理查询 API - /api/v1/governance/query

提供 SQL-like 查询接口，支持:
- 多数据源联合查询 (raw + curated + analytics)
- 时间范围、Agent、工具、规则多维过滤
- 聚合、分组、排序、分页
- 导出格式: JSON, CSV, Parquet

集成到 sidecar FastAPI
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

LAKE_ROOT = Path(os.environ.get("MAREF_GOVERNANCE_LAKE", os.path.expanduser("~/maref-governance-lake")))

router = APIRouter(prefix="/api/v1/governance", tags=["governance-query"])

# 可查询的表映射
QUERYABLE_TABLES = {
    # Raw
    "raw.coding_agents": LAKE_ROOT / "raw" / "coding_agents",
    "raw.obs_events": LAKE_ROOT / "raw" / "obs_events",
    "raw.audit_logs": LAKE_ROOT / "raw" / "audit_logs",
    "raw.telemetry": LAKE_ROOT / "raw" / "telemetry",
    "raw.probe_readings": LAKE_ROOT / "raw" / "probe_readings",
    "raw.mcp_governance": LAKE_ROOT / "raw" / "mcp_governance",
    # Curated
    "curated.agent_sessions": LAKE_ROOT / "curated" / "agent_sessions",
    "curated.tool_executions": LAKE_ROOT / "curated" / "tool_executions",
    "curated.governance_decisions": LAKE_ROOT / "curated" / "governance_decisions",
    "curated.cross_agent_flows": LAKE_ROOT / "curated" / "cross_agent_flows",
    "curated.violation_patterns": LAKE_ROOT / "curated" / "violation_patterns",
    # Analytics
    "analytics.daily_governance_kpi": LAKE_ROOT / "analytics" / "daily_governance_kpi",
    "analytics.agent_health_index": LAKE_ROOT / "analytics" / "agent_health_index",
    "analytics.rule_effectiveness": LAKE_ROOT / "analytics" / "rule_effectiveness",
    "analytics.evolution_fuel": LAKE_ROOT / "analytics" / "evolution_fuel",
}


class QueryRequest(BaseModel):
    """查询请求"""
    sql: str = Field(..., description="SQL 查询语句 (仅支持 SELECT)")
    params: dict[str, Any] = Field(default_factory=dict, description="参数化查询参数")
    format: str = Field("json", description="输出格式: json, csv, parquet")
    limit: int = Field(1000, ge=1, le=10000, description="最大返回行数")


class QueryResponse(BaseModel):
    """查询响应"""
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    execution_time_ms: float
    truncated: bool


def _validate_sql(sql: str) -> tuple[bool, str]:
    """简单的 SQL 安全校验"""
    sql_upper = sql.strip().upper()

    # 必须是 SELECT
    if not sql_upper.startswith("SELECT"):
        return False, "Only SELECT queries are allowed"

    # 禁止危险关键字
    forbidden = [
        "DROP", "DELETE", "INSERT", "UPDATE", "CREATE", "ALTER", "TRUNCATE",
        "ATTACH", "DETACH", "COPY", "EXPORT", "IMPORT", "PRAGMA",
        "LOAD", "INSTALL", "SET", "RESET",
    ]
    for kw in forbidden:
        if re.search(rf"\b{kw}\b", sql_upper):
            return False, f"Forbidden keyword: {kw}"

    # 禁止多语句
    if sql.count(";") > 1:
        return False, "Multiple statements not allowed"

    return True, ""


def _get_table_path(table_name: str) -> Path | None:
    """获取表路径"""
    return QUERYABLE_TABLES.get(table_name)


def _build_glob_path(table_name: str) -> str:
    """构建 DuckDB glob 路径"""
    path = _get_table_path(table_name)
    if not path:
        return ""
    return str(path / "**" / "*.parquet")


def _execute_query(sql: str, params: dict, limit: int) -> tuple[list[str], list[list[Any]], bool]:
    """执行查询"""
    if not DUCKDB_AVAILABLE:
        raise HTTPException(status_code=503, detail="DuckDB not available. Install with: pip install duckdb")

    # 注册所有表为视图
    conn = duckdb.connect()
    try:
        for table_name, path in QUERYABLE_TABLES.items():
            if path.exists():
                view_name = table_name.replace(".", "_")
                glob_path = _build_glob_path(table_name)
                if glob_path:
                    try:
                        conn.execute(f"""
                            CREATE OR REPLACE VIEW {view_name} AS
                            SELECT * FROM read_parquet('{glob_path}', hive_partitioning=1)
                        """)
                    except Exception:
                        pass  # 视图创建失败不阻断

        # 执行查询 (添加 LIMIT)
        if "LIMIT" not in sql.upper():
            sql = f"{sql.rstrip(';')} LIMIT {limit}"

        # 参数化查询
        if params:
            result = conn.execute(sql, params).fetchall()
        else:
            result = conn.execute(sql).fetchall()

        columns = [desc[0] for desc in conn.description] if conn.description else []
        truncated = len(result) >= limit

        return columns, result, truncated

    finally:
        conn.close()


@router.post("/query", response_model=QueryResponse)
async def governance_query(request: QueryRequest) -> QueryResponse:
    """执行治理数据查询"""
    import time
    start = time.perf_counter()

    # SQL 安全校验
    ok, err = _validate_sql(request.sql)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Invalid SQL: {err}")

    try:
        columns, rows, truncated = _execute_query(request.sql, request.params, request.limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query execution failed: {e}")

    exec_time = (time.perf_counter() - start) * 1000

    return QueryResponse(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        execution_time_ms=round(exec_time, 2),
        truncated=truncated,
    )


@router.get("/tables")
async def list_tables() -> dict[str, Any]:
    """列出可查询的表"""
    tables = []
    for name, path in QUERYABLE_TABLES.items():
        exists = path.exists()
        parquet_count = 0
        size_mb = 0.0
        if exists:
            try:
                files = list(path.rglob("*.parquet"))
                parquet_count = len(files)
                size_mb = sum(f.stat().st_size for f in files) / 1024 / 1024
            except Exception:
                pass

        tables.append({
            "name": name,
            "layer": name.split(".")[0],
            "exists": exists,
            "parquet_files": parquet_count,
            "size_mb": round(size_mb, 2),
            "path": str(path),
        })

    return {
        "tables": tables,
        "total": len(tables),
        "duckdb_available": DUCKDB_AVAILABLE,
    }


@router.get("/tables/{table_name}/schema")
async def get_table_schema(table_name: str) -> dict[str, Any]:
    """获取表 Schema (从 DuckDB 推断)"""
    if table_name not in QUERYABLE_TABLES:
        raise HTTPException(status_code=404, detail=f"Table not found: {table_name}")

    if not DUCKDB_AVAILABLE:
        raise HTTPException(status_code=503, detail="DuckDB not available")

    path = _get_table_path(table_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Table data not found: {table_name}")

    glob_path = _build_glob_path(table_name)
    try:
        conn = duckdb.connect()
        # 推断 schema
        result = conn.execute(f"DESCRIBE SELECT * FROM read_parquet('{glob_path}') LIMIT 0").fetchall()
        columns = [{"name": r[0], "type": r[1], "nullable": r[2]} for r in result]
        conn.close()
        return {"table": table_name, "columns": columns}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Schema inference failed: {e}")


@router.get("/tables/{table_name}/preview")
async def preview_table(
    table_name: str,
    limit: int = Query(10, ge=1, le=100),
    since: str | None = Query(None, description="起始时间 ISO 格式"),
    until: str | None = Query(None, description="结束时间 ISO 格式"),
) -> dict[str, Any]:
    """预览表数据"""
    if table_name not in QUERYABLE_TABLES:
        raise HTTPException(status_code=404, detail=f"Table not found: {table_name}")

    view_name = table_name.replace(".", "_")
    sql = f"SELECT * FROM {view_name}"

    # 添加时间过滤
    conditions = []
    if since:
        conditions.append(f"timestamp >= {datetime.fromisoformat(since.replace('Z', '+00:00')).timestamp()}")
    if until:
        conditions.append(f"timestamp <= {datetime.fromisoformat(until.replace('Z', '+00:00')).timestamp()}")

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += f" LIMIT {limit}"

    try:
        columns, rows, truncated = _execute_query(sql, {}, limit)
        return {
            "table": table_name,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview failed: {e}")


# 常用查询模板端点
@router.get("/kpi/daily")
async def get_daily_kpi(
    days: int = Query(7, ge=1, le=90),
) -> dict[str, Any]:
    """获取每日治理 KPI"""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    sql = f"""
        SELECT * FROM analytics_daily_governance_kpi
        WHERE date >= '{since}'
        ORDER BY date DESC
    """
    columns, rows, _ = _execute_query(sql, {}, 1000)
    return {"columns": columns, "rows": rows, "period_days": days}


@router.get("/kpi/agent-health")
async def get_agent_health(
    agent_id: str | None = Query(None),
    days: int = Query(7, ge=1, le=90),
) -> dict[str, Any]:
    """获取 Agent 健康指数"""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    where = f"date >= '{since}'"
    if agent_id:
        where += f" AND agent_id = '{agent_id}'"

    sql = f"""
        SELECT * FROM analytics_agent_health_index
        WHERE {where}
        ORDER BY date DESC, agent_id
    """
    columns, rows, _ = _execute_query(sql, {}, 1000)
    return {"columns": columns, "rows": rows, "period_days": days}


@router.get("/kpi/rule-effectiveness")
async def get_rule_effectiveness(
    rule_id: str | None = Query(None),
    days: int = Query(7, ge=1, le=90),
) -> dict[str, Any]:
    """获取规则有效度"""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    where = f"date >= '{since}'"
    if rule_id:
        where += f" AND rule_id = '{rule_id}'"

    sql = f"""
        SELECT * FROM analytics_rule_effectiveness
        WHERE {where}
        ORDER BY date DESC, rule_id
    """
    columns, rows, _ = _execute_query(sql, {}, 1000)
    return {"columns": columns, "rows": rows, "period_days": days}


@router.get("/flows/cross-agent")
async def get_cross_agent_flows(
    correlation_id: str | None = Query(None),
    agent_id: str | None = Query(None),
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(100, ge=1, le=1000),
) -> dict[str, Any]:
    """获取跨 Agent 协作流"""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    where = f"date >= '{since}'"
    if correlation_id:
        where += f" AND correlation_id = '{correlation_id}'"
    if agent_id:
        where += f" AND (root_agent_id = '{agent_id}' OR agent_sequence LIKE '%{agent_id}%')"

    sql = f"""
        SELECT * FROM curated_cross_agent_flows
        WHERE {where}
        ORDER BY start_time DESC
        LIMIT {limit}
    """
    columns, rows, _ = _execute_query(sql, {}, limit)
    return {"columns": columns, "rows": rows, "period_days": days}


__all__ = ["router"]