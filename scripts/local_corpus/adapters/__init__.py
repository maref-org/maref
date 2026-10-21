"""Runtime adapters that normalize external logs into :class:`Event` rows."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from ..normalize import Event


class Adapter(Protocol):
    """Contract for a runtime log adapter."""

    source: str

    def iter_events(self, since: float, limit: int | None = None) -> Iterator[Event]:
        """Yield events with ``ts > since``, newest-last, capped by ``limit``."""


__all__ = ["Adapter", "Event"]
