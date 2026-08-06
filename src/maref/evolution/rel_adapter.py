from __future__ import annotations

import logging
import time

from maref.evolution._async_util import run_async
from maref.evolution.daily_loop import DailyEvolutionResult
from maref.recursive.recursive_evolution_loop import RecursiveEvolutionLoop

logger = logging.getLogger(__name__)


class RELAdapter:
    """
    Wraps RecursiveEvolutionLoop to match DailyEvolutionLoop.run_once() signature.
    Enables drop-in replacement in EvolutionDaemon.
    """

    def __init__(self, dry_run: bool = True) -> None:
        self._dry_run = dry_run
        self._rel = RecursiveEvolutionLoop()

    def _reset(self) -> None:
        self._rel.state_machine.reset()
        self._rel._current_round = 0
        self._rel._rounds.clear()
        self._rel._current_snapshot = None
        self._rel._current_report = None
        self._rel._current_proposal = None
        self._rel._current_code = None

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
            self._reset()
            result = run_async(self._rel.run_session())
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
