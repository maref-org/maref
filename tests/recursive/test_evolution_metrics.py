from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maref.recursive.recursive_evolution_loop import RecursiveEvolutionLoop
from maref.recursive.self_observer import SelfObserver, SystemSnapshot


class TestSystemSnapshotRealMetrics:
    def test_snapshot_computes_pass_rate_from_test_stats(self) -> None:
        o = SelfObserver(root_path="/tmp")
        with patch.object(o, "observe_codebase", return_value={}), patch.object(
            o,
            "observe_tests",
            return_value={"total": 100, "passed": 95, "failed": 5},
        ), patch.object(o, "observe_git", return_value={}), patch.object(
            o, "_build_state_machine_status", return_value={}
        ):
            snap = o.snapshot(collect_only=False)
        assert snap.test_pass_rate == pytest.approx(0.95)
        assert snap.test_count == 100

    def test_snapshot_zero_total_keeps_pass_rate_zero(self) -> None:
        o = SelfObserver(root_path="/tmp")
        with patch.object(o, "observe_codebase", return_value={}), patch.object(
            o,
            "observe_tests",
            return_value={"total": 0, "passed": 0, "failed": 0},
        ), patch.object(o, "observe_git", return_value={}), patch.object(
            o, "_build_state_machine_status", return_value={}
        ):
            snap = o.snapshot(collect_only=False)
        assert snap.test_pass_rate == 0.0
        assert snap.test_count == 0


class TestCollectCurrentMetrics:
    def test_uses_real_snapshot_values_not_fabricated(self) -> None:
        loop = RecursiveEvolutionLoop()
        snap = SystemSnapshot(
            source_file_count=10,
            total_lines=500,
            test_stats={"total": 80, "passed": 60, "failed": 20},
            test_pass_rate=0.75,
            coverage_pct=42.0,
            test_count=80,
        )
        with patch.object(
            SelfObserver, "snapshot", return_value=snap
        ):
            metrics = loop._collect_current_metrics()
        assert metrics["test_pass_rate"] == pytest.approx(0.75)
        assert metrics["coverage_pct"] == pytest.approx(42.0)
        assert metrics["source_file_count"] == pytest.approx(10.0)
        assert metrics["test_count"] == pytest.approx(80.0)

    def test_runs_real_tests_not_collect_only(self) -> None:
        loop = RecursiveEvolutionLoop()
        observed: dict[str, bool] = {}
        real_snapshot = MagicMock()
        real_snapshot.test_pass_rate = 1.0
        real_snapshot.coverage_pct = 0.0
        real_snapshot.source_file_count = 5
        real_snapshot.test_count = 40

        def fake_snapshot(collect_only: bool = False):
            observed["collect_only"] = collect_only
            return real_snapshot

        with patch.object(SelfObserver, "snapshot", side_effect=fake_snapshot):
            loop._collect_current_metrics()
        assert observed["collect_only"] is False

    def test_fallback_path_does_not_fabricate_pass_rate(self) -> None:
        loop = RecursiveEvolutionLoop()
        with patch.object(
            SelfObserver, "snapshot", side_effect=RuntimeError("boom")
        ), patch(
            "maref.recursive.recursive_evolution_loop.subprocess.run",
            return_value=MagicMock(stdout="", returncode=0),
        ):
            metrics = loop._collect_current_metrics()
        assert metrics["test_pass_rate"] == 0.0
        assert metrics["coverage_pct"] == 0.0


class TestRunQualityChecks:
    def test_runs_real_pytest_via_observer(self) -> None:
        loop = RecursiveEvolutionLoop()
        with patch.object(
            SelfObserver,
            "observe_tests",
            return_value={"total": 40, "passed": 40, "failed": 0, "errors": 0},
        ) as mock_observe:
            result = loop._run_quality_checks()
        mock_observe.assert_called_once()
        assert result["passed"] == 40
        assert result["failed"] == 0

    def test_quality_check_failure_is_recorded(self) -> None:
        loop = RecursiveEvolutionLoop()
        with patch.object(
            SelfObserver,
            "observe_tests",
            return_value={"total": 40, "passed": 38, "failed": 2, "errors": 0},
        ):
            result = loop._run_quality_checks()
        assert result["failed"] == 2
