from __future__ import annotations

import pytest

from maref.recursive.self_loop_runner import SelfLoopRunner, LoopResult, LoopConfig


class TestSelfLoopRunnerInit:
    def test_default_config(self) -> None:
        runner = SelfLoopRunner()
        assert runner.config.max_iterations == 5
        assert runner.config.convergence_threshold == 0.05
        assert runner.current_iteration == 0
        assert runner.is_running is False


class TestSelfLoopRunnerDryRun:
    @pytest.fixture
    def runner(self) -> SelfLoopRunner:
        return SelfLoopRunner()

    def test_dry_run_completes(self, runner: SelfLoopRunner) -> None:
        result = runner.dry_run()
        assert result.iterations_completed >= 0
        assert isinstance(result.converged, bool)

    def test_dry_run_respects_max_iterations(self) -> None:
        config = LoopConfig(max_iterations=2)
        runner = SelfLoopRunner(config=config)
        result = runner.dry_run()
        assert result.iterations_completed <= 2

    def test_dry_run_produces_iteration_results(self, runner: SelfLoopRunner) -> None:
        result = runner.dry_run()
        assert len(result.iteration_results) == result.iterations_completed


class TestSelfLoopRunnerObservations:
    @pytest.fixture
    def runner(self) -> SelfLoopRunner:
        return SelfLoopRunner()

    def test_observer_snapshot_created(self, runner: SelfLoopRunner) -> None:
        snapshot = runner._observe()
        assert snapshot is not None
        assert hasattr(snapshot, "timestamp")
        assert hasattr(snapshot, "module_graph")

    def test_diagnostician_report_generated(self, runner: SelfLoopRunner) -> None:
        snapshot = runner._observe()
        report = runner._diagnose(snapshot)
        assert report is not None
        assert hasattr(report, "overall_risk")
        assert hasattr(report, "recommendations")


class TestSelfLoopRunnerFullCycle:
    @pytest.fixture
    def runner(self) -> SelfLoopRunner:
        return SelfLoopRunner()

    def test_run_one_iteration_has_all_core_steps(self, runner: SelfLoopRunner) -> None:
        result = runner.run_one_iteration()
        assert "observe" in result.steps_completed
        assert "diagnose" in result.steps_completed
        assert result.snapshot is not None
        assert result.diagnosis is not None

    def test_run_one_iteration_no_execute_by_default(self, runner: SelfLoopRunner) -> None:
        result = runner.run_one_iteration()
        assert "execute" not in result.steps_completed

    def test_run_one_iteration_duration_positive(self, runner: SelfLoopRunner) -> None:
        result = runner.run_one_iteration()
        assert result.duration > 0.0

    def test_run_converges_with_high_threshold(self) -> None:
        config = LoopConfig(max_iterations=5, convergence_threshold=0.99)
        runner = SelfLoopRunner(config=config)
        result = runner.run()
        assert result.converged is True
        assert result.iterations_completed >= 1


class TestSelfLoopRunnerAudit:
    @pytest.fixture
    def runner(self) -> SelfLoopRunner:
        return SelfLoopRunner()

    def test_audit_records_written_on_dry_run(self, runner: SelfLoopRunner) -> None:
        before = runner._audit_store.count()
        runner.dry_run()
        after = runner._audit_store.count()
        assert after > before

    def test_audit_records_have_event_types(self, runner: SelfLoopRunner) -> None:
        runner.dry_run()
        events = runner._audit_store.stats_by_event_type()
        assert "observe_complete" in events
        assert "diagnose_complete" in events


class TestSelfLoopRunnerErrorHandling:
    def test_sequential_runs_ok(self) -> None:
        runner = SelfLoopRunner(config=LoopConfig(max_iterations=1))
        result1 = runner.run()
        assert result1.iterations_completed == 1
        result2 = runner.run()
        assert result2.iterations_completed == 1

    def test_dry_run_does_not_throw(self) -> None:
        runner = SelfLoopRunner()
        result = runner.dry_run()
        assert result is not None
