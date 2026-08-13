from __future__ import annotations

import logging
import tempfile
import time

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
            with tempfile.TemporaryDirectory(prefix="saeb_daemon_") as tmpdir:
                from pathlib import Path

                scenario = SAEBScenario(
                    name=f"daemon_run_{self._run_count}",
                    description=f"DAEMON SAEB benchmark run {self._run_count}",
                    workdir=Path(tmpdir) / "calc",
                )
                result = run_saeb(scenario, rounds=3)
            fnrs = result.fnr_trajectory()
            avg_fnr = sum(fnrs) / len(fnrs) if fnrs else 0.0
            return DailyEvolutionResult(
                day=current_day,
                phases=["saeb_benchmark"],
                dry_run=False,
                real_writes_enabled=True,
                priority="high" if result.oscillation_count > 0 else "low",
                stop_reason=f"{result.rounds_completed}_rounds_fnr_{avg_fnr:.4f}",
                artifacts={
                    "rounds": str(result.rounds_completed),
                    "convergence_round": str(result.convergence_round),
                    "oscillation_count": str(result.oscillation_count),
                    "avg_fnr": f"{avg_fnr:.4f}",
                    "total_time_s": f"{result.total_time_s:.1f}",
                },
            )
        except Exception:
            logger.exception("SAEB benchmark failed")
            return None
