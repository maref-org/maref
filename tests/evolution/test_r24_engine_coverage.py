from __future__ import annotations

import asyncio
import tempfile
from unittest.mock import MagicMock

import pytest

from maref.evolution.engine import (
    BREAKER_FAIL_CONSECUTIVE_LIMIT,
    CANONICAL_PATH,
    EvolutionConfig,
    RecursiveEvolutionEngine,
)
from maref.evolution.metrics import CycleSpec, EvolutionMetrics
from maref.governance import BreakerState, GovernanceState


class TestNoopStabilize:
    def test_noop_stabilize(self) -> None:
        assert RecursiveEvolutionEngine._noop_stabilize("reason") is True
        assert RecursiveEvolutionEngine._noop_stabilize() is True


class TestStopDuringRun:
    def test_manual_stop_during_execution(self) -> None:
        engine = RecursiveEvolutionEngine()
        engine._running = True
        engine.stop()
        assert engine._running is False

    @pytest.mark.asyncio
    async def test_cancelled_error_in_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvolutionConfig(
                cycles={"c1": CycleSpec(name="C1", rounds=5, description="baseline")},
                max_total_rounds=10,
                output_dir=tmpdir,
            )
            engine = RecursiveEvolutionEngine(config=config, seed=1)
            original_run_one_round = engine._run_one_round
            call_count = [0]

            async def _raise_cancelled(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] >= 3:
                    raise asyncio.CancelledError()
                return await original_run_one_round(*args, **kwargs)

            engine._run_one_round = _raise_cancelled
            result = await engine.run()
            assert result.stop_reason == "manual_stop"

    @pytest.mark.asyncio
    async def test_unexpected_exception_in_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvolutionConfig(
                cycles={"c1": CycleSpec(name="C1", rounds=5, description="baseline")},
                max_total_rounds=10,
                output_dir=tmpdir,
            )
            engine = RecursiveEvolutionEngine(config=config, seed=1)
            call_count = [0]

            async def _raise_on_third(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] >= 3:
                    raise RuntimeError("unexpected")
                return {
                    "round": call_count[0],
                    "fnr": 0.1,
                    "fpr": 0.05,
                    "final_entropy": 0,
                    "entropy_sequence": [0],
                    "transition_count": 9,
                    "failed_transitions": 0,
                    "total_attempts": 9,
                    "halt_reason": "normal",
                    "final_state": "HALT",
                }

            engine._run_one_round = _raise_on_third
            engine._collect_round_metrics = MagicMock()

            with pytest.raises(RuntimeError, match="unexpected"):
                await engine.run()


class TestRunOneRoundEdgeCases:
    def test_force_halt_when_cannot_transition_to_halt(self) -> None:
        from maref.governance.state_machine import GovernanceStateMachine

        sm = GovernanceStateMachine()
        for target in CANONICAL_PATH:
            if target != GovernanceState.HALT:
                sm.transition(target, "test")
        sm.force_halt("normal_completion")
        assert sm.current_state == GovernanceState.HALT

    def test_force_halt_at_round_end(self) -> None:
        from maref.governance.state_machine import GovernanceStateMachine

        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "test")
        assert sm.current_state != GovernanceState.HALT
        sm.force_halt("round_end")
        assert sm.current_state == GovernanceState.HALT


class TestStopConditions:
    def test_gradient_disaster_with_high_fnr(self) -> None:
        metrics = EvolutionMetrics()
        for _ in range(10):
            metrics.fnr_series.append(0.60)
            metrics.fpr_series.append(0.02)

        from maref.evolution.engine import RecursiveEvolutionEngine
        engine = RecursiveEvolutionEngine()
        result = engine._check_stop_conditions(metrics, "c1")
        assert result == "gradient_disaster"

    def test_gradient_disaster_not_triggered_low_fnr(self) -> None:
        metrics = EvolutionMetrics()
        for _ in range(10):
            metrics.fnr_series.append(0.10)
            metrics.fpr_series.append(0.02)

        engine = RecursiveEvolutionEngine()
        result = engine._check_stop_conditions(metrics, "c1")
        assert result is None

    def test_circuit_breaker_permanent_open(self) -> None:
        metrics = EvolutionMetrics()
        engine = RecursiveEvolutionEngine()
        engine._breaker._state = BreakerState.OPEN
        engine._breaker._trip_count = BREAKER_FAIL_CONSECUTIVE_LIMIT
        engine._breaker._consecutive_failures = BREAKER_FAIL_CONSECUTIVE_LIMIT
        engine._breaker.get_stats = MagicMock(return_value={
            "state": BreakerState.OPEN.value,
            "trip_count": BREAKER_FAIL_CONSECUTIVE_LIMIT,
        })
        result = engine._check_stop_conditions(metrics, "c1")
        assert result == "circuit_breaker_permanent_open"

    def test_circuit_breaker_open_but_below_limit(self) -> None:
        metrics = EvolutionMetrics()
        engine = RecursiveEvolutionEngine()
        engine._breaker._state = BreakerState.OPEN
        engine._breaker._trip_count = 1

        result = engine._check_stop_conditions(metrics, "c1")
        assert result is None

    def test_check_stop_conditions_normal(self) -> None:
        metrics = EvolutionMetrics()
        engine = RecursiveEvolutionEngine()
        result = engine._check_stop_conditions(metrics, "c1")
        assert result is None


