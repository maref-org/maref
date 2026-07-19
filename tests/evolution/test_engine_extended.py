from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maref.evolution.engine import (
    EvolutionConfig,
    RecursiveEvolutionEngine,
)
from maref.evolution.metrics import AcceptanceCriteria, CycleSpec
from maref.governance import BreakerState


class TestEvolutionConfigExtended:
    def test_default_config_acceptance_criteria(self):
        config = EvolutionConfig()
        assert isinstance(config.acceptance_criteria, AcceptanceCriteria)
        assert config.acceptance_criteria.c1_fnr_max == 0.15

    def test_custom_acceptance_criteria(self):
        criteria = AcceptanceCriteria(c1_fnr_max=0.20, c2_fpr_budget_pp=0.10)
        config = EvolutionConfig(acceptance_criteria=criteria)
        assert config.acceptance_criteria.c1_fnr_max == 0.20
        assert config.acceptance_criteria.c2_fpr_budget_pp == 0.10

    def test_max_total_rounds_matches_cycle_sum(self):
        config = EvolutionConfig()
        total = sum(c.rounds for c in config.cycles.values())
        assert config.max_total_rounds >= total

    def test_to_dict_acceptance_criteria_serialized(self):
        config = EvolutionConfig()
        d = config.to_dict()
        assert "acceptance_criteria" in d
        assert d["acceptance_criteria"]["c1_fnr_max"] == 0.15

    def test_to_dict_default_output_dir(self):
        config = EvolutionConfig()
        d = config.to_dict()
        assert d["output_dir"] == "./evolution_results/"

    def test_custom_cycle_no_meta_learning(self):
        config = EvolutionConfig(
            cycles={
                "c1": CycleSpec(
                    name="Custom",
                    rounds=10,
                    description="no ml",
                    meta_learning_enabled=False,
                )
            }
        )
        assert config.cycles["c1"].meta_learning_enabled is False
        assert config.cycles["c1"].name == "Custom"
        assert config.cycles["c1"].rounds == 10


class TestEngineInitExtended:
    def test_with_quality_gate(self):
        quality_gate = MagicMock()
        engine = RecursiveEvolutionEngine(quality_gate=quality_gate)
        assert engine.quality_gate is quality_gate

    def test_without_quality_gate_returns_none(self):
        engine = RecursiveEvolutionEngine()
        assert engine.quality_gate is None

    def test_with_metrics_collector(self):
        collector = MagicMock()
        engine = RecursiveEvolutionEngine(metrics_collector=collector)
        assert engine._metrics_collector is collector

    def test_with_none_metrics_collector(self):
        engine = RecursiveEvolutionEngine(metrics_collector=None)
        assert engine._metrics_collector is None

    def test_seed_consistency(self):
        engine1 = RecursiveEvolutionEngine(seed=42)
        engine2 = RecursiveEvolutionEngine(seed=42)
        r1 = engine1._simulate_detector_metrics(0)
        r2 = engine2._simulate_detector_metrics(0)
        assert r1 == r2

    def test_different_seeds_differ(self):
        engine1 = RecursiveEvolutionEngine(seed=1)
        engine2 = RecursiveEvolutionEngine(seed=99)
        r1 = engine1._simulate_detector_metrics(0)
        r2 = engine2._simulate_detector_metrics(0)
        assert r1 != r2

    def test_output_path_from_config(self):
        config = EvolutionConfig(output_dir="/tmp/maref_test/")
        engine = RecursiveEvolutionEngine(config=config)
        assert str(engine._output_base) == "/tmp/maref_test"


