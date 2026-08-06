from __future__ import annotations

import asyncio
from typing import Any
from unittest import mock

import pytest

from maref.evolution.engine import EvolutionConfig, RecursiveEvolutionEngine


class TestEvolutionConfig:
    def test_default_config(self) -> None:
        config = EvolutionConfig()
        assert config.max_total_rounds == 300
        assert config.dry_run is False
        assert config.output_dir == "./evolution_results/"

    def test_to_dict(self) -> None:
        config = EvolutionConfig()
        d = config.to_dict()
        assert "cycles" in d
        assert "c1" in d["cycles"]
        assert d["cycles"]["c1"]["rounds"] == 50
        assert "acceptance_criteria" in d

    def test_dry_run_rounds(self) -> None:
        config = EvolutionConfig(dry_run=True, dry_run_rounds=3)
        assert config.dry_run is True
        assert config.dry_run_rounds == 3


class TestRecursiveEvolutionEngine:
    def test_init_defaults(self) -> None:
        engine = RecursiveEvolutionEngine()
        assert engine.quality_gate is None

    def test_quality_gate_none(self) -> None:
        engine = RecursiveEvolutionEngine()
        result = engine.evaluate_candidate_with_quality_gate("candidate_1")
        assert result["verdict"] == "approved"
        assert result["reason"] == "no_quality_gate_configured"

    def test_quality_gate_with_unknown_cycle(self) -> None:
        qg = mock.Mock()
        engine = RecursiveEvolutionEngine()
        engine._quality_gate = qg
        result = engine.evaluate_candidate_with_quality_gate("cand", cycle="c4")
        assert result["verdict"] == "unknown"

    def test_stop_sets_running_false(self) -> None:
        engine = RecursiveEvolutionEngine()
        engine._running = True
        engine.stop()
        assert engine._running is False

    def test_get_live_status(self) -> None:
        engine = RecursiveEvolutionEngine()
        status = engine.get_live_status()
        assert "running" in status
        assert "total_rounds" in status
        assert "meta_learning" in status
        assert "sandbox" in status
        assert "circuit_breaker" in status

    def test_noop_stabilize(self) -> None:
        assert RecursiveEvolutionEngine._noop_stabilize() is True
        assert RecursiveEvolutionEngine._noop_stabilize("test") is True

    def test_evaluate_candidate_c1(self) -> None:
        qg = mock.MagicMock()
        qg.build_mock_report.return_value = {"score": 80}

        class MockVerdict:
            value = "approved"

        class MockResult:
            verdict = MockVerdict()
            score = 80
            reason = "good"

        qg.evaluate_c1_to_c2.return_value = MockResult()
        engine = RecursiveEvolutionEngine()
        engine._quality_gate = qg
        result = engine.evaluate_candidate_with_quality_gate("cand", cycle="c1")
        assert result["verdict"] == "approved"

    def test_evaluate_candidate_c2(self) -> None:
        qg = mock.MagicMock()
        qg.build_mock_report.return_value = {"score": 85}

        class MockVerdict:
            value = "approved"

        class MockResult:
            verdict = MockVerdict()
            score = 85
            reason = "good"

        qg.evaluate_c2_to_c3.return_value = MockResult()
        engine = RecursiveEvolutionEngine()
        engine._quality_gate = qg
        result = engine.evaluate_candidate_with_quality_gate("cand", cycle="c2")
        assert result["verdict"] == "approved"


class TestEngineRun:
    @pytest.mark.asyncio
    async def test_run_one_round_uses_injected_real_metrics(self) -> None:
        class FakeMetricsCollector:
            def __init__(self) -> None:
                self.calls = 0

            def collect_incremental(self) -> Any:
                from maref.evolution.real_metrics import RealMetrics

                self.calls += 1
                return RealMetrics(
                    fnr=0.02,
                    fpr=0.01,
                    test_pass_rate=0.98,
                    coverage_pct=80.0,
                    total_tests=50,
                    import_time_ms=100.0,
                    cb_state="CLOSED",
                )

        config = EvolutionConfig(dry_run=True, metrics_mode="real")
        collector = FakeMetricsCollector()
        engine = RecursiveEvolutionEngine(config=config, metrics_collector=collector)
        engine._running = True

        snapshot = await engine._run_one_round("c1", 0, config.cycles["c1"])

        assert snapshot["fnr"] == 0.02
        assert snapshot["fpr"] == 0.01
        assert snapshot["metrics_source"] == "real"
        assert snapshot["real_metrics"]["test_pass_rate"] == 0.98
        assert collector.calls == 1

    @pytest.mark.asyncio
    async def test_dry_run_completes(self) -> None:
        config = EvolutionConfig(dry_run=True)
        engine = RecursiveEvolutionEngine(config)
        result = await engine.run()
        assert result.stop_reason == "dry_run_complete"
        assert result.total_rounds == 1

    @pytest.mark.asyncio
    async def test_resume_from_c2(self) -> None:
        config = EvolutionConfig(resume_from_cycle="c2")
        engine = RecursiveEvolutionEngine(config)
        await engine.run()
        assert engine._total_rounds > 0

    @pytest.mark.asyncio
    async def test_cancelled_error_stops(self) -> None:
        config = EvolutionConfig(max_total_rounds=300)
        engine = RecursiveEvolutionEngine(config)
        with mock.patch.object(engine, "_run_one_round", side_effect=asyncio.CancelledError()):
            result = await engine.run()
            assert result.stop_reason == "manual_stop"

    @pytest.mark.asyncio
    async def test_timeout_stops(self) -> None:
        config = EvolutionConfig(max_total_rounds=0)
        engine = RecursiveEvolutionEngine(config)
        result = await engine.run()
        assert result.stop_reason == "timeout"
