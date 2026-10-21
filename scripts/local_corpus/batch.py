"""Calibration batch: export pending episodes for human labeling, then apply."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .cluster import anchor
from .label import FIX_TYPES, ROOT_CAUSES, SEVERITIES, record_label

ROOT_CAUSE_VALUES = set(ROOT_CAUSES.values())
FIX_TYPE_VALUES = set(FIX_TYPES.values())
SEVERITY_VALUES = set(SEVERITIES.values())


def _pending(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM episode WHERE label_status = 'pending'
        ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                              WHEN 'medium' THEN 2 ELSE 3 END,
                 started_at DESC
        """
    ).fetchall()


def stratified(rows: list[sqlite3.Row], limit: int) -> list[sqlite3.Row]:
    """Round-robin across failure families, one episode per signature first."""
    buckets: dict[tuple[str, str], list[sqlite3.Row]] = {}
    seen: set[str] = set()
    overflow: list[sqlite3.Row] = []
    for row in rows:
        sig = str(row["failure_sig"])
        if sig in seen:
            overflow.append(row)
            continue
        seen.add(sig)
        key = (
            str(row["error_class"] or "unknown"),
            anchor(str(row["error_class"] or "unknown"), str(row["snippet"] or "")),
        )
        buckets.setdefault(key, []).append(row)
    ordered = sorted(buckets.values(), key=lambda group: -len(group))
    picked: list[sqlite3.Row] = []
    while ordered and len(picked) < limit:
        for group in list(ordered):
            if group and len(picked) < limit:
                picked.append(group.pop(0))
        ordered = [group for group in ordered if group]
    if len(picked) < limit:
        picked.extend(overflow[: limit - len(picked)])
    return picked


def create_batch(
    conn: sqlite3.Connection, out: Path, limit: int = 100, notes: str = ""
) -> dict[str, Any]:
    items = stratified(_pending(conn), limit)
    out.parent.mkdir(parents=True, exist_ok=True)
    created_at = time.time()
    with out.open("w", encoding="utf-8") as handle:
        for row in items:
            payload = {
                "id": row["id"],
                "runtime": row["runtime"],
                "error_class": row["error_class"],
                "tool": row["tool"],
                "severity": row["severity"],
                "outcome": row["outcome"],
                "started_at": row["started_at"],
                "failure_sig": row["failure_sig"],
                "snippet": row["snippet"],
                "fix": json.loads(row["fix_json"] or "{}"),
                "label": {
                    "root_cause": "",
                    "fix_type": "",
                    "severity": "",
                    "reusable": None,
                    "notes": "",
                },
            }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    _write_markdown(items, out.with_suffix(".md"), created_at, notes)
    return {"path": str(out), "markdown": str(out.with_suffix(".md")), "items": len(items)}


def _write_markdown(items: list[sqlite3.Row], path: Path, created_at: float, notes: str) -> None:
    lines = [
        "# Local corpus calibration batch",
        "",
        f"created_at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(created_at))}",
        f"items: {len(items)}",
    ]
    if notes:
        lines.append(f"notes: {notes}")
    lines += [
        "",
        "填写同目录 JSONL 的 `label` 字段后运行：",
        "`local-corpus label --from-file <batch>.jsonl`",
        "",
    ]
    for index, row in enumerate(items, start=1):
        snippet = (row["snippet"] or "(no snippet)")[:400]
        lines += [
            f"## {index}. `{row['id']}`",
            "",
            f"- runtime: {row['runtime']} / class: {row['error_class']} / tool: {row['tool']}",
            f"- severity: {row['severity']} / outcome: {row['outcome']}",
            f"- sig: `{row['failure_sig']}`",
            "",
            "```",
            snippet,
            "```",
            "",
            "- [ ] root_cause: ____  fix_type: ____  severity: ____  reusable: y/n",
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")


def apply_batch(conn: sqlite3.Connection, path: Path, labeled_by: str = "batch") -> dict[str, int]:
    applied = 0
    skipped = 0
    tag = f"batch:{path.name}"
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if not isinstance(item, dict) or "_meta" in item:
                continue
            label = item.get("label") or {}
            root_cause = str(label.get("root_cause") or "").strip().lower()
            fix_type = str(label.get("fix_type") or "").strip().lower()
            severity = str(label.get("severity") or "").strip().lower()
            reusable = label.get("reusable")
            if (
                root_cause not in ROOT_CAUSE_VALUES
                or fix_type not in FIX_TYPE_VALUES
                or severity not in SEVERITY_VALUES
                or not isinstance(reusable, bool)
            ):
                skipped += 1
                continue
            record_label(
                conn,
                str(item["id"]),
                root_cause=root_cause,
                fix_type=fix_type,
                severity=severity,
                reusable=reusable,
                notes=f"[{tag}] {str(label.get('notes') or '')}"[:500],
                labeled_by=labeled_by,
            )
            applied += 1
    return {"applied": applied, "skipped": skipped}
