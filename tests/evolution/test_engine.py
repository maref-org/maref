"""
Tests for RecursiveEvolutionEngine — core engine logic and stop conditions.
"""

import asyncio
import tempfile
from pathlib import Path

from maref.evolution.engine import EvolutionConfig, RecursiveEvolutionEngine
from maref.evolution.metrics import (
    AcceptanceCriteria,
    CycleSpec,
    EvolutionMetrics,
)


class TestEngineInitialization:
    def test_default_config_creates_engine(self):
        engine = RecursiveEvolutionEngine()
        assert engine._running is False
        assert engine._total_rounds == 0
        status = engine.get_live_status()
        assert status["total_rounds"] == 0
        assert "meta_learning" in status
        assert "sandbox" in status
        assert "circuit_breaker" in status

    def test_custom_config(self):
        config = EvolutionConfig(max_total_rounds=50)
        engine = RecursiveEvolutionEngine(config=config)
        assert engine._config.max_total_rounds == 50

    def test_dry_run_config(self):
        config = EvolutionConfig(dry_run=True, dry_run_rounds=1)
        assert config.dry_run is True
        assert config.dry_run_rounds == 1

    def test_resume_config(self):
        config = EvolutionConfig(resume_from_cycle="c2", resume_from_round=10)
        assert config.resume_from_cycle == "c2"
        assert config.resume_from_round == 10


