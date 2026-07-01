from __future__ import annotations

import asyncio
import base64
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.desktop.browser_auth import AuthSessionManager
from maref.desktop.browser_session_pool import BrowserSessionPool, PlaywrightNotAvailableError
from maref.desktop.browser_types import BrowserType

logger = logging.getLogger(__name__)


class _DeprecatedBrowserType(str, Enum):
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
    links: list[dict[str, str]] = field(default_factory=list)
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
    DEFAULT_SAFE_DOMAINS: list[str] = [
        "docs.python.org",
        "developer.apple.com",
        "learn.microsoft.com",
        "github.com",
        "stackoverflow.com",
        "wikipedia.org",
    ]

    def __init__(
        self,
        browser_type: BrowserType = BrowserType.CHROMIUM,
        dry_run: bool | None = None,
        safe_domains: list[str] | None = None,
        session_id: str | None = None,
    ) -> None:
        self.browser_type = browser_type
        dry_run_env = os.environ.get("MAREF_BROWSER_DRY_RUN")
        if dry_run is not None:
            self._dry_run = dry_run
        elif dry_run_env is not None:
            self._dry_run = dry_run_env.lower() in ("1", "true", "yes")
        else:
            self._dry_run = False
        from maref.tools.browser_server import DomainWhitelist as _DomainWhitelist
        self._domain_whitelist = _DomainWhitelist(safe_domains or self.DEFAULT_SAFE_DOMAINS)
        self._session_id = session_id or f"bc_{id(self)}"
        self._pool = BrowserSessionPool()
        self._operation_log: list[BrowserResult] = []
        self._auth_manager = AuthSessionManager()
        self._page: Any | None = None

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def pool(self) -> BrowserSessionPool:
        return self._pool

    def is_safe_domain(self, url: str) -> bool:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        hostname = hostname.removeprefix("www.")
        return self._domain_whitelist.is_allowed(hostname)

    def navigate(self, url: str) -> BrowserResult:
        if not self.is_safe_domain(url):
            result = BrowserResult(
                success=False,
                action=BrowserAction.NAVIGATE,
                url=url,
                error=f"Domain not in safe list: {url}",
            )
        elif self._dry_run:
            result = BrowserResult(
                success=True,
                action=BrowserAction.NAVIGATE,
                url=url,
                text=f"[DRY RUN] Navigated to {url}",
            )
        else:
            result = _run_async(self._do_navigate(url))
        self._operation_log.append(result)
        return result

    def click(self, selector: str) -> BrowserResult:
        if self._dry_run:
            result = BrowserResult(success=True, action=BrowserAction.CLICK, text=f"[DRY RUN] Clicked {selector}")
        else:
            result = _run_async(self._do_click(selector))
        self._operation_log.append(result)
        return result

    def type_text(self, selector: str, text: str) -> BrowserResult:
        if self._dry_run:
            result = BrowserResult(
                success=True, action=BrowserAction.TYPE, text=f"[DRY RUN] Typed '{text}' into {selector}"
            )
        else:
            result = _run_async(self._do_type(selector, text))
        self._operation_log.append(result)
        return result

    def extract_text(self) -> BrowserResult:
        if self._dry_run:
            result = BrowserResult(success=True, action=BrowserAction.EXTRACT_TEXT, text="[DRY RUN] Page text content")
        else:
            result = _run_async(self._do_extract_text())
        self._operation_log.append(result)
        return result

    def extract_links(self) -> BrowserResult:
        if self._dry_run:
            result = BrowserResult(
                success=True, action=BrowserAction.EXTRACT_LINKS, links=[{"href": "https://example.com", "text": "Example"}]
            )
        else:
            result = _run_async(self._do_extract_links())
        self._operation_log.append(result)
        return result

    def screenshot(self) -> BrowserResult:
        if self._dry_run:
            result = BrowserResult(success=True, action=BrowserAction.SCREENSHOT, text="[DRY RUN] Screenshot captured")
        else:
            result = _run_async(self._do_screenshot())
        self._operation_log.append(result)
        return result

    def execute_js(self, script: str) -> BrowserResult:
        dangerous_patterns = [
            "fetch(", "XMLHttpRequest", "WebSocket",
            "localStorage", "sessionStorage", "document.cookie",
        ]
        for pattern in dangerous_patterns:
            if pattern in script:
                return BrowserResult(
                    success=False, action=BrowserAction.EXECUTE_JS,
                    error=f"Blocked: dangerous JS pattern '{pattern}'",
                )
        if self._dry_run:
            result = BrowserResult(success=True, action=BrowserAction.EXECUTE_JS, text="[DRY RUN] Executed JS")
        else:
            result = _run_async(self._do_execute_js(script))
        self._operation_log.append(result)
        return result

    def get_html(self) -> BrowserResult:
        if self._dry_run:
            result = BrowserResult(success=True, action=BrowserAction.GET_HTML, html="<html><body>[DRY RUN]</body></html>")
        else:
            result = _run_async(self._do_get_html())
        self._operation_log.append(result)
        return result

    def wait_for_selector(self, selector: str, timeout: float = 10.0) -> BrowserResult:
        if self._dry_run:
            result = BrowserResult(success=True, action=BrowserAction.WAIT, text=f"[DRY RUN] Waited for {selector}")
        else:
            result = _run_async(self._do_wait_for_selector(selector, timeout))
        self._operation_log.append(result)
        return result

    def wait_for_navigation(self, timeout: float = 30.0) -> BrowserResult:
        if self._dry_run:
            result = BrowserResult(success=True, action=BrowserAction.WAIT, text="[DRY RUN] Waited for navigation")
        else:
            result = _run_async(self._do_wait_for_navigation(timeout))
        self._operation_log.append(result)
        return result

    def get_cookies(self) -> list[dict[str, Any]]:
        result = _run_async(self._do_get_cookies())
        return result

    def set_cookies(self, cookies: list[dict[str, Any]]) -> BrowserResult:
        return _run_async(self._do_set_cookies(cookies))

    def get_operation_log(self) -> list[BrowserResult]:
        return list(self._operation_log)

    def close(self) -> None:
        _run_async(self._pool.release(self._session_id))

    # ------------------------------------------------------------------
    # Async implementations
    # ------------------------------------------------------------------

    async def _ensure_session(self) -> Any | None:
        try:
            session = await self._pool.acquire(self._session_id, self.browser_type)
            return session
        except PlaywrightNotAvailableError:
            return None

    async def _ensure_page(self) -> Any | None:
        if self._page is not None:
            return self._page
        session = await self._ensure_session()
        return session.active_page if session else None

    async def _do_navigate(self, url: str) -> BrowserResult:
        try:
            session = await self._pool.acquire(self._session_id, self.browser_type)
            page = session.active_page
            if page is None:
                page = await self._pool.new_page(self._session_id)
            await page.goto(url, timeout=30000)
            text = await page.evaluate("document.body.innerText")
            try:
                cookies = await page.context.cookies()
                self._auth_manager.save_state(url, cookies=cookies)
            except Exception:
                pass
            return BrowserResult(success=True, action=BrowserAction.NAVIGATE, url=url, text=text)
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.NAVIGATE, url=url, error=str(e))

    async def _do_click(self, selector: str) -> BrowserResult:
        try:
            page = await self._ensure_page()
            if page is None:
                return BrowserResult(success=False, action=BrowserAction.CLICK, error="No active page")
            await page.click(selector, timeout=5000)
            return BrowserResult(success=True, action=BrowserAction.CLICK, text=f"Clicked {selector}")
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.CLICK, error=str(e))

    async def _do_type(self, selector: str, text: str) -> BrowserResult:
        try:
            page = await self._ensure_page()
            if page is None:
                return BrowserResult(success=False, action=BrowserAction.TYPE, error="No active page")
            count = await page.locator(selector).count()
            if count > 0:
                await page.fill(selector, text)
            else:
                await page.type(selector, text)
            return BrowserResult(success=True, action=BrowserAction.TYPE, text=f"Typed into {selector}")
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.TYPE, error=str(e))

    async def _do_extract_text(self) -> BrowserResult:
        try:
            page = await self._ensure_page()
            if page is None:
                return BrowserResult(success=False, action=BrowserAction.EXTRACT_TEXT, error="No active page")
            text = await page.evaluate("document.body.innerText")
            return BrowserResult(success=True, action=BrowserAction.EXTRACT_TEXT, text=text)
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.EXTRACT_TEXT, error=str(e))

    async def _do_extract_links(self) -> BrowserResult:
        try:
            page = await self._ensure_page()
            if page is None:
                return BrowserResult(success=False, action=BrowserAction.EXTRACT_LINKS, error="No active page")
            links = await page.evaluate(
                "Array.from(document.querySelectorAll('a')).map(a => ({href: a.href, text: a.textContent.trim()}))"
            )
            return BrowserResult(success=True, action=BrowserAction.EXTRACT_LINKS, links=links)
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.EXTRACT_LINKS, error=str(e))

    async def _do_screenshot(self) -> BrowserResult:
        try:
            page = await self._ensure_page()
            if page is None:
                return BrowserResult(success=False, action=BrowserAction.SCREENSHOT, error="No active page")
            png_bytes = await page.screenshot(full_page=True)
            b64 = base64.b64encode(png_bytes).decode("ascii")
            return BrowserResult(
                success=True, action=BrowserAction.SCREENSHOT, text=b64, screenshot_bytes=png_bytes,
            )
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.SCREENSHOT, error=str(e))

    async def _do_execute_js(self, script: str) -> BrowserResult:
        try:
            page = await self._ensure_page()
            if page is None:
                return BrowserResult(success=False, action=BrowserAction.EXECUTE_JS, error="No active page")
            result = await page.evaluate(script)
            return BrowserResult(success=True, action=BrowserAction.EXECUTE_JS, text=str(result))
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.EXECUTE_JS, error=str(e))

    async def _do_get_html(self) -> BrowserResult:
        try:
            page = await self._ensure_page()
            if page is None:
                return BrowserResult(success=False, action=BrowserAction.GET_HTML, error="No active page")
            html = await page.evaluate("document.documentElement.outerHTML")
            return BrowserResult(success=True, action=BrowserAction.GET_HTML, html=html)
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.GET_HTML, error=str(e))

    async def _do_wait_for_selector(self, selector: str, timeout: float) -> BrowserResult:
        try:
            page = await self._ensure_page()
            if page is None:
                return BrowserResult(success=False, action=BrowserAction.WAIT, error="No active page")
            await page.wait_for_selector(selector, timeout=int(timeout * 1000))
            return BrowserResult(success=True, action=BrowserAction.WAIT, text=f"Selector '{selector}' visible")
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.WAIT, error=str(e))

    async def _do_wait_for_navigation(self, timeout: float) -> BrowserResult:
        try:
            page = await self._ensure_page()
            if page is None:
                return BrowserResult(success=False, action=BrowserAction.WAIT, error="No active page")
            await page.wait_for_load_state("networkidle", timeout=int(timeout * 1000))
            return BrowserResult(success=True, action=BrowserAction.WAIT, text="Navigation completed")
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.WAIT, error=str(e))

    async def _do_get_cookies(self) -> list[dict[str, Any]]:
        try:
            page = await self._ensure_page()
            if page is None:
                return []
            return await page.context.cookies()
        except Exception:
            return []

    async def _do_set_cookies(self, cookies: list[dict[str, Any]]) -> BrowserResult:
        try:
            page = await self._ensure_page()
            if page is None:
                return BrowserResult(success=False, action=BrowserAction.EXECUTE_JS, error="No active page")
            await page.context.add_cookies(cookies)
            return BrowserResult(success=True, action=BrowserAction.EXECUTE_JS, text="Cookies set")
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.EXECUTE_JS, error=str(e))


def _run_async(coro: Any) -> Any:
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(asyncio.run, coro)
                return fut.result()
    except RuntimeError:
        pass
    return asyncio.run(coro)
