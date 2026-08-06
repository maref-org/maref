from __future__ import annotations

import pytest

from maref.recursive.self_observer import SystemSnapshot
from maref.recursive.self_optimizer import (
    BenchmarkResult,
    OptimizationHypothesis,
    SelfOptimizer,
)


def _mock_benchmark() -> dict[str, float]:
    return {
        "test_count": 678.0,
        "coverage_pct": 83.0,
        "execution_time_ms": 26000.0,
        "tests_passed": 650.0,
        "tests_failed": 28.0,
    }


def _mock_benchmark_improved() -> dict[str, float]:
    return {
        "test_count": 678.0,
        "coverage_pct": 88.0,
        "execution_time_ms": 24000.0,
        "tests_passed": 670.0,
        "tests_failed": 8.0,
    }


def _mock_benchmark_regressed() -> dict[str, float]:
    return {
        "test_count": 650.0,
        "coverage_pct": 75.0,
        "execution_time_ms": 32000.0,
        "tests_passed": 600.0,
        "tests_failed": 50.0,
    }


class TestSelfOptimizer:
    @pytest.fixture
    def optimizer(self) -> SelfOptimizer:
        return SelfOptimizer(adopt_threshold=0.05, benchmark_fn=_mock_benchmark)

    @pytest.fixture
    def large_snapshot(self) -> SystemSnapshot:
        deps = {f"module_{i}": [f"dep_{j}" for j in range(5)] for i in range(10)}
        return SystemSnapshot(
            module_graph=deps,
            source_file_count=50,
            test_stats={"total": 678},
            git_stats={"tags": []},
        )

    def test_propose_optimizations_generates_hypotheses(
        self,
        optimizer: SelfOptimizer,
        large_snapshot: SystemSnapshot,
    ) -> None:
        hypotheses = optimizer.propose_optimizations(large_snapshot)
        assert len(hypotheses) >= 3

    def test_propose_small_snapshot(self, optimizer: SelfOptimizer) -> None:
        snapshot = SystemSnapshot(
            module_graph={"a": ["b"]},
            source_file_count=5,
            test_stats={"total": 100},
            git_stats={"tags": []},
        )
        hypotheses = optimizer.propose_optimizations(snapshot)
        assert len(hypotheses) >= 1

    def test_run_experiment_produces_benchmark(self, optimizer: SelfOptimizer) -> None:
        hyp = OptimizationHypothesis(
            hypothesis_id="test-1",
            description="test",
            target_module="test",
        )
        result = optimizer.run_experiment(hyp)
        assert isinstance(result, BenchmarkResult)
        assert "test_count" in result.before
        assert result.before["coverage_pct"] == 83.0

    def test_run_experiment_with_apply_fn(self) -> None:
        call_count = [0]
        improved = [False]

        def mock_before() -> dict[str, float]:
            return _mock_benchmark()

        def mock_after() -> dict[str, float]:
            return _mock_benchmark_improved()

        def apply_fn() -> None:
            call_count[0] += 1
            improved[0] = True

        opt = SelfOptimizer(adopt_threshold=0.05, benchmark_fn=mock_before)
        hyp = OptimizationHypothesis(
            hypothesis_id="test-apply",
            description="test with apply",
            target_module="test",
        )
        result = opt.run_experiment(hyp, apply_fn=apply_fn)
        assert call_count[0] == 1
        assert result.before["coverage_pct"] == 83.0
        assert result.after["coverage_pct"] == 83.0

    def test_adopt_if_gain_above_threshold(self, optimizer: SelfOptimizer) -> None:
        hyp = OptimizationHypothesis(
            hypothesis_id="test-1",
            description="test",
            target_module="test",
            gain_pct=0.10,
        )
        adopted = optimizer.adopt_if_gain(hyp)
        assert adopted is True
        assert hyp.adopted is True
        assert len(optimizer.adopted) == 1

    def test_adopt_if_gain_below_threshold(self, optimizer: SelfOptimizer) -> None:
        hyp = OptimizationHypothesis(
            hypothesis_id="test-2",
            description="test",
            target_module="test",
            gain_pct=0.01,
        )
        adopted = optimizer.adopt_if_gain(hyp)
        assert adopted is False

    def test_revert_if_regression(self, optimizer: SelfOptimizer) -> None:
        hyp = OptimizationHypothesis(
            hypothesis_id="test-3",
            description="test",
            target_module="test",
            gain_pct=-0.05,
        )
        reverted = optimizer.revert_if_regression(hyp)
        assert reverted is True
        assert hyp.reverted is True
        assert hyp.adopted is False

    def test_no_revert_if_positive(self, optimizer: SelfOptimizer) -> None:
        hyp = OptimizationHypothesis(
            hypothesis_id="test-4",
            description="test",
            target_module="test",
            gain_pct=0.05,
        )
        reverted = optimizer.revert_if_regression(hyp)
        assert reverted is False

    def test_negative_gain_allowed(self, optimizer: SelfOptimizer) -> None:
        hyp = OptimizationHypothesis(
            hypothesis_id="test-neg",
            description="test negative gain",
            target_module="test",
        )
        result = optimizer.run_experiment(hyp)
        assert result.gain_pct == 0.0

    def test_full_cycle(self, optimizer: SelfOptimizer, large_snapshot: SystemSnapshot) -> None:
        hypotheses = optimizer.propose_optimizations(large_snapshot)
        for hyp in hypotheses[:1]:
            result = optimizer.run_experiment(hyp)
            assert isinstance(result, BenchmarkResult)
            if hyp.gain_pct >= 0.05:
                optimizer.adopt_if_gain(hyp)
            if hyp.gain_pct < 0:
                optimizer.revert_if_regression(hyp)
        assert len(optimizer.hypotheses) >= 3

    def test_benchmark_result_fields(self) -> None:
        result = BenchmarkResult(
            before={"test_count": 100.0, "coverage_pct": 80.0},
            after={"test_count": 100.0, "coverage_pct": 85.0},
            gain_pct=0.0625,
        )
        assert result.gain_pct > 0
        assert result.before["test_count"] == 100.0

    @pytest.mark.skip(reason="real benchmark requires full pytest run, tested in integration")
    def test_real_benchmark_integration(self) -> None:
        from maref.recursive.self_optimizer import _run_real_benchmark

        result = _run_real_benchmark(
            timeout=30, test_path="tests/recursive/test_r4_optimization.py"
        )
        assert "test_count" in result
        assert isinstance(result["test_count"], float)
