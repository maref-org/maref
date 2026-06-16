"""
MAREF Fault Recovery System

Handles errors gracefully during continuous autoresearch.
Implements retry, degrade, skip, and alert strategies.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RecoveryResult:
    """Result of a fault recovery attempt."""

    success: bool
    result: Any = None
    error: str = ""
    strategy_used: str = ""
    attempts: int = 0


class FaultRecovery:
    """
    Fault recovery system for continuous autoresearch.

    Recovery hierarchy:
    1. Retry (transient errors)
    2. Degrade (reduce complexity)
    3. Skip (record and continue)
    4. Alert (escalate to human)
    """

    def __init__(
        self,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        alert_threshold: int = 5,
    ) -> None:
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._alert_threshold = alert_threshold
        self._consecutive_failures = 0
        self._failure_log: list[dict[str, Any]] = []

    async def run_with_recovery(
        self,
        experiment_fn: Callable[[], Coroutine[Any, Any, Any]],
        degrade_fn: Callable[[], Coroutine[Any, Any, Any]] | None = None,
    ) -> RecoveryResult:
        """
        Run an experiment with full fault recovery.

        Args:
            experiment_fn: The experiment to run
            degrade_fn: Simplified version to run if main fails

        Returns:
            RecoveryResult with outcome details
        """
        # Strategy 1: Retry with backoff
        for attempt in range(self._max_retries):
            try:
                result = await experiment_fn()
                self._consecutive_failures = 0
                return RecoveryResult(
                    success=True,
                    result=result,
                    strategy_used="retry",
                    attempts=attempt + 1,
                )
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt < self._max_retries - 1:
                    await self._backoff(attempt)
                else:
                    last_error = str(e)

        # Strategy 2: Degrade
        if degrade_fn is not None:
            try:
                result = await degrade_fn()
                self._consecutive_failures = 0
                return RecoveryResult(
                    success=True,
                    result=result,
                    strategy_used="degrade",
                    attempts=self._max_retries + 1,
                )
            except Exception as e:
                logger.warning(f"Degraded experiment also failed: {e}")

        # Strategy 3: Skip and log
        self._consecutive_failures += 1
        self._log_failure(last_error, experiment_fn.__name__)

        # Strategy 4: Alert if threshold reached
        if self._consecutive_failures >= self._alert_threshold:
            self._alert_human()

        return RecoveryResult(
            success=False,
            error=last_error,
            strategy_used="skip",
            attempts=self._max_retries + (1 if degrade_fn else 0),
        )

    async def _backoff(self, attempt: int) -> None:
        """Exponential backoff between retries."""
        delay = self._backoff_base * (2**attempt)
        logger.info(f"Backing off for {delay}s before retry...")
        await asyncio.sleep(delay)

    def _log_failure(self, error: str, experiment_name: str) -> None:
        """Log failure details for later analysis."""
        self._failure_log.append(
            {
                "timestamp": time.time(),
                "experiment": experiment_name,
                "error": error,
                "consecutive_failures": self._consecutive_failures,
            }
        )

    def _alert_human(self) -> None:
        """Alert human operator of persistent failures."""
        logger.error(
            f"ALERT: {self._consecutive_failures} consecutive failures. "
            "Human intervention may be required."
        )
        # In production, this could send email/Slack notification

    def get_stats(self) -> dict[str, Any]:
        """Get fault recovery statistics."""
        return {
            "consecutive_failures": self._consecutive_failures,
            "total_failures": len(self._failure_log),
            "alert_threshold": self._alert_threshold,
            "needs_attention": self._consecutive_failures >= self._alert_threshold,
            "recent_failures": self._failure_log[-5:],
        }
