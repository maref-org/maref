#!/usr/bin/env python3
"""审计日志健康检查 (Phase Alpha A1) — 诊断 OpenClaw 侧审计停滞根因"""
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

AUDIT_LOG = "/Volumes/1TB-M2/public/maref/governance_audit.jsonl"
RECURSIVE_LOG = "/Volumes/1TB-M2/public/maref/recursive_governance_audit.jsonl"
DB_PATH = "/Volumes/1TB-M2/public/maref/governance_observations.db"


def check_audit_health():
    now = datetime.now(timezone.utc)
    status = {"checked_at": now.isoformat(), "healthy": True, "issues": []}

    for name, path in [("governance_audit", AUDIT_LOG), ("recursive_governance_audit", RECURSIVE_LOG)]:
        if not os.path.exists(path):
            status["healthy"] = False
            status["issues"].append(f"{name}: FILE_MISSING")
            continue

        size_mb = os.path.getsize(path) / (1024 * 1024)
        line_count = sum(1 for _ in open(path))

        last_ts = None
        with open(path) as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    ts = entry.get("timestamp")
                    if ts and (last_ts is None or ts > last_ts):
                        last_ts = ts
                except json.JSONDecodeError:
                    pass

        hours_stale = 999
        if last_ts:
            try:
                last_dt = datetime.fromtimestamp(last_ts, tz=timezone.utc)
                hours_stale = (now - last_dt).total_seconds() / 3600
            except (OSError, ValueError, OverflowError):
                pass

        status[name] = {
            "size_mb": round(size_mb, 2),
            "line_count": line_count,
            "last_entry_ts": last_ts,
            "hours_stale": round(hours_stale, 1),
        }

        if hours_stale > 24:
            status["healthy"] = False
            status["issues"].append(f"{name}: STALE_{hours_stale:.0f}h (stalled >24h)")

    # 检查 DB
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT MAX(timestamp) FROM probe_readings")
        max_ts = c.fetchone()[0]
        conn.close()
        if max_ts:
            hours_stale = (now.timestamp() - max_ts) / 3600
            status["probe_db"] = {"last_reading_ts": max_ts, "hours_stale": round(hours_stale, 1)}
            if hours_stale > 24:
                status["healthy"] = False
                status["issues"].append(f"probe_db: STALE_{hours_stale:.0f}h")

    return status


def main():
    print("=" * 60)
    print("审计日志健康检查 (Phase Alpha A1)")
    print("=" * 60)

    status = check_audit_health()
    print(f"\n整体健康: {'✅ 正常' if status['healthy'] else '❌ 异常'}")

    for name in ["governance_audit", "recursive_governance_audit"]:
        if name in status:
            s = status[name]
            print(f"\n{name}:")
            print(f"  文件大小: {s['size_mb']}MB")
            print(f"  条目数: {s['line_count']}")
            print(f"  最后写入: {s['hours_stale']}h 前")

    if status.get("probe_db"):
        print(f"\nprobe_db: {status['probe_db']['hours_stale']}h 前")

    if status["issues"]:
        print(f"\n⚠️ 发现 {len(status['issues'])} 个问题:")
        for issue in status["issues"]:
            print(f"  - {issue}")

    output = "/Volumes/1TB-M2/public/maref/reports/audit_health_check.json"
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)
    print(f"\n报告已保存: {output}")


if __name__ == "__main__":
    main()