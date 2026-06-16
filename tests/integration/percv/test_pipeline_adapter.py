"""Tests for PipelineAdapter — PERCV research pipeline to MAREF governance bridge."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maref.integration.percv.pipeline_adapter import (
    PERCVPipelineAdapter as PipelineAdapter,
)
from maref.integration.percv.pipeline_adapter import (
    PipelineDirective,
    PipelineStepResult,
)


class TestPipelineDirective:
    def test_directive_values(self) -> None:
        assert PipelineDirective.CONTINUE.value == "continue"
        assert PipelineDirective.DEGRADE.value == "degrade"
        assert PipelineDirective.RETRY.value == "retry"
        assert PipelineDirective.HALT.value == "halt"
        assert PipelineDirective.ESCALATE.value == "escalate"


class TestPipelineStepResult:
    def test_default_directive(self) -> None:
        r = PipelineStepResult(step_name="test", success=True)
        assert r.directive == PipelineDirective.CONTINUE

    def test_with_data(self) -> None:
        r = PipelineStepResult(step_name="harvest", success=True, data=["signal1"])
        assert r.data == ["signal1"]


class TestPipelineAdapter:
    def test_init_defaults(self) -> None:
        adapter = PipelineAdapter()
        assert adapter._error_policy == "degrade"
        assert adapter._results == []

    def test_run_research_cycle_no_percv(self) -> None:
        adapter = PipelineAdapter()
        with (
            patch(
                "maref.integration.percv.pipeline_adapter.PERCVPipelineAdapter._create_pipeline",
                side_effect=RuntimeError("PERCV package is required"),
            ),
            pytest.raises(RuntimeError, match="PERCV package is required"),
        ):
            adapter.run_research_cycle("test topic")

    def test_run_research_cycle_mock(self) -> None:
        adapter = PipelineAdapter()
        mock_pipeline = MagicMock()

        def fake_create() -> MagicMock:
            mock_step = MagicMock()
            mock_step.success = True
            mock_step.data = ["mock_signal"]
            mock_step.error = None
            mock_pipeline.run_step.return_value = mock_step
            return mock_pipeline

        with patch.object(adapter, "_create_pipeline", fake_create):
            results = adapter.run_research_cycle(
                "AI agents",
                harvester_fn=lambda: ["signal1", "signal2"],
            )

        assert "harvest" in results
        assert results["harvest"].success

    def test_directive_on_success(self) -> None:
        adapter = PipelineAdapter()
        directive = adapter._determine_directive("test", success=True, error=None)
        assert directive == PipelineDirective.CONTINUE

    def test_directive_on_failure(self) -> None:
        adapter = PipelineAdapter()
        directive = adapter._determine_directive("test", success=False, error="fail")
        assert directive == PipelineDirective.DEGRADE

    def test_directive_halt_on_circuit_breaker(self) -> None:
        cb = MagicMock()
        cb.is_open.return_value = True
        adapter = PipelineAdapter(circuit_breaker=cb)
        directive = adapter._determine_directive("test", success=False, error="fail")
        assert directive == PipelineDirective.HALT

    def test_directive_halt_on_fail_fast(self) -> None:
        adapter = PipelineAdapter(error_policy="fail_fast")
        directive = adapter._determine_directive("test", success=False, error="fail")
        assert directive == PipelineDirective.HALT

    def test_directive_with_governance_state(self) -> None:
        sm = MagicMock()
        sm.current_state.value = 2  # ANALYZE
        adapter = PipelineAdapter(governance_state_machine=sm)
        directive = adapter._determine_directive("test", success=False, error="fail")
        assert directive == PipelineDirective.RETRY

    def test_directive_high_state(self) -> None:
        sm = MagicMock()
        sm.current_state.value = 7  # STABILIZE
        adapter = PipelineAdapter(governance_state_machine=sm)
        directive = adapter._determine_directive("test", success=False, error="fail")
        assert directive == PipelineDirective.HALT

    def test_run_scout_empty(self) -> None:
        adapter = PipelineAdapter()
        result = adapter._run_scout("test", harvester_fn=lambda: [])
        assert result == []

    def test_get_summary_empty(self) -> None:
        adapter = PipelineAdapter()
        summary = adapter.get_summary()
        assert summary["total_steps"] == 0
        assert summary["successful"] == 0

    def test_get_summary_with_results(self) -> None:
        adapter = PipelineAdapter()
        adapter._results = [
            PipelineStepResult(step_name="a", success=True, duration_ms=10.0),
            PipelineStepResult(step_name="b", success=False, error="err", duration_ms=20.0),
        ]
        summary = adapter.get_summary()
        assert summary["total_steps"] == 2
        assert summary["successful"] == 1
        assert summary["failed"] == 1

    def test_reset(self) -> None:
        adapter = PipelineAdapter()
        adapter._results = [PipelineStepResult(step_name="x", success=True)]
        adapter.reset()
        assert adapter._results == []
