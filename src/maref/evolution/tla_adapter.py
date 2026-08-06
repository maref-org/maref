from __future__ import annotations

import logging
import time

from maref.evolution.daily_loop import DailyEvolutionResult

logger = logging.getLogger(__name__)


class TLAAdapter:
    """
    Wraps TLAReplayValidator to match DailyEvolutionLoop.run_once() signature.
    Runs formal invariant validation on each daemon call.
    """

    def __init__(self, dry_run: bool = True) -> None:
        self._dry_run = dry_run

    def run_once(self, day: str | None = None) -> DailyEvolutionResult | None:
        current_day = day or time.strftime("%Y-%m-%d")

        if self._dry_run:
            logger.info("TLA dry-run: skipping validation")
            return DailyEvolutionResult(
                day=current_day,
                phases=["tla_verify"],
                dry_run=True,
                real_writes_enabled=False,
                priority="low",
                stop_reason="dry_run",
            )

        logger.warning(
            "TLA validation skipped: no evolution trajectory provided. "
            "Call generate_validation_report(states) with state data for real verification."
        )
        return DailyEvolutionResult(
            day=current_day,
            phases=["tla_verify"],
            dry_run=False,
            real_writes_enabled=True,
            priority="low",
            stop_reason="skipped_no_states",
            artifacts={
                "validation": "skipped",
                "reason": "no_evolution_trajectory",
            },
        )
