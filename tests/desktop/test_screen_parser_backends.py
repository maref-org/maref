"""Tests for OmniParserInterface backend selection."""

from __future__ import annotations

import platform

import pytest

from maref.desktop.screen_parser import OmniParserInterface


class TestAccessibilityBackendRegistration:
    def test_supports_accessibility_backend(self):
        assert "accessibility" in OmniParserInterface.SUPPORTED_BACKENDS

    @pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
    def test_auto_selects_accessibility_on_macos(self):
        parser = OmniParserInterface(backend="auto")
        parser.initialize()
        if parser.actual_backend == "accessibility":
            assert parser.initialized
            result = parser.parse("/tmp/test.png", 1440, 900)
            assert len(result.elements) > 0
        else:
            pytest.skip("AX permissions not available; skipping accessibility verification")

    @pytest.mark.skipif(platform.system() == "Darwin", reason="non-macOS only")
    def test_auto_falls_back_on_non_macos(self):
        parser = OmniParserInterface(backend="auto")
        parser.initialize()
        assert parser.actual_backend == "mock"

    def test_accessibility_backend_explicit_init(self):
        parser = OmniParserInterface(backend="accessibility")
        # On macOS with AX permissions, should init; on non-macOS, should fail
        if platform.system() == "Darwin":
            result = parser.initialize()
            assert result == parser.initialized
        else:
            assert not parser.initialize()
