from __future__ import annotations

from maref.evolution.iteration_analyzer import IterationAnalyzer


def test_iteration_analyzer_detects_regression() -> None:
    analyzer = IterationAnalyzer()
    result = analyzer.compare_snapshots(
        previous={"fnr": 0.02, "coverage": 82.0, "test_pass_rate": 1.0},
        current={"fnr": 0.08, "coverage": 78.0, "test_pass_rate": 0.95},
    )
    assert "fnr_regression" in result.degradations
    assert "coverage_drop" in result.degradations
    assert "test_pass_rate_drop" in result.degradations
    assert result.priority == "P0"


def test_iteration_analyzer_detects_opportunities() -> None:
    analyzer = IterationAnalyzer()
    result = analyzer.compare_snapshots(
        previous={"fnr": 0.08, "coverage": 75.0, "test_pass_rate": 0.95},
        current={"fnr": 0.02, "coverage": 82.0, "test_pass_rate": 0.99},
    )
    assert "fnr_improved" in result.opportunities
    assert "coverage_improved" in result.opportunities
    assert result.priority == "P2"


def test_iteration_analyzer_stable_priority_low() -> None:
    analyzer = IterationAnalyzer()
    result = analyzer.compare_snapshots(
        previous={"fnr": 0.02, "coverage": 82.0, "test_pass_rate": 0.99},
        current={"fnr": 0.021, "coverage": 82.5, "test_pass_rate": 0.99},
    )
    assert result.degradations == []
    assert result.priority == "P3"
