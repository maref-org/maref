from __future__ import annotations

import logging
import time

from maref.evolution.daily_loop import DailyEvolutionResult
from maref.recursive.tla_replay import TLAReplayValidator

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

        try:
            validator = TLAReplayValidator()
            report = validator.generate_validation_report()
            return DailyEvolutionResult(
                day=current_day,
                phases=["tla_verify"],
                dry_run=False,
                real_writes_enabled=True,
                priority="high" if report.failed > 0 else "low",
                stop_reason=f"{report.passed}_passed_{report.failed}_failed" if report.failed > 0 else "all_passed",
                artifacts={
                    "total_checks": str(report.total_checks),
                    "passed": str(report.passed),
                    "failed": str(report.failed),
                },
            )
        except Exception:
            logger.exception("TLA validation failed")
            return None
