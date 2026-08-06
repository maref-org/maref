"""Smoke tests for drift_guard.drift_benchmark."""
from __future__ import annotations

import pytest

from drift_guard.drift_benchmark import (
    DRIFT_CLASS_DESCRIPTIONS,
    DriftBenchmark,
    DriftClass,
    DriftResult,
    DriftScenario,
)


class TestDriftClass:
    def test_values(self) -> None:
        assert DriftClass.THEME_COLOR.value == "theme_color"
        assert DriftClass.LAYOUT_UPDATE.value == "layout_update"
        assert DriftClass.OS_VERSION.value == "os_version"
        assert DriftClass.RESOLUTION.value == "resolution"
        assert DriftClass.LOCALE.value == "locale"
        assert DriftClass.FONT_RENDERING.value == "font_rendering"
        assert DriftClass.WINDOW_SIZE.value == "window_size"
        assert DriftClass.DARK_MODE.value == "dark_mode"
        assert DriftClass.NEW_ELEMENT.value == "new_element"
        assert DriftClass.ELEMENT_REMOVAL.value == "element_removal"

    def test_descriptions(self) -> None:
        assert DriftClass.THEME_COLOR in DRIFT_CLASS_DESCRIPTIONS
        assert "accent color" in DRIFT_CLASS_DESCRIPTIONS[DriftClass.THEME_COLOR]


class TestDriftScenario:
    def test_init_minimal(self) -> None:
        scenario = DriftScenario(
            drift_class=DriftClass.THEME_COLOR,
            description="Test scenario",
            baseline_distribution={"a": 0.5, "b": 0.5},
            drifted_distribution={"a": 0.3, "b": 0.7},
        )
        assert scenario.drift_class == DriftClass.THEME_COLOR
        assert scenario.expected_detected is True
        assert scenario.metadata == {}

    def test_to_dict(self) -> None:
        scenario = DriftScenario(
            drift_class=DriftClass.RESOLUTION,
            description="Resolution change",
            baseline_distribution={"x": 1.0},
            drifted_distribution={"x": 0.5},
            expected_detected=False,
            metadata={"scale": 2.0},
        )
        d = scenario.to_dict()
        assert d["drift_class"] == "resolution"
        assert d["expected_detected"] is False


class TestDriftResult:
    def test_init_minimal(self) -> None:
        scenario = DriftScenario(
            drift_class=DriftClass.THEME_COLOR,
            description="Test", baseline_distribution={"a": 0.5, "b": 0.5},
            drifted_distribution={"a": 0.3, "b": 0.7},
        )
        result = DriftResult(
            scenario=scenario, kl_divergence=0.1, js_divergence=0.05,
            hellinger_distance=0.3, detected=True, f1_score=0.9,
        )
        assert result.kl_divergence == 0.1
        assert result.detected is True
        assert result.f1_score == 0.9

    def test_to_dict(self) -> None:
        scenario = DriftScenario(
            drift_class=DriftClass.THEME_COLOR,
            description="Test", baseline_distribution={"a": 0.5, "b": 0.5},
            drifted_distribution={"a": 0.3, "b": 0.7},
        )
        result = DriftResult(
            scenario=scenario, kl_divergence=0.123456, js_divergence=0.05,
            hellinger_distance=0.3, detected=True, f1_score=0.9,
        )
        d = result.to_dict()
        assert d["drift_class"] == "theme_color"
        assert d["kl"] == 0.123456
        assert d["detected"] is True


class TestDriftBenchmark:
    def test_init_default(self) -> None:
        benchmark = DriftBenchmark()
        assert benchmark is not None
        assert len(benchmark.scenarios) == 10

    def test_init_custom_thresholds(self) -> None:
        benchmark = DriftBenchmark(threshold_kl=0.2, threshold_js=0.1)
        assert benchmark is not None
        assert len(benchmark.scenarios) == 10

    def test_scenarios(self) -> None:
        benchmark = DriftBenchmark()
        scenarios = benchmark.scenarios
        assert len(scenarios) == 10
        classes = {s.drift_class for s in scenarios}
        assert DriftClass.THEME_COLOR in classes
        assert DriftClass.ELEMENT_REMOVAL in classes
