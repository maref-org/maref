"""Smoke tests for maref.stress.volc_ark_code_agent."""
from __future__ import annotations

import pytest

from maref.stress.volc_ark_code_agent import CodeGenerationResult, VolcArkCodeAgent


class TestCodeGenerationResult:
    def test_init_default(self) -> None:
        result = CodeGenerationResult(success=True)
        assert result.success is True
        assert result.code == ""
        assert result.model == ""
        assert result.input_tokens == 0
        assert result.has_tests is False

    def test_init_custom(self) -> None:
        result = CodeGenerationResult(
            success=True, code="def foo(): pass", model="doubao-seed",
            input_tokens=50, output_tokens=100, total_tokens=150,
            duration_ms=500.0, has_tests=True, has_docstrings=True,
            has_type_hints=True, stop_reason="end_turn",
        )
        assert result.code == "def foo(): pass"
        assert result.model == "doubao-seed"
        assert result.total_tokens == 150
        assert result.stop_reason == "end_turn"

    def test_to_quality_metrics_failure(self) -> None:
        result = CodeGenerationResult(success=False)
        metrics = result.to_quality_metrics()
        assert metrics.test_coverage_pct == 0.0

    def test_to_quality_metrics_success(self) -> None:
        result = CodeGenerationResult(
            success=True, code="def foo(): pass\n",
            has_tests=True, has_docstrings=True, has_type_hints=True,
            stop_reason="end_turn",
        )
        metrics = result.to_quality_metrics()
        assert metrics.test_coverage_pct == 75.0
        assert metrics.files_generated == 1


class TestVolcArkCodeAgent:
    def test_class_constants(self) -> None:
        assert VolcArkCodeAgent.DEFAULT_BASE_URL == "https://ark.cn-beijing.volces.com/api/coding"
        assert VolcArkCodeAgent.DEFAULT_MODEL == "doubao-seed-code-preview-latest"
        assert VolcArkCodeAgent.DEFAULT_TIMEOUT == 300.0
        assert VolcArkCodeAgent.DEFAULT_MAX_TOKENS == 4096

    def test_init_missing_anthropic(self) -> None:
        try:
            from anthropic import Anthropic  # noqa: F401
            pytest.skip("anthropic is available")
        except ImportError:
            with pytest.raises(ImportError, match="anthropic"):
                VolcArkCodeAgent(api_key="test-key")
