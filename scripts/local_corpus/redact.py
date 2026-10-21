"""Redaction at ingest time.

Secrets and identifying paths are replaced before anything is written to the
corpus. The same rule set is reused by the export leak scanner.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field

_ENTROPY_CANDIDATE = re.compile(r"[A-Za-z0-9+/=_\-]{32,}")

_SIMPLE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private_key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    ("aws_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("openai_key", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b")),
    ("bearer", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{16,}")),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
    ),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("home_path", re.compile(r"/(?:Users|home)/[A-Za-z0-9._\-]+")),
    (
        "internal_path",
        re.compile(r"/(?:Volumes|private|var/folders)/[^\s\"'`]+"),
    ),
)

_MIN_ENTROPY = 3.5


def _shannon(text: str) -> float:
    if not text:
        return 0.0
    counts: dict[str, int] = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    total = len(text)
    return -sum((n / total) * math.log2(n / total) for n in counts.values())


_PATH_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".json", ".md", ".sh", ".yaml", ".yml", ".txt")


def _looks_random(token: str) -> bool:
    if not any(c.isdigit() for c in token) or not any(c.isalpha() for c in token):
        return False
    # File paths and dotted identifiers are not credentials.
    if "/" in token or "." in token or token.lower().endswith(_PATH_SUFFIXES):
        return False
    if _shannon(token) < _MIN_ENTROPY:
        return False
    # Pure hex digests are common (hashes); keep them, they are not credentials.
    return not re.fullmatch(r"[0-9a-fA-F]+", token)


@dataclass
class RedactResult:
    text: str
    count: int = 0
    rules: tuple[str, ...] = ()
    matched_hashes: list[str] = field(default_factory=list)


def redact(text: str) -> RedactResult:
    """Replace secrets with ``[REDACTED:<rule>]`` and report what matched."""
    if not text:
        return RedactResult(text="")

    out = text
    hits: list[str] = []
    hashes: list[str] = []

    for name, pattern in _SIMPLE_RULES:

        def _sub(match: re.Match[str], rule: str = name) -> str:
            hits.append(rule)
            hashes.append(hashlib.sha256(match.group(0).encode()).hexdigest()[:16])
            return f"[REDACTED:{rule}]"

        out = pattern.sub(_sub, out)

    def _entropy_sub(match: re.Match[str]) -> str:
        token = match.group(0)
        if not _looks_random(token):
            return token
        hits.append("high_entropy")
        hashes.append(hashlib.sha256(token.encode()).hexdigest()[:16])
        return "[REDACTED:high_entropy]"

    out = _ENTROPY_CANDIDATE.sub(_entropy_sub, out)
    return RedactResult(
        text=out,
        count=len(hits),
        rules=tuple(hits),
        matched_hashes=hashes,
    )


def find_leaks(text: str) -> list[str]:
    """Return the rule names that still fire on ``text`` (used by export gate)."""
    result = redact(text)
    return list(result.rules)
