#!/usr/bin/env python3
"""
跨 Agent 协作链路重建脚本

从多源治理事件中重建多 Agent 协作 DAG:
- 基于 correlation_id 关联同一用户请求的全链路
- 基于 chain_id + delegation_depth 重建委托关系
- 输出 curated/cross_agent_flows Parquet 分区表

用法:
    python scripts/rebuild_cross_agent_flows.py           # 重建最近 24h
    python scripts/rebuild_cross_agent_flows.py --since 7d # 重建最近 7 天
    python scripts/rebuild_cross_agent_flows.py --date 20260915 # 重建指定日期
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
    print("⚠️  duckdb 未安装，将使用 JSON 输出 (pip install duckdb)")

from maref_config import REPO_DIR

LAKE_ROOT = Path(os.environ.get("MAREF_GOVERNANCE_LAKE", "/Volumes/1TB-M2/maref-governance-lake"))


def _load_obs_events(since_hours: int) -> list[dict]:
    """加载 ObsEvent (本地 + sidecar telemetry 推送)"""
    events = []
    since_ts = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp()

    # 本地缓冲
    obs_dir = Path.home() / ".maref" / "obs"
    for f in obs_dir.glob("behavior_*.ndjson"):
        try:
            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                        if ev.get("timestamp", 0) >= since_ts:
                            events.append(("obs_local", ev))
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

    # 数据湖 raw/obs_events
    raw_obs = LAKE_ROOT / "raw" / "obs_events"
    if raw_obs.exists():
        for f in raw_obs.rglob("*.parquet"):
            try:
                if DUCKDB_AVAILABLE:
                    conn = duckdb.connect()
                    df = conn.execute(f"SELECT * FROM read_parquet('{f}')").fetchdf()
                    for _, row in df.iterrows():
                        ts = row.get("timestamp", 0)
                        if ts >= since_ts:
                            events.append(("obs_lake", row.to_dict()))
            except Exception:
                pass

    return events


def _load_tool_executions(since_hours: int) -> list[dict]:
    """加载工具执行事件 (来自 MCP 决策日志 / telemetry)"""
    events = []
    since_ts = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp()

    # 从审计日志提取
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
                            events.append(("audit", ev))
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

    # 从 telemetry 提取
    telemetry_root = REPO_DIR / "data" / "telemetry"
    if telemetry_root.exists():
        for f in telemetry_root.rglob("*.jsonl"):
            try:
                with open(f) as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            ev = json.loads(line)
                            ts = ev.get("timestamp", 0)
                            if ts >= since_ts:
                                data = ev.get("data", {})
                                if data.get("event_type") in ("tool_call_start", "tool_call_end", "tool_call_intercepted"):
                                    events.append(("telemetry", data))
                        except json.JSONDecodeError:
                            pass
            except Exception:
                pass

    return events


def _load_delegation_events(since_hours: int) -> list[dict]:
    """加载委托/切换 Agent 事件"""
    events = []
    since_ts = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp()

    # 从 ObsEvent 和 telemetry 中提取 delegation_start/end, agent_handoff
    for src_events in [_load_obs_events(since_hours), _load_tool_executions(since_hours)]:
        for src, ev in src_events:
            meta = ev.get("metadata", ev)
            ev_type = ev.get("event_type") or meta.get("event_type")
            if ev_type in ("delegation_start", "delegation_end", "agent_handoff"):
                events.append((src, meta))
    return events


def _extract_correlation_fields(event: dict) -> dict[str, Any]:
    """从事件中提取关联字段"""
    meta = event.get("metadata", event)
    return {
        "correlation_id": meta.get("correlation_id") or event.get("correlation_id"),
        "chain_id": meta.get("chain_id") or event.get("chain_id"),
        "delegation_depth": meta.get("delegation_depth", 0),
        "agent_id": meta.get("agent_id") or event.get("agent_id") or event.get("actor") or "unknown",
        "tool_name": meta.get("tool_name"),
        "event_type": event.get("event_type") or meta.get("event_type"),
        "timestamp": event.get("timestamp") or meta.get("timestamp"),
        "verdict": meta.get("verdict"),
        "latency_ms": meta.get("latency_ms"),
        "hitl_event_id": meta.get("hitl_event_id"),
        "risk_score": meta.get("risk_score"),
        "batch_id": meta.get("batch_id"),
        "client_session_id": meta.get("client_session_id"),
        "from_agent_id": meta.get("from_agent_id"),
        "to_agent_id": meta.get("to_agent_id"),
        "success": meta.get("success"),
        "raw": event,
    }


def rebuild_flows(since_hours: int = 24) -> list[dict]:
    """重建跨 Agent 协作流"""
    print(f"🔍 加载最近 {since_hours}h 事件...")

    # 1. 收集所有相关事件
    all_events = []

    # 工具调用事件
    for src, ev in _load_tool_executions(since_hours):
        fields = _extract_correlation_fields(ev)
        fields["source"] = src
        all_events.append(fields)

    # 委托事件
    for src, ev in _load_delegation_events(since_hours):
        fields = _extract_correlation_fields(ev)
        fields["source"] = src
        all_events.append(fields)

    print(f"   共收集 {len(all_events)} 个相关事件")

    # 2. 按 correlation_id 分组
    by_correlation: dict[str, list[dict]] = defaultdict(list)
    for ev in all_events:
        corr_id = ev.get("correlation_id")
        if corr_id:
            by_correlation[corr_id].append(ev)

    print(f"   发现 {len(by_correlation)} 个唯一 correlation_id")

    # 3. 重建每个 correlation_id 的协作流
    flows = []

    for corr_id, events in by_correlation.items():
        if not events:
            continue

        # 按时间排序
        events.sort(key=lambda e: e.get("timestamp", 0))

        # 提取链路信息
        chain_ids = set(e.get("chain_id") for e in events if e.get("chain_id"))
        chain_id = chain_ids.pop() if chain_ids else corr_id

        # Agent 序列 (按首次出现顺序)
        agent_sequence = []
        seen_agents = set()
        for e in events:
            aid = e.get("agent_id")
            if aid and aid not in seen_agents:
                agent_sequence.append(aid)
                seen_agents.add(aid)

        # 委托边
        delegation_edges = []
        for e in events:
            if e.get("event_type") == "delegation_start":
                delegation_edges.append({
                    "from": e.get("from_agent_id"),
                    "to": e.get("to_agent_id"),
                    "tool": e.get("tool_name"),
                    "depth": e.get("delegation_depth", 0),
                    "timestamp": e.get("timestamp"),
                })
            elif e.get("event_type") == "agent_handoff":
                delegation_edges.append({
                    "from": e.get("from_agent_id") or e.get("agent_id"),
                    "to": e.get("to_agent_id"),
                    "tool": e.get("tool_name"),
                    "depth": e.get("delegation_depth", 0),
                    "timestamp": e.get("timestamp"),
                })

        # 统计
        tool_calls = [e for e in events if e.get("event_type") in ("tool_call_start", "tool_call_end")]
        total_tool_calls = len(tool_calls)
        intercepted = sum(1 for e in events if e.get("event_type") == "tool_call_intercepted")
        hitl = sum(1 for e in events if e.get("event_type") == "hitl_triggered")

        # 瓶颈分析: 延迟最高的 agent/tool
        bottleneck_agent = ""
        bottleneck_tool = ""
        max_latency = 0
        for e in events:
            lat = e.get("latency_ms")
            if lat is not None and lat > max_latency:
                max_latency = lat
                bottleneck_agent = e.get("agent_id", "")
                bottleneck_tool = e.get("tool_name", "")

        # 时间范围
        timestamps = [e.get("timestamp", 0) for e in events if e.get("timestamp")]
        start_time = min(timestamps) if timestamps else 0
        end_time = max(timestamps) if timestamps else 0

        flow = {
            "correlation_id": corr_id,
            "chain_id": chain_id,
            "root_agent_id": agent_sequence[0] if agent_sequence else "unknown",
            "start_time": start_time,
            "end_time": end_time,
            "total_duration_ms": int((end_time - start_time) * 1000) if end_time > start_time else 0,
            "agent_sequence": json.dumps(agent_sequence),
            "delegation_edges": json.dumps(delegation_edges),
            "total_tool_calls": total_tool_calls,
            "total_interceptions": intercepted,
            "total_hitl": hitl,
            "final_outcome": "success" if intercepted == 0 else "partial" if total_tool_calls > intercepted else "failed",
            "bottleneck_agent": bottleneck_agent,
            "bottleneck_tool": bottleneck_tool,
        }
        flows.append(flow)

    print(f"   重建 {len(flows)} 个协作流")
    return flows


def write_flows(flows: list[dict], date_str: str) -> None:
    """写入数据湖 curated/cross_agent_flows"""
    if not flows:
        print("⚠️  无协作流数据")
        return

    curated_dir = LAKE_ROOT / "curated" / "cross_agent_flows"
    curated_dir.mkdir(parents=True, exist_ok=True)

    # JSON 输出 (兼容)
    json_file = curated_dir / f"cross_agent_flows_{date_str}.json"
    with open(json_file, "w") as f:
        json.dump(flows, f, indent=2, ensure_ascii=False)
    print(f"📝 JSON 输出: {json_file}")

    # Parquet 输出 (DuckDB)
    if DUCKDB_AVAILABLE:
        try:
            parquet_file = curated_dir / f"cross_agent_flows_{date_str}.parquet"
            conn = duckdb.connect()
            conn.execute(f"""
                COPY (
                    SELECT * FROM read_json_auto('{json.dumps(flows)}')
                ) TO '{parquet_file}' (FORMAT PARQUET, PARTITION_BY (root_agent_id))
            """)
            conn.close()
            print(f"📊 Parquet 输出: {parquet_file}")
        except Exception as e:
            print(f"⚠️  Parquet 写入失败: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="跨 Agent 协作链路重建")
    parser.add_argument("--since", default="24h", help="时间范围: 24h, 7d, 30d")
    parser.add_argument("--date", help="指定日期 YYYYMMDD (覆盖 since)")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    args = parser.parse_args()

    # 解析时间范围
    if args.date:
        since_hours = 24
        date_str = args.date
    else:
        since_map = {"1h": 1, "6h": 6, "24h": 24, "7d": 168, "30d": 720}
        since_hours = since_map.get(args.since, 24)
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

    print("=" * 60)
    print("跨 Agent 协作链路重建")
    print("=" * 60)
    print(f"时间范围: 最近 {since_hours} 小时")
    print(f"输出日期: {date_str}")
    print()

    flows = rebuild_flows(since_hours)

    if args.dry_run:
        print("\n[dry-run] 结果预览:")
        for f in flows[:5]:
            print(f"  {f['correlation_id'][:20]}... | agents: {f['agent_sequence']} | tools: {f['total_tool_calls']} | outcome: {f['final_outcome']}")
        return 0

    write_flows(flows, date_str)

    # 统计摘要
    if flows:
        total_tools = sum(f["total_tool_calls"] for f in flows)
        total_intercepted = sum(f["total_interceptions"] for f in flows)
        total_hitl = sum(f["total_hitl"] for f in flows)
        multi_agent = sum(1 for f in flows if len(json.loads(f["agent_sequence"])) > 1)

        print(f"\n📈 统计摘要:")
        print(f"   协作流总数: {len(flows)}")
        print(f"   多 Agent 协作: {multi_agent} ({multi_agent/len(flows)*100:.1f}%)")
        print(f"   总工具调用: {total_tools}")
        print(f"   总拦截: {total_intercepted}")
        print(f"   总 HITL: {total_hitl}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())