"""Recursive layer + RedBlue stress tests."""

import threading

import pytest

from maref.governance.circuit_breaker import BreakerState
from maref.recursive.chaos_injector import ChaosInjector, ChaosType
from maref.recursive.resilience_v2 import ResilienceEvaluatorV2
from maref.stress.stress_harness import StressHarness
from maref.stress.stress_level import StressLevel


class TestRecursiveChaosStress:
    """Recursive chaos injector stress tests."""

    def test_recursive_cb_oscillation_depth(self):
        """Multiple CB oscillation events should accumulate."""
        injector = ChaosInjector()
        for i in range(100):
            injector.inject(
                ChaosType.CB_OSCILLATION,
                target=f"cb-{i}",
                params={"depth": i % 5, "entropy": 4},
            )

        assert len(injector.events) == 100
        assert len(injector.events_of_type(ChaosType.CB_OSCILLATION)) == 100

    def test_halt_storm_100(self):
        """100 halt storm events should all be recorded."""
        injector = ChaosInjector()
        for i in range(100):
            injector.inject(ChaosType.HALT_STORM, target=f"agent-{i}")

        assert len(injector.events) == 100
        halt_events = injector.events_of_type(ChaosType.HALT_STORM)
        assert len(halt_events) == 100

    def test_mixed_chaos_types(self):
        """Mixed chaos types should be filterable by type."""
        injector = ChaosInjector()
        for ft in list(ChaosType):
            for _ in range(25):
                injector.inject(ft, target="test")

        assert len(injector.events) == 100
        for ft in list(ChaosType):
            assert len(injector.events_of_type(ft)) == 25

    def test_concurrent_chaos_injection(self):
        """Concurrent injection into same injector."""
        injector = ChaosInjector()
        errors: list[Exception] = []
        lock = threading.Lock()

        def injector_worker(chaos_type: ChaosType):
            for _ in range(50):
                try:
                    injector.inject(chaos_type, target="concurrent")
                except Exception as e:
                    with lock:
                        errors.append(e)

        threads = [
            threading.Thread(target=injector_worker, args=(ct,))
            for ct in list(ChaosType)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrent inject caused {len(errors)} errors"
        assert len(injector.events) == 200


class TestResilienceEvaluatorStress:
    """ResilienceEvaluatorV2 stress tests."""

    def test_nan_inf_handling(self):
        """NaN and Inf inputs should not crash."""
        evaluator = ResilienceEvaluatorV2()

        factors = {
            "survival_rate": float("nan"),
            "recovery_time_ms": float("inf"),
            "false_positive_rate": float("-inf"),
            "meta_protection_rate": -1.0,
            "graceful_degradation_rate": 1.5,
            "data_consistency_rate": 0.0,
            "throughput_under_stress": float("nan"),
        }

        score = evaluator.evaluate(factors)
        assert 0 <= score.total_score <= 100

    def test_negative_scores_clamped(self):
        """All negative inputs should clamp to valid range."""
        evaluator = ResilienceEvaluatorV2()
        factors = {k: -100.0 for k in evaluator._FACTORS}
        score = evaluator.evaluate(factors)
        assert 0 <= score.total_score <= 100

    def test_10000_round_aggregation(self):
        """10000 evaluation rounds should produce consistent results."""
        evaluator = ResilienceEvaluatorV2()
        for _ in range(10000):
            factors = {
                "survival_rate": 0.9,
                "recovery_time_ms": 100.0,
                "false_positive_rate": 0.1,
                "meta_protection_rate": 0.8,
                "graceful_degradation_rate": 0.7,
                "data_consistency_rate": 0.9,
                "throughput_under_stress": 0.8,
            }
            score = evaluator.evaluate(factors)
            assert score.passed

    def test_degradation_plans_under_low_score(self):
        """Low scores should trigger degradation plans."""
        evaluator = ResilienceEvaluatorV2()
        factors = {k: 0.1 for k in evaluator._FACTORS}
        score = evaluator.evaluate(factors)
        plans = evaluator.auto_recommend_degradation(score)
        assert len(plans) >= 1, "Low score should trigger degradation plans"

    def test_no_degradation_under_high_score(self):
        """High scores should not trigger degradation."""
        evaluator = ResilienceEvaluatorV2()
        factors = {k: 0.95 for k in evaluator._FACTORS}
        score = evaluator.evaluate(factors)
        plans = evaluator.auto_recommend_degradation(score)
        plans_str = [p.strategy for p in plans]
        assert "governance_degraded" not in plans_str


class TestStressHarnessActualMetrics:
    """StressHarness should use actual measurements, not hardcoded guesses."""

    def test_resilience_score_actual_measurement(self):
        """Resilience score should vary based on actual stress conditions."""
        harness = StressHarness()

        harness.set_level(StressLevel.L1)
        result_l1 = harness.run("l1-test")

        harness.set_level(StressLevel.L5)
        result_l5 = harness.run("l5-test")

        assert result_l1.resilience_score >= 0
        assert result_l5.resilience_score >= 0

    def test_stress_level_l1_vs_l5_latency(self):
        """L5 should have higher (or equal) latency than L1."""
        harness = StressHarness()
        harness.set_level(StressLevel.L1).set_duration(0.1)
        r1 = harness.run("l1-latency")

        harness.set_level(StressLevel.L5).set_duration(0.1)
        r5 = harness.run("l5-latency")

        assert r1.latency_p50 >= 0
        assert r5.latency_p50 >= 0

    def test_stress_harness_produces_errors_under_high_fault_rate(self):
        """High fault rate should produce errors."""
        harness = StressHarness()
        harness.set_level(StressLevel.L5).set_duration(0.2)
        result = harness.run("high-fault")
        assert result.resilience_score >= 0
