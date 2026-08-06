"""Tests for DesktopAgent with AccessibilityParser."""

from __future__ import annotations

import platform

import pytest

from maref.desktop.agent import DesktopAgent


class TestDesktopAgentWithAccessibility:
    @pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
    def test_agent_reports_accessibility_backend(self) -> None:
        agent = DesktopAgent(dry_run=True)
        env = agent.check_environment()
        if env.get("parser_actual_backend") == "accessibility":
            assert env["parser_initialized"]
            parse = agent.parse_screen()
            assert len(parse.elements) > 0
            for el in parse.elements:
                assert el.bbox.width > 0
                assert el.bbox.height > 0
