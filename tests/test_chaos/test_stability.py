from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from maref.stress.stability_test import (
    ITERATIONS_FOR_24H,
    LEAK_THRESHOLD_PCT,
    IterationSnapshot,
    StabilityReport,
    StabilityTestRunner,
)


class TestIterationSnapshot:
    def test_creates_snapshot(self) -> None:
        snap = IterationSnapshot(
            iteration=1,
            timestamp=time.time(),
            memory_rss_mb=100.0,
            memory_traced_mb=50.0,
            elapsed_s=0.01,
            success=True,
        )
        assert snap.iteration == 1
        assert snap.memory_rss_mb == 100.0
        assert snap.success is True

    def test_snapshot_with_error(self) -> None:
        snap = IterationSnapshot(
            iteration=5,
            timestamp=time.time(),
            memory_rss_mb=120.0,
            memory_traced_mb=60.0,
            elapsed_s=0.02,
            success=False,
            error="test failure",
        )
        assert snap.success is False
        assert snap.error == "test failure"


class TestStabilityReport:
    def test_default_values(self) -> None:
        report = StabilityReport(total_iterations=100, duration_s=3600.0)
        assert report.total_iterations == 100
        assert report.duration_s == 3600.0
        assert report.leak_detected is False
        assert report.success_rate == 1.0

    def test_to_dict(self) -> None:
        report = StabilityReport(
            total_iterations=50,
            duration_s=1800.0,
            start_memory_mb=100.0,
            end_memory_mb=102.0,
            peak_memory_mb=105.0,
            memory_growth_pct=2.0,
            success_rate=0.98,
        )
        d = report.to_dict()
        assert d["total_iterations"] == 50
        assert d["duration_s"] == 1800.0
        assert d["memory_growth_pct"] == 2.0
        assert d["leak_detected"] is False

    def test_detects_leak(self) -> None:
        report = StabilityReport(
            total_iterations=100,
            duration_s=3600.0,
            start_memory_mb=100.0,
            end_memory_mb=120.0,
            memory_growth_pct=20.0,
            leak_detected=True,
            leak_message="Memory leak detected: 20% growth",
        )
        assert report.leak_detected is True
        assert "20%" in report.leak_message


class TestStabilityTestRunner:
    def test_default_operation(self) -> None:
        runner = StabilityTestRunner(iterations=5, enable_tracemalloc=False)
        report = runner.run(report_interval=10)
        assert isinstance(report, StabilityReport)
        assert report.total_iterations == 5
        assert report.success_rate == 1.0

    def test_custom_operation(self) -> None:
        side_effects: list[int] = []
        runner = StabilityTestRunner(
            operation=lambda i: side_effects.append(i),
            iterations=3,
            enable_tracemalloc=False,
        )
        runner.run(report_interval=10)
        assert side_effects == [0, 1, 2]

    def test_records_memory_snapshots(self) -> None:
        runner = StabilityTestRunner(iterations=3, enable_tracemalloc=False)
        report = runner.run(report_interval=10)
        assert len(report.memory_snapshots) == 3
        for snap in report.memory_snapshots:
            assert snap.memory_rss_mb >= 0
            assert snap.memory_traced_mb >= 0

    def test_detects_operation_failures(self) -> None:
        def failing_op(iteration: int) -> None:
            if iteration == 2:
                msg = "intentional failure"
                raise RuntimeError(msg)

        runner = StabilityTestRunner(operation=failing_op, iterations=5, enable_tracemalloc=False)
        report = runner.run(report_interval=10)
        assert len(report.errors) == 1
        assert "intentional failure" in report.errors[0]
        assert report.success_rate == 0.8

    def test_leak_detection(self) -> None:
        runner = StabilityTestRunner(
            iterations=10,
            leak_threshold_pct=0.1,
            enable_tracemalloc=False,
        )
        with patch.object(runner, "_get_memory_mb") as mock_mem:
            mock_mem.side_effect = [
                50.0,
                50.5,
                51.0,
                51.5,
                52.0,
                52.5,
                53.0,
                53.5,
                54.0,
                60.0,
                65.0,
            ]
            report = runner.run(report_interval=10)
        assert report.leak_detected
        assert report.memory_growth_pct > 0.1

    def test_no_false_positive_leak(self) -> None:
        def stable_op(iteration: int) -> None:
            _ = sum(range(100))

        runner = StabilityTestRunner(
            operation=stable_op,
            iterations=3,
            leak_threshold_pct=50.0,
            enable_tracemalloc=False,
        )
        report = runner.run(report_interval=10)
        assert not report.leak_detected

    @pytest.mark.chaos
    def test_longer_run(self) -> None:
        runner = StabilityTestRunner(iterations=20, enable_tracemalloc=False)
        report = runner.run(report_interval=10)
        assert report.total_iterations == 20
        assert report.success_rate == 1.0

    @patch("maref.stress.stability_test.StabilityTestRunner._get_memory_mb")
    def test_memory_growth_detection(self, mock_memory) -> None:
        mock_memory.side_effect = [100.0, 100.5, 101.0, 101.5, 102.0, 120.0, 120.0]
        runner = StabilityTestRunner(iterations=6, enable_tracemalloc=False)
        report = runner.run(report_interval=10)
        assert report.start_memory_mb == 100.0
        assert report.end_memory_mb == 120.0

    def test_report_duration(self) -> None:
        runner = StabilityTestRunner(iterations=5, enable_tracemalloc=False)
        report = runner.run(report_interval=10)
        assert report.duration_s > 0


class TestConstants:
    def test_constants_defined(self) -> None:
        assert ITERATIONS_FOR_24H == 1000
        assert LEAK_THRESHOLD_PCT == 5.0