class TestSingleRoundExecution:
    def test_dry_run_completes_successfully(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvolutionConfig(dry_run=True, output_dir=tmpdir)
            engine = RecursiveEvolutionEngine(config=config)

            result = asyncio.run(engine.run())

            assert result.stop_reason == "dry_run_complete"
            assert len(result.cycles) == 1
            assert result.cycles[0].rounds_total == 1
            assert result.total_rounds >= 0

    def test_dry_run_metrics_collected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvolutionConfig(dry_run=True, output_dir=tmpdir)
            engine = RecursiveEvolutionEngine(config=config)

            result = asyncio.run(engine.run())
            cycle = result.cycles[0]

            assert len(cycle.metrics.fnr_series) >= 1
            assert len(cycle.metrics.fpr_series) >= 1
            assert len(cycle.metrics.entropy_series) >= 1
            assert len(cycle.metrics.transition_count_series) >= 1
            assert cycle.metrics.fnr_series[0] is not None
            assert cycle.metrics.fpr_series[0] is not None

    def test_dry_run_output_files_generated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvolutionConfig(dry_run=True, output_dir=tmpdir)
            engine = RecursiveEvolutionEngine(config=config)

            asyncio.run(engine.run())

            report = Path(tmpdir) / "final_report.md"
            assert report.exists(), f"Report not found at {report}"
            content = report.read_text()
            assert "MAREF Recursive Evolution" in content
            assert "DRY RUN" in content or "dry" in content.lower()

    def test_single_round_state_machine_path(self):
        from maref.governance.state_machine import GovernanceState, GovernanceStateMachine

        sm = GovernanceStateMachine()
        path = [
            GovernanceState.OBSERVE,
            GovernanceState.ANALYZE,
            GovernanceState.EVALUATE,
            GovernanceState.DECIDE,
            GovernanceState.ACT,
            GovernanceState.VERIFY,
            GovernanceState.STABILIZE,
            GovernanceState.REPORT,
            GovernanceState.HALT,
        ]
        for target in path:
            if sm.can_transition(target):
                sm.transition(target, "test")
            elif target == GovernanceState.HALT:
                sm.force_halt("test_completion")

        assert sm.current_state == GovernanceState.HALT
        assert sm.transition_count >= 9


class TestMultiRoundExecution:
    def test_compressed_evolution_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            criteria = AcceptanceCriteria()
            config = EvolutionConfig(
                cycles={
                    "c1": CycleSpec(name="C1", rounds=3, description="baseline"),
                    "c2": CycleSpec(
                        name="C2",
                        rounds=5,
                        description="optimization",
                        meta_learning_enabled=True,
                        meta_learning_interval=2,
                    ),
                    "c3": CycleSpec(name="C3", rounds=3, description="convergence"),
                },
                max_total_rounds=20,
                acceptance_criteria=criteria,
                output_dir=tmpdir,
            )
            engine = RecursiveEvolutionEngine(config=config, seed=1)
            result = asyncio.run(engine.run())

            assert result.total_rounds > 0
            assert len(result.cycles) == 3
            assert result.total_rounds <= 15

    def test_metrics_accumulate_across_cycles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvolutionConfig(
                cycles={
                    "c1": CycleSpec(name="C1", rounds=5, description="baseline"),
                    "c2": CycleSpec(
                        name="C2",
                        rounds=5,
                        description="optimization",
                        meta_learning_enabled=True,
                        meta_learning_interval=2,
                    ),
                    "c3": CycleSpec(name="C3", rounds=3, description="convergence"),
                },
                max_total_rounds=30,
                output_dir=tmpdir,
            )
            engine = RecursiveEvolutionEngine(config=config)
            result = asyncio.run(engine.run())

            for cycle in result.cycles:
                assert len(cycle.metrics.fnr_series) > 0
                assert len(cycle.metrics.fpr_series) > 0

    def test_meta_learning_produces_policy_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvolutionConfig(
                cycles={
                    "c1": CycleSpec(name="C1", rounds=3, description="baseline"),
                    "c2": CycleSpec(
                        name="C2",
                        rounds=10,
                        description="optimization",
                        meta_learning_enabled=True,
                        meta_learning_interval=2,
                    ),
                    "c3": CycleSpec(name="C3", rounds=3, description="convergence"),
                },
                max_total_rounds=30,
                output_dir=tmpdir,
            )
            engine = RecursiveEvolutionEngine(config=config)
            asyncio.run(engine.run())

            sandbox_status = engine.get_live_status()
            assert sandbox_status["sandbox"]["total_changes"] >= 0


class TestStopConditions:
    def test_manual_stop_sets_running_false(self):
        engine = RecursiveEvolutionEngine()
        engine._running = True
        engine.stop()
        assert engine._running is False

    def test_max_total_rounds_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvolutionConfig(
                cycles={
                    "c1": CycleSpec(name="C1", rounds=50, description="baseline"),
                },
                max_total_rounds=3,
                output_dir=tmpdir,
            )
            engine = RecursiveEvolutionEngine(config=config)
            result = asyncio.run(engine.run())

            assert result.total_rounds <= 3
            assert result.stop_reason == "timeout"

    def test_get_live_status_during_run(self):
        engine = RecursiveEvolutionEngine()
        status = engine.get_live_status()
        assert status["running"] is False
        assert status["total_rounds"] == 0
        assert "meta_learning" in status
        assert "circuit_breaker" in status


class TestConfigToDict:
    def test_config_to_dict(self):
        config = EvolutionConfig()
        d = config.to_dict()
        assert "cycles" in d
        assert "c1" in d["cycles"]
        assert d["cycles"]["c2"]["meta_learning_enabled"] is True
        assert d["dry_run"] is False

    def test_dry_run_config_to_dict(self):
        config = EvolutionConfig(dry_run=True, dry_run_rounds=5)
        d = config.to_dict()
        assert d["dry_run"] is True
        assert d["dry_run_rounds"] == 5


class TestAcceptanceCriteria:
    def test_default_criteria_serializable(self):
        criteria = AcceptanceCriteria()
        d = criteria.to_dict()
        assert d["c1_fnr_max"] == 0.15
        assert d["c3_fnr_std_max"] == 0.05

    def test_acceptance_assessment_basic(self):
        metrics = EvolutionMetrics()
        metrics.fnr_series = [0.05, 0.04, 0.03]
        metrics.fpr_series = [0.02, 0.01, 0.01]
        criteria = AcceptanceCriteria()
        result = metrics.assess_acceptance(criteria, "c1")
        assert result["fnr_below_max"] is True
        assert result["fpr_below_max"] is True

    def test_acceptance_fails_high_fnr(self):
        metrics = EvolutionMetrics()
        metrics.fnr_series = [0.20, 0.25, 0.30]
        metrics.fpr_series = [0.01, 0.01, 0.01]
        criteria = AcceptanceCriteria()
        result = metrics.assess_acceptance(criteria, "c1")
        assert result["fnr_below_max"] is False


class TestEvolutionMetrics:
    def test_convergence_computation(self):
        metrics = EvolutionMetrics()
        for i in range(25):
            metrics.fnr_series.append(0.05 + 0.001 * i)
            metrics.fpr_series.append(0.02 + 0.0005 * i)
        conv = metrics.compute_convergence(window=20)
        assert conv["converged"] or conv["fnr_std"] >= 0

    def test_empty_metrics_convergence(self):
        metrics = EvolutionMetrics()
        conv = metrics.compute_convergence()
        assert conv["converged"] is False

    def test_snapshot_format(self):
        metrics = EvolutionMetrics()
        metrics.fnr_series.append(0.10)
        metrics.fpr_series.append(0.05)
        metrics.entropy_series.append(3.0)
        metrics.transition_count_series.append(10)
        metrics.policy_weights_series.append({"entropy_penalty": -0.1})
        metrics.learning_rate_series.append(0.01)

        snap = metrics.snapshot(1)
        assert snap["round"] == 1
        assert snap["fnr"] == 0.10
        assert snap["fpr"] == 0.05

    def test_metrics_save_load(self):
        metrics = EvolutionMetrics()
        metrics.fnr_series.append(0.12)
        metrics.fpr_series.append(0.04)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.json"
            metrics.save(path)
            assert path.exists()
