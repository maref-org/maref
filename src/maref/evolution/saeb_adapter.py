from __future__ import annotations

import logging
import time
from pathlib import Path

from maref.evaluation.saeb.runner import run_saeb
from maref.evaluation.saeb.scenario import SAEBScenario
from maref.evolution.daily_loop import DailyEvolutionResult

logger = logging.getLogger(__name__)


class SAEBAdapter:
    """
    Wraps SAEB benchmark to match DailyEvolutionLoop.run_once() signature.
    Runs a full SAEB self-benchmark on each call.
    """

    def __init__(self, dry_run: bool = True) -> None:
        self._dry_run = dry_run
        self._run_count = 0

    def run_once(self, day: str | None = None) -> DailyEvolutionResult | None:
        current_day = day or time.strftime("%Y-%m-%d")
        self._run_count += 1

        if self._dry_run:
            logger.info("SAEB dry-run: skipping benchmark")
            return DailyEvolutionResult(
                day=current_day,
                phases=["saeb_benchmark"],
                dry_run=True,
                real_writes_enabled=False,
                priority="low",
                stop_reason="dry_run",
            )

        try:
            scenario = SAEBScenario(name=f"daemon_run_{self._run_count}")
            result = run_saeb(scenario, rounds=3)
            return DailyEvolutionResult(
                day=current_day,
                phases=["saeb_benchmark"],
                dry_run=False,
                real_writes_enabled=True,
                priority="high" if result.failure_count > 0 else "low",
                stop_reason=f"sae_{result.failure_count}_failures_{result.passed_count}_passed",
                artifacts={
                    "total_scenarios": str(result.total_scenarios),
                    "passed": str(result.passed_count),
                    "failed": str(result.failure_count),
                    "avg_fnr": f"{result.average_fnr:.4f}",
                    "duration_s": f"{result.duration_seconds:.1f}",
                },
            )
        except Exception:
            logger.exception("SAEB benchmark failed")
            return None
