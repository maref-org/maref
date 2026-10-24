"""Interactive labeling queue for failure episodes."""

from __future__ import annotations

import sqlite3
import time

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

ROOT_CAUSES = {
    "1": "lint",
    "2": "type",
    "3": "dependency",
    "4": "environment",
    "5": "prompt",
    "6": "tool",
    "7": "logic",
    "8": "other",
    "9": "unknown",
}
FIX_TYPES = {"1": "code", "2": "config", "3": "prompt", "4": "retry", "5": "none"}
SEVERITIES = {"c": "critical", "h": "high", "m": "medium", "l": "low"}


def pending_count(conn: sqlite3.Connection, severity: str | None = None) -> int:
    sql = "SELECT COUNT(*) AS n FROM episode WHERE label_status='pending'"
    args: tuple[object, ...] = ()
    if severity:
        sql += " AND severity=?"
        args = (severity,)
    row = conn.execute(sql, args).fetchone()
    return int(row["n"]) if row else 0


def next_pending(conn: sqlite3.Connection, severity: str | None = None) -> sqlite3.Row | None:
    sql = "SELECT * FROM episode WHERE label_status='pending'"
    args: tuple[object, ...] = ()
    if severity:
        sql += " AND severity=?"
        args = (severity,)
    sql += " ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, started_at"
    return conn.execute(sql + " LIMIT 1", args).fetchone()


def record_label(
    conn: sqlite3.Connection,
    episode_id: str,
    root_cause: str,
    fix_type: str,
    severity: str,
    reusable: bool,
    notes: str = "",
    labeled_by: str = "local",
) -> None:
    conn.execute(
        """
        INSERT INTO label(episode_id, root_cause, fix_type, severity, reusable, notes,
                          labeled_by, labeled_at)
        VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(episode_id) DO UPDATE SET
            root_cause=excluded.root_cause, fix_type=excluded.fix_type,
            severity=excluded.severity, reusable=excluded.reusable,
            notes=excluded.notes, labeled_by=excluded.labeled_by,
            labeled_at=excluded.labeled_at
        """,
        (episode_id, root_cause, fix_type, severity, int(reusable), notes, labeled_by, time.time()),
    )
    conn.execute(
        "UPDATE episode SET label_status='labeled', severity=? WHERE id=?", (severity, episode_id)
    )
    conn.commit()


def skip(conn: sqlite3.Connection, episode_id: str) -> None:
    conn.execute("UPDATE episode SET label_status='skipped' WHERE id=?", (episode_id,))
    conn.commit()


def run_interactive(conn: sqlite3.Connection, limit: int = 20, severity: str | None = None) -> int:
    console = Console()
    if pending_count(conn, severity) == 0:
        console.print("[yellow]no pending episodes[/yellow]")
        return 0
    labeled = 0
    for index in range(1, limit + 1):
        row = next_pending(conn, severity)
        if row is None:
            break
        console.print(
            Panel(
                f"[bold]{index}/{limit}[/bold]  runtime={row['runtime']}  "
                f"agent={row['agent_id']}  model={row['model']}\n"
                f"error={row['error_class']}  tool={row['tool']}  "
                f"severity={row['severity']}  outcome={row['outcome']}\n"
                f"sig={row['failure_sig']}\n"
                f"snippet: {(row['snippet'] or '')[:200]}",
                title=str(row["id"]),
            )
        )
        console.print(
            "root cause: 1 lint 2 type 3 dep 4 env 5 prompt 6 tool 7 logic 8 other 9 unknown"
        )
        console.print("fix type:   1 code 2 config 3 prompt 4 retry 5 none")
        console.print("severity:   c/h/m/l    reusable: y/n    s=skip q=quit")

        answer = Prompt.ask("root cause", default="9").strip().lower()
        if answer == "q":
            break
        if answer == "s":
            skip(conn, str(row["id"]))
            continue
        root_cause = ROOT_CAUSES.get(answer, "unknown")
        fix_type = FIX_TYPES.get(Prompt.ask("fix type", default="1").strip().lower(), "none")
        sev = SEVERITIES.get(
            Prompt.ask("severity", default=str(row["severity"])[:1]).strip().lower(), "medium"
        )
        reusable = Prompt.ask("reusable (y/n)", default="y").strip().lower().startswith("y")
        notes = Prompt.ask("notes", default="").strip()
        record_label(conn, str(row["id"]), root_cause, fix_type, sev, reusable, notes=notes[:500])
        labeled += 1
    console.print(f"[green]labeled {labeled} episode(s)[/green]")
    return labeled
