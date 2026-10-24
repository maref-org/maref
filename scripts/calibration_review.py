#!/usr/bin/env python3
"""校准复核 (24h 观察) — 对比基线快照与当前状态

用法:
    python3 scripts/calibration_review.py            # 用最新基线复核
    python3 scripts/calibration_review.py --capture  # 捕获新基线

复核维度: 样本累积 / 方差变化 / 阈值是否被数据驱动重设 / 置信度迁移
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
import time
from datetime import datetime, timezone

from maref_config import PROBE_DB, config_path, report_path

BASELINE_DIR = report_path("calibration-baseline").parent / "calibration-baseline"


def _current() -> dict:
    conn = sqlite3.connect(str(PROBE_DB))
    c = conn.cursor()
    snap = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "unix": time.time(),
        "total_samples": c.execute("SELECT COUNT(*) FROM probe_readings").fetchone()[0],
        "per_probe": {},
    }
    for name, cnt, mn, avg, mx in c.execute(
        "SELECT probe_name, COUNT(*), MIN(value), AVG(value), MAX(value) "
        "FROM probe_readings GROUP BY probe_name"
    ):
        snap["per_probe"][name] = {"n": cnt, "min": round(mn, 2), "avg": round(avg, 2), "max": round(mx, 2)}
    conn.close()
    cfg_path = config_path("probe_thresholds.json")
    if os.path.exists(cfg_path):
        with open(cfg_path) as f:
            cfg = json.load(f)
        snap["thresholds"] = cfg.get("probes")
        snap["threshold_method"] = cfg.get("method")
    rp = report_path("confidence_audit.json")
    if os.path.exists(rp):
        with open(rp) as f:
            snap["confidence"] = json.load(f).get("confidence_30d")
    return snap


def _latest_baseline() -> dict | None:
    files = sorted(glob.glob(str(BASELINE_DIR / "baseline-*.json")))
    if not files:
        return None
    with open(files[-1]) as f:
        return json.load(f)


def capture() -> None:
    snap = _current()
    os.makedirs(BASELINE_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    path = BASELINE_DIR / f"baseline-{stamp}.json"
    with open(path, "w") as f:
        json.dump(snap, f, indent=2, ensure_ascii=False)
    print(f"基线已捕获: {path}")
    print(f"  样本 {snap['total_samples']}, 置信度 {snap.get('confidence')}")


def review() -> None:
    baseline = _latest_baseline()
    if not baseline:
        print("⚠️ 无基线快照，请先运行 --capture")
        return

    cur = _current()
    elapsed_h = (cur["unix"] - baseline["unix"]) / 3600

    print("=" * 60)
    print("校准复核报告")
    print("=" * 60)
    print(f"\n基线: {baseline['captured_at']} ({elapsed_h:.1f}h 前)")
    print(f"当前: {cur['captured_at']}")

    print(f"\n--- 样本累积 ---")
    print(f"  总样本: {baseline['total_samples']} → {cur['total_samples']} "
          f"(+{cur['total_samples'] - baseline['total_samples']})")

    print(f"\n--- 各探针方差 ---")
    for name in sorted(set(baseline.get("per_probe", {})) | set(cur.get("per_probe", {}))):
        b = baseline.get("per_probe", {}).get(name, {})
        v = cur.get("per_probe", {}).get(name, {})
        b_spread = (b.get("max", 0) - b.get("min", 0)) if b else 0
        v_spread = (v.get("max", 0) - v.get("min", 0)) if v else 0
        print(f"  {name}: n {b.get('n','-')}→{v.get('n','-')}, "
              f"spread {b_spread:.2f}→{v_spread:.2f}, avg {b.get('avg','-')}→{v.get('avg','-')}")

    print(f"\n--- 阈值变化 ---")
    b_th = baseline.get("thresholds", {})
    v_th = cur.get("thresholds", {})
    b_method = baseline.get("threshold_method", "?")
    v_method = cur.get("threshold_method", "?")
    print(f"  方法: {b_method} → {v_method}")
    for name in sorted(set(b_th) | set(v_th)):
        bt = b_th.get(name, {})
        vt = v_th.get(name, {})
        changed = bt != vt
        flag = " ← 已重校准" if changed else ""
        print(f"  {name}: {bt} → {vt}{flag}")

    print(f"\n--- 置信度 ---")
    print(f"  {baseline.get('confidence')} → {cur.get('confidence')}")

    # 判定
    print(f"\n--- 判定 ---")
    samples_ok = cur["total_samples"] >= 24
    recalibrated = v_method != "provisional_windowed"
    has_variance = any(
        (cur.get("per_probe", {}).get(n, {}).get("max", 0) - cur.get("per_probe", {}).get(n, {}).get("min", 0)) > 0
        for n in cur.get("per_probe", {})
    )
    print(f"  样本达标 (≥24): {'✅' if samples_ok else '❌'} ({cur['total_samples']})")
    print(f"  数据驱动重校准: {'✅' if recalibrated else '⏳ 仍为临时阈值'}")
    print(f"  滑窗方差: {'✅' if has_variance else '❌'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="校准复核")
    parser.add_argument("--capture", action="store_true", help="捕获新基线")
    args = parser.parse_args()
    if args.capture:
        capture()
    else:
        review()


if __name__ == "__main__":
    main()
