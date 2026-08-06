"""Smoke tests for maref.stress.demo_volc_ark_e2e."""
from __future__ import annotations

import pytest

from maref.stress.demo_volc_ark_e2e import (
    CODE_PROMPTS,
    VOLC_ARK_API_KEY,
    VOLC_ARK_BASE_URL,
    VOLC_ARK_MODEL,
)


class TestConstants:
    def test_constants_exist(self) -> None:
        assert isinstance(VOLC_ARK_API_KEY, str)
        assert VOLC_ARK_BASE_URL == "https://ark.cn-beijing.volces.com/api/coding"
        assert VOLC_ARK_MODEL == "doubao-seed-code-preview-latest"

    def test_code_prompts(self) -> None:
        assert len(CODE_PROMPTS) >= 5
        assert "prompt" in CODE_PROMPTS[0]
