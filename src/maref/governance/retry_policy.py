"""重试策略 — 指数退避 + jitter."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RetryDecision:
    should_retry: bool
    delay_seconds: float = 0.0
    attempt: int = 0
    reason: str = ""


class RetryPolicy(ABC):
    """重试策略基类."""

    @abstractmethod
    def decide(self, attempt: int, error: Exception | None = None) -> RetryDecision:
        ...


@dataclass
class ExponentialBackoff(RetryPolicy):
    """
    指数退避重试.

    delay = base_delay * (multiplier ** attempt) + jitter
    """
    base_delay: float = 1.0
    multiplier: float = 2.0
    max_delay: float = 60.0
    max_attempts: int = 5
    jitter_factor: float = 0.1  # +/- 10% jitter

    def decide(self, attempt: int, error: Exception | None = None) -> RetryDecision:
        if attempt >= self.max_attempts:
            return RetryDecision(
                should_retry=False,
                attempt=attempt,
                reason=f"max_attempts={self.max_attempts} exceeded",
            )
        delay = self.base_delay * (self.multiplier ** attempt)
        delay = min(delay, self.max_delay)
        jitter = random.uniform(-delay * self.jitter_factor, delay * self.jitter_factor)
        return RetryDecision(
            should_retry=True,
            delay_seconds=delay + jitter,
            attempt=attempt,
            reason=f"backoff attempt {attempt + 1}/{self.max_attempts}",
        )
