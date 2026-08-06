"""Unit tests for BrowserController (dry-run mode only)."""

from __future__ import annotations

import pytest

from maref.desktop.browser_controller import (
    BrowserAction,
    BrowserController,
    BrowserResult,
)
from maref.desktop.browser_types import BrowserType


class TestBrowserControllerDryRun:
    @pytest.fixture
    def controller(self) -> BrowserController:
        return BrowserController(dry_run=True)

    def test_init_dry_run(self, controller: BrowserController) -> None:
        assert controller.dry_run is True

    def test_init_chromium_default(self) -> None:
        ctrl = BrowserController(dry_run=True)
        assert ctrl.dry_run is True

    def test_navigate_safe_domain(self, controller: BrowserController) -> None:
        result = controller.navigate("https://github.com/maref-org/maref")
        assert isinstance(result, BrowserResult)
        assert result.success is True
        assert result.action == BrowserAction.NAVIGATE

    def test_navigate_unsafe_domain(self, controller: BrowserController) -> None:
        result = controller.navigate("https://evil.example.com")
        assert isinstance(result, BrowserResult)
        assert result.success is False
        assert "not in safe list" in result.error.lower()

    def test_click(self, controller: BrowserController) -> None:
        result = controller.click("#submit-btn")
        assert isinstance(result, BrowserResult)
        assert result.action == BrowserAction.CLICK

    def test_type_text(self, controller: BrowserController) -> None:
        result = controller.type_text("#username", "test_user")
        assert isinstance(result, BrowserResult)
        assert result.action == BrowserAction.TYPE

    def test_extract_text(self, controller: BrowserController) -> None:
        result = controller.extract_text()
        assert isinstance(result, BrowserResult)
        assert result.action == BrowserAction.EXTRACT_TEXT
        assert "dry run" in result.text.lower()

    def test_extract_links(self, controller: BrowserController) -> None:
        result = controller.extract_links()
        assert isinstance(result, BrowserResult)
        assert result.action == BrowserAction.EXTRACT_LINKS
        assert len(result.links) >= 0

    def test_screenshot(self, controller: BrowserController) -> None:
        result = controller.screenshot()
        assert isinstance(result, BrowserResult)
        assert result.action == BrowserAction.SCREENSHOT

    def test_execute_js_safe(self, controller: BrowserController) -> None:
        result = controller.execute_js("document.title")
        assert isinstance(result, BrowserResult)
        assert result.action == BrowserAction.EXECUTE_JS

    def test_execute_js_blocked(self, controller: BrowserController) -> None:
        result = controller.execute_js("fetch('https://evil.com')")
        assert isinstance(result, BrowserResult)
        assert result.success is False

    def test_get_operation_log_empty(self, controller: BrowserController) -> None:
        log = controller.get_operation_log()
        assert isinstance(log, list)
        assert len(log) >= 0

    def test_get_operation_log_after_actions(self, controller: BrowserController) -> None:
        controller.navigate("https://github.com")
        controller.click("#btn")
        controller.type_text("#input", "hello")
        log = controller.get_operation_log()
        assert len(log) == 3

    def test_is_safe_domain_whitelisted(self, controller: BrowserController) -> None:
        assert controller.is_safe_domain("https://docs.python.org/3/") is True

    def test_is_safe_domain_not_whitelisted(self, controller: BrowserController) -> None:
        assert controller.is_safe_domain("https://unknown-site.org") is False

    def test_close(self, controller: BrowserController) -> None:
        controller.close()


class TestBrowserControllerEdgeCases:
    def test_navigate_empty_url(self) -> None:
        controller = BrowserController(dry_run=True)
        result = controller.navigate("")
        assert result.success is False

    def test_navigate_invalid_url(self) -> None:
        controller = BrowserController(dry_run=True)
        result = controller.navigate("not-a-valid-url")
        assert result.success is False
        assert result.error

    def test_click_empty_selector(self) -> None:
        controller = BrowserController(dry_run=True)
        result = controller.click("")
        assert result.success is True

    def test_type_empty_text(self) -> None:
        controller = BrowserController(dry_run=True)
        result = controller.type_text("#input", "")
        assert result.success is True

    def test_execute_js_with_fetch(self) -> None:
        controller = BrowserController(dry_run=True)
        result = controller.execute_js("fetch('/api/data')")
        assert result.success is False

    def test_execute_js_with_xmlhttp(self) -> None:
        controller = BrowserController(dry_run=True)
        result = controller.execute_js("new XMLHttpRequest()")
        assert result.success is False

    def test_execute_js_with_websocket(self) -> None:
        controller = BrowserController(dry_run=True)
        result = controller.execute_js("new WebSocket('wss://example.com')")
        assert result.success is False

    def test_execute_js_with_localstorage(self) -> None:
        controller = BrowserController(dry_run=True)
        result = controller.execute_js("localStorage.setItem('key', 'val')")
        assert result.success is False

    def test_browser_result_to_dict(self) -> None:
        result = BrowserResult(success=True, action=BrowserAction.NAVIGATE, url="https://example.com")
        d = result.to_dict()
        assert d["success"] is True
        assert d["action"] == "navigate"
        assert d["url"] == "https://example.com"


class TestBrowserControllerNewMethods:
    @pytest.fixture
    def controller(self) -> BrowserController:
        return BrowserController(dry_run=True)

    def test_get_html_dry_run(self, controller: BrowserController) -> None:
        result = controller.get_html()
        assert isinstance(result, BrowserResult)
        assert result.action == BrowserAction.GET_HTML
        assert "[DRY RUN]" in result.html

    def test_wait_for_selector_dry_run(self, controller: BrowserController) -> None:
        result = controller.wait_for_selector("#test-btn", timeout=5.0)
        assert isinstance(result, BrowserResult)
        assert result.action == BrowserAction.WAIT
        assert result.success is True

    def test_wait_for_navigation_dry_run(self, controller: BrowserController) -> None:
        result = controller.wait_for_navigation(timeout=10.0)
        assert isinstance(result, BrowserResult)
        assert result.action == BrowserAction.WAIT
        assert result.success is True

    def test_get_cookies_dry_run(self, controller: BrowserController) -> None:
        cookies = controller.get_cookies()
        assert isinstance(cookies, list)

    def test_set_cookies_dry_run(self, controller: BrowserController) -> None:
        result = controller.set_cookies([{"name": "test", "value": "val", "domain": ".example.com"}])
        assert isinstance(result, BrowserResult)

    def test_session_id_unique(self) -> None:
        c1 = BrowserController(dry_run=True)
        c2 = BrowserController(dry_run=True)
        assert c1.session_id != c2.session_id

    def test_dry_run_default_false_when_no_env(self) -> None:
        import os
        old = os.environ.pop("MAREF_BROWSER_DRY_RUN", None)
        ctrl = BrowserController()
        assert ctrl.dry_run is False
        if old is not None:
            os.environ["MAREF_BROWSER_DRY_RUN"] = old
