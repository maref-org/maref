"""CLI entry point for the local governance corpus factory."""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from rich.console import Console

from . import analyze, batch, cluster, db
from . import label as label_mod
from .adapters.claude_code import ClaudeCodeAdapter
from .adapters.claude_code import inventory as claude_inventory
from .adapters.claude_transcript import ClaudeTranscriptAdapter
from .adapters.claude_transcript import inventory as transcript_inventory
from .adapters.openclaw import OpenclawAdapter
from .adapters.opencode import OpencodeAdapter
from .adapters.opencode import inventory as opencode_inventory
from .export import export_attestations
from .link import link_episodes, relink_signatures

INSERT_EVENT = """
INSERT OR IGNORE INTO event(
    source, source_event_id, session_id, agent_id, model, ts, kind, tool,
    verdict, risk, error_class, error_sig, payload_hash, snippet, redaction_count
) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""

SOURCES = ("claude_code", "claude_transcript", "opencode", "openclaw")


def _adapter(name: str) -> Any:
    if name == "claude_code":
        return ClaudeCodeAdapter()
    if name == "claude_transcript":
        return ClaudeTranscriptAdapter()
    if name == "opencode":
        return OpencodeAdapter()
    if name == "openclaw":
        return OpenclawAdapter()
    raise SystemExit(f"unknown source: {name}")


def cmd_init(_: argparse.Namespace) -> int:
    root = db.ensure_dirs()
    conn = db.connect()
    try:
        db.init_db(conn)
    finally:
        conn.close()
    Console().print(f"[green]initialized[/green] {root} (db={db.db_path()})")
    return 0


def cmd_probe(_: argparse.Namespace) -> int:
    console = Console()
    for name, info in (
        ("claude_code", claude_inventory()),
        ("claude_transcript", transcript_inventory()),
        ("opencode", opencode_inventory()),
        ("openclaw", OpenclawAdapter().probe()),
    ):
        console.print(f"[bold]{name}[/bold] {json.dumps(info, ensure_ascii=False)[:800]}")
    return 0


def _backfill_one(
    conn: sqlite3.Connection, name: str, since: float, limit: int | None
) -> dict[str, Any]:
    adapter = _adapter(name)
    run_id = db.start_run(conn, name)
    rows_in = 0
    rows_new = 0
    max_ts = since
    try:
        for event in adapter.iter_events(since, limit):
            rows_in += 1
            cur = conn.execute(INSERT_EVENT, event.as_row())
            if cur.rowcount:
                rows_new += 1
            max_ts = max(max_ts, event.ts)
            if rows_in % 500 == 0:
                conn.commit()
        conn.commit()
        db.set_meta(conn, f"cursor:{name}", str(max_ts))
        db.finish_run(conn, run_id, rows_in, rows_new)
    except Exception as exc:  # noqa: BLE001 - surfaced in the run table
        db.finish_run(conn, run_id, rows_in, rows_new, status="error", error=str(exc)[:500])
        raise
    return {"source": name, "rows_in": rows_in, "rows_new": rows_new, "cursor": max_ts}


def cmd_backfill(args: argparse.Namespace) -> int:
    conn = db.connect()
    try:
        db.init_db(conn)
        results = []
        for name in args.source or SOURCES:
            cursor = db.get_meta(conn, f"cursor:{name}")
            since = float(cursor) if cursor else time.time() - args.days * 86400
            results.append(_backfill_one(conn, name, since, args.limit))
    finally:
        conn.close()
    Console().print(json.dumps(results, ensure_ascii=False))
    return 0


def cmd_link(_: argparse.Namespace) -> int:
    conn = db.connect()
    try:
        result = link_episodes(conn)
        relink_signatures(conn)
        counts = db.table_counts(conn)
    finally:
        conn.close()
    Console().print(json.dumps({**result, **counts}, ensure_ascii=False))
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    conn = db.connect()
    try:
        out = (
            Path(args.out)
            if args.out
            else db.data_dir() / "exports" / f"batch-{time.strftime('%Y%m%d')}.jsonl"
        )
        result = batch.create_batch(conn, out, args.limit, args.notes)
    finally:
        conn.close()
    Console().print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_label(args: argparse.Namespace) -> int:
    conn = db.connect()
    try:
        if args.from_file:
            result = batch.apply_batch(conn, Path(args.from_file))
            Console().print(json.dumps(result, ensure_ascii=False))
            return 0
        if args.non_interactive:
            Console().print(
                json.dumps(
                    {"pending": label_mod.pending_count(conn, args.severity)},
                    ensure_ascii=False,
                )
            )
            return 0
        label_mod.run_interactive(conn, args.limit, args.severity)
        return 0
    finally:
        conn.close()


def cmd_cluster(args: argparse.Namespace) -> int:
    conn = db.connect()
    try:
        db.init_db(conn)
        result = cluster.build_clusters(conn, args.threshold)
    finally:
        conn.close()
    Console().print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    conn = db.connect()
    try:
        result = analyze.report(conn, args.top)
    finally:
        conn.close()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    conn = db.connect()
    try:
        out = Path(args.out) if args.out else db.data_dir() / "exports" / "attestation_v1.jsonl"
        result = export_attestations(conn, out)
    finally:
        conn.close()
    Console().print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_stats(_: argparse.Namespace) -> int:
    conn = db.connect()
    try:
        counts = db.table_counts(conn)
        runs = [
            dict(row)
            for row in conn.execute(
                "SELECT source, started_at, rows_in, rows_new, status FROM run"
                " ORDER BY id DESC LIMIT 5"
            )
        ]
    finally:
        conn.close()
    Console().print(json.dumps({"counts": counts, "runs": runs}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="local-corpus")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)
    sub.add_parser("probe").set_defaults(func=cmd_probe)

    p_backfill = sub.add_parser("backfill")
    p_backfill.add_argument("--source", action="append", choices=SOURCES)
    p_backfill.add_argument("--days", type=int, default=90)
    p_backfill.add_argument("--limit", type=int, default=None)
    p_backfill.set_defaults(func=cmd_backfill)

    sub.add_parser("link").set_defaults(func=cmd_link)
    sub.add_parser("sync").set_defaults(func=cmd_backfill, source=None, days=7, limit=None)

    p_label = sub.add_parser("label")
    p_label.add_argument("--limit", type=int, default=20)
    p_label.add_argument("--severity", choices=("critical", "high", "medium", "low"))
    p_label.add_argument("--non-interactive", action="store_true")
    p_label.add_argument("--from-file", help="apply labels filled in a batch JSONL")
    p_label.set_defaults(func=cmd_label)

    p_batch = sub.add_parser("batch")
    p_batch.add_argument("--out")
    p_batch.add_argument("--limit", type=int, default=100)
    p_batch.add_argument("--notes", default="")
    p_batch.set_defaults(func=cmd_batch)

    p_cluster = sub.add_parser("cluster")
    p_cluster.add_argument("--threshold", type=float, default=0.55)
    p_cluster.set_defaults(func=cmd_cluster)

    p_report = sub.add_parser("report")
    p_report.add_argument("--top", type=int, default=20)
    p_report.add_argument("--json", action="store_true")
    p_report.set_defaults(func=cmd_report)

    p_export = sub.add_parser("export")
    p_export.add_argument("--out")
    p_export.set_defaults(func=cmd_export)

    sub.add_parser("stats").set_defaults(func=cmd_stats)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
