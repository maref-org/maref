"""Link raw events into failure episodes and update signature aggregates."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from .normalize import sha16

FAILURE_CLASSES = {
    "governance_denial",
    "hitl",
    "permission",
    "network",
    "timeout",
    "oom",
    "test_fail",
    "syntax",
    "not_found",
    "lint",
    "assertion",
    "type",
    "tool_error",
    "exception",
    "user_correction",
}

HIGH_CLASSES = {"governance_denial", "permission", "network", "timeout", "oom"}

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "str_replace_editor", "apply_patch"}


def _severity(error_class: str, verdict: str) -> str:
    if verdict.upper() == "DENY" or error_class in HIGH_CLASSES:
        return "high"
    if error_class in {"test_fail", "syntax", "not_found", "assertion", "type"}:
        return "medium"
    return "low"


def _candidates(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT e.* FROM event e
        WHERE (e.kind = 'error' OR e.error_class != '')
          AND NOT EXISTS (SELECT 1 FROM episode ep WHERE ep.failure_event_id = e.id)
        ORDER BY e.session_id, e.ts, e.id
        """
    ).fetchall()


def _find_fix(
    conn: sqlite3.Connection, session_id: str, start_ts: float, tool: str, window: float
) -> tuple[str, float | None, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT ts, kind, tool, error_class FROM event
        WHERE session_id = ? AND ts > ? AND ts <= ?
        ORDER BY ts LIMIT 500
        """,
        (session_id, start_ts, start_ts + window),
    ).fetchall()
    last_ts: float | None = None
    saw_edit = False
    retry_at: float | None = None
    for row in rows:
        last_ts = float(row["ts"])
        if not row["error_class"] and (row["kind"] == "edit" or row["tool"] in EDIT_TOOLS):
            saw_edit = True
        if (
            row["tool"] == tool
            and not row["error_class"]
            and row["kind"]
            in {
                "tool_call",
                "tool_result",
            }
        ):
            if saw_edit:
                return "fixed", last_ts, {"type": "retry_after_edit", "at": last_ts}
            if retry_at is None:
                retry_at = last_ts
    if retry_at is not None:
        return "retried", retry_at, {"type": "retry_success", "at": retry_at}
    if saw_edit:
        return "patched", last_ts, {"type": "edit_only", "at": last_ts}
    return "unknown", last_ts, {}


def _upsert_signature(
    conn: sqlite3.Connection,
    sig: str,
    ts: float,
    runtime: str,
    episode_id: str,
) -> None:
    row = conn.execute("SELECT * FROM signature WHERE sig = ?", (sig,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO signature(sig, first_seen, last_seen, count, runtimes_json, example_episode)"
            " VALUES(?, ?, ?, 1, ?, ?)",
            (sig, ts, ts, json.dumps([runtime]), episode_id),
        )
        return
    runtimes = set(json.loads(row["runtimes_json"] or "[]"))
    runtimes.add(runtime)
    conn.execute(
        "UPDATE signature SET last_seen=?, count=count+1, runtimes_json=?, example_episode=?"
        " WHERE sig=?",
        (
            max(ts, float(row["last_seen"])),
            json.dumps(sorted(runtimes)),
            row["example_episode"],
            sig,
        ),
    )


def link_episodes(conn: sqlite3.Connection, window: float = 7200.0) -> dict[str, int]:
    candidates = _candidates(conn)
    created = 0
    fixed = 0
    for row in candidates:
        error_class = str(row["error_class"] or "")
        if error_class not in FAILURE_CLASSES:
            continue
        tool = str(row["tool"] or "")
        runtime = str(row["source"] or "")
        session_id = str(row["session_id"])
        ts = float(row["ts"])
        outcome, ended_at, fix = _find_fix(conn, session_id, ts, tool, window)
        sig = sha16(error_class, str(row["error_sig"] or "") or tool)
        episode_id = sha16(session_id, str(row["id"]))
        versions = {"runtime": runtime}
        model = str(row["model"] or "")
        if model:
            versions["model"] = model
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO episode(
                id, runtime, agent_id, model, session_id, task_class,
                started_at, ended_at, failure_sig, failure_event_id,
                error_class, tool, severity, outcome, label_status,
                snippet, fix_json, versions_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                episode_id,
                runtime,
                str(row["agent_id"] or ""),
                model,
                session_id,
                runtime,
                ts,
                ended_at,
                sig,
                int(row["id"]),
                error_class,
                tool,
                _severity(error_class, str(row["verdict"] or "")),
                outcome,
                "pending",
                str(row["snippet"] or ""),
                json.dumps(fix, ensure_ascii=False),
                json.dumps(versions, ensure_ascii=False),
            ),
        )
        if cur.rowcount:
            created += 1
            if outcome == "fixed":
                fixed += 1
            _upsert_signature(conn, sig, ts, runtime, episode_id)
    conn.commit()
    return {"created": created, "fixed": fixed, "candidates": len(candidates)}


def relink_signatures(conn: sqlite3.Connection) -> int:
    """Rebuild the signature aggregate table from episodes (idempotent)."""
    conn.execute("DELETE FROM signature")
    rows = conn.execute(
        "SELECT failure_sig, COUNT(*) AS n, MIN(started_at) AS a, MAX(started_at) AS b FROM episode"
        " GROUP BY failure_sig"
    ).fetchall()
    for row in rows:
        runtimes = [
            r["runtime"]
            for r in conn.execute(
                "SELECT DISTINCT runtime FROM episode WHERE failure_sig=?", (row["failure_sig"],)
            )
        ]
        example = conn.execute(
            "SELECT id FROM episode WHERE failure_sig=? LIMIT 1", (row["failure_sig"],)
        ).fetchone()
        conn.execute(
            "INSERT INTO signature(sig, first_seen, last_seen, count, runtimes_json, example_episode)"
            " VALUES(?,?,?,?,?,?)",
            (
                row["failure_sig"],
                float(row["a"]),
                float(row["b"]),
                int(row["n"]),
                json.dumps(sorted(runtimes)),
                str(example["id"]) if example else "",
            ),
        )
    conn.commit()
    return len(rows)


def now() -> float:
    return time.time()
