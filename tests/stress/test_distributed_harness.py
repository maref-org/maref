from __future__ import annotations

from unittest.mock import patch

import pytest

from maref.stress.distributed_harness import (
    DistributedStressHarness,
    WorkerResult,
)
from maref.stress.stress_level import StressLevel
from maref.stress.stress_result import StressResult


class TestWorkerResult:
    def test_defaults(self):
        wr = WorkerResult(worker_id=0)
        assert wr.results == []
        assert wr.errors == []
        assert wr.elapsed_s == 0.0
        assert wr.latency_report == {}


class TestDistributedStressHarness:
    def test_min_workers_is_one(self):
        h = DistributedStressHarness(num_workers=0)
        assert h._num_workers == 1

    def test_min_workers_negative(self):
        h = DistributedStressHarness(num_workers=-5)
        assert h._num_workers == 1

    @patch("maref.stress.distributed_harness.multiprocessing.Pool")
    def test_run_concurrent_empty_results(self, mock_pool):
        mock_pool_instance = mock_pool.return_value.__enter__.return_value
        mock_pool_instance.starmap.return_value = [
            WorkerResult(worker_id=0, results=[], elapsed_s=0.1),
            WorkerResult(worker_id=1, results=[], elapsed_s=0.2),
        ]
        h = DistributedStressHarness(num_workers=2)
        results = h.run_concurrent(StressLevel.L1, rounds_per_worker=0, duration_min=0.1)
        assert len(results) == 2
        assert results[0].worker_id == 0
        assert results[1].worker_id == 1

    @patch("maref.stress.distributed_harness.multiprocessing.Pool")
    def test_run_concurrent_with_results(self, mock_pool):
        mock_pool_instance = mock_pool.return_value.__enter__.return_value
        mock_pool_instance.starmap.return_value = [
            WorkerResult(
                worker_id=0,
                results=[
                    StressResult(round_id="w0-r0", stress_level="L1", resilience_score=0.9),
                ],
                elapsed_s=0.1,
            ),
        ]
        h = DistributedStressHarness(num_workers=1)
        results = h.run_concurrent(StressLevel.L1, rounds_per_worker=1, duration_min=0.1)
        assert len(results) == 1
        assert results[0].results[0].resilience_score == 0.9

    def test_aggregate_empty(self):
        results = [
            WorkerResult(worker_id=0, results=[], errors=[], elapsed_s=0.0),
            WorkerResult(worker_id=1, results=[], errors=[], elapsed_s=0.0),
        ]
        agg = DistributedStressHarness.aggregate(results)
        assert agg["total_workers"] == 2
        assert agg["total_rounds"] == 0
        assert agg["mean_resilience"] == 0.0
        assert agg["min_resilience"] == 0
        assert agg["max_resilience"] == 0
        assert agg["cb_trips"] == 0
        assert agg["errors"] == []

    def test_aggregate_with_scores(self):
        results = [
            WorkerResult(
                worker_id=0,
                results=[
                    StressResult(round_id="r0", stress_level="L1", resilience_score=0.5, cb_state="CLOSED"),
                    StressResult(round_id="r1", stress_level="L1", resilience_score=1.0, cb_state="OPEN"),
                ],
                errors=[],
                elapsed_s=0.5,
            ),
            WorkerResult(
                worker_id=1,
                results=[
                    StressResult(round_id="r2", stress_level="L1", resilience_score=0.75, cb_state="CLOSED"),
                ],
                errors=["error1"],
                elapsed_s=0.3,
            ),
        ]
        agg = DistributedStressHarness.aggregate(results)
        assert agg["total_workers"] == 2
        assert agg["total_rounds"] == 3
        assert agg["mean_resilience"] == pytest.approx(0.75, abs=0.01)
        assert agg["min_resilience"] == 0.5
        assert agg["max_resilience"] == 1.0
        assert agg["cb_trips"] == 1
        assert agg["errors"] == ["error1"]

    def test_aggregate_limits_errors_to_20(self):
        results = [
            WorkerResult(
                worker_id=0,
                results=[],
                errors=[f"err{i}" for i in range(25)],
                elapsed_s=0.0,
            ),
        ]
        agg = DistributedStressHarness.aggregate(results)
        assert len(agg["errors"]) == 20

    @patch("maref.stress.distributed_harness.multiprocessing.cpu_count")
    @patch("maref.stress.distributed_harness.DistributedStressHarness.run_concurrent")
    def test_progressive_load_uses_capped_workers(self, mock_run, mock_cpu_count):
        mock_cpu_count.return_value = 4
        mock_run.return_value = [WorkerResult(worker_id=0, results=[], elapsed_s=0.1)]
        h = DistributedStressHarness(num_workers=2)
        results = h.run_progressive_load(StressLevel.L1, rounds_per_step=1)
        assert mock_run.call_count >= 1
        assert len(results) >= 1
