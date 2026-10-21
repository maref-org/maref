"""Canonical event model and error classification."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_ERROR_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("timeout", re.compile(r"timed?\s*out|timeout|ETIMEDOUT|TimeoutError", re.IGNORECASE)),
    (
        "permission",
        re.compile(
            r"permission denied|EACCES|operation not permitted|PermissionError", re.IGNORECASE
        ),
    ),
    (
        "not_found",
        re.compile(
            r"no such file|command not found|ModuleNotFoundError|ImportError|FileNotFoundError"
        ),
    ),
    ("syntax", re.compile(r"SyntaxError|IndentationError|unexpected token", re.IGNORECASE)),
    ("type", re.compile(r"\b(?:TypeError|AttributeError|ValueError|NameError|KeyError)\b")),
    ("assertion", re.compile(r"\bAssertionError\b|\bassert\b")),
    ("test_fail", re.compile(r"\b\d+\s+failed\b|\bFAILED\b|\bFAILURES\b")),
    ("lint", re.compile(r"\bE\d{3}\b|\bruff\b|\beslint\b|\bmypy\b")),
    (
        "network",
        re.compile(
            r"ConnectionError|URLError|ECONNREFUSED|name resolution|ENOTFOUND", re.IGNORECASE
        ),
    ),
    ("oom", re.compile(r"OutOfMemory|OOM|Killed", re.IGNORECASE)),
)

_OUTPUT_FAILURE: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "timeout",
        re.compile(r"\btimed out\b|command timed out|timeout after|ETIMEDOUT", re.IGNORECASE),
    ),
    ("permission", re.compile(r"permission denied|operation not permitted", re.IGNORECASE)),
    ("not_found", re.compile(r"no such file or directory|command not found", re.IGNORECASE)),
    ("test_fail", re.compile(r"\b\d+ failed\b|\bFAILURES\b|\bFAILED\b\s+\S+::")),
    ("syntax", re.compile(r"SyntaxError|IndentationError")),
    ("exception", re.compile(r"Traceback \(most recent call last\)")),
    ("network", re.compile(r"connection refused|could not resolve host", re.IGNORECASE)),
)
_EXIT_CODE = re.compile(r"exit (?:code|status)\s*[:=]?\s*([1-9]\d*)", re.IGNORECASE)

_FIX_PHRASES = re.compile(
    r"不对|还是报错|重新|重试|再试|仍然失败|still failing|still fails|try again|fix it",
    re.IGNORECASE,
)


def sha16(*parts: str) -> str:
    """Stable short hash used for event ids, payloads and failure signatures."""
    payload = "\x1f".join(parts).encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()[:16]


def detect_error(text: str) -> str:
    """Return a known error class, or ``""`` when the text looks successful."""
    if not text:
        return ""
    for name, pattern in _ERROR_PATTERNS:
        if pattern.search(text):
            return name
    return ""


def detect_output_failure(text: str) -> str:
    """Conservative failure detection for successfully-exited tool output."""
    if not text:
        return ""
    for name, pattern in _OUTPUT_FAILURE:
        if pattern.search(text):
            return name
    if _EXIT_CODE.search(text):
        return "tool_error"
    return ""


def classify_error(text: str) -> str:
    if not text:
        return ""
    line = _informative_line(text)
    return detect_error(line) or detect_error(text) or "tool_error"


_HEADER_LINE = re.compile(r"^(?:exit (?:code|status)\s*[:=]?\s*\d+|command)\s*$", re.IGNORECASE)


_EXCEPTION_LINE = re.compile(r"^(?:[A-Za-z_][\w.]*\.)?[A-Z][A-Za-z]*(?:Error|Exception|Warning)\b")


def _informative_line(text: str) -> str:
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if any("Traceback (most recent call last)" in line for line in lines):
        for line in reversed(lines):
            if _EXCEPTION_LINE.match(line):
                return line
        return lines[-1]
    candidate = ""
    for line in lines:
        if _HEADER_LINE.match(line):
            continue
        if detect_error(line):
            return line
        if not candidate:
            candidate = line
    return candidate or (lines[0] if lines else "")


def normalize_error_text(text: str) -> str:
    """Pick the most informative line, then strip volatile parts."""
    if not text:
        return ""
    first = _informative_line(text)[:200].lower()
    first = re.sub(r"/[^\s:]+", "<path>", first)
    first = re.sub(r"\b[0-9a-f]{8,}\b", "<hex>", first)
    first = re.sub(r"\b\d+\b", "<n>", first)
    return first


def error_signature(text: str) -> str:
    normalized = normalize_error_text(text)
    return sha16(normalized) if normalized else ""


def is_user_correction(text: str) -> bool:
    return bool(_FIX_PHRASES.search(text or ""))


@dataclass(frozen=True, slots=True)
class Event:
    source: str
    source_event_id: str
    session_id: str
    agent_id: str
    model: str
    ts: float
    kind: str
    tool: str = ""
    verdict: str = ""
    risk: float = 0.0
    error_class: str = ""
    error_sig: str = ""
    payload_hash: str = ""
    snippet: str = ""
    redaction_count: int = 0

    def as_row(self) -> tuple[object, ...]:
        return (
            self.source,
            self.source_event_id,
            self.session_id,
            self.agent_id,
            self.model,
            self.ts,
            self.kind,
            self.tool,
            self.verdict,
            self.risk,
            self.error_class,
            self.error_sig,
            self.payload_hash,
            self.snippet,
            self.redaction_count,
        )
