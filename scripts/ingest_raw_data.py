#!/usr/bin/env python3
"""
将现有审计日志/ObsEvent/Telemetry 导入数据湖 Raw 层
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False

LAKE_ROOT = Path(os.environ.get("MAREF_GOVERNANCE_LAKE", "/Volumes/1TB-M2/maref-governance-lake"))

# 源文件路径
AUDIT_LOG = Path("/Volumes/1TB-M2/public/maref/.governance/governance_audit.jsonl")
RECURSIVE_LOG = Path("/Volumes/1TB-M2/public/maref/recursive_governance_audit.jsonl")
OBS_DIR = Path.home() / ".maref" / "obs"
TELEMETRY_ROOT = Path("/Volumes/1TB-M2/public/maref/data/telemetry")
PROBE_DB = Path("/Volumes/1TB-M2/public/maref/governance_observations.db")


def _ts_to_date(ts: float) -> str:
    """时间戳转日期分区"""
    if ts <= 0:
        return datetime.now(timezone.utc).strftime("%Y%m%d")
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%d")


def _write_parquet(table_name: str, records: list[dict], partition_cols: list[str]) -> int:
    """写入 Parquet (使用 DuckDB)"""
    if not records or not DUCKDB_AVAILABLE:
        return 0

    try:
        import pandas as pd
        conn = duckdb.connect()
        # 转换为 pandas DataFrame 并写入
        df = pd.DataFrame(records)
        table_path = LAKE_ROOT / table_name
        table_path.mkdir(parents=True, exist_ok=True)

        # 按分区列写入
        partition_str = ", ".join(partition_cols)
        conn.execute(f"""
            COPY df TO '{table_path}' 
            (FORMAT PARQUET, PARTITION_BY ({partition_str}), OVERWRITE_OR_IGNORE)
        """)
        count = len(records)
        conn.close()
        return count
    except Exception as e:
        print(f"⚠️  写入 {table_name} 失败: {e}")
        return 0


def ingest_audit_logs():
    """导入 governance_audit.jsonl"""
    print("📥 导入 governance_audit.jsonl...")
    if not AUDIT_LOG.exists():
        print("  文件不存在")
        return 0

    records = []
    with open(AUDIT_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                ts = e.get("timestamp", 0)
                if isinstance(ts, str):
                    try:
                        ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                    except Exception:
                        ts = 0
                records.append({
                    "id": e.get("id", ""),
                    "timestamp": ts,
                    "date": _ts_to_date(ts),
                    "event_type": e.get("event_type", ""),
                    "actor": e.get("actor", ""),
                    "action": e.get("action", ""),
                    "details": e.get("details", ""),
                    "metadata": e.get("metadata", {}),
                    "previous_hash": e.get("previous_hash", ""),
                    "chain_hash": e.get("chain_hash", ""),
                })
            except json.JSONDecodeError:
                pass

    count = _write_parquet("raw/audit_logs", records, ["date", "event_type", "actor"])
    print(f"  ✅ 导入 {count} 条审计记录")
    return count


def ingest_recursive_logs():
    """导入 recursive_governance_audit.jsonl"""
    print("📥 导入 recursive_governance_audit.jsonl...")
    if not RECURSIVE_LOG.exists():
        print("  文件不存在")
        return 0

    records = []
    with open(RECURSIVE_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                ts = e.get("timestamp", 0)
                if isinstance(ts, str):
                    try:
                        ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                    except Exception:
                        ts = 0
                records.append({
                    "id": e.get("id", ""),
                    "timestamp": ts,
                    "date": _ts_to_date(ts),
                    "event_type": e.get("event_type", ""),
                    "actor": e.get("actor", ""),
                    "action": e.get("action", ""),
                    "details": e.get("details", ""),
                    "metadata": e.get("metadata", {}),
                })
            except json.JSONDecodeError:
                pass

    count = _write_parquet("raw/audit_logs", records, ["date", "event_type", "actor"])
    print(f"  ✅ 导入 {count} 条递归审计记录")
    return count


def ingest_obs_events():
    """导入 ObsEvent ndjson"""
    print("📥 导入 ObsEvent...")
    if not OBS_DIR.exists():
        print("  目录不存在")
        return 0

    records = []
    for f in OBS_DIR.glob("behavior_*.ndjson"):
        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    ts = e.get("timestamp", 0)
                    meta = e.get("metadata", {})
                    records.append({
                        "session_id": e.get("session_id", ""),
                        "event_type": e.get("event_type", ""),
                        "version": e.get("version", ""),
                        "timestamp": ts,
                        "date": _ts_to_date(ts),
                        "event_sequence": e.get("event_sequence", 0),
                        "agent_id": meta.get("agent_id", "") or meta.get("from_agent_id", "") or meta.get("to_agent_id", "") or "unknown",
                        "metadata": meta,
                    })
                except json.JSONDecodeError:
                    pass

    count = _write_parquet("raw/obs_events", records, ["date", "event_type", "agent_id"])
    print(f"  ✅ 导入 {count} 条 ObsEvent")
    return count


def ingest_telemetry():
    """导入 Telemetry"""
    print("📥 导入 Telemetry...")
    if not TELEMETRY_ROOT.exists():
        print("  目录不存在")
        return 0

    records = []
    for f in TELEMETRY_ROOT.rglob("*.jsonl"):
        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    ts = e.get("timestamp", 0)
                    if isinstance(ts, str):
                        try:
                            ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                        except Exception:
                            ts = 0
                    records.append({
                        "source": e.get("source", "unknown"),
                        "telemetry_type": e.get("telemetry_type", "unknown"),
                        "timestamp": ts,
                        "date": _ts_to_date(ts),
                        "data": e.get("data", {}),
                        "ingested_at": e.get("ingested_at", ""),
                    })
                except json.JSONDecodeError:
                    pass

    count = _write_parquet("raw/telemetry", records, ["date", "source", "telemetry_type"])
    print(f"  ✅ 导入 {count} 条 Telemetry")
    return count


def ingest_probe_readings():
    """导入 Probe Readings (从 SQLite)"""
    print("📥 导入 Probe Readings...")
    if not PROBE_DB.exists():
        print("  DB 不存在")
        return 0

    records = []
    try:
        conn = sqlite3.connect(str(PROBE_DB))
        cur = conn.cursor()
        cur.execute("SELECT probe_name, severity, value, threshold, timestamp, context_json FROM probe_readings")
        for row in cur.fetchall():
            ts = row[4]
            records.append({
                "probe_name": row[0],
                "severity": row[1],
                "value": row[2],
                "threshold": row[3],
                "timestamp": ts,
                "date": _ts_to_date(ts),
                "context_json": row[5],
            })
        conn.close()
    except Exception as e:
        print(f"  读取失败: {e}")
        return 0

    count = _write_parquet("raw/probe_readings", records, ["date", "probe_name"])
    print(f"  ✅ 导入 {count} 条探针读数")
    return count


def ingest_mcp_governance():
    """导入 MCP 治理决策 (从审计日志提取)"""
    print("📥 导入 MCP 治理决策...")
    if not AUDIT_LOG.exists():
        return 0

    records = []
    with open(AUDIT_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                if e.get("event_type") != "governance_decision":
                    continue
                ts = e.get("timestamp", 0)
                if isinstance(ts, str):
                    try:
                        ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                    except Exception:
                        ts = 0
                meta = e.get("metadata", {})
                records.append({
                    "timestamp": ts,
                    "date": _ts_to_date(ts),
                    "agent_id": e.get("actor", ""),
                    "tool_name": e.get("action", ""),
                    "trust_level": meta.get("trust_level", ""),
                    "verdict": meta.get("verdict", "").lower(),
                    "risk_score": meta.get("risk_score", 0.0),
                    "matched_rule": meta.get("matched_rule", ""),
                    "reason": meta.get("reason", ""),
                    "hitl_event_id": meta.get("hitl_event_id", ""),
                    "chain_id": meta.get("chain_id", ""),
                    "delegation_depth": meta.get("delegation_depth", 0),
                    "latency_ms": meta.get("latency_ms", 0),
                    "args_hash": meta.get("args_hash", ""),
                })
            except json.JSONDecodeError:
                pass

    count = _write_parquet("raw/mcp_governance", records, ["date", "agent_id", "verdict"])
    print(f"  ✅ 导入 {count} 条 MCP 决策")
    return count


def main():
    print("=" * 60)
    print("数据湖 Raw 层历史数据导入")
    print("=" * 60)

    if not DUCKDB_AVAILABLE:
        print("❌ 需要 duckdb")
        return 1

    total = 0
    total += ingest_audit_logs()
    total += ingest_recursive_logs()
    total += ingest_obs_events()
    total += ingest_telemetry()
    total += ingest_probe_readings()
    total += ingest_mcp_governance()

    print(f"\n{'=' * 60}")
    print(f"总导入: {total} 条记录")
    print(f"{'=' * 60}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())