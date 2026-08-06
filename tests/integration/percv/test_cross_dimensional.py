from __future__ import annotations

import pytest

from maref.integration.percv.cross_dimensional_analyzer import CrossDimensionalAnalyzer
from maref.integration.percv.multi_target_ratchet import ExperimentResult


def _make_exp(
    metric: float = 0.8,
    status: str = "keep",
    dim_scores: dict[str, float] | None = None,
) -> ExperimentResult:
    return ExperimentResult(
        commit="abc",
        metric_value=metric,
        previous_best=0.7,
        delta=metric - 0.7,
        status=status,
        description="test",
        memory_mb=100.0,
        dimension_scores=dim_scores,
    )


class TestCrossDimensionalAnalyzer:
    def test_init_empty(self) -> None:
        cda = CrossDimensionalAnalyzer()
        assert cda.history == []
        assert "correctness" in cda.interaction_matrix

    def test_detect_effects_empty_history(self) -> None:
        cda = CrossDimensionalAnalyzer()
        effects = cda.detect_cross_effects()
        assert effects == []

    def test_detect_effects_insufficient_data(self) -> None:
        history = [_make_exp() for _ in range(2)]
        cda = CrossDimensionalAnalyzer(history)
        effects = cda.detect_cross_effects()
        assert effects == []

    def test_detect_effects_with_dimension_scores(self) -> None:
        history = []
        for i in range(5):
            history.append(_make_exp(
                metric=0.7 + i * 0.05,
                dim_scores={"correctness": 0.7 + i * 0.05, "testing": 0.6 + i * 0.03},
            ))
        cda = CrossDimensionalAnalyzer(history)
        effects = cda.detect_cross_effects(window=5)
        assert isinstance(effects, list)

    def test_recommend_multi_objective_empty_weights(self) -> None:
        cda = CrossDimensionalAnalyzer()
        result = cda.recommend_multi_objective({})
        assert result is None

    def test_recommend_multi_objective_with_weights(self) -> None:
        history = []
        for i in range(5):
            history.append(_make_exp(
                dim_scores={"correctness": 0.7, "testing": 0.6, "code_quality": 0.5, "security": 0.4},
            ))
        cda = CrossDimensionalAnalyzer(history)
        pareto = cda.recommend_multi_objective(
            {"correctness": 0.7, "testing": 0.6, "code_quality": 0.5, "security": 0.4},
        )
        assert pareto is not None
        assert "correctness" in pareto.recommended_weights

    def test_pearson_correlation(self) -> None:
        cda = CrossDimensionalAnalyzer()
        result = cda._pearson([1.0, 2.0, 3.0], [2.0, 4.0, 6.0])
        assert result == pytest.approx(1.0, abs=0.01)

    def test_pearson_no_variance(self) -> None:
        cda = CrossDimensionalAnalyzer()
        result = cda._pearson([1.0, 1.0, 1.0], [2.0, 3.0, 4.0])
        assert result == 0.0

    def test_pearson_insufficient_data(self) -> None:
        cda = CrossDimensionalAnalyzer()
        result = cda._pearson([1.0], [2.0])
        assert result == 0.0

    def test_interaction_matrix_preserved(self) -> None:
        cda1 = CrossDimensionalAnalyzer()
        cda2 = CrossDimensionalAnalyzer()
        cda1.interaction_matrix["correctness"]["testing"] = 0.5
        assert cda2.interaction_matrix["correctness"]["testing"] == 0.3
