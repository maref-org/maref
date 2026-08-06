from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ClipboardContentType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE_LIST = "file_list"
    UNKNOWN = "unknown"


_SENSITIVE_PATTERNS = [
    "password",
    "secret",
    "key",
    "token",
    "credentials",
    "Bearer ",
    "sk-",
    "api-key",
    "authorization:",
]


@dataclass
class ClipboardEntry:
    content: str = ""
    content_type: ClipboardContentType = ClipboardContentType.TEXT
    timestamp: float = field(default_factory=time.time)
    source_app: str = ""
    byte_size: int = field(default=0)

    def __post_init__(self) -> None:
        if self.byte_size == 0 and self.content:
            self.byte_size = len(self.content.encode("utf-8"))

    @property
    def is_sensitive(self) -> bool:
        content_lower = self.content.lower()
        return any(pattern.lower() in content_lower for pattern in _SENSITIVE_PATTERNS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_type": self.content_type.value,
            "source_app": self.source_app,
            "byte_size": self.byte_size,
            "is_sensitive": self.is_sensitive,
        }


class ClipboardSafetyFilter:
    """Safety filter for clipboard operations in desktop agent context.

    Prevents accidental exposure of sensitive data through clipboard:
    - Detects API keys, passwords, tokens
    - Optionally scrubs sensitive content
    - Logs all clipboard access for audit
    """

    def __init__(self, scrub_sensitive: bool = True, max_content_size: int = 1_000_000) -> None:
        self.scrub_sensitive = scrub_sensitive
        self.max_content_size = max_content_size
        self._access_log: list[dict[str, Any]] = []

    @property
    def access_log(self) -> list[dict[str, Any]]:
        return list(self._access_log)

    def check_read(self, entry: ClipboardEntry) -> bool:
        self._log("read", entry)
        return True

    def check_write(self, entry: ClipboardEntry) -> tuple[bool, str]:
        if entry.byte_size > self.max_content_size:
            self._log("write_blocked", entry, reason="exceeds_max_size")
            return False, f"Content size {entry.byte_size} exceeds max {self.max_content_size}"

        if entry.is_sensitive and self.scrub_sensitive:
            self._log("write_scrubbed", entry, reason="sensitive_content_detected")
            return False, "Sensitive content detected and scrubbed"

        self._log("write", entry)
        return True, ""

    def detect_sensitive(self, text: str) -> list[str]:
        text_lower = text.lower()
        found: list[str] = []
        for pattern in _SENSITIVE_PATTERNS:
            if pattern.lower() in text_lower:
                found.append(pattern)
        return found

    def _log(self, action: str, entry: ClipboardEntry, reason: str = "") -> None:
        self._access_log.append(
            {
                "timestamp": time.time(),
                "action": action,
                "content_type": entry.content_type.value,
                "source_app": entry.source_app,
                "byte_size": entry.byte_size,
                "is_sensitive": entry.is_sensitive,
                "reason": reason,
            }
        )


class ClipboardController:
    """Safe clipboard read/write with MAREF safety filtering.

    All clipboard access goes through ClipboardSafetyFilter.
    Supports dry-run mode for safe testing.
    """

    def __init__(
        self,
        safety_filter: ClipboardSafetyFilter | None = None,
        dry_run: bool = True,
    ) -> None:
        self._filter = safety_filter or ClipboardSafetyFilter()
        self._dry_run = dry_run
        self._pyperclip_available = False
        try:
            import pyperclip  # noqa: F401

            self._pyperclip_available = True
        except ImportError:
            pass

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    @dry_run.setter
    def dry_run(self, value: bool) -> None:
        self._dry_run = value

    def read(self) -> ClipboardEntry:
        if self._dry_run:
            entry = ClipboardEntry(
                content="[dry_run clipboard content]",
                content_type=ClipboardContentType.TEXT,
                source_app="maref",
                byte_size=28,
            )
        elif self._pyperclip_available:
            import pyperclip

            content = pyperclip.paste()
            entry = ClipboardEntry(
                content=content,
                content_type=ClipboardContentType.TEXT,
                byte_size=len(content.encode("utf-8")),
            )
        else:
            entry = ClipboardEntry(
                content="",
                content_type=ClipboardContentType.UNKNOWN,
                byte_size=0,
            )
        self._filter.check_read(entry)
        return entry

    def write(self, text: str, source_app: str = "maref") -> bool:
        entry = ClipboardEntry(
            content=text,
            content_type=ClipboardContentType.TEXT,
            source_app=source_app,
            byte_size=len(text.encode("utf-8")),
        )
        allowed, reason = self._filter.check_write(entry)
        if not allowed:
            return False

        if not self._dry_run and self._pyperclip_available:
            import pyperclip

            pyperclip.copy(text)
        return True

    def clear(self) -> bool:
        if not self._dry_run and self._pyperclip_available:
            import pyperclip

            pyperclip.copy("")
        return True

    def get_access_log(self) -> list[dict[str, Any]]:
        return self._filter.access_log
