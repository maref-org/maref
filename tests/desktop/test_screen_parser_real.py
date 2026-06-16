"""Tests for OmniParser auto-backend fallback behavior."""

from __future__ import annotations

import os

import pytest

from maref.desktop.screen_parser import OmniParserInterface

IS_CI = bool(os.environ.get("CI"))


class TestOmniParserAutoBackend:
    def test_auto_backend_default(self) -> None:
        parser = OmniParserInterface()
        assert parser.backend == "auto"

    def test_auto_backend_initialize(self) -> None:
        parser = OmniParserInterface(backend="auto")
        ok = parser.initialize()
        assert ok is True
        assert parser.initialized is True
        assert parser.actual_backend in ("omni_parser", "mock")

    def test_auto_backend_parse_returns_elements(self) -> None:
        parser = OmniParserInterface(backend="auto")
        parser.initialize()
        result = parser.parse("/tmp/test.png", 1920, 1080)
        assert len(result.elements) >= 3
        assert result.parse_time_ms >= 0

    def test_auto_fallback_to_mock_when_omni_unavailable(self) -> None:
        parser = OmniParserInterface(backend="auto")
        ok = parser.initialize()
        assert ok is True
        info = parser.backend_info
        if parser.actual_backend == "mock":
            assert "fallback_reason" in info or info.get("loaded") is True

    @pytest.mark.skipif(IS_CI, reason="OmniParser model download not suitable for CI")
    def test_explicit_omni_parser_initialization(self) -> None:
        parser = OmniParserInterface(backend="omni_parser")
        ok = parser.initialize()
        if not ok:
            info = parser.backend_info
            assert "error" in info

    def test_mock_backend_still_works(self) -> None:
        parser = OmniParserInterface(backend="mock")
        assert parser.initialize() is True
        result = parser.parse("/tmp/test.png", 1920, 1080)
        assert len(result.elements) >= 3
        assert parser.actual_backend == "mock"

    def test_benchmark_on_auto_backend(self) -> None:
        parser = OmniParserInterface(backend="auto")
        bm = parser.benchmark("", num_runs=3)
        assert "backend" in bm
        assert "avg_latency_ms" in bm
        assert bm["num_runs"] == 3


class TestOmniParserBackendInfo:
    def test_backend_info_after_auto_init(self) -> None:
        parser = OmniParserInterface(backend="auto")
        parser.initialize()
        info = parser.backend_info
        assert "backend" in info
        assert info["loaded"] is True

    def test_actual_backend_matches_parse_output(self) -> None:
        parser = OmniParserInterface(backend="auto")
        parser.initialize()
        result = parser.parse("/tmp/test.png", 1920, 1080)
        assert (
            result.model_name == "mock-omni-parser-v0" or "omni-parser" in result.model_name.lower()
        )
