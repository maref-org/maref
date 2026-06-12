from __future__ import annotations

import time
from typing import Any

from maref.execution.harness.base import BaseHarness
from maref.execution.harness.types import HarnessConfig, HarnessResult, HarnessStatus
from maref.stress.emergence_harness import EmergenceTestHarness


class EmergenceHarnessAdapter(BaseHarness):
    def __init__(self) -> None:
        super().__init__()
        self._harness = EmergenceTestHarness()
        self._scenario_name: str = "temporal_perturbation"
        self._run_count: int = 10
        self._agents: list[str] | None = None

    def configure(self, config: HarnessConfig) -> None:
        super().configure(config)
        self._scenario_name = str(config.extra.get("scenario", "temporal_perturbation"))
        self._run_count = int(config.extra.get("runs", 10))
        self._agents = config.extra.get("agents")

    def run(self, round_id: str = "") -> HarnessResult:
        config = self._config or HarnessConfig()
        rid = round_id or config.round_id or f"emergence-{int(time.time())}"
        start = time.time()
        try:
            agents = self._agents or ["agent_a", "agent_b", "agent_c"]

            def _dummy_run(ordering: list[str]) -> dict[str, Any]:
                return {"executed_by": ordering, "timestamp": time.time()}

            report = self._harness.temporal_perturbation(
                scenario_name=self._scenario_name,
                agents=agents,
                run_fn=_dummy_run,
                runs=self._run_count,
            )
            elapsed = time.time() - start
            return HarnessResult(
                harness_type="emergence",
                round_id=rid,
                status=HarnessStatus.SUCCEEDED if report.consistency_rate > 0.5 else HarnessStatus.FAILED,
                duration_s=round(elapsed, 2),
                errors=[] if report.consistency_rate >= 1.0 else [f"inconsistency detected: {report.inconsistent_runs}/{report.run_count} runs"],
                metrics={
                    "scenario": report.scenario_name,
                    "run_count": report.run_count,
                    "consistent_runs": report.consistent_runs,
                    "inconsistent_runs": report.inconsistent_runs,
                    "consistency_rate": round(report.consistency_rate, 3),
                    "p99_latency_ms": round(report.p99_latency_ms, 1),
                },
                raw=report,
            )
        except Exception as e:
            return HarnessResult(
                harness_type="emergence",
                round_id=rid,
                status=HarnessStatus.FAILED,
                duration_s=round(time.time() - start, 2),
                errors=[str(e)],
            )
