from __future__ import annotations

from unittest.mock import patch

from maref.recursive.self_observer import SystemSnapshot
from maref.recursive.self_optimizer import (
    OptimizationHypothesis,
    SelfOptimizer,
)


class TestSelfOptimizerExtended:
    def test_propose_optimizations_top_3_modules(self) -> None:
        opt = SelfOptimizer()
        snapshot = SystemSnapshot(
            module_graph={
                "mod_a": ["d1", "d2", "d3", "d4", "d5"],
                "mod_b": ["d1", "d2", "d3", "d4"],
                "mod_c": ["d1", "d2"],
                "mod_d": ["d1"],
            },
            source_file_count=10,
        )
        hypotheses = opt.propose_optimizations(snapshot)
        deps_hypotheses = [
            h for h in hypotheses if "reduce dependencies" in h.description
        ]
        assert len(deps_hypotheses) >= 1
        assert any("mod_a" in h.description for h in deps_hypotheses)

    def test_propose_optimizations_returns_list(self) -> None:
        opt = SelfOptimizer()
        snapshot = SystemSnapshot(
            module_graph={"mod_a": ["d1", "d2", "d3", "d4"]},
            source_file_count=5,
        )
        hypotheses = opt.propose_optimizations(snapshot)
        assert len(hypotheses) >= 1
        assert any("reduce dependencies" in h.description for h in hypotheses)

    def test_run_experiment_apply_fn_failure_logged(self) -> None:
        opt = SelfOptimizer()
        h = OptimizationHypothesis(
            hypothesis_id="h1", description="test", target_module="mod"
        )

        def failing_apply() -> None:
            msg = "executor failure"
            raise RuntimeError(msg)

        with patch.object(opt, "_benchmark_fn", return_value={"coverage_pct": 80.0}):
            result = opt.run_experiment(h, apply_fn=failing_apply)

        assert result.gain_pct == 0.0
        assert h.experiment_result is not None

    def test_run_experiment_apply_fn_none_with_fallback(self) -> None:
        opt = SelfOptimizer()
        h = OptimizationHypothesis(
            hypothesis_id="h1", description="test", target_module="mod"
        )

        called = False

        def custom_apply() -> None:
            nonlocal called
            called = True

        opt = SelfOptimizer(apply_fn=custom_apply)

        with patch.object(opt, "_benchmark_fn", return_value={"coverage_pct": 80.0}):
            opt.run_experiment(h)
            assert called is True

    def test_run_experiment_no_benchmark_change_still_writes_result(self) -> None:
        opt = SelfOptimizer()
        h = OptimizationHypothesis(
            hypothesis_id="h1", description="test", target_module="mod"
        )

        with patch.object(
            opt, "_benchmark_fn", return_value={"coverage_pct": 75.0}
        ):
            result = opt.run_experiment(h, apply_fn=lambda: None)
            assert result.before == {"coverage_pct": 75.0}
            assert result.after == {"coverage_pct": 75.0}
            assert result.gain_pct == 0.0

    def test_run_experiment_coverage_gain_positive(self) -> None:
        opt = SelfOptimizer()
        h = OptimizationHypothesis(
            hypothesis_id="h1", description="test", target_module="mod"
        )

        with patch.object(
            opt,
            "_benchmark_fn",
            side_effect=[
                {"coverage_pct": 50.0, "test_count": 10},
                {"coverage_pct": 75.0, "test_count": 10},
            ],
        ):
            result = opt.run_experiment(h, apply_fn=lambda: None)
            assert result.gain_pct == (75.0 - 50.0) / 50.0

    def test_run_experiment_time_gain_positive(self) -> None:
        opt = SelfOptimizer()
        h = OptimizationHypothesis(
            hypothesis_id="h1", description="test", target_module="mod"
        )

        with patch.object(
            opt,
            "_benchmark_fn",
            side_effect=[
                {"coverage_pct": 0, "execution_time_ms": 200.0},
                {"coverage_pct": 0, "execution_time_ms": 100.0},
            ],
        ):
            result = opt.run_experiment(h, apply_fn=lambda: None)
            assert result.gain_pct == (200.0 - 100.0) / 200.0

    def test_run_experiment_no_metrics_falls_back_to_zero_gain(self) -> None:
        opt = SelfOptimizer()
        h = OptimizationHypothesis(
            hypothesis_id="h1", description="test", target_module="mod"
        )

        with patch.object(
            opt,
            "_benchmark_fn",
            side_effect=[
                {"some_metric": 10.0},
                {"some_metric": 20.0},
            ],
        ):
            result = opt.run_experiment(h, apply_fn=lambda: None)
            assert result.gain_pct == 0.0

    def test_adopt_if_gain_exactly_threshold(self) -> None:
        opt = SelfOptimizer(adopt_threshold=0.05)
        h = OptimizationHypothesis(
            hypothesis_id="h1",
            description="test",
            target_module="mod",
            gain_pct=0.05,
        )
        assert opt.adopt_if_gain(h) is True
        assert h.adopted is True

    def test_adopt_if_gain_barely_below_threshold(self) -> None:
        opt = SelfOptimizer(adopt_threshold=0.05)
        h = OptimizationHypothesis(
            hypothesis_id="h1",
            description="test",
            target_module="mod",
            gain_pct=0.0499,
        )
        assert opt.adopt_if_gain(h) is False
        assert h.adopted is False

    def test_revert_if_regression_zero_gain(self) -> None:
        opt = SelfOptimizer()
        h = OptimizationHypothesis(
            hypothesis_id="h1",
            description="test",
            target_module="mod",
            gain_pct=0.0,
        )
        assert opt.revert_if_regression(h) is False
        assert h.reverted is False

    def test_revert_if_regression_negative(self) -> None:
        opt = SelfOptimizer()
        h = OptimizationHypothesis(
            hypothesis_id="h1",
            description="test",
            target_module="mod",
            gain_pct=-0.01,
        )
        assert opt.revert_if_regression(h) is True
        assert h.reverted is True
        assert "rolled back" in h.conclusion

    def test_ingest_rel_result_adopted(self) -> None:
        opt = SelfOptimizer()
        hypothesis = opt.ingest_rel_result(
            round_number=5,
            before_metrics={"coverage_pct": 60.0},
            after_metrics={"coverage_pct": 80.0},
            adopted=True,
        )
        assert hypothesis.adopted is True
        assert hypothesis.gain_pct > 0
        assert hypothesis in opt.adopted

    def test_ingest_rel_result_rejected(self) -> None:
        opt = SelfOptimizer()
        hypothesis = opt.ingest_rel_result(
            round_number=5,
            before_metrics={"coverage_pct": 80.0},
            after_metrics={"coverage_pct": 60.0},
            adopted=False,
        )
        assert hypothesis.adopted is False
        assert hypothesis.gain_pct < 0
        assert hypothesis in opt.hypotheses

    def test_ingest_rel_result_adopted_negative_gain_not_adopted(self) -> None:
        opt = SelfOptimizer()
        hypothesis = opt.ingest_rel_result(
            round_number=6,
            before_metrics={"coverage_pct": 80.0},
            after_metrics={"coverage_pct": 70.0},
            adopted=True,
        )
        assert hypothesis.adopted is False
        assert "rejected" in hypothesis.conclusion

    def test_ingest_rel_result_no_coverage(self) -> None:
        opt = SelfOptimizer()
        hypothesis = opt.ingest_rel_result(
            round_number=7,
            before_metrics={"execution_time_ms": 100.0},
            after_metrics={"execution_time_ms": 50.0},
            adopted=True,
        )
        assert hypothesis.gain_pct == 0.0

    def test_ingest_rel_result_zero_coverage_denom(self) -> None:
        opt = SelfOptimizer()
        hypothesis = opt.ingest_rel_result(
            round_number=8,
            before_metrics={"coverage_pct": 0},
            after_metrics={"coverage_pct": 10.0},
            adopted=True,
        )
        assert hypothesis.gain_pct == 0.0

    def test_run_experiment_stores_result_on_hypothesis(self) -> None:
        opt = SelfOptimizer()
        h = OptimizationHypothesis(
            hypothesis_id="h1", description="test", target_module="mod"
        )

        with patch.object(
            opt,
            "_benchmark_fn",
            side_effect=[
                {"coverage_pct": 40.0, "test_count": 5},
                {"coverage_pct": 60.0, "test_count": 5},
            ],
        ):
            opt.run_experiment(h, apply_fn=lambda: None)
            assert "before" in h.experiment_result
            assert "after" in h.experiment_result
            assert h.experiment_result["before"]["coverage_pct"] == 40.0
            assert h.experiment_result["after"]["coverage_pct"] == 60.0