class TestQualityGateEvaluation:
    def test_no_quality_gate_returns_approved(self):
        engine = RecursiveEvolutionEngine()
        result = engine.evaluate_candidate_with_quality_gate("agent-1")
        assert result["verdict"] == "approved"
        assert result["reason"] == "no_quality_gate_configured"

    def test_no_quality_gate_returns_for_any_cycle(self):
        engine = RecursiveEvolutionEngine()
        for cycle in ("c1", "c2", "c3", "unknown"):
            result = engine.evaluate_candidate_with_quality_gate("agent-1", cycle=cycle)
            assert result["verdict"] == "approved"

    def test_quality_gate_c1_evaluation(self):
        mock_qg = MagicMock()
        mock_result = MagicMock()
        mock_result.verdict.value = "approved"
        mock_result.score = 85.0
        mock_result.reason = "meets_criteria"
        mock_qg.build_mock_report.return_value = {"report": "mock"}
        mock_qg.evaluate_c1_to_c2.return_value = mock_result

        engine = RecursiveEvolutionEngine(quality_gate=mock_qg)
        result = engine.evaluate_candidate_with_quality_gate(
            "agent-1", cycle="c1", score=85.0
        )

        mock_qg.build_mock_report.assert_called_once_with(
            agent_id="agent-1", score=85.0
        )
        mock_qg.evaluate_c1_to_c2.assert_called_once_with(
            "agent-1", {"report": "mock"}
        )
        assert result["verdict"] == "approved"
        assert result["score"] == 85.0
        assert result["reason"] == "meets_criteria"
        assert result["candidate_id"] == "agent-1"
        assert result["cycle"] == "c1"

    def test_quality_gate_c2_evaluation(self):
        mock_qg = MagicMock()
        mock_result = MagicMock()
        mock_result.verdict.value = "rejected"
        mock_result.score = 60.0
        mock_result.reason = "below_threshold"
        mock_qg.build_mock_report.return_value = {"report": "mock"}
        mock_qg.evaluate_c2_to_c3.return_value = mock_result

        engine = RecursiveEvolutionEngine(quality_gate=mock_qg)
        result = engine.evaluate_candidate_with_quality_gate(
            "agent-2", cycle="c2", score=60.0
        )

        mock_qg.evaluate_c2_to_c3.assert_called_once()
        assert result["verdict"] == "rejected"
        assert result["score"] == 60.0
        assert result["candidate_id"] == "agent-2"

    def test_quality_gate_unknown_cycle(self):
        mock_qg = MagicMock()
        engine = RecursiveEvolutionEngine(quality_gate=mock_qg)
        result = engine.evaluate_candidate_with_quality_gate(
            "agent-3", cycle="c3"
        )
        assert result["verdict"] == "unknown"
        assert "unknown_cycle:c3" in result["reason"]
        # build_mock_report is always called when quality_gate is set
        mock_qg.build_mock_report.assert_called_once_with(
            agent_id="agent-3", score=80.0
        )
        mock_qg.evaluate_c1_to_c2.assert_not_called()
        mock_qg.evaluate_c2_to_c3.assert_not_called()


class TestCollectDetectorMetrics:
    def test_simulated_mode_returns_correct_structure(self):
        config = EvolutionConfig(metrics_mode="simulated")
        engine = RecursiveEvolutionEngine(config=config, seed=42)
        fnr, fpr, source, real_metrics = engine._collect_detector_metrics(0)
        assert source == "simulated"
        assert real_metrics == {}
        assert isinstance(fnr, float)
        assert isinstance(fpr, float)

    @patch("maref.evolution.real_metrics.RealMetricsCollector")
    def test_real_mode_without_collector_lazy_init(self, mock_collector_cls):
        mock_collector = MagicMock()
        mock_metrics = MagicMock()
        mock_metrics.fnr = 0.05
        mock_metrics.fpr = 0.02
        mock_metrics.to_dict.return_value = {"fnr": 0.05, "fpr": 0.02}
        mock_collector.collect_incremental.return_value = mock_metrics
        mock_collector_cls.return_value = mock_collector

        config = EvolutionConfig(metrics_mode="real")
        engine = RecursiveEvolutionEngine(config=config)
        fnr, fpr, source, real_metrics = engine._collect_detector_metrics(0)

        assert source == "real"
        assert fnr == 0.05
        assert fpr == 0.02
        assert real_metrics == {"fnr": 0.05, "fpr": 0.02}
        mock_collector_cls.assert_called_once()
        assert engine._metrics_collector is mock_collector

    def test_real_mode_with_existing_collector(self):
        mock_collector = MagicMock()
        mock_metrics = MagicMock()
        mock_metrics.fnr = 0.03
        mock_metrics.fpr = 0.01
        mock_metrics.to_dict.return_value = {"fnr": 0.03, "fpr": 0.01}
        mock_collector.collect_incremental.return_value = mock_metrics

        config = EvolutionConfig(metrics_mode="real")
        engine = RecursiveEvolutionEngine(
            config=config, metrics_collector=mock_collector
        )
        fnr, fpr, source, real_metrics = engine._collect_detector_metrics(0)

        assert source == "real"
        assert fnr == 0.03
        assert fpr == 0.01

    def test_simulated_metrics_fnr_in_range(self):
        engine = RecursiveEvolutionEngine(seed=42)
        for r in range(50):
            fnr, fpr = engine._simulate_detector_metrics(r)
            assert 0.0 <= fnr <= 0.30
            assert 0.0 <= fpr <= 0.20


