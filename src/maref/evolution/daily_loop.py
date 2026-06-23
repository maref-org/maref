from __future__ import annotations

import argparse
import asyncio
import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maref.evolution.constitution_harness import ConstitutionHarness, EvolutionChange
from maref.evolution.engine import EvolutionConfig, RecursiveEvolutionEngine
from maref.evolution.evolution_vault import EvolutionVault
from maref.evolution.iteration_analyzer import IterationAnalyzer
from maref.evolution.real_metrics import RealMetricsCollector

logger = logging.getLogger(__name__)


@dataclass
class DailyEvolutionResult:
    day: str
    phases: list[str]
    dry_run: bool
    real_writes_enabled: bool
    priority: str
    stop_reason: str
    artifacts: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "phases": list(self.phases),
            "dry_run": self.dry_run,
            "real_writes_enabled": self.real_writes_enabled,
            "priority": self.priority,
            "stop_reason": self.stop_reason,
            "artifacts": dict(self.artifacts),
        }


class DailyEvolutionLoop:
    PHASES = [
        "environment_check",
        "data_collection",
        "trend_analysis",
        "hypothesis_generation",
        "constitution_review",
        "experiment_execution",
        "result_persistence",
        "next_planning",
    ]

    def __init__(
        self,
        vault_dir: str | Path = ".evolution_vault",
        dry_run: bool = True,
        metrics_collector: Any | None = None,
    ) -> None:
        self._vault = EvolutionVault(vault_dir)
        self._dry_run = dry_run
        self._metrics_collector = metrics_collector or RealMetricsCollector()
        self._analyzer = IterationAnalyzer()
        self._constitution = ConstitutionHarness()

    def run_once(self, day: str | None = None) -> DailyEvolutionResult | None:
        current_day = day or time.strftime("%Y-%m-%d")
        self._environment_check()
        metrics = self._metrics_collector.collect_incremental()
        current_snapshot = {
            "fnr": metrics.fnr,
            "coverage": metrics.coverage_pct,
            "test_pass_rate": metrics.test_pass_rate,
        }
        previous_snapshot = self._load_previous_metrics(current_day)
        analysis = self._analyzer.compare_snapshots(previous_snapshot, current_snapshot)
        constitution_result = self._constitution.check_change(
            EvolutionChange(
                change_id=f"daily-{current_day}",
                files=[],
                description="daily dry-run evolution",
                audit_planned=True,
            )
        )
        config = EvolutionConfig(dry_run=True, metrics_mode="real")
        try:
            evolution_result = asyncio.run(
                RecursiveEvolutionEngine(config, metrics_collector=self._metrics_collector).run()
            )
        except Exception:
            logger.exception("Daily evolution failed on day %s", current_day)
            return None
        self._vault.write_metrics_snapshot(current_day, current_snapshot)
        self._vault.write_experiment_result(
            current_day,
            {
                "stop_reason": evolution_result.stop_reason,
                "all_passed": evolution_result.all_passed,
                "constitution_allowed": constitution_result.allowed,
            },
        )
        self._vault.write_daily_report(current_day, self._build_report(current_day, analysis.priority))
        self._vault.write_next_plan(
            current_day,
            {"priority": analysis.priority, "degradations": analysis.degradations},
        )
        day_dir = self._vault.start_day(current_day)
        return DailyEvolutionResult(
            day=current_day,
            phases=list(self.PHASES),
            dry_run=self._dry_run,
            real_writes_enabled=False,
            priority=analysis.priority,
            stop_reason=evolution_result.stop_reason,
            artifacts={"vault_dir": str(day_dir)},
        )

    @staticmethod
    def _environment_check() -> dict[str, Any]:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {"git_status_exit": result.returncode, "dirty": bool(result.stdout.strip())}

    def _load_previous_metrics(self, day: str) -> dict[str, Any]:
        loaded = self._vault.load_day(day)
        metrics = loaded.get("metrics_snapshot", {})
        return metrics if isinstance(metrics, dict) else {}

    @staticmethod
    def _build_report(day: str, priority: str) -> str:
        return f"# Daily Evolution Report\n\n- day: {day}\n- priority: {priority}\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MAREF daily recursive evolution loop")
    parser.add_argument("--vault", default=".evolution_vault")
    parser.add_argument("--dry-run", action="store_true", default=True)
    args = parser.parse_args()
    result = DailyEvolutionLoop(vault_dir=args.vault, dry_run=args.dry_run).run_once()
    print(result.to_dict())


if __name__ == "__main__":
    main()


__all__ = ["DailyEvolutionLoop", "DailyEvolutionResult", "main"]
