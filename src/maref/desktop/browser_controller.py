from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BrowserType(str, Enum):
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class BrowserAction(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    SCREENSHOT = "screenshot"
    EXTRACT_TEXT = "extract_text"
    EXTRACT_LINKS = "extract_links"
    WAIT = "wait"
    EXECUTE_JS = "execute_js"
    GET_HTML = "get_html"


@dataclass
class BrowserResult:
    success: bool
    action: BrowserAction
    url: str = ""
    text: str = ""
    links: list[str] = field(default_factory=list)
    html: str = ""
    error: str = ""
    screenshot_bytes: bytes | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action.value,
            "url": self.url,
            "text_preview": self.text[:200],
            "link_count": len(self.links),
            "error": self.error,
        }


class BrowserController:
    """Safe browser automation wrapper for Playwright.

    Provides DOM-level control for web application interaction.
    Safety: runs in dry-run mode by default; all navigation goes through
    safe-site allow list.
    """

    SAFE_DOMAINS = {
        "docs.python.org",
        "developer.apple.com",
        "learn.microsoft.com",
        "github.com",
        "stackoverflow.com",
        "wikipedia.org",
    }

    def __init__(
        self,
        browser_type: BrowserType = BrowserType.CHROMIUM,
        dry_run: bool = True,
        safe_domains: set[str] | None = None,
    ) -> None:
        self.browser_type = browser_type
        self._dry_run = dry_run
        self._safe_domains = safe_domains or self.SAFE_DOMAINS
        self._playwright_available = False
        self._browser = None
        self._page = None
        self._operation_log: list[BrowserResult] = []
        try:
            import playwright  # noqa: F401

            self._playwright_available = True
        except ImportError:
            pass

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    def is_safe_domain(self, url: str) -> bool:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        return domain in self._safe_domains

    def navigate(self, url: str) -> BrowserResult:
        if not self.is_safe_domain(url):
            return BrowserResult(
                success=False,
                action=BrowserAction.NAVIGATE,
                url=url,
                error=f"Domain not in safe list: {url}",
            )
        if self._dry_run:
            result = BrowserResult(
                success=True,
                action=BrowserAction.NAVIGATE,
                url=url,
                text=f"[DRY RUN] Navigated to {url}",
            )
        else:
            result = self._do_navigate(url)
        self._operation_log.append(result)
        return result

    def click(self, selector: str) -> BrowserResult:
        if self._dry_run:
            result = BrowserResult(
                success=True, action=BrowserAction.CLICK, text=f"[DRY RUN] Clicked {selector}"
            )
        else:
            result = self._do_click(selector)
        self._operation_log.append(result)
        return result

    def type_text(self, selector: str, text: str) -> BrowserResult:
        if self._dry_run:
            result = BrowserResult(
                success=True,
                action=BrowserAction.TYPE,
                text=f"[DRY RUN] Typed '{text}' into {selector}",
            )
        else:
            result = self._do_type(selector, text)
        self._operation_log.append(result)
        return result

    def extract_text(self) -> BrowserResult:
        if self._dry_run:
            result = BrowserResult(
                success=True, action=BrowserAction.EXTRACT_TEXT, text="[DRY RUN] Page text content"
            )
        else:
            result = self._do_extract_text()
        self._operation_log.append(result)
        return result

    def extract_links(self) -> BrowserResult:
        if self._dry_run:
            result = BrowserResult(
                success=True, action=BrowserAction.EXTRACT_LINKS, links=["https://example.com"]
            )
        else:
            result = self._do_extract_links()
        self._operation_log.append(result)
        return result

    def screenshot(self) -> BrowserResult:
        if self._dry_run:
            result = BrowserResult(
                success=True, action=BrowserAction.SCREENSHOT, text="[DRY RUN] Screenshot captured"
            )
        else:
            result = self._do_screenshot()
        self._operation_log.append(result)
        return result

    def execute_js(self, script: str) -> BrowserResult:
        dangerous_patterns = [
            "fetch(",
            "XMLHttpRequest",
            "WebSocket",
            "localStorage",
            "sessionStorage",
            "document.cookie",
        ]
        for pattern in dangerous_patterns:
            if pattern in script:
                return BrowserResult(
                    success=False,
                    action=BrowserAction.EXECUTE_JS,
                    error=f"Blocked: dangerous JS pattern '{pattern}'",
                )
        if self._dry_run:
            result = BrowserResult(
                success=True, action=BrowserAction.EXECUTE_JS, text="[DRY RUN] Executed JS"
            )
        else:
            result = self._do_execute_js(script)
        self._operation_log.append(result)
        return result

    def get_operation_log(self) -> list[BrowserResult]:
        return list(self._operation_log)

    def close(self) -> None:
        if self._browser and self._playwright_available:
            self._browser.close()

    def _do_navigate(self, url: str) -> BrowserResult:
        try:
            import asyncio

            from playwright.async_api import async_playwright

            async def _nav():
                async with async_playwright() as p:
                    browser = await getattr(p, self.browser_type.value).launch()
                    page = await browser.new_page()
                    await page.goto(url)
                    text = await page.inner_text("body")
                    await browser.close()
                    return text

            text = asyncio.run(_nav())
            return BrowserResult(success=True, action=BrowserAction.NAVIGATE, url=url, text=text)
        except Exception as e:
            return BrowserResult(
                success=False, action=BrowserAction.NAVIGATE, url=url, error=str(e)
            )

    def _do_click(self, selector: str) -> BrowserResult:
        return BrowserResult(
            success=False, action=BrowserAction.CLICK, error="Not implemented in shortcut path"
        )

    def _do_type(self, selector: str, text: str) -> BrowserResult:
        return BrowserResult(
            success=False, action=BrowserAction.TYPE, error="Not implemented in shortcut path"
        )

    def _do_extract_text(self) -> BrowserResult:
        return BrowserResult(
            success=False,
            action=BrowserAction.EXTRACT_TEXT,
            error="Not implemented in shortcut path",
        )

    def _do_extract_links(self) -> BrowserResult:
        return BrowserResult(
            success=False,
            action=BrowserAction.EXTRACT_LINKS,
            error="Not implemented in shortcut path",
        )

    def _do_screenshot(self) -> BrowserResult:
        return BrowserResult(
            success=False, action=BrowserAction.SCREENSHOT, error="Not implemented in shortcut path"
        )

    def _do_execute_js(self, script: str) -> BrowserResult:
        return BrowserResult(
            success=False, action=BrowserAction.EXECUTE_JS, error="Not implemented in shortcut path"
        )
