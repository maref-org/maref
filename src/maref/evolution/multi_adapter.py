from __future__ import annotations

import logging
import time

from maref.evolution._async_util import run_async
from maref.evolution.daily_loop import DailyEvolutionResult
from maref.evolution.multi_agent_engine import (
    MultiAgentEvolutionConfig,
    MultiAgentEvolutionEngine,
)

logger = logging.getLogger(__name__)


class MultiAdapter:
    """
    Wraps MultiAgentEvolutionEngine to match DailyEvolutionLoop.run_once() signature.
    Enables drop-in replacement in EvolutionDaemon via --engine multi.
    """

    def __init__(self, dry_run: bool = True) -> None:
        self._dry_run = dry_run
        config = MultiAgentEvolutionConfig.with_default_agents()
        if dry_run:
            config.base_config.dry_run = True
        self._engine = MultiAgentEvolutionEngine(config)

    def run_once(self, day: str | None = None) -> DailyEvolutionResult | None:
        current_day = day or time.strftime("%Y-%m-%d")

        if self._dry_run:
            logger.info("Multi dry-run: skipping session")
            return DailyEvolutionResult(
                day=current_day,
                phases=["multi_agent"],
                dry_run=True,
                real_writes_enabled=False,
                priority="low",
                stop_reason="dry_run",
            )

        try:
            result = run_async(self._engine.run())
            return DailyEvolutionResult(
                day=current_day,
                phases=["multi_agent"],
                dry_run=False,
                real_writes_enabled=True,
                priority="medium" if result.evolution_result.all_passed else "high",
                stop_reason=result.evolution_result.stop_reason,
                artifacts={
                    "total_rounds": str(result.evolution_result.total_rounds),
                    "constitution_violations": str(result.constitution_violations_total),
                    "agent_count": str(len(result.agent_stats)),
                },
            )
        except Exception:
            logger.exception("Multi-agent evolution session failed")
            return None
