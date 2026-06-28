from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from maref.evolution.daily_loop import DailyEvolutionResult
from maref.recursive.recursive_evolution_loop import RecursiveEvolutionLoop

logger = logging.getLogger(__name__)


def _run_async(coro: Any) -> Any:
    """Safely await a coroutine from a sync context, even inside a running loop."""
    try:
        asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


class RELAdapter:
    """
    Wraps RecursiveEvolutionLoop to match DailyEvolutionLoop.run_once() signature.
    Enables drop-in replacement in EvolutionDaemon.
    """

    def __init__(self, dry_run: bool = True) -> None:
        self._dry_run = dry_run
        self._rel = RecursiveEvolutionLoop()

    def run_once(self, day: str | None = None) -> DailyEvolutionResult | None:
        current_day = day or time.strftime("%Y-%m-%d")

        if self._dry_run:
            logger.info("REL dry-run: skipping session")
            return DailyEvolutionResult(
                day=current_day,
                phases=["rel_session"],
                dry_run=True,
                real_writes_enabled=False,
                priority="low",
                stop_reason="dry_run",
            )

        try:
            result = _run_async(self._rel.run_session())
            return DailyEvolutionResult(
                day=current_day,
                phases=["rel_session"],
                dry_run=False,
                real_writes_enabled=True,
                priority="medium" if result.success else "high",
                stop_reason=result.reason,
            )
        except Exception:
            logger.exception("REL session failed")
            return None
