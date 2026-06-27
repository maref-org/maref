"""Tests for macOS Accessibility API parser."""

from __future__ import annotations

import json
import platform

import pytest

from maref.desktop.accessibility_parser import (
    AccessibilityParser,
    ax_role_to_element_type,
)
from maref.desktop.screen_parser import UIElementType


class TestAXRoleMapping:
    def test_button_mapping(self):
        assert ax_role_to_element_type("AXButton") == UIElementType.BUTTON

    def test_text_field_mapping(self):
        assert ax_role_to_element_type("AXTextField") == UIElementType.TEXT_FIELD

    def test_checkbox_mapping(self):
        assert ax_role_to_element_type("AXCheckBox") == UIElementType.CHECKBOX

    def test_unknown_role(self):
        assert ax_role_to_element_type("AXSplonge") == UIElementType.UNKNOWN

    def test_static_text(self):
        assert ax_role_to_element_type("AXStaticText") == UIElementType.LABEL


class TestAccessibilityParserInit:
    def test_create_parser(self):
        parser = AccessibilityParser()
        assert parser.backend == "accessibility"

    def test_permission_check(self):
        parser = AccessibilityParser()
        result = parser.check_permissions()
        assert isinstance(result, bool)

    def test_initialized_false_by_default(self):
        parser = AccessibilityParser()
        assert not parser.initialized


class TestAccessibilityParserIntegration:
    @pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
    def test_parse_frontmost_window(self):
        parser = AccessibilityParser()
        parser.initialize()
        result = parser.parse()
        assert result is not None
        assert len(result.elements) > 0
        assert len(result.elements) > 0

    @pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
    def test_parse_specific_app(self):
        parser = AccessibilityParser()
        parser.initialize()
        result = parser.parse(target_app="Finder")
        assert result is not None
        assert len(result.elements) > 0

    @pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
    def test_elements_have_positions(self):
        parser = AccessibilityParser()
        parser.initialize()
        result = parser.parse()
        for el in result.elements:
            assert el.bbox.width > 0
            assert el.bbox.height > 0


class TestAccessibilityParserMocked:
    def test_parse_mocked_elements(self):
        mock_json = json.dumps([
            {"role": "AXButton", "title": "OK", "x": 10, "y": 20, "width": 80, "height": 30,
             "enabled": True, "focused": False, "selected": False, "description": "", "value": ""},
            {"role": "AXTextField", "title": "Search", "x": 100, "y": 20, "width": 200, "height": 22,
             "enabled": True, "focused": True, "selected": False, "description": "", "value": ""},
        ])
        parser = AccessibilityParser()
        parser._initialized = True
        parser._permission_granted = True
        parser._run_jxa = lambda app: mock_json
        result = parser.parse()
        assert len(result.elements) == 2
        assert result.elements[0].element_type == UIElementType.BUTTON
        assert result.elements[0].text == "OK"
        assert result.elements[1].element_type == UIElementType.TEXT_FIELD
        assert result.elements[0].bbox.x == 10
        assert result.elements[1].bbox.width == 200

    def test_parse_handles_disabled_elements(self):
        mock_json = json.dumps([
            {"role": "AXButton", "title": "Disabled", "x": 10, "y": 20, "width": 80, "height": 30,
             "enabled": False, "focused": False, "selected": False, "description": "", "value": ""},
            {"role": "AXButton", "title": "Enabled", "x": 100, "y": 20, "width": 80, "height": 30,
             "enabled": True, "focused": False, "selected": False, "description": "", "value": ""},
        ])
        parser = AccessibilityParser()
        parser._initialized = True
        parser._permission_granted = True
        parser._run_jxa = lambda app: mock_json
        result = parser.parse()
        assert len(result.elements) == 1
        assert result.elements[0].text == "Enabled"

    def test_parse_handles_jxa_failure(self):
        parser = AccessibilityParser()
        parser._initialized = True
        parser._permission_granted = True
        parser._run_jxa = lambda app: ""
        result = parser.parse()
        assert len(result.elements) == 0
