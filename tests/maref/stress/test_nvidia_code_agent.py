"""Smoke tests for maref.stress.nvidia_code_agent."""
from __future__ import annotations

import pytest

from maref.stress.nvidia_code_agent import CodeGenerationResult, NvidiaCodeAgent


class TestCodeGenerationResult:
    def test_init_default(self) -> None:
        result = CodeGenerationResult(success=True)
        assert result.success is True
        assert result.code == ""
        assert result.model == ""
        assert result.prompt_tokens == 0
        assert result.has_tests is False

    def test_init_custom(self) -> None:
        result = CodeGenerationResult(
            success=True, code="def foo(): pass", model="llama-3.1",
            prompt_tokens=50, completion_tokens=100, total_tokens=150,
            duration_ms=500.0, has_tests=True, has_docstrings=True,
            has_type_hints=True,
        )
        assert result.code == "def foo(): pass"
        assert result.model == "llama-3.1"
        assert result.total_tokens == 150
        assert result.has_tests is True

    def test_to_quality_metrics_failure(self) -> None:
        result = CodeGenerationResult(success=False)
        metrics = result.to_quality_metrics()
        assert metrics.test_coverage_pct == 0.0

    def test_to_quality_metrics_success(self) -> None:
        result = CodeGenerationResult(
            success=True, code="def foo(): pass\n",
            has_tests=True, has_docstrings=True, has_type_hints=True,
            metadata={"finish_reason": "stop"},
        )
        metrics = result.to_quality_metrics()
        assert metrics.test_coverage_pct == 75.0
        assert metrics.files_generated == 1


class TestNvidiaCodeAgent:
    def test_class_constants(self) -> None:
        assert NvidiaCodeAgent.DEFAULT_BASE_URL == "https://integrate.api.nvidia.com/v1"
        assert NvidiaCodeAgent.DEFAULT_MODEL == "meta/llama-3.1-8b-instruct"
        assert NvidiaCodeAgent.DEFAULT_TIMEOUT == 60.0
        assert NvidiaCodeAgent.DEFAULT_MAX_TOKENS == 4096

    def test_init_missing_openai(self) -> None:
        try:
            from openai import OpenAI  # noqa: F401
            pytest.skip("openai is available")
        except ImportError:
            with pytest.raises(ImportError, match="openai"):
                NvidiaCodeAgent(api_key="test-key")