class TestResumeFromCycle:
    def test_resume_from_cycle_skips_earlier(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvolutionConfig(
                cycles={
                    "c1": CycleSpec(name="C1", rounds=2, description="baseline"),
                    "c2": CycleSpec(name="C2", rounds=2, description="optimization"),
                    "c3": CycleSpec(name="C3", rounds=2, description="convergence"),
                },
                max_total_rounds=10,
                resume_from_cycle="c2",
                resume_from_round=0,
                output_dir=tmpdir,
            )
            engine = RecursiveEvolutionEngine(config=config, seed=1)
            result = asyncio.run(engine.run())
            assert len(result.cycles) == 2
            assert result.cycles[0].cycle_id == "c2"

    def test_resume_from_cycle_with_round_offset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvolutionConfig(
                cycles={
                    "c1": CycleSpec(name="C1", rounds=2, description="baseline"),
                    "c2": CycleSpec(name="C2", rounds=5, description="optimization"),
                    "c3": CycleSpec(name="C3", rounds=2, description="convergence"),
                },
                max_total_rounds=10,
                resume_from_cycle="c2",
                resume_from_round=3,
                output_dir=tmpdir,
            )
            engine = RecursiveEvolutionEngine(config=config, seed=1)
            result = asyncio.run(engine.run())
            assert len(result.cycles) >= 1


class TestSimulateDetectorMetrics:
    def test_metrics_in_valid_range(self) -> None:
        engine = RecursiveEvolutionEngine(seed=42)
        for r in range(100):
            fnr, fpr = engine._simulate_detector_metrics(r)
            assert 0.0 <= fnr <= 0.30
            assert 0.0 <= fpr <= 0.20

    def test_metrics_vary_across_rounds(self) -> None:
        engine = RecursiveEvolutionEngine(seed=42)
        fnrs = [engine._simulate_detector_metrics(r)[0] for r in range(20)]
        assert len(set(fnrs)) > 1


class TestMetaLearningStep:
    def test_meta_learning_with_high_reward_approves(self) -> None:
        engine = RecursiveEvolutionEngine()
        engine._meta_learner._state.avg_reward = 0.8
        engine._meta_learner.record_decision = MagicMock()
        engine._meta_learner.optimize_policy = MagicMock(return_value={"threshold": 0.1})
        engine._meta_learner.get_stats = MagicMock(return_value={"avg_reward": 0.8})

        mock_sandbox = MagicMock()
        mock_change = MagicMock()
        mock_change.change_id = "ch_001"
        mock_sandbox.propose_change.return_value = mock_change
        engine._sandbox = mock_sandbox

        engine._run_meta_learning_step(5, 0.08)
        mock_sandbox.approve_change.assert_called_once_with("ch_001", reviewer="meta_recursive_evolution")

    def test_meta_learning_with_low_reward_skips_approve(self) -> None:
        engine = RecursiveEvolutionEngine()
        engine._meta_learner._state.avg_reward = 0.2
        engine._meta_learner.record_decision = MagicMock()
        engine._meta_learner.optimize_policy = MagicMock(return_value={"threshold": 0.1})
        engine._meta_learner.get_stats = MagicMock(return_value={"avg_reward": 0.2})

        mock_sandbox = MagicMock()
        mock_change = MagicMock()
        mock_change.change_id = "ch_002"
        mock_sandbox.propose_change.return_value = mock_change
        engine._sandbox = mock_sandbox

        engine._run_meta_learning_step(5, 0.30)
        mock_sandbox.approve_change.assert_not_called()

    def test_meta_learning_no_new_config(self) -> None:
        engine = RecursiveEvolutionEngine()
        engine._meta_learner.record_decision = MagicMock()
        engine._meta_learner.optimize_policy = MagicMock(return_value=None)

        mock_sandbox = MagicMock()
        engine._sandbox = mock_sandbox

        engine._run_meta_learning_step(5, 0.08)
        mock_sandbox.propose_change.assert_not_called()


class TestCollectRoundMetrics:
    def test_collect_appends_all_series(self) -> None:
        metrics = EvolutionMetrics()
        engine = RecursiveEvolutionEngine()
        snapshot = {
            "round": 0,
            "fnr": 0.12,
            "fpr": 0.04,
            "final_entropy": 0,
            "entropy_sequence": [0, 0, 0],
            "transition_count": 9,
            "failed_transitions": 0,
            "total_attempts": 9,
            "halt_reason": "normal_completion",
            "final_state": "HALT",
        }
        engine._collect_round_metrics(metrics, snapshot)

        assert len(metrics.fnr_series) == 1
        assert metrics.fnr_series[0] == 0.12
        assert len(metrics.fpr_series) == 1
        assert metrics.fpr_series[0] == 0.04
        assert len(metrics.entropy_series) == 1
        assert len(metrics.transition_count_series) == 1
        assert len(metrics.halt_reasons) == 1
        assert len(metrics.policy_weights_series) == 1
        assert len(metrics.learning_rate_series) == 1
