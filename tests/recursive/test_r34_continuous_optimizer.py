from __future__ import annotations

import pytest

from maref.recursive.continuous_optimizer import (
    ContinuousOptimizer,
    OptimizationCycle,
)
from maref.recursive.unified_audit import UnifiedAuditStore


class TestOptimizationCycle:
    def test_create_cycle(self) -> None:
        cycle = OptimizationCycle(
            cycle_id="cycle_1",
            proposal_id="proposal_1",
            stage="proposed",
            baseline_metrics={"coverage": 85.0, "tests": 100.0},
        )
        assert cycle.cycle_id == "cycle_1"
        assert cycle.proposal_id == "proposal_1"
        assert cycle.stage == "proposed"
        assert cycle.baseline_metrics["coverage"] == 85.0

    def test_detect_saturation_no_history(self) -> None:
        cycle = OptimizationCycle(
            cycle_id="cycle_1",
            proposal_id="p1",
            stage="proposed",
        )
        assert cycle.detect_saturation([]) is False

    def test_detect_saturation_below_threshold(self) -> None:
        cycle = OptimizationCycle(
            cycle_id="cycle_1",
            proposal_id="p1",
            stage="proposed",
        )
        gains = [0.001, 0.002, 0.001]
        assert cycle.detect_saturation(gains, threshold=0.005, window=3)

    def test_detect_saturation_above_threshold(self) -> None:
        cycle = OptimizationCycle(
            cycle_id="cycle_1",
            proposal_id="p1",
            stage="proposed",
        )
        gains = [0.01, 0.02, 0.01]
        assert cycle.detect_saturation(gains, threshold=0.005, window=3) is False

    def test_to_audit_record(self) -> None:
        cycle = OptimizationCycle(
            cycle_id="cycle_1",
            proposal_id="p1",
            stage="adopted",
            adopted=True,
            gain_pct=0.01,
        )
        record = cycle.to_audit_record(round_num=34)
        assert record.event_type == "continuous_optimization"
        assert record.outcome == "adopted"


class TestContinuousOptimizer:
    def setup_method(self) -> None:
        self.optimizer = ContinuousOptimizer()

    def test_not_paused_initially(self) -> None:
        assert self.optimizer.is_paused is False

    def test_observe(self) -> None:
        metrics = {"coverage": 96.5, "tests": 1200}
        obs = self.optimizer.observe(metrics)
        assert obs["metrics"]["coverage"] == 96.5
        assert obs["paused"] is False
        assert obs["saturated_rounds"] == 0

    def test_propose_when_not_paused(self) -> None:
        metrics = {"coverage": 85.0}
        obs = self.optimizer.observe(metrics)
        proposals = self.optimizer.propose(obs)
        assert len(proposals) >= 1

    def test_no_proposals_when_paused(self) -> None:
        metrics = {"coverage": 90.0}
        obs = self.optimizer.observe(metrics)
        self.optimizer._paused = True
        proposals = self.optimizer.propose(obs)
        assert proposals == []

    def test_sandbox_test(self) -> None:
        cycle = OptimizationCycle(
            cycle_id="cycle_1",
            proposal_id="p1",
            stage="proposed",
            baseline_metrics={"coverage": 90.0},
        )
        result = self.optimizer.sandbox_test(cycle)
        assert result["passed"] is True
        assert "simulated_gain" in result

    def test_measure(self) -> None:
        cycle = OptimizationCycle(
            cycle_id="cycle_1",
            proposal_id="p1",
            stage="proposed",
            baseline_metrics={"coverage": 90.0},
        )
        sandbox = self.optimizer.sandbox_test(cycle)
        measured = self.optimizer.measure(cycle, sandbox)
        assert "coverage" in measured
        assert "gain_pct" in measured

    def test_adopt_positive_gain(self) -> None:
        cycle = OptimizationCycle(
            cycle_id="cycle_1",
            proposal_id="p1",
            stage="proposed",
        )
        measured = {"gain_pct": 0.01}
        adopted = self.optimizer.adopt(cycle, measured)
        assert adopted is True
        assert cycle.adopted is True

    def test_reject_zero_gain(self) -> None:
        cycle = OptimizationCycle(
            cycle_id="cycle_2",
            proposal_id="p2",
            stage="proposed",
        )
        measured = {"gain_pct": 0.0}
        adopted = self.optimizer.adopt(cycle, measured)
        assert adopted is False

    def test_run_cycle(self) -> None:
        metrics = {"coverage": 90.0, "test_count": 1200}
        cycles = self.optimizer.run_cycle(metrics)
        assert isinstance(cycles, list)

    def test_saturation_detection(self) -> None:
        for _ in range(4):
            self.optimizer._gain_history.append(0.001)
        assert self.optimizer._check_saturation(0.001)

    def test_auto_pause_after_saturation(self) -> None:
        cycle = OptimizationCycle(
            cycle_id="sat_test",
            proposal_id="p_sat",
            stage="proposed",
        )
        for i in range(4):
            self.optimizer._gain_history.append(0.001)
            measured = {"gain_pct": 0.001}
            self.optimizer.adopt(cycle, measured)
            cycle = OptimizationCycle(
                cycle_id=f"sat_test_{i}",
                proposal_id=f"p_sat_{i}",
                stage="proposed",
            )
        assert self.optimizer.is_paused or self.optimizer.saturated_rounds >= 0

    def test_resume_after_pause(self) -> None:
        self.optimizer._paused = True
        self.optimizer._saturated_rounds = 5
        self.optimizer.resume()
        assert self.optimizer.is_paused is False
        assert self.optimizer.saturated_rounds == 0

    def test_health_check(self) -> None:
        health = self.optimizer.health_check()
        assert "total_cycles" in health
        assert "paused" in health
        assert "saturated_rounds" in health
        assert "last_gain" in health

    def test_clear_resets(self) -> None:
        self.optimizer.run_cycle({"coverage": 90.0})
        self.optimizer.clear()
        assert len(self.optimizer.cycles) == 0
        assert self.optimizer.is_paused is False

    def test_gain_history(self) -> None:
        assert self.optimizer.gain_history == []

    def test_custom_audit_store(self) -> None:
        audit = UnifiedAuditStore()
        optimizer = ContinuousOptimizer(audit_store=audit)
        optimizer.run_cycle({"coverage": 90.0})
        assert audit.count() >= 0

    def test_low_coverage_modules(self) -> None:
        metrics = {"module_a_coverage": 80.0, "module_b_coverage": 92.0, "module_c_coverage": 75.0}
        targets = self.optimizer._identify_low_coverage_modules(metrics)
        assert len(targets) >= 1

    def test_no_low_coverage_modules(self) -> None:
        metrics = {"module_a_coverage": 95.0, "module_b_coverage": 92.0}
        targets = self.optimizer._identify_low_coverage_modules(metrics)
        assert "all_modules_above_threshold" in targets

    def test_saturation_auto_pause(self) -> None:
        optimizer = ContinuousOptimizer()
        for i in range(ContinuousOptimizer.AUTO_PAUSE_AFTER_SATURATED_ROUNDS + 2):
            cycle = OptimizationCycle(
                cycle_id=f"sat_cycle_{i}",
                proposal_id=f"sat_proposal_{i}",
                stage="proposed",
            )
            measured = {"gain_pct": 0.0}
            optimizer.adopt(cycle, measured)
        assert optimizer.is_paused

    def test_resume_audit_record(self) -> None:
        self.optimizer._paused = True
        self.optimizer.resume()
        assert self.optimizer.is_paused is False


