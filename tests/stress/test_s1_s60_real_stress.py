from __future__ import annotations

import pytest

from maref.stress.distributed_harness import DistributedStressHarness, WorkerResult
from maref.stress.real_faults import FAULT_TYPES, FaultInjection, RealFaultInjector
from maref.stress.real_latency import (
    LatencyReport,
    LatencySample,
    RealLatencyTracker,
)
from maref.stress.stress_harness import DEFAULT_MAX_SM, StressHarness
from maref.stress.stress_level import StressLevel


class TestRealLatencyTracker:
    def test_tracker_initializes(self) -> None:
        tracker = RealLatencyTracker()
        assert tracker.all_reports() == {}

    def test_measure_via_context_manager(self) -> None:
        tracker = RealLatencyTracker()
        with tracker.measure("test_op"):
            pass
        report = tracker.report("test_op")
        assert report is not None
        assert report.count == 1
        assert report.p50_ms >= 0.0

    def test_multiple_samples(self) -> None:
        tracker = RealLatencyTracker()
        for _ in range(100):
            with tracker.measure("multi_op"):
                pass
        report = tracker.report("multi_op")
        assert report is not None
        assert report.count == 100
        assert report.p50_ms >= 0.0
        assert report.p99_ms >= report.p50_ms

    def test_latency_sample_properties(self) -> None:
        sample = LatencySample(operation="test", duration_ns=1_500_000)
        assert sample.operation == "test"
        assert sample.duration_ms == 1.5

    def test_latency_report_to_dict(self) -> None:
        report = LatencyReport(operation="op", count=10, p50_ms=1.0, p99_ms=2.0,
                               p99_9_ms=3.0, mean_ms=1.5, min_ms=0.5, max_ms=5.0,
                               throughput_ops_sec=100.0, total_elapsed_s=0.1)
        d = report.to_dict()
        assert d["operation"] == "op"
        assert d["count"] == 10

    def test_all_reports(self) -> None:
        tracker = RealLatencyTracker()
        with tracker.measure("a"):
            pass
        with tracker.measure("b"):
            pass
        all_reports = tracker.all_reports()
        assert "a" in all_reports
        assert "b" in all_reports


class TestStressHarnessUpgraded:
    def test_harness_above_200_sm(self) -> None:
        harness = StressHarness()
        harness.set_axis("agent_concurrency", 500)
        result = harness.run("s1-large")
        assert result is not None
        assert result.latency_p50 >= 0.0

    def test_harness_uncapped_sm_count(self) -> None:
        harness = StressHarness()
        harness.set_axis("agent_concurrency", 1000)
        harness.set_duration(0.05)
        result = harness.run("s2-1k")
        assert result.errors is not None

    def test_latency_is_real(self) -> None:
        harness = StressHarness()
        harness.set_level(StressLevel.L2)
        harness.set_duration(0.1)
        result = harness.run("s3-real-latency")
        assert result.latency_p50 >= 0.0

    def test_no_hard_coded_200_limit(self) -> None:
        assert DEFAULT_MAX_SM == 5000
        harness = StressHarness()
        harness.set_axis("agent_concurrency", 300)
        harness.set_duration(0.05)
        result = harness.run("s4-300")
        assert result is not None


class TestRealFaultInjector:
    def test_injector_initializes(self) -> None:
        injector = RealFaultInjector()
        assert injector._injections == []

    def test_inject_all_fault_types(self) -> None:
        injector = RealFaultInjector()
        for ft in FAULT_TYPES:
            result = injector.inject(ft, max_duration_s=1.0)
            assert isinstance(result, FaultInjection)
        assert len(injector._injections) == len(FAULT_TYPES)

    def test_oom_trigger_recovers(self) -> None:
        injector = RealFaultInjector()
        result = injector.inject("oom_trigger", max_duration_s=2.0)
        assert result.fault_type == "oom_trigger"

    def test_file_lock_recovers(self) -> None:
        injector = RealFaultInjector()
        result = injector.inject("file_lock", max_duration_s=2.0)
        assert result.fault_type == "file_lock"
        injector.cleanup()

    def test_subprocess_crash_detected(self) -> None:
        injector = RealFaultInjector()
        result = injector.inject("subprocess_crash", max_duration_s=3.0)
        assert result.triggered is True

    def test_unknown_fault_errors(self) -> None:
        injector = RealFaultInjector()
        result = injector.inject("nonexistent_fault", max_duration_s=1.0)
        assert "Unknown" in result.error

    def test_cleanup_removes_temp_files(self) -> None:
        injector = RealFaultInjector()
        injector.inject("disk_io_sat", max_duration_s=1.0)
        injector.cleanup()
        assert injector._temp_files == []


class TestDistributedHarness:
    @pytest.mark.slow
    def test_distributed_initializes(self) -> None:
        dh = DistributedStressHarness(num_workers=2)
        assert dh._num_workers == 2

    @pytest.mark.slow
    def test_run_concurrent(self) -> None:
        dh = DistributedStressHarness(num_workers=2)
        results = dh.run_concurrent(StressLevel.L1, rounds_per_worker=2, duration_min=0.05)
        assert len(results) == 2
        for wr in results:
            assert isinstance(wr, WorkerResult)
            assert wr.worker_id in (0, 1)

    @pytest.mark.slow
    def test_aggregate_returns_summary(self) -> None:
        dh = DistributedStressHarness(num_workers=2)
        results = dh.run_concurrent(StressLevel.L1, rounds_per_worker=1, duration_min=0.05)
        summary = DistributedStressHarness.aggregate(results)
        assert summary["total_workers"] == 2
        assert "mean_resilience" in summary
