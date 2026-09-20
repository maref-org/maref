#!/usr/bin/env python3
"""探针采样器 (P0-B v3) — 多数据源融合采样

数据源 (按优先级):
1. ObsEvent (本地 ~/.maref/obs/ + sidecar telemetry) - 实时治理事件
2. Telemetry (data/telemetry/) - OpenClaw 推送遥测
3. Audit Log (.governance/governance_audit.jsonl) - 审计决策
4. MCP 决策日志 - 工具调用治理裁决
5. Recursive Audit - 递归治理审计

采样语义 (v3, 多源率基 + 滑窗 + 语义标签)
-----------------------------------------
每个探针从多个数据源聚合，按语义标签分类计算率基指标:

- oscillation 探针 (状态振荡/不稳定信号)
    源: 所有源中的 oscillation_intervention, force_stabilize, auto_transition,
        tool_call_intercepted, hitl_triggered, breaker_trip
    value = 不稳定事件占比 % = Σ(不稳定事件计数) / 窗口内总事件数 × 100

- entropy 探针 (混沌/异常/风险信号)
    源: anomaly_detected, trust_boundary_violation, constitution_violation,
        governance_bypass, sanction, cost_breach, tool_call_intercepted
    value = 高风险事件占比 % = Σ(高风险事件计数) / 窗口内总事件数 × 100

- governance_health 探针 (治理健康度)
    源: tool_call_start, tool_call_end, rule_matched, policy_evaluated
    value = 治理覆盖率 % = 有治理决策的工具调用 / 总工具调用 × 100

- agent_trust 探针 (Agent 信任度聚合)
    源: 所有 agent 的 trust_score 加权平均
    value = 综合信任分 (0-100)

滑窗: 取最近 N 条事件 (默认 1000，可配 MAREF_PROBE_WINDOW)
时间窗: 可选按时间过滤 (MAREF_PROBE_TIME_WINDOW_HOURS)

输出: probe_readings 表 + 数据湖 curated/probe_readings 分区
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from maref_config import (
    AUDIT_LOG,
    RECURSIVE_AUDIT_LOG as RECURSIVE_LOG,
    PROBE_DB,
    config_path,
    REPO_DIR,
)

# 采样器本地阈值 (率基 滑窗 %, 可后续校准)
DEFAULT_THRESHOLDS = {
    "oscillation": {"normal_max": 30.0, "critical_min": 60.0},
    "entropy": {"normal_max": 10.0, "critical_min": 25.0},
    "governance_health": {"normal_min": 80.0, "critical_min": 50.0},  # 反向: 越高越好
    "agent_trust": {"normal_min": 70.0, "critical_min": 40.0},  # 反向: 越高越好
}

# 语义标签定义: 探针名 -> {源事件类型集合, 权重}
PROBE_SIGNATURES = {
    "oscillation": {
        "source_events": {
            "oscillation_intervention",
            "force_stabilize",
            "auto_transition",
            "tool_call_intercepted",
            "hitl_triggered",
            "breaker_trip",
            "circuit_breaker_monitor_trip",
        },
        "weight": 1.0,
    },
    "entropy": {
        "source_events": {
            "anomaly_detected",
            "trust_boundary_violation",
            "constitution_violation",
            "governance_bypass",
            "sanction",
            "cost_breach",
            "tool_call_intercepted",
            "rule_matched_deny",
        },
        "weight": 1.0,
    },
    "governance_health": {
        "source_events": {
            "tool_call_start",
            "tool_call_end",
            "rule_matched",
            "policy_evaluated",
            "tool_execution",
        },
        "weight": 1.0,
        "positive": True,  # 正向指标
    },
    "agent_trust": {
        "source_events": {"token_usage", "api_cost", "context_window"},  # 通过代理事件推导
        "weight": 1.0,
        "positive": True,
    },
}

DEFAULT_WINDOW = 1000  # 滑窗大小: 最近 N 条事件


def _load_entries(path) -> list[dict]:
    """加载 JSONL 文件"""
    if not os.path.exists(path):
        return []
    entries = []
    with open(path) as f:
        for line in f:
            try:
                entries.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                pass
    return entries


def _load_obs_events(since_hours: int = 24) -> list[dict]:
    """加载本地 ObsEvent 缓冲区"""
    obs_dir = Path.home() / ".maref" / "obs"
    events = []
    since_ts = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp()

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
                            events.append(ev)
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass
    return events


def _load_telemetry(since_hours: int = 24) -> list[dict]:
    """加载 Telemetry 数据"""
    telemetry_root = REPO_DIR / "data" / "telemetry"
    events = []
    since_ts = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp()

    if not telemetry_root.exists():
        return events

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
                            events.append(ev)
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass
    return events


def _load_mcp_decisions(since_hours: int = 24) -> list[dict]:
    """从审计日志提取 MCP 治理决策"""
    events = []
    since_ts = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp()

    if not AUDIT_LOG.exists():
        return events

    try:
        with open(AUDIT_LOG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    ts = ev.get("timestamp", 0)
                    if ts >= since_ts and ev.get("event_type") == "governance_decision":
                        events.append(ev)
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    return events


def _load_thresholds() -> dict:
    """阈值解析优先级: env > config > 默认"""
    env = os.environ.get("MAREF_PROBE_THRESHOLDS")
    if env:
        try:
            cfg = json.loads(env)
            merged = dict(DEFAULT_THRESHOLDS)
            for name, t in cfg.items():
                if name in merged and "normal_max" in t and "critical_min" in t:
                    merged[name] = {"normal_max": t["normal_max"], "critical_min": t["critical_min"]}
                elif name in merged and "normal_min" in t and "critical_min" in t:
                    merged[name] = {"normal_min": t["normal_min"], "critical_min": t["critical_min"]}
            return merged
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    cfg_path = config_path("probe_thresholds.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path) as f:
                cfg = json.load(f)
            merged = dict(DEFAULT_THRESHOLDS)
            for name, t in cfg.get("probes", {}).items():
                if name in merged:
                    if "normal_max" in t and "critical_min" in t:
                        merged[name] = {"normal_max": float(t["normal_max"]), "critical_min": float(t["critical_min"])}
                    elif "normal_min" in t and "critical_min" in t:
                        merged[name] = {"normal_min": float(t["normal_min"]), "critical_min": float(t["critical_min"])}
            return merged
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass
    return dict(DEFAULT_THRESHOLDS)


def _classify(probe_name: str, value: float, thresholds: dict) -> str:
    t = thresholds[probe_name]
    if "positive" in PROBE_SIGNATURES.get(probe_name, {}):
        # 正向指标: 越高越好
        if value < t.get("critical_min", 0):
            return "critical"
        if value < t.get("normal_min", 0):
            return "warning"
        return "normal"
    else:
        # 反向指标: 越低越好
        if value > t.get("critical_min", 100):
            return "critical"
        if value > t.get("normal_max", 100):
            return "warning"
        return "normal"


def _ts_key(entry: dict) -> float:
    """时间戳归一化为 float epoch"""
    t = entry.get("timestamp", 0)
    if isinstance(t, (int, float)):
        return float(t)
    if isinstance(t, str):
        try:
            return float(t)
        except ValueError:
            return 0.0
    return 0.0


def _window(entries: list[dict], k: int) -> list[dict]:
    """取最近 k 条事件（按 timestamp 降序取尾部）"""
    if k <= 0 or len(entries) <= k:
        return entries
    return sorted(entries, key=_ts_key)[-k:]


def _normalize_event(entry: dict, source: str) -> dict | None:
    """将各源事件标准化为统一格式"""
    # 统一字段: event_type, timestamp, agent_id, metadata
    ev_type = entry.get("event_type") or entry.get("action") or entry.get("telemetry_type")
    ts = entry.get("timestamp") or entry.get("ingested_at")
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except Exception:
            ts = 0.0

    if not ev_type or not ts:
        return None

    agent_id = entry.get("agent_id") or entry.get("actor") or entry.get("source") or "unknown"
    metadata = entry.get("metadata") or entry.get("data") or entry.get("details") or {}

    return {
        "event_type": ev_type,
        "timestamp": float(ts),
        "agent_id": agent_id,
        "source": source,
        "metadata": metadata,
        "raw": entry,
    }


def sample() -> list[dict]:
    # 1. 加载所有数据源
    since_hours = int(os.environ.get("MAREF_PROBE_TIME_WINDOW_HOURS", "24"))

    audit = _load_entries(AUDIT_LOG)
    recursive = _load_entries(RECURSIVE_LOG)
    obs_events = _load_obs_events(since_hours)
    telemetry = _load_telemetry(since_hours)
    mcp_decisions = _load_mcp_decisions(since_hours)

    # 2. 标准化并合并
    all_normalized = []

    for src, entries in [
        ("audit", audit),
        ("recursive", recursive),
        ("obs", obs_events),
        ("telemetry", telemetry),
        ("mcp", mcp_decisions),
    ]:
        for e in entries:
            norm = _normalize_event(e, src)
            if norm:
                all_normalized.append(norm)

    # 3. 滑窗采样
    try:
        window_size = int(os.environ.get("MAREF_PROBE_WINDOW", str(DEFAULT_WINDOW)))
    except ValueError:
        window_size = DEFAULT_WINDOW

    windowed = _window(all_normalized, window_size)

    # 4. 统计各探针
    event_counts = Counter(e["event_type"] for e in windowed)
    agent_events = defaultdict(list)
    for e in windowed:
        agent_events[e["agent_id"]].append(e)

    total = len(windowed) or 1
    thresholds = _load_thresholds()
    now = time.time()

    readings = []

    # --- oscillation 探针 ---
    osc_events = PROBE_SIGNATURES["oscillation"]["source_events"]
    osc_count = sum(event_counts[ev] for ev in osc_events)
    osc_rate = osc_count / total * 100.0

    t = thresholds["oscillation"]
    readings.append({
        "probe_name": "oscillation",
        "severity": _classify("oscillation", osc_rate, thresholds),
        "value": round(osc_rate, 4),
        "threshold": t["critical_min"],
        "timestamp": now,
        "context_json": json.dumps({
            "source": "probe_sampler_v3",
            "semantics": "multi_source_rate_based_windowed",
            "unit": "percent_of_events",
            "window_size": window_size,
            "window_used": total,
            "matched_events": osc_count,
            "source_breakdown": {src: sum(1 for e in windowed if e["source"] == src) for src in set(e["source"] for e in windowed)},
            "normal_max": t["normal_max"],
            "critical_min": t["critical_min"],
        }, ensure_ascii=False),
    })

    # --- entropy 探针 ---
    ent_events = PROBE_SIGNATURES["entropy"]["source_events"]
    ent_count = sum(event_counts[ev] for ev in ent_events)
    ent_rate = ent_count / total * 100.0

    t = thresholds["entropy"]
    readings.append({
        "probe_name": "entropy",
        "severity": _classify("entropy", ent_rate, thresholds),
        "value": round(ent_rate, 4),
        "threshold": t["critical_min"],
        "timestamp": now,
        "context_json": json.dumps({
            "source": "probe_sampler_v3",
            "semantics": "multi_source_rate_based_windowed",
            "unit": "percent_of_events",
            "window_size": window_size,
            "window_used": total,
            "matched_events": ent_count,
            "normal_max": t["normal_max"],
            "critical_min": t["critical_min"],
        }, ensure_ascii=False),
    })

    # --- governance_health 探针 ---
    health_events = PROBE_SIGNATURES["governance_health"]["source_events"]
    tool_start = event_counts.get("tool_call_start", 0)
    tool_end = event_counts.get("tool_call_end", 0)
    tool_total = max(tool_start, tool_end, 1)
    governed = sum(event_counts.get(ev, 0) for ev in ["tool_call_end", "rule_matched", "policy_evaluated"])
    health_rate = governed / tool_total * 100.0

    t = thresholds["governance_health"]
    readings.append({
        "probe_name": "governance_health",
        "severity": _classify("governance_health", health_rate, thresholds),
        "value": round(health_rate, 4),
        "threshold": t.get("critical_min", 50.0),
        "timestamp": now,
        "context_json": json.dumps({
            "source": "probe_sampler_v3",
            "semantics": "governance_coverage_rate",
            "unit": "percent",
            "tool_calls_total": tool_total,
            "governed_calls": governed,
            "normal_min": t.get("normal_min", 80.0),
            "critical_min": t.get("critical_min", 50.0),
        }, ensure_ascii=False),
    })

    # --- agent_trust 探针 (从 coding_agent_status 或 MCP 决策推导) ---
    trust_scores = []
    for agent_id, evs in agent_events.items():
        # 简化: 基于该 agent 的拦截率反推信任分
        agent_tool_starts = sum(1 for e in evs if e["event_type"] == "tool_call_start")
        agent_intercepted = sum(1 for e in evs if e["event_type"] == "tool_call_intercepted")
        if agent_tool_starts > 0:
            intercept_rate = agent_intercepted / agent_tool_starts
            trust = max(0, 100 - intercept_rate * 100)
            trust_scores.append(trust)

    avg_trust = sum(trust_scores) / len(trust_scores) if trust_scores else 50.0

    t = thresholds["agent_trust"]
    readings.append({
        "probe_name": "agent_trust",
        "severity": _classify("agent_trust", avg_trust, thresholds),
        "value": round(avg_trust, 4),
        "threshold": t.get("critical_min", 40.0),
        "timestamp": now,
        "context_json": json.dumps({
            "source": "probe_sampler_v3",
            "semantics": "agent_trust_aggregate",
            "unit": "score_0_100",
            "agents_with_data": len(trust_scores),
            "normal_min": t.get("normal_min", 70.0),
            "critical_min": t.get("critical_min", 40.0),
        }, ensure_ascii=False),
    })

    return readings


def write_readings(readings: list[dict]) -> None:
    """写入 SQLite (兼容旧版) 和数据湖 Parquet (新版)"""
    # 1. SQLite (旧版兼容)
    conn = sqlite3.connect(str(PROBE_DB))
    cur = conn.cursor()
    for r in readings:
        cur.execute(
            "INSERT INTO probe_readings "
            "(probe_name, severity, value, threshold, timestamp, context_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (r["probe_name"], r["severity"], r["value"], r["threshold"], r["timestamp"], r["context_json"]),
        )
    conn.commit()
    conn.close()

    # 2. 数据湖 (新版) - 写入 curated/probe_readings 分区
    try:
        import duckdb
        lake_root = Path(os.environ.get("MAREF_GOVERNANCE_LAKE", "/Volumes/1TB-M2/maref-governance-lake"))
        curated_dir = lake_root / "curated" / "probe_readings"
        curated_dir.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        parquet_file = curated_dir / f"probe_readings_{date_str}.parquet"

        # 使用 DuckDB 写入 Parquet (支持分区追加)
        conn = duckdb.connect()
        conn.execute(f"""
            COPY (
                SELECT * FROM read_json_auto('{json.dumps(readings)}')
            ) TO '{parquet_file}' (FORMAT PARQUET, PARTITION_BY (probe_name))
        """)
        conn.close()
    except Exception as e:
        # 数据湖写入失败不阻断主流程
        print(f"⚠️ 数据湖写入失败 (非阻断): {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="MAREF 探针采样器 (P0-B v3 多数据源融合)")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    parser.add_argument("--sources", default="all", help="数据源: all,audit,obs,telemetry,mcp")
    args = parser.parse_args()

    print("=" * 60)
    print("探针采样器 (P0-B v3 多数据源融合)")
    print("=" * 60)
    print(f"审计日志: {AUDIT_LOG}")
    print(f"递归日志: {RECURSIVE_LOG}")
    print(f"ObsEvent:  ~/.maref/obs/")
    print(f"Telemetry: data/telemetry/")
    print(f"探针 DB:  {PROBE_DB}")
    print()

    readings = sample()
    print(f"\n采样结果:")
    for r in readings:
        print(f"  {r['probe_name']}: value={r['value']:.2f}, severity={r['severity']}, "
              f"threshold={r['threshold']:.0f}")

    if args.dry_run:
        print("\n[dry-run] 未写入")
        return 0

    write_readings(readings)
    print(f"\n✅ 已写入 {len(readings)} 条探针读数 (SQLite + 数据湖)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())