"""Smoke tests for maref.stress.full_chain_test."""
from __future__ import annotations

import pytest

from maref.stress.full_chain_test import PhaseResult


class TestPhaseResult:
    def test_init_default(self) -> None:
        result = PhaseResult(phase_name="benchmark", success=True, duration_ms=100.0)
        assert result.phase_name == "benchmark"
        assert result.success is True
        assert result.duration_ms == 100.0
        assert result.metrics == {}
        assert result.details == ""
        assert result.error == ""

    def test_init_custom(self) -> None:
        result = PhaseResult(
            phase_name="pressure", success=False, duration_ms=5000.0,
            metrics={"rate": 0.5}, details="Completed with errors",
            error="Timeout",
        )
        assert result.phase_name == "pressure"
        assert result.success is False
        assert result.metrics == {"rate": 0.5}
        assert result.error == "Timeout"
