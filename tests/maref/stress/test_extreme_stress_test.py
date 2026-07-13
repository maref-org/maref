"""Smoke tests for maref.stress.extreme_stress_test."""
from __future__ import annotations

import pytest

from maref.stress.extreme_stress_test import ExtremeStressTester, ExtremeTestResult


class TestExtremeTestResult:
    def test_init_default(self) -> None:
        result = ExtremeTestResult(test_name="test", scenario="scenario", success=True)
        assert result.test_name == "test"
        assert result.scenario == "scenario"
        assert result.success is True
        assert result.metrics == {}
        assert result.details == ""
        assert result.warnings == []

    def test_init_custom(self) -> None:
        result = ExtremeTestResult(
            test_name="cascade", scenario="5_faults", success=False,
            metrics={"rate": 0.5}, details="some details",
            warnings=["warn1"], duration_ms=100.0,
        )
        assert result.test_name == "cascade"
        assert result.success is False
        assert result.metrics == {"rate": 0.5}
        assert result.duration_ms == 100.0


class TestExtremeStressTester:
    def test_init_default(self) -> None:
        tester = ExtremeStressTester()
        assert tester is not None
        assert tester.results == []

    def test_init_with_seed(self) -> None:
        tester = ExtremeStressTester(seed=123)
        assert tester.results == []
