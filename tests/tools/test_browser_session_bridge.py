from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from maref.tools.browser_session_bridge import BrowserSessionBridge


class TestBrowserSessionBridge:
    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        BrowserSessionBridge._instance = None

    @pytest.fixture
    def bridge(self) -> BrowserSessionBridge:
        return BrowserSessionBridge()

    def test_singleton(self) -> None:
        b1 = BrowserSessionBridge()
        b2 = BrowserSessionBridge()
        assert b1 is b2

    def test_register_and_get_controller(self, bridge: BrowserSessionBridge) -> None:
        mock_ctrl = MagicMock()
        mock_ctrl.session_id = "test-session"
        bridge.register(mock_ctrl)
        assert bridge.get_controller("test-session") is mock_ctrl

    def test_unregister(self, bridge: BrowserSessionBridge) -> None:
        mock_ctrl = MagicMock()
        mock_ctrl.session_id = "test-session"
        bridge.register(mock_ctrl)
        bridge.unregister("test-session")
        assert bridge.get_controller("test-session") is None

    def test_get_first_controller_when_no_session_id(self, bridge: BrowserSessionBridge) -> None:
        mock_ctrl = MagicMock()
        mock_ctrl.session_id = "s1"
        bridge.register(mock_ctrl)
        assert bridge.get_controller() is mock_ctrl

    def test_get_controller_returns_none_when_empty(self, bridge: BrowserSessionBridge) -> None:
        assert bridge.get_controller() is None
        assert bridge.get_controller("any") is None

    def test_has_active_session_false_when_empty(self, bridge: BrowserSessionBridge) -> None:
        assert bridge.has_active_session() is False

    def test_has_active_session_true_with_active_page(self, bridge: BrowserSessionBridge) -> None:
        mock_ctrl = MagicMock()
        mock_ctrl.session_id = "s1"
        mock_pool = MagicMock()
        mock_pool.get_active_page.return_value = MagicMock()
        mock_ctrl.pool = mock_pool
        bridge.register(mock_ctrl)
        assert bridge.has_active_session() is True

    def test_screenshot_url_returns_none_when_no_controller(self, bridge: BrowserSessionBridge) -> None:
        result = bridge.screenshot_url("https://example.com")
        assert result is None

    def test_screenshot_url_returns_error_on_unsafe_domain(self, bridge: BrowserSessionBridge) -> None:
        mock_ctrl = MagicMock()
        mock_ctrl.session_id = "s1"
        mock_pool = MagicMock()
        mock_pool.get_active_page.return_value = MagicMock()
        mock_ctrl.pool = mock_pool
        mock_ctrl.is_safe_domain.return_value = False
        bridge.register(mock_ctrl)
        result = bridge.screenshot_url("https://evil.com")
        assert result is not None
        assert "error" in result

    def test_screenshot_url_success(self, bridge: BrowserSessionBridge) -> None:
        mock_ctrl = MagicMock()
        mock_ctrl.session_id = "s1"
        mock_pool = MagicMock()
        mock_pool.get_active_page.return_value = MagicMock()
        mock_ctrl.pool = mock_pool
        mock_ctrl.is_safe_domain.return_value = True

        mock_nav = MagicMock()
        mock_nav.success = True
        mock_ctrl.navigate.return_value = mock_nav

        mock_shot = MagicMock()
        mock_shot.success = True
        mock_shot.screenshot_bytes = b"fake_png_bytes"
        mock_ctrl.screenshot.return_value = mock_shot

        bridge.register(mock_ctrl)
        result = bridge.screenshot_url("https://github.com")
        assert result is not None
        assert result["source"] == "bridge"
        assert "screenshot" in result

    def test_take_headless_screenshot_no_playwright(self, bridge: BrowserSessionBridge) -> None:
        with patch("maref.tools.browser_session_bridge.BrowserSessionPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool.is_available = False
            mock_pool_cls.return_value = mock_pool
            result = bridge.take_headless_screenshot("https://example.com")
            assert result is None
