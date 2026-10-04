#!/usr/bin/env python3
"""探针观测库合并 (T2-3) — REPO 遗留历史库 → PROBE_DB（RUNTIME 优先库）。

背景: T0-2 三级解析使 PROBE_DB 指向 RUNTIME_DIR 下的库; openclaw 侧进程
先行创建了空库, 历史 18 万行读数留在 REPO_DIR 遗留库被绕过, 导致
confidence/calibrate 读到错误数据源。本脚本幂等合并 (语义去重,
id 由目标库自增重排), 可重复执行。

幂等键: (probe_name, timestamp, value) — 同源采样不会出现同三元组的不同行。
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from maref_config import PROBE_DB, REPO_DIR, report_path

LEGACY_DB = REPO_DIR / "governance_observations.db"
DST_DB = PROBE_DB

DST_SCHEMA = ["probe_name", "severity", "value", "threshold", "timestamp", "context_json"]


def _open_ro(path: Path):
    if not path.exists():
        raise FileNotFoundError(path)
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def merge() -> dict:
    if not LEGACY_DB.exists():
        return {"status": "skipped", "reason": "legacy db 不存在", "merged": 0}
    if LEGACY_DB.resolve() == DST_DB.resolve():
        return {"status": "skipped", "reason": "src == dst (PROBE_DB 即遗留库)", "merged": 0}

    src = _open_ro(LEGACY_DB)
    dst = sqlite3.connect(DST_DB)
    try:
        src_n = src.execute("SELECT COUNT(*) FROM probe_readings").fetchone()[0]
        dst_n = dst.execute("SELECT COUNT(*) FROM probe_readings").fetchone()[0]
        dst.execute(f"ATTACH DATABASE '{LEGACY_DB}' AS legacy")

        # 语义去重插入: 目标库无同 (probe_name, timestamp, value) 才插
        cur = dst.execute(
            f"""
            INSERT INTO probe_readings ({', '.join(DST_SCHEMA)})
            SELECT {', '.join(DST_SCHEMA)} FROM legacy.probe_readings l
            WHERE NOT EXISTS (
                SELECT 1 FROM main.probe_readings d
                WHERE d.probe_name = l.probe_name
                  AND d.timestamp = l.timestamp
                  AND d.value = l.value
            )
            """,
        )
        merged = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        if merged == 0:
            # ATTACH 方式在部分构建不可用时的回退: 逐行批插
            rows = src.execute(
                f"SELECT {', '.join(DST_SCHEMA)} FROM probe_readings"
            ).fetchall()
            existing = {
                (r[0], r[1], r[2])
                for r in dst.execute(
                    "SELECT probe_name, timestamp, value FROM probe_readings"
                )
            }
            batch = [
                r for r in rows
                if (r[0], r[4], r[2]) not in existing
            ]
            if batch:
                dst.executemany(
                    f"INSERT INTO probe_readings ({', '.join(DST_SCHEMA)}) "
                    f"VALUES ({', '.join('?' * len(DST_SCHEMA))})",
                    batch,
                )
                merged = len(batch)
        dst.commit()

        final_n = dst.execute("SELECT COUNT(*) FROM probe_readings").fetchone()[0]
        report = {
            "merged_at": datetime.now(timezone.utc).isoformat(),
            "legacy_db": str(LEGACY_DB),
            "target_db": str(DST_DB),
            "legacy_rows": src_n,
            "target_rows_before": dst_n,
            "merged": merged,
            "target_rows_after": final_n,
            "status": "ok",
        }
    finally:
        src.close()
        dst.close()

    out = str(report_path("probe_db_merge_report.json"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return report


def main() -> int:
    print("=" * 60)
    print("探针观测库合并 (T2-3) — 遗留库 → PROBE_DB")
    print("=" * 60)
    try:
        r = merge()
    except FileNotFoundError as e:
        print(f"⚠️ 跳过: {e}")
        return 0
    print(f"  状态: {r.get('status')}")
    if r.get("status") == "ok":
        print(f"  遗留库: {r['legacy_rows']} 行 ({r['legacy_db']})")
        print(f"  目标库: {r['target_rows_before']} → {r['target_rows_after']} 行")
        print(f"  本次合并: {r['merged']} 行")
    elif r.get("reason"):
        print(f"  原因: {r['reason']}")
    print(f"  目标库: {DST_DB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
