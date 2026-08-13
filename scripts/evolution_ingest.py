#!/usr/bin/env python3
"""evolution_ingest — 全域数据飞轮统一数据承接接口（Track B 侧）。

对齐补全分析 §4.1：三类幂等 ingest 入口，schema 与 openclaw nightly JSON 一致：

    ingest redblue → .evolution_vault/rounds.db（D/M/R/A/cb 向量，逐轮追加）
    ingest chaos   → .chaos-reports/（fault-mode / 恢复耗时，JSON 落盘）
    ingest immune  → .evolution_vault/gene_updates.jsonl（绕过案例 → 基因库候选）

设计要点:
    - 幂等: 按 date + run id 去重，重复 ingest 不产生脏数据
    - 本地优先: 一律落 .evolution_vault/ 等 gitignore 目录，不入 OSS 发布
    - schema 对齐: 字段名与 openclaw nightly_evolution.py 输出一致

用法:
    python scripts/evolution_ingest.py add --part redblue --json '<payload>'
    python scripts/evolution_ingest.py add --part chaos   --json '<payload>'
    python scripts/evolution_ingest.py add --part immune  --json '<payload>'
    python scripts/evolution_ingest.py list --part redblue [--tail 10]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = REPO_ROOT / ".evolution_vault"
CHAOS_DIR = REPO_ROOT / ".chaos-reports"
DB_PATH = VAULT_DIR / "evolution_rounds.db"
GENE_LOG = VAULT_DIR / "gene_updates.jsonl"

SCHEMA = {
    "redblue": ("run", ["rounds", "mean_score", "detection", "mitigation", "recovery", "adaptation", "passed", "cb_triggers"]),
    "chaos": ("run", ["test_suite", "passed", "failed", "total", "success", "duration_ms"]),
    "immune": ("update", ["gene", "source", "severity", "note"]),
}


def get_conn() -> sqlite3.Connection:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rounds (
            id TEXT PRIMARY KEY,
            part TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    return conn


def _run_id(part: str, payload: dict) -> str:
    run = payload.get("run") or payload.get("update") or {}
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    # 内容指纹作幂等键：同一 payload 只入库一次（跨进程/重复调度天然幂等）
    digest = hashlib.sha256(
        json.dumps(run, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"{date}-{part}-{digest}"


def cmd_add(part: str, payload_raw: str) -> int:
    if part not in SCHEMA:
        print(f"❌ 未知 part: {part}（可选: {'/'.join(SCHEMA)}）", file=sys.stderr)
        return 2
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}", file=sys.stderr)
        return 2

    rid = _run_id(part, payload)
    conn = get_conn()
    cur = conn.execute("SELECT 1 FROM rounds WHERE id = ?", (rid,))
    if cur.fetchone():
        print(f"  [ingest:{part}] 幂等跳过（已存在 {rid}）")
        conn.close()
        return 0

    conn.execute(
        "INSERT INTO rounds (id, part, payload, created_at) VALUES (?, ?, ?, ?)",
        (rid, part, json.dumps(payload, ensure_ascii=False),
         datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
    )
    conn.commit()
    conn.close()
    print(f"  [ingest:{part}] 已落盘 {rid}")

    # chaos/immune 额外镜像文件落盘（.chaos-reports / gene_updates.jsonl）
    if part == "chaos":
        CHAOS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        (CHAOS_DIR / f"ingested-{rid}-{stamp}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if part == "immune":
        VAULT_DIR.mkdir(parents=True, exist_ok=True)
        with GENE_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload | {"id": rid}, ensure_ascii=False) + "\n")
    return 0


def cmd_list(part: str, tail: int) -> int:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, part, created_at FROM rounds WHERE part = ? ORDER BY created_at DESC LIMIT ?",
        (part, tail),
    ).fetchall()
    if not rows:
        print(f"  [ingest:{part}] 暂无记录")
    for rid, p, ts in rows:
        print(f"  {ts}  {p:10s} {rid}")
    conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="全域数据飞轮统一 ingest 接口")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add")
    p_add.add_argument("--part", required=True, choices=list(SCHEMA))
    p_add.add_argument("--json", required=True, help="JSON payload（对齐 openclaw schema）")

    p_list = sub.add_parser("list")
    p_list.add_argument("--part", required=True, choices=list(SCHEMA))
    p_list.add_argument("--tail", type=int, default=10)

    args = parser.parse_args()
    if args.cmd == "add":
        return cmd_add(args.part, args.json)
    if args.cmd == "list":
        return cmd_list(args.part, args.tail)
    return 1


if __name__ == "__main__":
    sys.exit(main())
