"""Calibration batch: export pending episodes for silver labeling, then apply."""

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
        SELECT * FROM episode
        WHERE label_status = 'pending' AND TRIM(snippet) != ''
        ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                              WHEN 'medium' THEN 2 ELSE 3 END,
                 started_at DESC
        """
    ).fetchall()


def _family_key(row: Any) -> tuple[str, str]:
    error_class = str(row["error_class"] or "unknown")
    return (error_class, anchor(error_class, str(row["snippet"] or "")))


def _is_cross(row: Any, cross_sigs: set[str], cross_families: set[tuple[str, str]]) -> bool:
    return str(row["failure_sig"]) in cross_sigs or _family_key(row) in cross_families


def _diverse(group: list[Any], limit: int, taken: set[str]) -> list[Any]:
    picked: list[Any] = []
    seen: set[str] = set()
    for row in group:
        if len(picked) >= limit:
            break
        if row["id"] in taken:
            continue
        sig = str(row["failure_sig"])
        if sig in seen:
            continue
        seen.add(sig)
        picked.append(row)
    return picked


def stratified(
    rows: list[Any],
    limit: int,
    per_family: int = 5,
    cross_sigs: set[str] | None = None,
    cross_families: set[tuple[str, str]] | None = None,
) -> list[Any]:
    """Quota sample: cross-runtime families first, then >=per_family per family."""
    cross_sigs = cross_sigs or set()
    cross_families = cross_families or set()
    taken: set[str] = set()
    picked: list[Any] = []

    seen_cross: set[tuple[str, str]] = set()
    for row in rows:
        if len(picked) >= limit:
            break
        key = _family_key(row)
        if _is_cross(row, cross_sigs, cross_families) and key not in seen_cross:
            seen_cross.add(key)
            picked.append(row)
            taken.add(row["id"])

    buckets: dict[tuple[str, str], list[Any]] = {}
    for row in rows:
        if row["id"] in taken:
            continue
        buckets.setdefault(_family_key(row), []).append(row)

    for key, group in sorted(buckets.items(), key=lambda item: -len(item[1])):
        if len(picked) >= limit:
            break
        current = sum(1 for row in picked if _family_key(row) == key)
        need = min(per_family - current, limit - len(picked))
        if need <= 0:
            continue
        added = 0
        for row in _diverse(group, need, taken):
            picked.append(row)
            taken.add(row["id"])
            added += 1
        need = min(per_family - current - added, limit - len(picked))
        if need <= 0:
            continue
        for row in group:
            if need <= 0 or len(picked) >= limit:
                break
            if row["id"] in taken:
                continue
            picked.append(row)
            taken.add(row["id"])
            need -= 1

    for row in rows:
        if len(picked) >= limit:
            break
        if row["id"] not in taken:
            picked.append(row)
            taken.add(row["id"])
    return picked


def create_batch(
    conn: sqlite3.Connection,
    out: Path,
    limit: int = 100,
    notes: str = "",
    per_family: int = 5,
) -> dict[str, Any]:
    try:
        cross_sigs = {
            str(row["sig"])
            for row in conn.execute(
                "SELECT sig FROM signature WHERE json_array_length(runtimes_json) >= 2"
            )
        }
    except sqlite3.OperationalError:
        cross_sigs = set()
    try:
        cross_families = {
            (str(row["error_class"]), str(row["anchor"]))
            for row in conn.execute(
                "SELECT error_class, anchor FROM family WHERE json_array_length(runtimes_json) >= 2"
            )
        }
    except sqlite3.OperationalError:
        cross_families = set()
    items = stratified(
        _pending(conn),
        limit,
        per_family=per_family,
        cross_sigs=cross_sigs,
        cross_families=cross_families,
    )
    cross_ids = {row["id"] for row in items if _is_cross(row, cross_sigs, cross_families)}
    excluded_empty = int(
        conn.execute(
            "SELECT COUNT(*) AS n FROM episode"
            " WHERE label_status = 'pending' AND TRIM(snippet) = ''"
        ).fetchone()["n"]
    )
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
                "cross_runtime": row["id"] in cross_ids,
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
    _write_markdown(items, out.with_suffix(".md"), created_at, notes, cross_ids)
    return {
        "path": str(out),
        "markdown": str(out.with_suffix(".md")),
        "items": len(items),
        "cross_runtime": len(cross_ids),
        "excluded_empty": excluded_empty,
    }


def _write_markdown(
    items: list[sqlite3.Row],
    path: Path,
    created_at: float,
    notes: str,
    cross_ids: set[str] | None = None,
) -> None:
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
    cross_ids = cross_ids or set()
    for index, row in enumerate(items, start=1):
        snippet = (row["snippet"] or "(no snippet)")[:400]
        lines += [
            f"## {index}. `{row['id']}`",
            "",
            f"- runtime: {row['runtime']} / class: {row['error_class']} / tool: {row['tool']}",
            f"- severity: {row['severity']} / outcome: {row['outcome']}"
            f" / cross_runtime: {'yes' if row['id'] in cross_ids else 'no'}",
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
