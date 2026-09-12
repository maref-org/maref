#!/usr/bin/env python3
"""探针采样器 (P0-B) — 从运行时审计日志派生 probe_readings

背景
----
probe_readings 表的历史写入者在两个仓库中均已不存在（孤表）：
- sidecar 的 ObservationCollector 是 mock 且无持久化
- 没有任何脚本引用 probe_readings
因此置信度计算（confidence_realtime.py）失去数据源。

本脚本为 MVP 重建：从运行时审计日志派生出可解释的健康探针读数。

采样语义 (v2, 率基 + 滑窗)
--------------------------
历史 probe_readings 的写入者已不存在，无法忠实还原其语义。本采样器采用
**率基 (rate-based)** 语义——把事件占比作为探针值，天然可比且不随日志规模漂移：

- oscillation 探针 (状态振荡信号)
    value = 不稳定事件占比 % = (oscillation_intervention + force_stabilize
            + auto_transition) / 窗口内事件数 × 100
- entropy 探针 (混沌/异常信号)
    value = 异常事件占比 % = anomaly_detected / 窗口内事件数 × 100

**滑窗**：取最近 N 条事件（默认 500，`MAREF_PROBE_WINDOW` 覆盖）而非全量日志。
全量日志静止时值恒定 → 校准样本无方差；滑窗使值随事件流变化。

severity 分级使用采样器本地阈值 (不读取陈旧的 probe_thresholds.json，
后者属于已孤立的旧度量)。缺省阈值见 DEFAULT_THRESHOLDS，可经环境变量覆盖。

用法
----
    python3 scripts/probe_sampler.py            # 采样一次并写入
    python3 scripts/probe_sampler.py --dry-run  # 只打印不写入
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from collections import Counter

from maref_config import (
    AUDIT_LOG,
    RECURSIVE_AUDIT_LOG as RECURSIVE_LOG,
    PROBE_DB,
    config_path,
)

# 采样器本地阈值 (率基 滑窗 %, 可后续校准)
DEFAULT_THRESHOLDS = {
    "oscillation": {"normal_max": 30.0, "critical_min": 60.0},
    "entropy": {"normal_max": 10.0, "critical_min": 25.0},
}

_OSCILLATION_ACTIONS = {"oscillation_intervention", "force_stabilize", "auto_transition"}
_ENTROPY_EVENTS = {"anomaly_detected"}


def _load_entries(path) -> list[dict]:
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


def _load_thresholds() -> dict:
    """阈值解析优先级: env(MAREF_PROBE_THRESHOLDS) > config(校准产物) > 默认。

    闭环: probe_threshold_calibrate.py 写 configs/probe_thresholds.json，
    采样器读取之，实现"采样→校准→再采样"闭环。
    """
    env = os.environ.get("MAREF_PROBE_THRESHOLDS")
    if env:
        try:
            cfg = json.loads(env)
            merged = dict(DEFAULT_THRESHOLDS)
            for name, t in cfg.items():
                if name in merged and "normal_max" in t and "critical_min" in t:
                    merged[name] = {"normal_max": t["normal_max"], "critical_min": t["critical_min"]}
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
                if name in merged and "normal_max" in t and "critical_min" in t:
                    merged[name] = {
                        "normal_max": float(t["normal_max"]),
                        "critical_min": float(t["critical_min"]),
                    }
            return merged
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass
    return dict(DEFAULT_THRESHOLDS)


def _classify(value: float, thresholds: dict) -> str:
    if value > thresholds["critical_min"]:
        return "critical"
    if value > thresholds["normal_max"]:
        return "warning"
    return "normal"


DEFAULT_WINDOW = 500  # 滑窗大小: 最近 N 条事件


def _ts_key(entry: dict) -> float:
    """时间戳归一化为 float epoch（兼容数值与数字字符串）。"""
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
    """取最近 k 条事件（按 timestamp 降序取尾部）。k<=0 或不足则返回全部。

    滑窗使探针值随事件流变化（全量日志静止时值恒定 → 校准样本无方差）。
    """
    if k <= 0 or len(entries) <= k:
        return entries
    return sorted(entries, key=_ts_key)[-k:]


def sample() -> list[dict]:
    audit = _load_entries(AUDIT_LOG)
    recursive = _load_entries(RECURSIVE_LOG)

    try:
        window_size = int(os.environ.get("MAREF_PROBE_WINDOW", str(DEFAULT_WINDOW)))
    except ValueError:
        window_size = DEFAULT_WINDOW

    combined = _window(audit + recursive, window_size)

    action_counts = Counter(e.get("action", "") for e in combined)
    event_counts = Counter(e.get("event_type", "") for e in combined)

    total = len(combined) or 1
    oscillation_rate = sum(action_counts[a] for a in _OSCILLATION_ACTIONS) / total * 100.0
    entropy_rate = sum(event_counts[t] for t in _ENTROPY_EVENTS) / total * 100.0

    thresholds = _load_thresholds()
    now = time.time()

    readings = []
    for probe_name, value in (("oscillation", oscillation_rate), ("entropy", entropy_rate)):
        t = thresholds[probe_name]
        readings.append({
            "probe_name": probe_name,
            "severity": _classify(value, t),
            "value": round(value, 4),
            "threshold": t["critical_min"],
            "timestamp": now,
            "context_json": json.dumps({
                "source": "probe_sampler",
                "semantics": "rate_based_v2_windowed",
                "unit": "percent_of_events",
                "window_size": window_size,
                "window_used": total,
                "normal_max": t["normal_max"],
                "critical_min": t["critical_min"],
                "audit_entries": len(audit),
                "recursive_entries": len(recursive),
            }, ensure_ascii=False),
        })
    return readings


def write_readings(readings: list[dict]) -> None:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="MAREF 探针采样器 (P0-B)")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    args = parser.parse_args()

    print("=" * 60)
    print("探针采样器 (P0-B)")
    print("=" * 60)
    print(f"审计日志: {AUDIT_LOG}")
    print(f"递归日志: {RECURSIVE_LOG}")
    print(f"探针 DB:  {PROBE_DB}")

    readings = sample()
    print(f"\n采样结果:")
    for r in readings:
        print(f"  {r['probe_name']}: value={r['value']:.0f}, severity={r['severity']}, "
              f"threshold={r['threshold']:.0f}")

    if args.dry_run:
        print("\n[dry-run] 未写入")
        return

    write_readings(readings)
    print(f"\n✅ 已写入 {len(readings)} 条探针读数")


if __name__ == "__main__":
    main()