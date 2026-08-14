from __future__ import annotations

from maref.desktop.browser_controller import (
    BrowserAction,
    BrowserController,
    BrowserResult,
    BrowserType,
)


class TestDeprecatedBrowserType:
    def test_values(self) -> None:
        assert BrowserType.CHROMIUM.value == "chromium"
        assert BrowserType.FIREFOX.value == "firefox"
        assert BrowserType.WEBKIT.value == "webkit"


class TestBrowserAction:
    def test_values(self) -> None:
        assert BrowserAction.NAVIGATE.value == "navigate"
        assert BrowserAction.CLICK.value == "click"
        assert BrowserAction.SCREENSHOT.value == "screenshot"
        assert BrowserAction.EXECUTE_JS.value == "execute_js"
        assert BrowserAction.GET_HTML.value == "get_html"
        assert BrowserAction.GO_BACK.value == "go_back"
        assert BrowserAction.GO_FORWARD.value == "go_forward"
        assert BrowserAction.RELOAD.value == "reload"
        assert BrowserAction.GET_ELEMENT_TEXT.value == "get_element_text"
        assert len(BrowserAction) == 14


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
        bc = BrowserController()
        # 契约 (2a14c38c): 无 MAREF_BROWSER_DRY_RUN env / 无显式参数 → 默认 live 模式
        assert bc.dry_run is False
        assert bc.browser_type == BrowserType.CHROMIUM

    def test_dry_run_from_constructor(self) -> None:
        bc = BrowserController(dry_run=True)
        assert bc.dry_run is True

    def test_dry_run_false_from_constructor(self) -> None:
        bc = BrowserController(dry_run=False)
        assert bc.dry_run is False

    def test_is_safe_domain_allowed(self) -> None:
        bc = BrowserController()
        assert bc.is_safe_domain("https://docs.python.org") is True
        assert bc.is_safe_domain("https://github.com/maref") is True

    def test_is_safe_domain_blocked(self) -> None:
        bc = BrowserController()
        assert bc.is_safe_domain("https://malware.com") is False
        assert bc.is_safe_domain("http://evil.example") is False

    def test_is_safe_domain_invalid(self) -> None:
        bc = BrowserController()
        assert bc.is_safe_domain("not-a-url") is False

    def test_navigate_dry_run(self) -> None:
        bc = BrowserController(dry_run=True)
        result = bc.navigate("https://docs.python.org")
        assert result.success is True
        assert "[DRY RUN]" in result.text

    def test_navigate_blocked_domain(self) -> None:
        bc = BrowserController()
        result = bc.navigate("https://malware.com")
        assert result.success is False
        assert "not in safe list" in result.error
