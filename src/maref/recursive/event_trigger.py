from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class RelEvent:
    event_id: str
    source: Literal["git_hook", "fs_watch", "test_watcher"]
    timestamp: float
    payload: dict[str, Any] = field(default_factory=dict)
    priority: int = 3


class EventTrigger:
    def __init__(self, cooldown_seconds: int = 300) -> None:
        self._cooldown = cooldown_seconds
        self._last_trigger: float = 0.0
        self._debounce_timers: dict[str, float] = {}

    def on_event(self, event: RelEvent) -> bool:
        now = time.time()

        if now - self._last_trigger < self._cooldown:
            return False

        if event.source in self._debounce_timers:
            if now - self._debounce_timers[event.source] < 5.0:
                return False

        self._debounce_timers[event.source] = now
        return True

    def record_trigger(self) -> None:
        self._last_trigger = time.time()

    def create_event(
        self,
        source: Literal["git_hook", "fs_watch", "test_watcher"],
        payload: dict[str, Any] | None = None,
        priority: int = 3,
    ) -> RelEvent:
        return RelEvent(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            source=source,
            timestamp=time.time(),
            payload=payload or {},
            priority=priority,
        )

    def reset(self) -> None:
        self._last_trigger = 0.0
        self._debounce_timers.clear()

    @property
    def cooldown_seconds(self) -> int:
        return self._cooldown

    @property
    def last_trigger(self) -> float:
        return self._last_trigger