class TestStopConditionsExtended:
    def test_gradient_disaster_edge_exact_five(self):
        metrics = MagicMock()
        metrics.fnr_series = [0.60, 0.61, 0.62, 0.63, 0.64]
        engine = RecursiveEvolutionEngine()
        result = engine._check_stop_conditions(metrics, "c1")
        assert result == "gradient_disaster"

    def test_gradient_disaster_not_triggered_with_low_fnr(self):
        metrics = MagicMock()
        metrics.fnr_series = [0.10, 0.12, 0.11, 0.09, 0.10]
        engine = RecursiveEvolutionEngine()
        result = engine._check_stop_conditions(metrics, "c1")
        assert result is None

    def test_gradient_disaster_mixed_fnr(self):
        metrics = MagicMock()
        metrics.fnr_series = [0.60, 0.10, 0.60, 0.60, 0.60]
        engine = RecursiveEvolutionEngine()
        result = engine._check_stop_conditions(metrics, "c1")
        assert result is None

    def test_circuit_breaker_below_limit(self):
        metrics = MagicMock()
        metrics.fnr_series = [0.10]
        engine = RecursiveEvolutionEngine()
        with patch.object(
            engine._breaker, "get_stats",
            return_value={"state": BreakerState.OPEN.value, "trip_count": 2},
        ):
            result = engine._check_stop_conditions(metrics, "c1")
        assert result is None

    def test_both_stop_conditions_none(self):
        metrics = MagicMock()
        metrics.fnr_series = [0.10, 0.11, 0.09, 0.10, 0.12]
        engine = RecursiveEvolutionEngine()
        with patch.object(
            engine._breaker, "get_stats",
            return_value={"state": BreakerState.CLOSED.value},
        ):
            result = engine._check_stop_conditions(metrics, "c1")
        assert result is None


class TestGetLiveStatusExtended:
    def test_initial_status_structure(self):
        engine = RecursiveEvolutionEngine()
        status = engine.get_live_status()
        assert isinstance(status["running"], bool)
        assert isinstance(status["total_rounds"], int)
        assert "meta_learning" in status
        assert "sandbox" in status
        assert "circuit_breaker" in status

    def test_status_reflects_running_state(self):
        engine = RecursiveEvolutionEngine()
        engine._running = True
        engine._total_rounds = 10
        status = engine.get_live_status()
        assert status["running"] is True
        assert status["total_rounds"] == 10

    def test_status_reflects_stopped_state(self):
        engine = RecursiveEvolutionEngine()
        engine._running = True
        engine.stop()
        status = engine.get_live_status()
        assert status["running"] is False


class TestStopDuringRunExt:
    def test_manual_stop_mid_loop(self):
        config = EvolutionConfig(
            cycles={"c1": CycleSpec(name="C1", rounds=100, description="baseline")},
        )
        engine = RecursiveEvolutionEngine(config=config)

        async def mock_round(*args, **kwargs):
            engine._running = False
            return {
                "round": 0,
                "fnr": 0.1,
                "fpr": 0.05,
                "final_entropy": 0,
                "entropy_sequence": [0],
                "transition_count": 9,
                "failed_transitions": 0,
                "total_attempts": 9,
                "halt_reason": "normal",
                "final_state": "HALT",
                "metrics_source": "simulated",
                "real_metrics": {},
            }

        engine._run_one_round = mock_round
        import asyncio
        result = asyncio.run(engine.run())
        assert result.stop_reason == "manual_stop"

    def test_timeout_on_max_rounds(self):
        config = EvolutionConfig(
            cycles={"c1": CycleSpec(name="C1", rounds=50, description="baseline")},
            max_total_rounds=1,
        )
        engine = RecursiveEvolutionEngine(config=config, seed=42)
        import asyncio
        result = asyncio.run(engine.run())
        assert result.stop_reason == "timeout"
        assert result.total_rounds <= 1


