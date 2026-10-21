"""Calibrate silver labels against failure families and error classes."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from .cluster import anchor

NARROW_EXPECTATIONS: dict[str, set[str]] = {
    "permission": {"environment"},
    "not_found": {"environment", "dependency"},
    "timeout": {"tool", "environment"},
    "test_fail": {"logic", "dependency", "environment"},
    "assertion": {"logic"},
    "syntax": {"type"},
    "type": {"type", "logic"},
    "lint": {"lint"},
    "user_correction": {"prompt"},
    "governance_denial": {"tool", "prompt"},
    "hitl": {"tool", "prompt"},
    "network": {"environment", "tool"},
    "oom": {"environment"},
}


def labeled_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT e.id, e.runtime, e.error_class, e.tool, e.snippet, e.failure_sig,
               l.root_cause, l.fix_type, l.severity, l.reusable,
               l.agree_with_llm, l.labeled_by
        FROM episode e JOIN label l ON l.episode_id = e.id
        WHERE e.label_status = 'labeled'
        ORDER BY e.started_at
        """
    ).fetchall()


def family_stats(rows: list[sqlite3.Row], top: int = 20) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for row in rows:
        key = (
            str(row["error_class"] or "unknown"),
            anchor(str(row["error_class"] or "unknown"), str(row["snippet"] or "")),
        )
        groups.setdefault(key, []).append(row)
    stats = []
    for (error_class, family), members in groups.items():
        causes = Counter(str(row["root_cause"]) for row in members)
        dominant, count = causes.most_common(1)[0]
        stats.append(
            {
                "error_class": error_class,
                "family": family,
                "episodes": len(members),
                "purity": round(count / len(members), 2),
                "dominant": dominant,
                "causes": dict(causes),
                "mean_agreement": round(
                    sum(int(row["agree_with_llm"] or 0) for row in members) / len(members)
                ),
            }
        )
    stats.sort(key=lambda item: (-item["episodes"], -item["purity"]))
    return stats[:top]


def class_matrix(rows: list[sqlite3.Row]) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = {}
    for row in rows:
        error_class = str(row["error_class"] or "unknown")
        cause = str(row["root_cause"] or "unknown")
        matrix.setdefault(error_class, {})
        matrix[error_class][cause] = matrix[error_class].get(cause, 0) + 1
    return dict(sorted(matrix.items(), key=lambda item: -sum(item[1].values())))


def mismatches(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    found = []
    for row in rows:
        error_class = str(row["error_class"] or "")
        expected = NARROW_EXPECTATIONS.get(error_class)
        cause = str(row["root_cause"] or "")
        if expected and cause not in expected:
            found.append(
                {
                    "id": row["id"],
                    "error_class": error_class,
                    "root_cause": cause,
                    "expected": sorted(expected),
                    "agreement": row["agree_with_llm"],
                    "snippet": str(row["snippet"] or "")[:120],
                }
            )
    return found


def agreement_buckets(rows: list[sqlite3.Row]) -> dict[str, int]:
    buckets: Counter[str] = Counter()
    for row in rows:
        buckets[f"{int(row['agree_with_llm'] or 0)}%"] += 1
    return dict(sorted(buckets.items(), key=lambda item: -int(item[0].rstrip("%"))))


def report(conn: sqlite3.Connection, top: int = 20) -> dict[str, Any]:
    rows = labeled_rows(conn)
    data = {
        "labeled": len(rows),
        "families": family_stats(rows, top),
        "matrix": class_matrix(rows),
        "mismatches": mismatches(rows),
        "agreement_buckets": agreement_buckets(rows),
        "root_cause_dist": dict(Counter(str(row["root_cause"]) for row in rows).most_common()),
    }
    console = Console()
    console.print(f"[bold]Calibration[/bold] labeled={len(rows)}")
    if rows:
        console.print(
            "root causes: " + ", ".join(f"{k}={v}" for k, v in data["root_cause_dist"].items())
        )
        table = Table(title="Family purity")
        for column in ("class", "family", "n", "purity", "dominant", "agree%"):
            table.add_column(column)
        for item in data["families"]:
            table.add_row(
                item["error_class"],
                item["family"],
                str(item["episodes"]),
                str(item["purity"]),
                item["dominant"],
                str(item["mean_agreement"]),
            )
        console.print(table)
        if data["mismatches"]:
            console.print(f"[yellow]class/label mismatches: {len(data['mismatches'])}[/yellow]")
    return data


def write_markdown(data: dict[str, Any], path: Path) -> None:
    lines = [
        "# Label calibration",
        "",
        f"- labeled episodes: {data['labeled']}",
        f"- root causes: {json.dumps(data['root_cause_dist'], ensure_ascii=False)}",
        f"- agreement buckets: {json.dumps(data['agreement_buckets'], ensure_ascii=False)}",
        "",
        "## Family purity",
        "",
        "| class | family | n | purity | dominant | agree% |",
        "|---|---|---:|---:|---|---:|",
    ]
    for item in data["families"]:
        lines.append(
            f"| {item['error_class']} | {item['family']} | {item['episodes']} | "
            f"{item['purity']} | {item['dominant']} | {item['mean_agreement']} |"
        )
    lines += ["", "## Class × root cause", "", "| class | root causes |", "|---|---|"]
    for error_class, causes in data["matrix"].items():
        rendered = ", ".join(f"{cause}={count}" for cause, count in causes.items())
        lines.append(f"| {error_class} | {rendered} |")
    lines += ["", "## Mismatches", ""]
    if data["mismatches"]:
        lines += ["| id | class | label | expected | agree |", "|---|---|---|---|---:|"]
        for item in data["mismatches"]:
            lines.append(
                f"| `{item['id']}` | {item['error_class']} | {item['root_cause']} | "
                f"{','.join(item['expected'])} | {item['agreement']} |"
            )
    else:
        lines.append("none")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
