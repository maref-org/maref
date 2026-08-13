from __future__ import annotations

from unittest import mock

import pytest

from maref.evolution.real_metrics import RealMetrics, RealMetricsCollector


class TestRealMetrics:
    def test_to_dict(self) -> None:
        rm = RealMetrics(
            fnr=0.05,
            fpr=0.01,
            test_pass_rate=0.95,
            coverage_pct=72.0,
            total_tests=100,
            import_time_ms=150.0,
            cb_state="CLOSED",
        )
        d = rm.to_dict()
        assert d["fnr"] == 0.05
        assert d["fpr"] == 0.01
        assert d["test_pass_rate"] == 0.95
        assert d["coverage_pct"] == 72.0
        assert d["cb_state"] == "CLOSED"


class TestRealMetricsCollector:
    def test_init_defaults(self) -> None:
        collector = RealMetricsCollector()
        assert collector._baseline is None

    def test_init_custom_src(self) -> None:
        collector = RealMetricsCollector(src_dir="/tmp/test")
        assert str(collector._src) == "/tmp/test"

    def test_collect_baseline_caches(self) -> None:
        collector = RealMetricsCollector()
        with mock.patch.object(collector, "_run_all_checks") as mock_checks:
            mock_checks.return_value = RealMetrics(0.0, 0.0, 1.0, 0.0, 0, 0.0, "CLOSED")
            collector.collect_baseline()
            collector.collect_baseline()
            assert mock_checks.call_count == 1

    def test_collect_incremental(self) -> None:
        collector = RealMetricsCollector()
        with mock.patch.object(collector, "_run_all_checks") as mock_all:
            mock_all.return_value = RealMetrics(0.0, 0.0, 1.0, 0.0, 0, 0.0, "CLOSED")
            rm = collector.collect_incremental()
            assert rm.coverage_pct == 0.0

    def test_collect_incremental_records_measurement_errors(self) -> None:
        collector = RealMetricsCollector()
        with (
            mock.patch.object(collector, "_measure_import_time", return_value=-1.0),
            mock.patch.object(collector, "_run_pytest", return_value=(1.0, 0, 0)),
            mock.patch.object(collector, "_run_coverage", return_value=0.0),
            mock.patch.object(collector, "_check_cb_state", return_value="CLOSED"),
            mock.patch("maref.recursive.self_observer.SelfObserver"),
            mock.patch("maref.observation.probes.EntropyProbe"),
        ):
            metrics = collector.collect_incremental()
            assert metrics.import_time_ms == -1.0
            assert "import_time_failed" in metrics.errors

    def test_run_pytest_success(self) -> None:
        with mock.patch("maref.evolution.real_metrics.subprocess.run") as mock_run:
            mock_run.return_value.stdout = "10 passed, 2 failed"
            mock_run.return_value.stderr = ""
            rate, total, failed = RealMetricsCollector._run_pytest()
            assert rate == pytest.approx(10 / 12, rel=1e-4)
            assert total == 12
            assert failed == 2

    def test_run_pytest_no_match(self) -> None:
        with mock.patch("maref.evolution.real_metrics.subprocess.run") as mock_run:
            mock_run.return_value.stdout = "some output with no match"
            mock_run.return_value.stderr = ""
            rate, total, failed = RealMetricsCollector._run_pytest()
            assert rate == 0.0
            assert total == 0
            assert failed == 0

    def test_run_pytest_exception_is_failure_not_success(self) -> None:
        with mock.patch("maref.evolution.real_metrics.subprocess.run", side_effect=Exception):
            rate, total, failed = RealMetricsCollector._run_pytest()
            assert rate == 0.0
            assert total == 1
            assert failed == 1

    def test_run_coverage_success(self) -> None:
        with mock.patch("maref.evolution.real_metrics.subprocess.run") as mock_run:
            mock_run.return_value.stdout = "TOTAL              500    100     80%"
            pct = RealMetricsCollector._run_coverage()
            assert pct == 80.0

    def test_run_coverage_no_match(self) -> None:
        with mock.patch("maref.evolution.real_metrics.subprocess.run") as mock_run:
            mock_run.return_value.stdout = "no coverage data"
            pct = RealMetricsCollector._run_coverage()
            assert pct == 0.0

    def test_run_coverage_exception(self) -> None:
        with mock.patch("maref.evolution.real_metrics.subprocess.run", side_effect=Exception):
            pct = RealMetricsCollector._run_coverage()
            assert pct == 0.0

    def test_measure_import_time_success(self) -> None:
        with mock.patch("maref.evolution.real_metrics.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            ms = RealMetricsCollector._measure_import_time()
            assert ms >= 0

    def test_measure_import_time_failure(self) -> None:
        with mock.patch("maref.evolution.real_metrics.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            ms = RealMetricsCollector._measure_import_time()
            assert ms == -1.0

    def test_measure_import_time_exception(self) -> None:
        with mock.patch("maref.evolution.real_metrics.subprocess.run", side_effect=Exception):
            ms = RealMetricsCollector._measure_import_time()
            assert ms == -1.0

    def test_check_cb_state_exception(self) -> None:
        with mock.patch("maref.evolution.real_metrics.subprocess.run"):
            state = RealMetricsCollector._check_cb_state()
            assert state == "CLOSED" or state == "closed"

    def test_run_all_checks(self) -> None:
        collector = RealMetricsCollector()
        with (
            mock.patch.object(collector, "_run_pytest", return_value=(1.0, 0, 0)),
            mock.patch.object(collector, "_run_coverage", return_value=0.0),
            mock.patch.object(collector, "_measure_import_time", return_value=100.0),
            mock.patch.object(collector, "_check_cb_state", return_value="CLOSED"),
            mock.patch("maref.recursive.self_observer.SelfObserver"),
            mock.patch("maref.observation.probes.EntropyProbe"),
        ):
            rm = collector._run_all_checks()
            assert rm.fnr == 0.0

    def test_run_quick_checks(self) -> None:
        collector = RealMetricsCollector()
        with mock.patch.object(collector, "_measure_import_time", return_value=50.0):
            rm = collector._run_quick_checks()
            assert rm.fnr == 0.0
            assert rm.total_tests == 0
            assert rm.coverage_pct == 0.0
