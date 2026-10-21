"""Link raw events into failure episodes and update signature aggregates."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from .normalize import classify_evidence, error_signature, sha16

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
    conn: sqlite3.Connection,
    session_id: str,
    start_ts: float,
    tool: str,
    payload_hash: str,
    window: float,
) -> tuple[str, float | None, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT ts, kind, tool, error_class, payload_hash FROM event
        WHERE session_id = ? AND ts > ? AND ts <= ?
        ORDER BY ts LIMIT 500
        """,
        (session_id, start_ts, start_ts + window),
    ).fetchall()
    last_ts: float | None = None
    saw_edit = False
    tool_key = tool.lower()
    for row in rows:
        last_ts = float(row["ts"])
        row_tool = str(row["tool"] or "")
        if not row["error_class"] and (row["kind"] == "edit" or row_tool in EDIT_TOOLS):
            saw_edit = True
        if row_tool.lower() != tool_key or row["kind"] not in {"tool_call", "tool_result"}:
            continue
        if row["error_class"]:
            return "unknown", last_ts, {"type": "failure_persisted", "at": last_ts}
        same_input = bool(payload_hash) and str(row["payload_hash"] or "") == payload_hash
        if same_input and saw_edit:
            return "fixed", last_ts, {"type": "retry_after_edit", "at": last_ts}
        if same_input:
            return "retried", last_ts, {"type": "retry_success", "at": last_ts}
        if saw_edit:
            return "patched", last_ts, {"type": "edit_then_changed_input", "at": last_ts}
        return "unknown", last_ts, {"type": "different_input", "at": last_ts}
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


def link_episodes(conn: sqlite3.Connection, window: float = 1800.0) -> dict[str, int]:
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
        outcome, ended_at, fix = _find_fix(
            conn, session_id, ts, tool, str(row["payload_hash"] or ""), window
        )
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


PRESERVE_CLASSES = {"governance_denial", "hitl", "user_correction"}


def reclassify_episodes(
    conn: sqlite3.Connection, window: float = 1800.0, dry_run: bool = False
) -> dict[str, Any]:
    """Recompute class, signature and outcome from the current episode snippet."""
    rows = conn.execute(
        """
        SELECT ep.id, ep.session_id, ep.error_class AS old_class,
               ep.failure_sig AS old_sig, ep.outcome AS old_outcome,
               ep.label_status,
               ev.id AS event_id, ev.tool, ev.verdict, ev.payload_hash,
               ev.error_sig AS old_event_sig,
               ev.snippet, ev.ts
        FROM episode ep JOIN event ev ON ev.id = ep.failure_event_id
        """
    ).fetchall()
    changed_class = changed_sig = changed_outcome = 0
    affected_labeled: list[str] = []
    affected_review: list[str] = []
    for row in rows:
        old_class = str(row["old_class"] or "")
        snippet = str(row["snippet"] or "")
        new_class = old_class
        evidence = ""
        if snippet and old_class not in PRESERVE_CLASSES:
            evidence = classify_evidence(snippet)
            if evidence in FAILURE_CLASSES:
                new_class = evidence
        new_sig_text = error_signature(snippet) if evidence else str(row["old_event_sig"] or "")
        tool = str(row["tool"] or "")
        new_failure_sig = sha16(new_class, new_sig_text or tool)
        outcome, ended_at, fix = _find_fix(
            conn,
            str(row["session_id"]),
            float(row["ts"]),
            tool,
            str(row["payload_hash"] or ""),
            window,
        )
        class_changed = new_class != old_class
        sig_changed = new_failure_sig != str(row["old_sig"] or "")
        outcome_changed = outcome != str(row["old_outcome"] or "")
        changed_class += int(class_changed)
        changed_sig += int(sig_changed)
        changed_outcome += int(outcome_changed)
        if class_changed or sig_changed:
            if row["label_status"] == "labeled":
                affected_labeled.append(str(row["id"]))
            elif row["label_status"] == "needs_review":
                affected_review.append(str(row["id"]))
        if dry_run or not (class_changed or sig_changed or outcome_changed):
            continue
        conn.execute(
            "UPDATE event SET error_class=?, error_sig=? WHERE id=?",
            (new_class, new_sig_text, int(row["event_id"])),
        )
        conn.execute(
            """
            UPDATE episode SET error_class=?, failure_sig=?, severity=?,
                   ended_at=?, outcome=?, fix_json=?
            WHERE id=?
            """,
            (
                new_class,
                new_failure_sig,
                _severity(new_class, str(row["verdict"] or "")),
                ended_at,
                outcome,
                json.dumps(fix, ensure_ascii=False),
                str(row["id"]),
            ),
        )
    if not dry_run:
        conn.commit()
        relink_signatures(conn)
    return {
        "episodes": len(rows),
        "class_changed": changed_class,
        "signature_changed": changed_sig,
        "outcome_changed": changed_outcome,
        "affected_labeled": affected_labeled,
        "affected_review": affected_review,
        "dry_run": dry_run,
    }


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
