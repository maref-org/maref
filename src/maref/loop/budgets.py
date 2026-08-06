from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class TokenBudget:
    max_tokens: int
    _used: int = 0

    @property
    def used(self) -> int:
        return self._used

    @property
    def remaining(self) -> int:
        return max(0, self.max_tokens - self._used)

    @property
    def exhausted(self) -> bool:
        return self._used >= self.max_tokens

    def consume(self, tokens: int) -> bool:
        if self._used + tokens > self.max_tokens:
            self._used = self.max_tokens
            return False
        self._used += tokens
        return True

    def reset(self) -> None:
        self._used = 0

    def snapshot(self) -> dict[str, Any]:
        return {
            "max_tokens": self.max_tokens,
            "used": self._used,
            "remaining": self.remaining,
            "exhausted": self.exhausted,
        }


@dataclass
class TimeBudget:
    max_seconds: float
    _start: float = 0.0
    _elapsed: float = 0.0

    def start(self) -> None:
        self._start = time.time()

    @property
    def elapsed(self) -> float:
        if self._start > 0:
            return time.time() - self._start
        return self._elapsed

    @property
    def remaining(self) -> float:
        return max(0.0, self.max_seconds - self.elapsed)

    @property
    def exhausted(self) -> bool:
        return self.elapsed >= self.max_seconds

    def reset(self) -> None:
        self._start = 0.0
        self._elapsed = 0.0

    def snapshot(self) -> dict[str, Any]:
        return {
            "max_seconds": self.max_seconds,
            "elapsed": self.elapsed,
            "remaining": self.remaining,
            "exhausted": self.exhausted,
        }
