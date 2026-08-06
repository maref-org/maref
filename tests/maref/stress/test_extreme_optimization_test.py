"""Smoke tests for maref.stress.extreme_optimization_test."""
from __future__ import annotations

import pytest

from maref.stress.extreme_optimization_test import (
    ExtremeOptimizationTester,
    OptimizationResult,
)


class TestOptimizationResult:
    def test_init_default(self) -> None:
        result = OptimizationResult(
            optimization_name="test", scenario="test",
            baseline_success=0.0, optimized_success=0.0,
            improvement=0.0, success=True,
        )
        assert result.optimization_name == "test"
        assert result.baseline_success == 0.0
        assert result.success is True
        assert result.details == ""

    def test_init_custom(self) -> None:
        result = OptimizationResult(
            optimization_name="cascading_fault_isolation",
            scenario="circuit_breaker",
            baseline_success=0.16, optimized_success=0.35,
            improvement=0.19, success=True,
            details="Improved by 19%", metrics={"agents": 4},
            duration_ms=500.0,
        )
        assert result.improvement == 0.19
        assert result.metrics == {"agents": 4}


class TestExtremeOptimizationTester:
    def test_init_default(self) -> None:
        tester = ExtremeOptimizationTester()
        assert tester is not None
        assert tester.results == []

    def test_init_with_seed(self) -> None:
        tester = ExtremeOptimizationTester(seed=123)
        assert tester.results == []
