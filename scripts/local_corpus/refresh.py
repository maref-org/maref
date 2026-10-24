"""Refresh episode evidence snippets from the source adapters."""

from __future__ import annotations

import sqlite3
from typing import Any

from .adapters.claude_code import ClaudeCodeAdapter
from .adapters.claude_transcript import ClaudeTranscriptAdapter
from .adapters.openclaw import OpenclawAdapter
from .adapters.opencode import OpencodeAdapter


def default_adapters() -> dict[str, Any]:
    return {
        "opencode": OpencodeAdapter(),
        "claude_transcript": ClaudeTranscriptAdapter(),
        "claude_code": ClaudeCodeAdapter(),
        "openclaw": OpenclawAdapter(),
    }


def refresh_snippets(
    conn: sqlite3.Connection,
    adapters: dict[str, Any] | None = None,
    since: float | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Refresh event and episode snippets without touching labels or classifications."""
    sources = adapters or default_adapters()
    rows = conn.execute(
        """
        SELECT ev.id AS event_id, ev.source, ev.source_event_id, ev.snippet AS old_snippet,
               ep.id AS episode_id, ep.label_status
        FROM event ev JOIN episode ep ON ep.failure_event_id = ev.id
        """
    ).fetchall()
    mapping: dict[tuple[str, str], sqlite3.Row] = {
        (str(row["source"]), str(row["source_event_id"])): row for row in rows
    }
    changed_episodes: set[str] = set()
    changed_labeled: set[str] = set()
    changed_review: set[str] = set()
    matched = changed = 0
    per_source: dict[str, dict[str, int]] = {}
    for source, adapter in sources.items():
        source_rows = [row for (src, _), row in mapping.items() if src == source]
        if not source_rows:
            continue
        start = since
        if start is None:
            row = conn.execute(
                "SELECT MIN(ts) AS ts FROM event WHERE source=?", (source,)
            ).fetchone()
            start = max(0.0, float(row["ts"] or 0.0) - 10.0) if row else 0.0
        source_matched = source_changed = 0
        for event in adapter.iter_events(start):
            row = mapping.get((source, str(event.source_event_id)))
            if row is None:
                continue
            source_matched += 1
            new_snippet = str(event.snippet or "")
            if new_snippet == str(row["old_snippet"] or ""):
                continue
            source_changed += 1
            changed_episodes.add(str(row["episode_id"]))
            if row["label_status"] == "labeled":
                changed_labeled.add(str(row["episode_id"]))
            elif row["label_status"] == "needs_review":
                changed_review.add(str(row["episode_id"]))
            if dry_run:
                continue
            conn.execute(
                "UPDATE event SET snippet=?, redaction_count=? WHERE id=?",
                (new_snippet, int(event.redaction_count), int(row["event_id"])),
            )
            conn.execute(
                "UPDATE episode SET snippet=? WHERE id=?",
                (new_snippet, str(row["episode_id"])),
            )
        matched += source_matched
        changed += source_changed
        per_source[source] = {"matched": source_matched, "changed": source_changed}
    if not dry_run:
        conn.commit()
    return {
        "matched": matched,
        "changed": changed,
        "changed_episodes": len(changed_episodes),
        "changed_labeled": sorted(changed_labeled),
        "changed_review": sorted(changed_review),
        "per_source": per_source,
        "dry_run": dry_run,
    }
