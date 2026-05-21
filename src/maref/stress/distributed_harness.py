"""Distributed multi-process stress harness."""
from __future__ import annotations

import multiprocessing
import time
from dataclasses import dataclass, field
from typing import Any

from maref.stress.real_latency import LatencyReport
from maref.stress.stress_harness import StressHarness
from maref.stress.stress_level import STRESS_PRESETS, StressLevel
from maref.stress.stress_result import StressResult


@dataclass
class WorkerResult:
    worker_id: int
    results: list[StressResult] = field(default_factory=list)
    latency_report: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    elapsed_s: float = 0.0


def _worker_runner(worker_id: int, level: StressLevel, rounds: int,
                    duration_min: float) -> WorkerResult:
    result = WorkerResult(worker_id=worker_id)
    start = time.time()
    try:
        harness = StressHarness()
        harness.set_level(level)
        harness.set_duration(duration_min)
        for i in range(rounds):
            r = harness.run(f"worker-{worker_id}-r{i}")
            result.results.append(r)
    except Exception as e:
        result.errors.append(str(e))
    result.elapsed_s = round(time.time() - start, 2)
    return result


class DistributedStressHarness:
    """Run stress tests across multiple processes simultaneously."""

    def __init__(self, num_workers: int = 4) -> None:
        self._num_workers = max(num_workers, 1)

    def run_concurrent(self, level: StressLevel, rounds_per_worker: int = 5,
                       duration_min: float = 0.5) -> list[WorkerResult]:
        with multiprocessing.Pool(processes=self._num_workers) as pool:
            args = [(i, level, rounds_per_worker, duration_min)
                    for i in range(self._num_workers)]
            results = pool.starmap(_worker_runner, args)
        return list(results)

    def run_progressive_load(self, base_level: StressLevel,
                              rounds_per_step: int = 3) -> list[WorkerResult]:
        all_results: list[WorkerResult] = []
        for worker_count in (2, 4, 8, 16, 32):
            workers = min(worker_count, multiprocessing.cpu_count() * 2)
            stress = DistributedStressHarness(num_workers=workers)
            results = stress.run_concurrent(base_level, rounds_per_step, 0.3)
            all_results.extend(results)
        return all_results

    @staticmethod
    def aggregate(results: list[WorkerResult]) -> dict[str, Any]:
        total_rounds = sum(len(r.results) for r in results)
        all_scores = []
        all_cb_trips = 0
        all_errors: list[str] = []
        for wr in results:
            for sr in wr.results:
                all_scores.append(sr.resilience_score)
                if sr.cb_state == "OPEN":
                    all_cb_trips += 1
            all_errors.extend(wr.errors)

        return {
            "total_workers": len(results),
            "total_rounds": total_rounds,
            "mean_resilience": round(sum(all_scores) / max(len(all_scores), 1), 2),
            "min_resilience": min(all_scores) if all_scores else 0,
            "max_resilience": max(all_scores) if all_scores else 0,
            "cb_trips": all_cb_trips,
            "errors": all_errors[:20],
            "total_elapsed_s": round(sum(r.elapsed_s for r in results), 2),
        }