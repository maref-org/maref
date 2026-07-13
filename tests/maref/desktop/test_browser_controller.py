from __future__ import annotations

from unittest.mock import patch

from maref.desktop.browser_controller import (
    BrowserAction,
    BrowserController,
    BrowserResult,
    _DeprecatedBrowserType,
)


class TestDeprecatedBrowserType:
    def test_values(self) -> None:
        assert _DeprecatedBrowserType.CHROMIUM.value == "chromium"
        assert _DeprecatedBrowserType.FIREFOX.value == "firefox"
        assert _DeprecatedBrowserType.WEBKIT.value == "webkit"


class TestBrowserAction:
    def test_values(self) -> None:
        assert BrowserAction.NAVIGATE.value == "navigate"
        assert BrowserAction.CLICK.value == "click"
        assert BrowserAction.SCREENSHOT.value == "screenshot"
        assert BrowserAction.EXECUTE_JS.value == "execute_js"
        assert BrowserAction.GET_HTML.value == "get_html"
        assert len(BrowserAction) == 10


class TestBrowserResult:
    def test_defaults(self) -> None:
        result = BrowserResult(success=True, action=BrowserAction.NAVIGATE)
        assert result.success is True
        assert result.action == BrowserAction.NAVIGATE
        assert result.url == ""
        assert result.text == ""
        assert result.links == []
        assert result.error == ""
        assert result.screenshot_bytes is None

    def test_with_error(self) -> None:
        result = BrowserResult(
            success=False,
            action=BrowserAction.NAVIGATE,
            url="https://example.com",
            error="timeout",
        )
        assert result.success is False
        assert result.url == "https://example.com"
        assert result.error == "timeout"

    def test_to_dict(self) -> None:
        result = BrowserResult(
            success=True,
            action=BrowserAction.CLICK,
            url="https://example.com",
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["action"] == "click"
        assert d["url"] == "https://example.com"


class TestBrowserController:
    def test_default_init(self) -> None:
        with patch("maref.desktop.browser_controller.BrowserSessionPool"):
            bc = BrowserController()
            assert bc.dry_run is False
            assert bc.session_id.startswith("bc_")

    def test_dry_run_from_env(self) -> None:
        with patch("maref.desktop.browser_controller.BrowserSessionPool"):
            with patch.dict("os.environ", {"MAREF_BROWSER_DRY_RUN": "1"}):
                bc = BrowserController()
                assert bc.dry_run is True

    def test_dry_run_from_constructor(self) -> None:
        with patch("maref.desktop.browser_controller.BrowserSessionPool"):
            bc = BrowserController(dry_run=True)
            assert bc.dry_run is True

    def test_dry_run_false_from_env(self) -> None:
        with patch("maref.desktop.browser_controller.BrowserSessionPool"):
            with patch.dict("os.environ", {"MAREF_BROWSER_DRY_RUN": "0"}):
                bc = BrowserController()
                assert bc.dry_run is False

    def test_is_safe_domain_allowed(self) -> None:
        with patch("maref.desktop.browser_controller.BrowserSessionPool"):
            bc = BrowserController()
            assert bc.is_safe_domain("https://docs.python.org") is True
            assert bc.is_safe_domain("https://github.com/maref") is True

    def test_is_safe_domain_blocked(self) -> None:
        with patch("maref.desktop.browser_controller.BrowserSessionPool"):
            bc = BrowserController()
            assert bc.is_safe_domain("https://malware.com") is False
            assert bc.is_safe_domain("http://evil.example") is False

    def test_is_safe_domain_invalid(self) -> None:
        with patch("maref.desktop.browser_controller.BrowserSessionPool"):
            bc = BrowserController()
            assert bc.is_safe_domain("not-a-url") is False

    def test_properties(self) -> None:
        with patch("maref.desktop.browser_controller.BrowserSessionPool"):
            bc = BrowserController()
            assert bc.pool is not None
