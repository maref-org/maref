"""Calibrate silver labels against failure families and error classes."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from .cluster import anchor

NARROW_EXPECTATIONS: dict[str, set[str]] = {
    "permission": {"environment", "tool"},
    "not_found": {"environment", "dependency", "tool", "logic"},
    "timeout": {"tool", "environment"},
    "test_fail": {"logic", "dependency", "environment"},
    "assertion": {"logic"},
    "syntax": {"type"},
    "type": {"type", "logic", "dependency"},
    "lint": {"lint"},
    "user_correction": {"prompt", "environment", "tool"},
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


def _wilson(count: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    p = count / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (round(max(0.0, centre - margin), 2), round(min(1.0, centre + margin), 2))


def family_stats(rows: list[sqlite3.Row], top: int = 20, min_n: int = 1) -> list[dict[str, Any]]:
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
        decided = [row for row in members if str(row["root_cause"] or "") not in ("", "unknown")]
        if decided:
            dominant, count = Counter(str(row["root_cause"]) for row in decided).most_common(1)[0]
            purity = round(count / len(decided), 2)
            low, high = _wilson(count, len(decided))
        else:
            dominant, count, purity, low, high = "unknown", 0, None, 0.0, 1.0
        stats.append(
            {
                "error_class": error_class,
                "family": family,
                "episodes": len(members),
                "decided": len(decided),
                "purity": purity,
                "purity_ci": [low, high],
                "dominant": dominant,
                "causes": dict(causes),
                "mean_agreement": round(
                    sum(int(row["agree_with_llm"] or 0) for row in members) / len(members)
                ),
                "reliable": len(decided) >= min_n,
            }
        )
    stats.sort(key=lambda item: (-item["episodes"], -(item["purity"] or 0)))
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
        if expected and cause not in ("", "unknown") and cause not in expected:
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


def abstentions(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    found = []
    for row in rows:
        error_class = str(row["error_class"] or "")
        expected = NARROW_EXPECTATIONS.get(error_class)
        if expected and str(row["root_cause"] or "") == "unknown":
            found.append(
                {
                    "id": row["id"],
                    "error_class": error_class,
                    "expected": sorted(expected),
                    "agreement": row["agree_with_llm"],
                }
            )
    return found


def agreement_buckets(rows: list[sqlite3.Row]) -> dict[str, int]:
    buckets: Counter[str] = Counter()
    for row in rows:
        buckets[f"{int(row['agree_with_llm'] or 0)}%"] += 1
    return dict(sorted(buckets.items(), key=lambda item: -int(item[0].rstrip("%"))))


def report(conn: sqlite3.Connection, top: int = 20, min_family: int = 5) -> dict[str, Any]:
    rows = labeled_rows(conn)
    all_families = family_stats(rows, top=10000, min_n=1)
    cross_families = {
        (str(row["error_class"]), str(row["anchor"]))
        for row in conn.execute(
            "SELECT error_class, anchor FROM family WHERE json_array_length(runtimes_json) >= 2"
        )
    }
    cross_labeled = sum(
        1
        for row in rows
        if (str(row["error_class"]), anchor(str(row["error_class"]), str(row["snippet"] or "")))
        in cross_families
    )
    data = {
        "labeled": len(rows),
        "min_family": min_family,
        "families": [item for item in all_families if item["decided"] >= min_family][:top],
        "low_n_families": sum(1 for item in all_families if item["decided"] < min_family),
        "cross_runtime_families": len(cross_families),
        "cross_runtime_labeled": cross_labeled,
        "matrix": class_matrix(rows),
        "mismatches": mismatches(rows),
        "abstentions": abstentions(rows),
        "agreement_buckets": agreement_buckets(rows),
        "root_cause_dist": dict(Counter(str(row["root_cause"]) for row in rows).most_common()),
    }
    console = Console()
    console.print(f"[bold]Calibration[/bold] labeled={len(rows)}")
    if rows:
        console.print(
            "root causes: " + ", ".join(f"{k}={v}" for k, v in data["root_cause_dist"].items())
        )
        table = Table(title=f"Family purity (decided n>={min_family})")
        for column in ("class", "family", "n", "decided", "purity", "dominant", "agree%"):
            table.add_column(column)
        for item in data["families"]:
            table.add_row(
                item["error_class"],
                item["family"],
                str(item["episodes"]),
                str(item["decided"]),
                "n/a" if item["purity"] is None else str(item["purity"]),
                item["dominant"],
                str(item["mean_agreement"]),
            )
        console.print(table)
        if data["low_n_families"]:
            console.print(
                f"[yellow]families with decided n<{min_family}: {data['low_n_families']}[/yellow]"
            )
        if data["mismatches"]:
            console.print(f"[yellow]class/label mismatches: {len(data['mismatches'])}[/yellow]")
        if data["abstentions"]:
            console.print(f"[cyan]class/label abstentions: {len(data['abstentions'])}[/cyan]")
    return data


def write_markdown(data: dict[str, Any], path: Path) -> None:
    lines = [
        "# Label calibration",
        "",
        f"- labeled episodes: {data['labeled']}",
        f"- family filter: decided n>={data['min_family']} "
        f"(low-n families: {data['low_n_families']})",
        f"- cross-runtime families: {data['cross_runtime_families']} "
        f"(labeled in cross families: {data['cross_runtime_labeled']})",
        f"- root causes: {json.dumps(data['root_cause_dist'], ensure_ascii=False)}",
        f"- agreement buckets: {json.dumps(data['agreement_buckets'], ensure_ascii=False)}",
        "",
        "## Family purity",
        "",
        "| class | family | n | decided | purity | 95% CI | dominant | agree% |",
        "|---|---|---:|---:|---:|---|---|---:|",
    ]
    for item in data["families"]:
        lines.append(
            f"| {item['error_class']} | {item['family']} | {item['episodes']} | "
            f"{item['decided']} | "
            f"{'n/a' if item['purity'] is None else item['purity']} | "
            f"{item['purity_ci'][0]}-{item['purity_ci'][1]} | "
            f"{item['dominant']} | {item['mean_agreement']} |"
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
    lines += ["", "## Abstentions", "", "| id | class | expected | agree |", "|---|---|---|---:|"]
    if data["abstentions"]:
        for item in data["abstentions"]:
            lines.append(
                f"| `{item['id']}` | {item['error_class']} | "
                f"{','.join(item['expected'])} | {item['agreement']} |"
            )
    else:
        lines.append("none")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
