"""Claude Code transcript adapter — reads ~/.claude/projects/**/*.jsonl.

The hook audit log only records governance decisions. Transcripts add tool
results and user corrections, which is what makes cross-runtime failure
matching meaningful.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

from ..normalize import (
    Event,
    classify_error,
    detect_output_failure,
    error_signature,
    evidence_snippet,
    is_user_correction,
    sha16,
)
from ..redact import redact
from .claude_code import _parse_ts

DEFAULT_ROOT = Path(os.environ.get("CLAUDE_PROJECTS", str(Path.home() / ".claude" / "projects")))

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "str_replace_editor", "apply_patch"}


def _block_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            elif block.get("type") == "image":
                parts.append("[image]")
    return "\n".join(parts)


def _result_text(record: dict[str, object], block: dict[str, object]) -> str:
    text = _block_text(block.get("content"))
    if text:
        return text
    raw = record.get("toolUseResult")
    if isinstance(raw, dict):
        return "\n".join(str(raw[key]) for key in ("stdout", "stderr") if raw.get(key))
    return ""


def inventory(root: Path | str | None = None) -> dict[str, object]:
    base = Path(root) if root else DEFAULT_ROOT
    files = sorted(base.rglob("*.jsonl")) if base.exists() else []
    total = 0
    newest = 0.0
    for path in files:
        try:
            stat = path.stat()
        except OSError:
            continue
        total += stat.st_size
        newest = max(newest, stat.st_mtime)
    return {
        "root": str(base),
        "exists": base.exists(),
        "files": len(files),
        "bytes": total,
        "newest_mtime": newest,
    }


class ClaudeTranscriptAdapter:
    source = "claude_transcript"

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root else DEFAULT_ROOT

    def iter_events(self, since: float, limit: int | None = None) -> Iterator[Event]:
        if not self.root.exists():
            return
        emitted = 0
        paths = sorted(self.root.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        for path in paths:
            tool_names: dict[str, str] = {}
            tool_hashes: dict[str, str] = {}
            session = path.stem
            try:
                handle = path.open("r", encoding="utf-8", errors="replace")
            except OSError:
                continue
            with handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(record, dict):
                        continue
                    ts = _parse_ts(record.get("timestamp"))
                    if ts <= 0 or ts < since:
                        continue
                    message = record.get("message")
                    if not isinstance(message, dict):
                        continue
                    content = message.get("content")
                    if not isinstance(content, list):
                        continue
                    session_id = str(record.get("sessionId") or session)
                    model = str(message.get("model") or "")
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type")
                        if btype == "tool_use":
                            tool = str(block.get("name") or "")
                            tool_id = str(block.get("id") or "")
                            tool_names[tool_id] = tool
                            payload = json.dumps(block.get("input") or {}, sort_keys=True)
                            payload_hash = sha16(payload)
                            tool_hashes[tool_id] = payload_hash
                            kind = "edit" if tool in EDIT_TOOLS else "tool_call"
                            event = Event(
                                source=self.source,
                                source_event_id=f"{session_id}:use:{tool_id}",
                                session_id=session_id,
                                agent_id="claude-code",
                                model=model,
                                ts=ts,
                                kind=kind,
                                tool=tool,
                                payload_hash=payload_hash,
                            )
                        elif btype == "tool_result":
                            tool_id = str(block.get("tool_use_id") or "")
                            tool = tool_names.get(tool_id, "")
                            text = _result_text(record, block)
                            is_error = bool(block.get("is_error"))
                            error_class = (
                                classify_error(text) if is_error else detect_output_failure(text)
                            )
                            redacted = redact(text)
                            event = Event(
                                source=self.source,
                                source_event_id=f"{session_id}:res:{tool_id}",
                                session_id=session_id,
                                agent_id="claude-code",
                                model=model,
                                ts=ts,
                                kind="error" if is_error else "tool_call",
                                tool=tool,
                                error_class=error_class,
                                error_sig=error_signature(text) if error_class else "",
                                payload_hash=tool_hashes.get(tool_id, ""),
                                snippet=evidence_snippet(redacted.text) if error_class else "",
                                redaction_count=redacted.count,
                            )
                        elif btype == "text":
                            text = str(block.get("text") or "")
                            if message.get("role") != "user" or not text.strip():
                                continue
                            if text.lstrip().startswith("<"):
                                continue
                            correction = is_user_correction(text)
                            redacted = redact(text)
                            event = Event(
                                source=self.source,
                                source_event_id=f"{session_id}:text:{record.get('uuid') or sha16(text)}",
                                session_id=session_id,
                                agent_id="claude-code",
                                model=model,
                                ts=ts,
                                kind="message",
                                error_class="user_correction" if correction else "",
                                error_sig=error_signature(text) if correction else "",
                                snippet=evidence_snippet(redacted.text) if correction else "",
                                redaction_count=redacted.count,
                            )
                        else:
                            continue
                        yield event
                        emitted += 1
                        if limit is not None and emitted >= limit:
                            return
