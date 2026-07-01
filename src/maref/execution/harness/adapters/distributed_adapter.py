from __future__ import annotations

import time

from maref.execution.harness.base import BaseHarness
from maref.execution.harness.types import HarnessConfig, HarnessResult, HarnessStatus

from maref.execution.harness.adapters.stress_adapter import _parse_level
from maref.stress.distributed_harness import DistributedStressHarness


class DistributedHarnessAdapter(BaseHarness):
    def __init__(self) -> None:
        super().__init__()
        self._harness: DistributedStressHarness | None = None
        self._num_workers: int = 4
        self._rounds_per_worker: int = 3

    def configure(self, config: HarnessConfig) -> None:
        super().configure(config)
        self._num_workers = int(config.extra.get("workers", 4))
        self._rounds_per_worker = int(config.extra.get("rounds", 3))
        self._harness = DistributedStressHarness(num_workers=self._num_workers)

    def run(self, round_id: str = "") -> HarnessResult:
        if self._harness is None:
            self._harness = DistributedStressHarness(num_workers=self._num_workers)
        config = self._config or HarnessConfig()
        rid = round_id or config.round_id or f"distributed-{int(time.time())}"
        level = _parse_level(config.level)
        start = time.time()
        try:
            worker_results = self._harness.run_concurrent(level, self._rounds_per_worker, max(config.duration_minutes, 0.3))
            aggregated = self._harness.aggregate(worker_results)
            elapsed = time.time() - start
            errors: list[str] = []
            for wr in worker_results:
                errors.extend(wr.errors)
            return HarnessResult(
                harness_type="distributed",
                round_id=rid,
                status=HarnessStatus.SUCCEEDED,
                duration_s=round(elapsed, 2),
                errors=errors[:20],
                metrics=aggregated,
                raw=worker_results,
            )
        except Exception as e:
            return HarnessResult(
                harness_type="distributed",
                round_id=rid,
                status=HarnessStatus.FAILED,
                duration_s=round(time.time() - start, 2),
                errors=[str(e)],
            )
