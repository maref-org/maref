"""Reports over the local corpus."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from rich.console import Console
from rich.table import Table

from . import cluster


def top_signatures(conn: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT sig, count, runtimes_json FROM signature ORDER BY count DESC LIMIT ?", (limit,)
    ).fetchall()
    return [
        {
            "sig": r["sig"],
            "count": int(r["count"]),
            "runtimes": json.loads(r["runtimes_json"] or "[]"),
        }
        for r in rows
    ]


def cross_runtime(conn: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT sig, count, runtimes_json FROM signature"
        " WHERE json_array_length(runtimes_json) >= 2 ORDER BY count DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "sig": r["sig"],
            "count": int(r["count"]),
            "runtimes": json.loads(r["runtimes_json"] or "[]"),
        }
        for r in rows
    ]


def coverage(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT label_status, COUNT(*) AS n FROM episode GROUP BY 1").fetchall()
    result = {str(r["label_status"]): int(r["n"]) for r in rows}
    total = sum(result.values())
    result["total"] = total
    labeled = result.get("labeled", 0)
    result["labeled_pct"] = int(round(labeled / total * 100)) if total else 0
    return result


def time_to_fix(conn: sqlite3.Connection) -> dict[str, float]:
    row = conn.execute(
        "SELECT COUNT(*) AS n, AVG((ended_at-started_at)/3600.0) AS avg_hours"
        " FROM episode WHERE outcome='fixed' AND ended_at IS NOT NULL"
    ).fetchone()
    return {"fixed": int(row["n"] or 0), "avg_hours": round(float(row["avg_hours"] or 0.0), 2)}


def calibration_samples(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT error_class, COUNT(*) AS n FROM episode GROUP BY error_class ORDER BY n DESC"
    ).fetchall()
    return [{"error_class": r["error_class"], "n": int(r["n"])} for r in rows]


def report(conn: sqlite3.Connection, top: int = 20) -> dict[str, Any]:
    data: dict[str, Any] = {
        "top_signatures": top_signatures(conn, top),
        "cross_runtime": cross_runtime(conn, top),
        "coverage": coverage(conn),
        "time_to_fix": time_to_fix(conn),
        "calibration_samples": calibration_samples(conn),
        "top_families": cluster.top_families(conn, top),
        "top_clusters": cluster.top_clusters(conn, top),
        "cross_runtime_clusters": cluster.cross_runtime_clusters(conn, top),
    }
    console = Console()
    console.print("[bold]Local corpus report[/bold]")
    console.print(
        f"episodes={data['coverage']['total']} labeled={data['coverage'].get('labeled', 0)} "
        f"({data['coverage']['labeled_pct']}%)  "
        f"fixed={data['time_to_fix']['fixed']} avg_fix_h={data['time_to_fix']['avg_hours']}"
    )

    table = Table(title="Top signatures")
    table.add_column("sig")
    table.add_column("count", justify="right")
    table.add_column("runtimes")
    for item in data["top_signatures"]:
        table.add_row(item["sig"], str(item["count"]), ",".join(item["runtimes"]))
    console.print(table)

    if data["top_families"]:
        table = Table(title="Top failure families")
        for column in ("family", "class", "sigs", "episodes", "runtimes"):
            table.add_column(column)
        for item in data["top_families"]:
            table.add_row(
                item["anchor"],
                item["error_class"],
                str(item["signatures"]),
                str(item["episodes"]),
                ",".join(item["runtimes"]),
            )
        console.print(table)

    if data["top_clusters"]:
        table = Table(title="Top clusters")
        for column in ("cluster", "class", "label", "episodes", "runtimes"):
            table.add_column(column)
        for item in data["top_clusters"]:
            table.add_row(
                item["id"],
                item["error_class"],
                item["label"],
                str(item["episodes"]),
                ",".join(item["runtimes"]),
            )
        console.print(table)

    if data["cross_runtime"]:
        console.print(
            f"[green]cross-runtime repeats: {len(data['cross_runtime'])}[/green]  "
            "(the core value evidence)"
        )
    else:
        console.print("[yellow]cross-runtime repeats: 0[/yellow]")
    return data
