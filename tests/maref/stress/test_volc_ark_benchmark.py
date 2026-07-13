"""Smoke tests for maref.stress.volc_ark_benchmark."""
from __future__ import annotations

import pytest

from maref.stress.volc_ark_benchmark import (
    BENCHMARK_PROMPTS,
    VOLC_ARK_API_KEY,
    VOLC_ARK_BASE_URL,
    VOLC_ARK_MODEL,
)


class TestConstants:
    def test_constants_exist(self) -> None:
        assert isinstance(VOLC_ARK_API_KEY, str)
        assert VOLC_ARK_BASE_URL == "https://ark.cn-beijing.volces.com/api/coding"
        assert VOLC_ARK_MODEL == "doubao-seed-code-preview-latest"

    def test_benchmark_prompts(self) -> None:
        assert len(BENCHMARK_PROMPTS) >= 10
        for prompt in BENCHMARK_PROMPTS:
            assert "title" in prompt
            assert "prompt" in prompt
            assert "category" in prompt
