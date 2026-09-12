#!/usr/bin/env python3
"""校准状态观察 (L4 + 滑窗) — 追踪 probe_readings 累积与校准生效进度

用法:
    python3 scripts/calibration_status.py

输出: 样本计数 / 阈值门槛进度 / 当前阈值 / 近期值方差 / 预计达标时间
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone

from maref_config import PROBE_DB, config_path

MIN_SAMPLES = 24          # 与 probe_threshold_calibrate.py 一致
SAMPLES_PER_DAY = 96      # 30 分钟 × 2 条


def _read_config():
    path = config_path("probe_thresholds.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def main() -> None:
    print("=" * 60)
    print("校准状态观察 (L4)")
    print("=" * 60)

    conn = sqlite3.connect(str(PROBE_DB))
    cur = conn.cursor()

    total = cur.execute("SELECT COUNT(*) FROM probe_readings").fetchone()[0]
    by_probe = cur.execute(
        "SELECT probe_name, COUNT(*), MIN(value), AVG(value), MAX(value) "
        "FROM probe_readings GROUP BY probe_name"
    ).fetchall()
    recent = cur.execute(
        "SELECT probe_name, severity, value, timestamp FROM probe_readings "
        "ORDER BY id DESC LIMIT 6"
    ).fetchall()
    first_ts = cur.execute("SELECT MIN(timestamp) FROM probe_readings").fetchone()[0]
    conn.close()

    print(f"\n总样本: {total} / 门槛 {MIN_SAMPLES}")
    progress = min(100.0, total / MIN_SAMPLES * 100) if MIN_SAMPLES else 0
    bar = "█" * int(progress / 5) + "░" * (20 - int(progress / 5))
    print(f"进度:  [{bar}] {progress:.0f}%")

    if total >= MIN_SAMPLES:
        print("状态:  ✅ 已达门槛 — 下次 probe_threshold_calibrate 将数据驱动重校准")
    else:
        remaining = MIN_SAMPLES - total
        hours = remaining / (SAMPLES_PER_DAY / 24)
        print(f"状态:  ⏳ 待累积 {remaining} 条 (约 {hours:.1f} 小时 @30min采样)")

    print(f"\n--- 各探针统计 ---")
    for name, cnt, mn, avg, mx in by_probe:
        spread = (mx - mn) if mx is not None and mn is not None else 0
        print(f"  {name}: n={cnt}, min={mn:.2f}, avg={avg:.2f}, max={mx:.2f}, spread={spread:.2f}")

    print(f"\n--- 当前阈值 ---")
    cfg = _read_config()
    if cfg:
        print(f"  来源: {cfg.get('method', '?')} @ {cfg.get('calibrated_at', '?')}")
        for name, t in cfg.get("probes", {}).items():
            print(f"  {name}: normal≤{t.get('normal_max')}, critical>{t.get('critical_min')}")
    else:
        print("  无配置 (使用采样器默认阈值)")

    print(f"\n--- 最近 6 条读数 ---")
    for name, sev, val, ts in recent:
        t = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%m-%d %H:%M")
        print(f"  [{t}] {name}: {sev} ({val:.2f})")

    if first_ts:
        span_h = (time.time() - first_ts) / 3600
        print(f"\n采样跨度: {span_h:.1f} 小时")


if __name__ == "__main__":
    main()
