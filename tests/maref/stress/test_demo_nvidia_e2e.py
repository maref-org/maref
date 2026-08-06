"""Smoke tests for maref.stress.demo_nvidia_e2e."""
from __future__ import annotations

import pytest

from maref.stress.demo_nvidia_e2e import (
    CODE_PROMPTS,
    NVIDIA_API_KEY,
    NVIDIA_BASE_URL,
    NVIDIA_MODEL,
)


class TestConstants:
    def test_constants_exist(self) -> None:
        assert isinstance(NVIDIA_API_KEY, str)
        assert NVIDIA_BASE_URL == "https://integrate.api.nvidia.com/v1"
        assert NVIDIA_MODEL == "meta/llama-3.1-8b-instruct"

    def test_code_prompts(self) -> None:
        assert len(CODE_PROMPTS) >= 5
        assert CODE_PROMPTS[0]["title"] == "Fibonacci Function"
        assert "prompt" in CODE_PROMPTS[0]
