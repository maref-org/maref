from __future__ import annotations

import logging
import time

from maref.evolution.daily_loop import DailyEvolutionResult
from maref.recursive.continuous_optimizer import ContinuousOptimizer
from maref.recursive.unified_audit import UnifiedAuditStore

logger = logging.getLogger(__name__)


class ContinuousAdapter:
    """
    Wraps ContinuousOptimizer to match DailyEvolutionLoop.run_once() signature.
    Runs one optimization cycle per daemon call.
    """

    def __init__(self, dry_run: bool = True) -> None:
        self._dry_run = dry_run
        self._optimizer = ContinuousOptimizer(audit_store=UnifiedAuditStore())

    def run_once(self, day: str | None = None) -> DailyEvolutionResult | None:
        current_day = day or time.strftime("%Y-%m-%d")

        if self._dry_run:
            logger.info("Continuous dry-run: skipping session")
            return DailyEvolutionResult(
                day=current_day,
                phases=["continuous_opt"],
                dry_run=True,
                real_writes_enabled=False,
                priority="low",
                stop_reason="dry_run",
            )

        try:
            import subprocess

            result = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            current_metrics = {
                "dirty_files": float(len(result.stdout.strip()) > 0),
                "test_pass_rate": 1.0,
            }

            cycles = self._optimizer.run_cycle(current_metrics)
            adopted = sum(1 for c in cycles if c.adopted)
            saturated = getattr(self._optimizer, "_paused", False)

            return DailyEvolutionResult(
                day=current_day,
                phases=["continuous_opt"],
                dry_run=False,
                real_writes_enabled=True,
                priority="low" if saturated else "medium",
                stop_reason="saturated" if saturated else f"{len(cycles)}_cycles_{adopted}_adopted",
                artifacts={
                    "cycles": str(len(cycles)),
                    "adopted": str(adopted),
                    "saturated": str(saturated),
                },
            )
        except Exception:
            logger.exception("Continuous optimization session failed")
            return None