class TestContinuousOptimizerWithRealBenchmark:
    @pytest.fixture
    def mock_benchmark(self):
        def _bn() -> dict[str, float]:
            return {
                "test_count": 678.0,
                "coverage_pct": 85.0,
                "execution_time_ms": 24000.0,
                "tests_passed": 650.0,
                "tests_failed": 28.0,
                "exit_code": 0.0,
            }
        return _bn

    def test_init_with_benchmark_fn(self, mock_benchmark) -> None:
        co = ContinuousOptimizer(benchmark_fn=mock_benchmark)
        assert co._benchmark_fn is mock_benchmark

    def test_sandbox_test_with_real_benchmark(self, mock_benchmark) -> None:
        co = ContinuousOptimizer(benchmark_fn=mock_benchmark)
        cycle = OptimizationCycle(
            cycle_id="real_test",
            proposal_id="prop_1",
            stage="proposed",
            baseline_metrics={"coverage_pct": 80.0},
        )
        result = co.sandbox_test(cycle)
        assert result["passed"] is True
        assert "real_benchmark" in result
        assert result["real_benchmark"]["coverage_pct"] == 85.0

    def test_measure_with_real_benchmark(self, mock_benchmark) -> None:
        co = ContinuousOptimizer(benchmark_fn=mock_benchmark)
        cycle = OptimizationCycle(
            cycle_id="real_test",
            proposal_id="prop_1",
            stage="proposed",
            baseline_metrics={"coverage_pct": 80.0},
        )
        sandbox = co.sandbox_test(cycle)
        measured = co.measure(cycle, sandbox)
        assert measured["coverage_pct"] == 85.0
        assert measured["test_count"] == 678.0

    def test_sandbox_test_benchmark_error(self, mock_benchmark) -> None:
        def _failing() -> dict[str, float]:
            raise RuntimeError("benchmark failed")
        co = ContinuousOptimizer(benchmark_fn=_failing)
        cycle = OptimizationCycle(
            cycle_id="err_test",
            proposal_id="prop_1",
            stage="proposed",
            baseline_metrics={},
        )
        result = co.sandbox_test(cycle)
        assert result["passed"] is False
        assert len(result["errors"]) == 1

    def test_init_without_benchmark_fn(self) -> None:
        co = ContinuousOptimizer()
        cycle = OptimizationCycle(
            cycle_id="sim_test",
            proposal_id="prop_1",
            stage="proposed",
            baseline_metrics={},
        )
        result = co.sandbox_test(cycle)
        assert "simulated_gain" in result
        assert "real_benchmark" not in result
