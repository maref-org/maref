"""Salted SHA256 trunc16 hasher for privacy-safe event metadata."""

from __future__ import annotations

import hashlib
import os


class ObsHasher:
    """One-way salted hash for event metadata fields.

    Uses SHA256 with a per-session salt, truncated to 16 hex characters.
    The salt is generated once per session and persisted to disk so that
    events within the same session are consistently hashed, while the
    same input across different sessions produces different hashes.
    """

    def __init__(self, salt: str | None = None) -> None:
        self._salt: str = salt if salt is not None else os.urandom(8).hex()

    @property
    def salt(self) -> str:
        return self._salt

    def hash(self, value: str) -> str:
        """Return salted SHA256 trunc16 of *value*."""
        raw = hashlib.sha256(f"{self._salt}:{value}".encode()).hexdigest()
        return raw[:16]

    def maybe_hash(self, value: str | None, level: str = "standard") -> str | None:
        """Hash *value* or return None, depending on telemetry level."""
        if value is None:
            return None
        if level == "basic":
            return None
        return self.hash(value)
