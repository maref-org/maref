from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.tools.browser_server import DomainWhitelist

logger = logging.getLogger(__name__)


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
    """Safe browser automation wrapper for Playwright.

    Provides DOM-level control for web application interaction.
    Safety: runs in dry-run mode by default; all navigation goes through
    safe-site allow list.
    """

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
        dry_run: bool = True,
        safe_domains: list[str] | None = None,
    ) -> None:
        self.browser_type = browser_type
        self._dry_run = dry_run
        self._domain_whitelist = DomainWhitelist(safe_domains or self.DEFAULT_SAFE_DOMAINS)
        self._playwright_available = False
        self._browser: Any = None
        self._page: Any = None
        self._playwright: Any = None
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
        hostname = parsed.hostname or ""
        hostname = hostname.removeprefix("www.")
        return self._domain_whitelist.is_allowed(hostname)

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
                success=True, action=BrowserAction.EXTRACT_LINKS, links=[{"href": "https://example.com", "text": "Example"}]
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
        import asyncio

        async def _close_all():
            if self._page is not None:
                try:
                    await self._page.close()
                except Exception as exc:
                    logger.debug("page.close() failed during close(): %s", exc)
                self._page = None
            if self._browser is not None:
                try:
                    await self._browser.close()
                except Exception as exc:
                    logger.debug("browser.close() failed during close(): %s", exc)
                self._browser = None
            if self._playwright is not None:
                try:
                    await self._playwright.stop()
                except Exception as exc:
                    logger.debug("playwright.stop() failed during close(): %s", exc)
                self._playwright = None

        try:
            asyncio.run(_close_all())
        except RuntimeError:
            pass

    def _do_navigate(self, url: str) -> BrowserResult:
        try:
            import asyncio

            from playwright.async_api import async_playwright

            async def _nav():
                self._playwright = await async_playwright().start()
                self._browser = await getattr(
                    self._playwright, self.browser_type.value
                ).launch()
                self._page = await self._browser.new_page()
                await self._page.goto(url)
                text = await self._page.inner_text("body")
                return text

            text = asyncio.run(_nav())
            return BrowserResult(success=True, action=BrowserAction.NAVIGATE, url=url, text=text)
        except Exception as e:
            # 异常路径必须主动释放已分配的 Playwright 资源，
            # 否则 self._playwright 指向的 Node 子进程会泄漏
            self._cleanup_async_resources()
            return BrowserResult(
                success=False, action=BrowserAction.NAVIGATE, url=url, error=str(e)
            )

    def _cleanup_async_resources(self) -> None:
        """同步释放已分配的 page/browser/playwright，异常路径专用.

        每层独立 try/except，保证上层失败不阻断下层释放。
        与 close() 的差异：本方法在 asyncio.run() 上下文外调度，
        适用于 _do_navigate 等 asyncio.run() 已退出的异常分支。
        """
        import asyncio

        async def _shutdown():
            if self._page is not None:
                try:
                    await self._page.close()
                except Exception as exc:
                    logger.debug("page.close() on abort: %s", exc)
            if self._browser is not None:
                try:
                    await self._browser.close()
                except Exception as exc:
                    logger.debug("browser.close() on abort: %s", exc)
            if self._playwright is not None:
                try:
                    await self._playwright.stop()
                except Exception as exc:
                    logger.debug("playwright.stop() on abort: %s", exc)

        try:
            asyncio.run(_shutdown())
        except RuntimeError as exc:
            # 事件循环已存在的边缘场景，退化为同步置空
            logger.warning("asyncio loop unavailable for cleanup: %s", exc)
        finally:
            self._page = None
            self._browser = None
            self._playwright = None

    def _ensure_page(self) -> None:
        if self._page is not None:
            return
        import asyncio

        from playwright.async_api import async_playwright

        async def _init():
            p = await async_playwright().start()
            self._playwright = p
            self._browser = await getattr(
                p, self.browser_type.value
            ).launch()
            self._page = await self._browser.new_page()

        asyncio.run(_init())

    def _do_click(self, selector: str) -> BrowserResult:
        try:
            import asyncio

            if self._page is None:
                return BrowserResult(
                    success=False, action=BrowserAction.CLICK, error="No active page. Call navigate() first."
                )

            async def _click():
                await self._page.click(selector, timeout=5000)

            asyncio.run(_click())
            return BrowserResult(success=True, action=BrowserAction.CLICK, text=f"Clicked {selector}")
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.CLICK, error=str(e))

    def _do_type(self, selector: str, text: str) -> BrowserResult:
        try:
            import asyncio

            if self._page is None:
                return BrowserResult(
                    success=False, action=BrowserAction.TYPE, error="No active page. Call navigate() first."
                )

            async def _type():
                count = await self._page.locator(selector).count()
                if count > 0:
                    await self._page.fill(selector, text)
                else:
                    await self._page.type(selector, text)

            asyncio.run(_type())
            return BrowserResult(success=True, action=BrowserAction.TYPE, text=f"Typed into {selector}")
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.TYPE, error=str(e))

    def _do_extract_text(self) -> BrowserResult:
        try:
            import asyncio

            if self._page is None:
                return BrowserResult(
                    success=False, action=BrowserAction.EXTRACT_TEXT, error="No active page. Call navigate() first."
                )

            async def _extract():
                return await self._page.evaluate("document.body.innerText")

            text = asyncio.run(_extract())
            return BrowserResult(success=True, action=BrowserAction.EXTRACT_TEXT, text=text)
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.EXTRACT_TEXT, error=str(e))

    def _do_extract_links(self) -> BrowserResult:
        try:
            import asyncio

            if self._page is None:
                return BrowserResult(
                    success=False, action=BrowserAction.EXTRACT_LINKS, error="No active page. Call navigate() first."
                )

            async def _extract():
                return await self._page.evaluate(
                    "Array.from(document.querySelectorAll('a')).map(a => ({href: a.href, text: a.textContent.trim()}))"
                )

            links = asyncio.run(_extract())
            return BrowserResult(success=True, action=BrowserAction.EXTRACT_LINKS, links=links)
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.EXTRACT_LINKS, error=str(e))

    def _do_screenshot(self) -> BrowserResult:
        try:
            import asyncio

            if self._page is None:
                return BrowserResult(
                    success=False, action=BrowserAction.SCREENSHOT, error="No active page. Call navigate() first."
                )

            async def _shot():
                png_bytes = await self._page.screenshot(full_page=True)
                return base64.b64encode(png_bytes).decode("ascii")

            b64 = asyncio.run(_shot())
            return BrowserResult(
                success=True,
                action=BrowserAction.SCREENSHOT,
                text=b64,
                screenshot_bytes=base64.b64decode(b64),
            )
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.SCREENSHOT, error=str(e))

    def _do_execute_js(self, script: str) -> BrowserResult:
        try:
            import asyncio

            if self._page is None:
                return BrowserResult(
                    success=False, action=BrowserAction.EXECUTE_JS, error="No active page. Call navigate() first."
                )

            async def _exec():
                return await self._page.evaluate(script)

            result = asyncio.run(_exec())
            return BrowserResult(success=True, action=BrowserAction.EXECUTE_JS, text=str(result))
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.EXECUTE_JS, error=str(e))