class TestMetaLearningStepExtended:
    def test_high_reward_approves_change(self):
        engine = RecursiveEvolutionEngine()
        mock_learner = MagicMock()
        mock_learner.record_decision.return_value = None
        mock_learner.optimize_policy.return_value = {"threshold": 0.1}
        mock_learner.get_stats.return_value = {"avg_reward": 0.8}
        engine._meta_learner = mock_learner

        mock_sandbox = MagicMock()
        mock_change = MagicMock()
        mock_change.change_id = "ch_001"
        mock_sandbox.propose_change.return_value = mock_change
        engine._sandbox = mock_sandbox

        engine._run_meta_learning_step(5, 0.08)
        mock_learner.record_decision.assert_called_once()
        mock_learner.optimize_policy.assert_called_once()
        mock_sandbox.propose_change.assert_called_once()
        mock_sandbox.approve_change.assert_called_once_with(
            "ch_001", reviewer="meta_recursive_evolution"
        )

    def test_low_reward_skips_approve(self):
        engine = RecursiveEvolutionEngine()
        mock_learner = MagicMock()
        mock_learner.record_decision.return_value = None
        mock_learner.optimize_policy.return_value = {"threshold": 0.1}
        mock_learner.get_stats.return_value = {"avg_reward": 0.2}
        engine._meta_learner = mock_learner

        mock_sandbox = MagicMock()
        mock_change = MagicMock()
        mock_change.change_id = "ch_002"
        mock_sandbox.propose_change.return_value = mock_change
        engine._sandbox = mock_sandbox

        engine._run_meta_learning_step(5, 0.30)
        mock_sandbox.propose_change.assert_called_once()
        mock_sandbox.approve_change.assert_not_called()

    def test_no_new_config_skips_sandbox(self):
        engine = RecursiveEvolutionEngine()
        mock_learner = MagicMock()
        mock_learner.record_decision.return_value = None
        mock_learner.optimize_policy.return_value = None
        engine._meta_learner = mock_learner

        mock_sandbox = MagicMock()
        engine._sandbox = mock_sandbox

        engine._run_meta_learning_step(5, 0.08)
        mock_sandbox.propose_change.assert_not_called()


class TestCollectRoundMetricsExtended:
    def test_all_fields_updated(self):
        metrics = MagicMock()
        engine = RecursiveEvolutionEngine()
        snapshot = {
            "fnr": 0.12,
            "fpr": 0.04,
            "final_entropy": 2,
            "transition_count": 9,
            "halt_reason": "normal_completion",
        }
        engine._collect_round_metrics(metrics, snapshot)
        metrics.fnr_series.append.assert_called_with(0.12)
        metrics.fpr_series.append.assert_called_with(0.04)
        metrics.entropy_series.append.assert_called_with(2)
        metrics.transition_count_series.append.assert_called_with(9)
        metrics.halt_reasons.append.assert_called_with("normal_completion")
        metrics.policy_weights_series.append.assert_called_once()
        metrics.learning_rate_series.append.assert_called_once()


class TestSimulateDetectorMetricsExtended:
    def test_metrics_vary_by_round(self):
        engine = RecursiveEvolutionEngine(seed=42)
        results = [engine._simulate_detector_metrics(r) for r in range(10)]
        fnrs = [r[0] for r in results]
        fprs = [r[1] for r in results]
        assert len(set(fnrs)) > 1
        assert len(set(fprs)) > 1

    def test_seeded_reproducibility(self):
        e1 = RecursiveEvolutionEngine(seed=42)
        e2 = RecursiveEvolutionEngine(seed=42)
        for r in range(20):
            assert e1._simulate_detector_metrics(r) == e2._simulate_detector_metrics(r)
