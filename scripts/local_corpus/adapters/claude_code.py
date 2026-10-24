"""Claude Code adapter — reads the governance hook audit JSONL."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from ..normalize import Event, detect_error, error_signature, evidence_snippet, sha16
from ..redact import redact

DEFAULT_LOG = Path(
    os.environ.get(
        "CLAUDE_AUDIT_LOG",
        str(Path.home() / ".claude" / "hooks" / "state" / "governance_audit.jsonl"),
    )
)

_SESSION_GAP = 1800.0


def _parse_ts(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _pseudo_session(project: str, ts: float) -> str:
    bucket = int(ts // 3600)
    return f"cc-{sha16(project or 'unknown', str(bucket))}"


class ClaudeCodeAdapter:
    source = "claude_code"

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_LOG

    def iter_events(self, since: float, limit: int | None = None) -> Iterator[Event]:
        if not self.path.exists():
            return
        emitted = 0
        last_ts: dict[str, float] = {}
        session_seq: dict[str, int] = {}
        with self.path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                ts = _parse_ts(row.get("timestamp"))
                if ts < since:
                    continue
                project = str(row.get("project_root") or "")
                previous = last_ts.get(project, 0.0)
                if ts - previous > _SESSION_GAP:
                    session_seq[project] = session_seq.get(project, 0) + 1
                last_ts[project] = ts
                session_id = f"{_pseudo_session(project, ts)}-{session_seq.get(project, 1)}"

                tool = str(row.get("tool_name") or "")
                verdict = str(row.get("verdict") or "")
                reason = str(row.get("reason") or "")
                args_hash = str(row.get("args_hash") or "")
                signature = str(row.get("hmac") or "")
                error_class = ""
                if verdict.upper() in {"DENY", "HITL"}:
                    error_class = "governance_denial" if verdict.upper() == "DENY" else "hitl"
                else:
                    error_class = detect_error(reason)

                redacted = redact(reason)
                yield Event(
                    source=self.source,
                    source_event_id=sha16(
                        str(self.path), str(ts), tool, args_hash, signature, str(line_no)
                    ),
                    session_id=session_id,
                    agent_id=str(row.get("agent_id") or ""),
                    model="",
                    ts=ts,
                    kind="tool_call",
                    tool=tool,
                    verdict=verdict,
                    risk=float(row.get("risk_score") or 0.0),
                    error_class=error_class,
                    error_sig=error_signature(reason) if reason else "",
                    payload_hash=args_hash,
                    snippet=evidence_snippet(redacted.text) if reason else "",
                    redaction_count=redacted.count,
                )
                emitted += 1
                if limit is not None and emitted >= limit:
                    return


def inventory(path: Path | str | None = None) -> dict[str, object]:
    target = Path(path) if path else DEFAULT_LOG
    if not target.exists():
        return {"path": str(target), "exists": False, "lines": 0, "bytes": 0}
    return {
        "path": str(target),
        "exists": True,
        "lines": sum(1 for _ in target.open("rb")),
        "bytes": target.stat().st_size,
        "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(target.stat().st_mtime)),
    }
