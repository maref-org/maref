"""opencode adapter — reads the opencode SQLite database read-only."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from ..normalize import (
    Event,
    classify_error,
    detect_output_failure,
    error_signature,
    is_user_correction,
    normalize_error_text,
    sha16,
)
from ..redact import redact

DEFAULT_DB = Path(
    os.environ.get(
        "OPENCODE_DB",
        str(Path.home() / ".local" / "share" / "opencode" / "opencode.db"),
    )
)

_QUERY = """
SELECT m.id AS mid, m.session_id AS session_id, m.time_created AS mts,
       m.data AS mdata, p.id AS pid, p.time_created AS pts, p.data AS pdata
FROM message m
LEFT JOIN part p ON p.message_id = m.id
WHERE m.time_created >= ?
ORDER BY m.time_created, p.time_created, p.id
"""


def _loads(value: object) -> dict[str, object]:
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _as_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


class OpencodeAdapter:
    source = "opencode"

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_DB

    def iter_events(self, since: float, limit: int | None = None) -> Iterator[Event]:
        if not self.path.exists():
            return
        conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=30)
        conn.row_factory = sqlite3.Row
        emitted = 0
        try:
            cursor = conn.execute(_QUERY, (int(since * 1000),))
            for row in cursor:
                message = _loads(row["mdata"])
                model = message.get("model") if isinstance(message.get("model"), dict) else {}
                provider = str((model or {}).get("providerID") or "")
                model_id = str((model or {}).get("modelID") or "")
                role = str(message.get("role") or "")
                agent = str(message.get("agent") or role or "")
                mts = _as_float(row["mts"]) / 1000.0
                part = _loads(row["pdata"])
                pts = _as_float(row["pts"]) / 1000.0 if row["pts"] else mts
                ts = pts or mts
                if ts <= 0.0:
                    continue
                part_id = str(row["pid"] or f"{row['mid']}:msg")
                ptype = str(part.get("type") or "")

                event: Event | None = None
                if ptype == "tool" and isinstance(part.get("state"), dict):
                    state = part["state"]
                    if not isinstance(state, dict):
                        state = {}
                    tool = str(part.get("tool") or "")
                    status = str(state.get("status") or "")
                    output = str(state.get("output") or "")
                    error = str(state.get("error") or "")
                    text = error or output
                    if status == "error":
                        error_class = classify_error(error)
                    else:
                        error_class = detect_output_failure(output)
                    kind = "tool_call"
                    if status == "error" or error_class:
                        kind = "error"
                        error_class = error_class or "tool_error"
                    redacted = redact(text)
                    event = Event(
                        source=self.source,
                        source_event_id=part_id,
                        session_id=str(row["session_id"]),
                        agent_id=agent,
                        model=f"{provider}/{model_id}".strip("/"),
                        ts=ts,
                        kind=kind,
                        tool=tool,
                        error_class=error_class,
                        error_sig=error_signature(text) if error_class else "",
                        payload_hash=sha16(json.dumps(state.get("input") or {}, sort_keys=True)),
                        snippet=redacted.text.splitlines()[0][:200] if redacted.text else "",
                        redaction_count=redacted.count,
                    )
                elif ptype == "text" and role == "user":
                    text = str(part.get("text") or "")
                    if is_user_correction(text):
                        event = Event(
                            source=self.source,
                            source_event_id=part_id,
                            session_id=str(row["session_id"]),
                            agent_id="user",
                            model=f"{provider}/{model_id}".strip("/"),
                            ts=ts,
                            kind="message",
                            error_class="user_correction",
                            error_sig=sha16(normalize_error_text(text)),
                            payload_hash=sha16(text),
                        )
                elif ptype == "patch":
                    event = Event(
                        source=self.source,
                        source_event_id=part_id,
                        session_id=str(row["session_id"]),
                        agent_id=agent,
                        model=f"{provider}/{model_id}".strip("/"),
                        ts=ts,
                        kind="edit",
                        tool="patch",
                        payload_hash=sha16(str(part.get("hash") or part_id)),
                    )

                if event is not None:
                    yield event
                    emitted += 1
                    if limit is not None and emitted >= limit:
                        return
        finally:
            conn.close()


def inventory(path: Path | str | None = None) -> dict[str, object]:
    target = Path(path) if path else DEFAULT_DB
    if not target.exists():
        return {"path": str(target), "exists": False, "sessions": 0, "messages": 0, "parts": 0}
    conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True, timeout=30)
    try:

        def count(table: str) -> int:
            row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            return int(row[0]) if row else 0

        return {
            "path": str(target),
            "exists": True,
            "bytes": target.stat().st_size,
            "sessions": count("session"),
            "messages": count("message"),
            "parts": count("part"),
        }
    finally:
        conn.close()
