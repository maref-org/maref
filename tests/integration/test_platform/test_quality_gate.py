"""Tests for EvolutionQualityGate L2 cross-dimension scoring."""

from __future__ import annotations

import pytest

from maref.integration.test_platform.quality_gate import (
    EvolutionQualityGate,
    EvolutionVerdict,
    QualityGateConfig,
    QualityGateResult,
)


class TestQualityGateL2:
    """Test suite for L2 cross-dimension quality gate."""

    def test_l2_dimension_count_below_threshold(self):
        gate = EvolutionQualityGate()
        dim_scores = {"correctness": 85.0, "testing": 80.0}
        result = gate.evaluate_l2("test-agent", dim_scores)
        assert not result.passed
        assert result.verdict == EvolutionVerdict.REJECTED
        assert result.details["dimension_count"]["passed"] is False

    def test_l2_per_dimension_score_below_threshold(self):
        gate = EvolutionQualityGate()
        dim_scores = {
            "correctness": 95.0,
            "testing": 85.0,
            "code_quality": 90.0,
            "security": 50.0,
            "performance": 80.0,
        }
        result = gate.evaluate_l2("test-agent", dim_scores)
        assert not result.passed
        assert result.verdict == EvolutionVerdict.REJECTED
        assert result.details["security"]["passed"] is False

    def test_l2_all_dimensions_passing(self):
        gate = EvolutionQualityGate()
        dim_scores = {
            "correctness": 95.0,
            "testing": 85.0,
            "code_quality": 90.0,
            "security": 88.0,
            "performance": 80.0,
        }
        result = gate.evaluate_l2("test-agent", dim_scores)
        assert result.passed
        assert result.verdict == EvolutionVerdict.APPROVED

    def test_l2_with_cross_impact_violations(self):
        gate = EvolutionQualityGate()
        dim_scores = {
            "correctness": 95.0,
            "testing": 85.0,
            "code_quality": 90.0,
            "security": 88.0,
            "performance": 80.0,
        }
        cross_impacts = [
            {"dim1": "correctness", "dim2": "testing", "correlation": -0.5},
        ]
        result = gate.evaluate_l2("test-agent", dim_scores, cross_impacts)
        assert not result.passed
        assert result.details["cross_impact"]["passed"] is False

    def test_l2_cross_impact_all_clear(self):
        gate = EvolutionQualityGate()
        dim_scores = {
            "correctness": 95.0,
            "testing": 85.0,
            "code_quality": 90.0,
            "security": 88.0,
            "performance": 80.0,
        }
        cross_impacts = [
            {"dim1": "correctness", "dim2": "testing", "correlation": -0.2},
            {"dim1": "testing", "dim2": "code_quality", "correlation": -0.1},
        ]
        result = gate.evaluate_l2("test-agent", dim_scores, cross_impacts)
        assert result.passed
        assert result.details["cross_impact"]["passed"] is True

    def test_l2_weighted_scoring_calculation(self):
        gate = EvolutionQualityGate()
        dim_scores = {
            "correctness": 100.0,
            "testing": 80.0,
            "code_quality": 90.0,
            "security": 70.0,
            "performance": 60.0,
        }
        expected = (
            100.0 * 0.30 + 80.0 * 0.20 + 90.0 * 0.20 + 70.0 * 0.20 + 60.0 * 0.10
        )
        result = gate.evaluate_l2("test-agent", dim_scores)
        assert result.score == pytest.approx(expected, rel=1e-2)

    def test_evaluate_all_l2_returns_all_gates(self):
        gate = EvolutionQualityGate()
        dim_scores = {
            "correctness": 95.0,
            "testing": 85.0,
            "code_quality": 90.0,
            "security": 88.0,
            "performance": 80.0,
        }
        results = gate.evaluate_all_l2("test-agent", dim_scores)
        assert set(results.keys()) == {"c1", "c2", "c3", "c4", "c5", "l2"}

    def test_evaluate_all_l2_includes_l2_gate_result(self):
        gate = EvolutionQualityGate()
        dim_scores = {
            "correctness": 95.0,
            "testing": 85.0,
            "code_quality": 90.0,
            "security": 88.0,
            "performance": 80.0,
        }
        results = gate.evaluate_all_l2("test-agent", dim_scores)
        assert "l2" in results
        assert isinstance(results["l2"], QualityGateResult)
        assert results["l2"].passed

    def test_l2_custom_config_thresholds(self):
        config = QualityGateConfig(
            l2_dim_count=3,
            l2_min_dim_score=80.0,
            l2_cross_impact_threshold=-0.2,
        )
        gate = EvolutionQualityGate(config=config)
        dim_scores = {
            "correctness": 95.0,
            "testing": 85.0,
            "code_quality": 82.0,
        }
        result = gate.evaluate_l2("test-agent", dim_scores)
        assert result.passed
        assert result.details["dimension_count"]["passed"] is True
        assert result.details["code_quality"]["passed"] is True

    def test_l2_empty_dimension_scores(self):
        gate = EvolutionQualityGate()
        result = gate.evaluate_l2("test-agent", {})
        assert not result.passed
        assert result.score == 0.0
        assert result.details["dimension_count"]["passed"] is False
