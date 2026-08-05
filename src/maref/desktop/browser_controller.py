from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.desktop.browser_session_pool import BrowserSessionPool
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
    GO_BACK = "go_back"
    GO_FORWARD = "go_forward"
    RELOAD = "reload"
    GET_ELEMENT_TEXT = "get_element_text"


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
    Safety: dry-run is enabled via the ``MAREF_BROWSER_DRY_RUN`` env var
    (values 1/true/yes) or the ``dry_run=True`` constructor flag; all
    navigation goes through the safe-site allow list. Defaults to live
    mode when neither is provided.
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
        self._domain_whitelist = DomainWhitelist(safe_domains or self.DEFAULT_SAFE_DOMAINS)
        self._session_id = session_id or f"bc_{id(self)}"
        self._pool = BrowserSessionPool()
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
                success=True,
                action=BrowserAction.EXTRACT_LINKS,
                links=[{"href": "https://example.com", "text": "Example"}],
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

    def get_html(self) -> BrowserResult:
        if self._dry_run:
            result = BrowserResult(
                success=True,
                action=BrowserAction.GET_HTML,
                html="<html><body>[DRY RUN]</body></html>",
            )
        else:
            result = self._do_get_html()
        self._operation_log.append(result)
        return result

    def wait_for_selector(self, selector: str, timeout: float = 10.0) -> BrowserResult:
        if self._dry_run:
            result = BrowserResult(
                success=True, action=BrowserAction.WAIT, text=f"[DRY RUN] Waited for {selector}"
            )
        else:
            result = self._do_wait_for_selector(selector, timeout)
        self._operation_log.append(result)
        return result

    def wait_for_navigation(self, timeout: float = 30.0) -> BrowserResult:
        if self._dry_run:
            result = BrowserResult(
                success=True, action=BrowserAction.WAIT, text="[DRY RUN] Waited for navigation"
            )
        else:
            result = self._do_wait_for_navigation(timeout)
        self._operation_log.append(result)
        return result

    def get_cookies(self) -> list[dict[str, Any]]:
        if self._dry_run:
            return []
        return self._do_get_cookies()

    def set_cookies(self, cookies: list[dict[str, Any]]) -> BrowserResult:
        if self._dry_run:
            return BrowserResult(
                success=True, action=BrowserAction.EXECUTE_JS, text="[DRY RUN] Cookies set"
            )
        return self._do_set_cookies(cookies)

    def go_back(self) -> BrowserResult:
        if self._dry_run:
            result = BrowserResult(
                success=True, action=BrowserAction.GO_BACK, text="[DRY RUN] Go back"
            )
        else:
            result = self._do_go_back()
        self._operation_log.append(result)
        return result

    def go_forward(self) -> BrowserResult:
        if self._dry_run:
            result = BrowserResult(
                success=True, action=BrowserAction.GO_FORWARD, text="[DRY RUN] Go forward"
            )
        else:
            result = self._do_go_forward()
        self._operation_log.append(result)
        return result

    def reload_page(self) -> BrowserResult:
        if self._dry_run:
            result = BrowserResult(
                success=True, action=BrowserAction.RELOAD, text="[DRY RUN] Reload page"
            )
        else:
            result = self._do_reload_page()
        self._operation_log.append(result)
        return result

    def get_element_text(self, selector: str) -> BrowserResult:
        if self._dry_run:
            result = BrowserResult(
                success=True,
                action=BrowserAction.GET_ELEMENT_TEXT,
                text=f"[DRY RUN] Get text for {selector}",
            )
        else:
            result = self._do_get_element_text(selector)
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
                await self._pool.release(self._session_id)
            except Exception as exc:
                logger.debug("pool.release() failed during close(): %s", exc)

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
                self._browser = await getattr(self._playwright, self.browser_type.value).launch()
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
            self._browser = await getattr(p, self.browser_type.value).launch()
            self._page = await self._browser.new_page()

        asyncio.run(_init())

    def _do_click(self, selector: str) -> BrowserResult:
        try:
            import asyncio

            if self._page is None:
                return BrowserResult(
                    success=False,
                    action=BrowserAction.CLICK,
                    error="No active page. Call navigate() first.",
                )

            async def _click():
                await self._page.click(selector, timeout=5000)

            asyncio.run(_click())
            return BrowserResult(
                success=True, action=BrowserAction.CLICK, text=f"Clicked {selector}"
            )
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.CLICK, error=str(e))

    def _do_type(self, selector: str, text: str) -> BrowserResult:
        try:
            import asyncio

            if self._page is None:
                return BrowserResult(
                    success=False,
                    action=BrowserAction.TYPE,
                    error="No active page. Call navigate() first.",
                )

            async def _type():
                count = await self._page.locator(selector).count()
                if count > 0:
                    await self._page.fill(selector, text)
                else:
                    await self._page.type(selector, text)

            asyncio.run(_type())
            return BrowserResult(
                success=True, action=BrowserAction.TYPE, text=f"Typed into {selector}"
            )
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.TYPE, error=str(e))

    def _do_extract_text(self) -> BrowserResult:
        try:
            import asyncio

            if self._page is None:
                return BrowserResult(
                    success=False,
                    action=BrowserAction.EXTRACT_TEXT,
                    error="No active page. Call navigate() first.",
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
                    success=False,
                    action=BrowserAction.EXTRACT_LINKS,
                    error="No active page. Call navigate() first.",
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
                    success=False,
                    action=BrowserAction.SCREENSHOT,
                    error="No active page. Call navigate() first.",
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
                    success=False,
                    action=BrowserAction.EXECUTE_JS,
                    error="No active page. Call navigate() first.",
                )

            async def _exec():
                return await self._page.evaluate(script)

            result = asyncio.run(_exec())
            return BrowserResult(success=True, action=BrowserAction.EXECUTE_JS, text=str(result))
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.EXECUTE_JS, error=str(e))

    def _do_get_html(self) -> BrowserResult:
        try:
            import asyncio

            if self._page is None:
                return BrowserResult(
                    success=False, action=BrowserAction.GET_HTML, error="No active page. Call navigate() first."
                )

            async def _extract():
                return await self._page.evaluate("document.documentElement.outerHTML")

            html = asyncio.run(_extract())
            return BrowserResult(success=True, action=BrowserAction.GET_HTML, html=html)
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.GET_HTML, error=str(e))

    def _do_wait_for_selector(self, selector: str, timeout: float) -> BrowserResult:
        try:
            import asyncio

            if self._page is None:
                return BrowserResult(
                    success=False, action=BrowserAction.WAIT, error="No active page. Call navigate() first."
                )

            async def _wait():
                await self._page.wait_for_selector(selector, timeout=int(timeout * 1000))

            asyncio.run(_wait())
            return BrowserResult(success=True, action=BrowserAction.WAIT, text=f"Selector '{selector}' visible")
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.WAIT, error=str(e))

    def _do_wait_for_navigation(self, timeout: float) -> BrowserResult:
        try:
            import asyncio

            if self._page is None:
                return BrowserResult(
                    success=False, action=BrowserAction.WAIT, error="No active page. Call navigate() first."
                )

            async def _wait():
                await self._page.wait_for_load_state("load", timeout=int(timeout * 1000))

            asyncio.run(_wait())
            return BrowserResult(success=True, action=BrowserAction.WAIT, text="Navigation completed")
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.WAIT, error=str(e))

    def _do_get_cookies(self) -> list[dict[str, Any]]:
        try:
            import asyncio

            if self._page is None:
                return []

            async def _cookies():
                return await self._page.context.cookies()

            return asyncio.run(_cookies())
        except Exception:
            return []

    def _do_set_cookies(self, cookies: list[dict[str, Any]]) -> BrowserResult:
        try:
            import asyncio

            for cookie in cookies:
                domain = str(cookie.get("domain", "")).removeprefix(".")
                if not domain:
                    return BrowserResult(
                        success=False,
                        action=BrowserAction.EXECUTE_JS,
                        error="Blocked: cookie without domain",
                    )
                if not self._domain_whitelist.is_allowed(domain):
                    return BrowserResult(
                        success=False,
                        action=BrowserAction.EXECUTE_JS,
                        error=f"Blocked: cookie domain not in safe list: {domain}",
                    )

            if self._page is None:
                return BrowserResult(
                    success=False, action=BrowserAction.EXECUTE_JS, error="No active page. Call navigate() first."
                )

            async def _set():
                await self._page.context.add_cookies(cookies)

            asyncio.run(_set())
            return BrowserResult(success=True, action=BrowserAction.EXECUTE_JS, text="Cookies set")
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.EXECUTE_JS, error=str(e))

    def _do_go_back(self) -> BrowserResult:
        try:
            import asyncio

            if self._page is None:
                return BrowserResult(
                    success=False,
                    action=BrowserAction.GO_BACK,
                    error="No active page. Call navigate() first.",
                )

            async def _run():
                await self._page.go_back()

            asyncio.run(_run())
            return BrowserResult(success=True, action=BrowserAction.GO_BACK, text="Navigated back")
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.GO_BACK, error=str(e))

    def _do_go_forward(self) -> BrowserResult:
        try:
            import asyncio

            if self._page is None:
                return BrowserResult(
                    success=False,
                    action=BrowserAction.GO_FORWARD,
                    error="No active page. Call navigate() first.",
                )

            async def _run():
                await self._page.go_forward()

            asyncio.run(_run())
            return BrowserResult(
                success=True, action=BrowserAction.GO_FORWARD, text="Navigated forward"
            )
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.GO_FORWARD, error=str(e))

    def _do_reload_page(self) -> BrowserResult:
        try:
            import asyncio

            if self._page is None:
                return BrowserResult(
                    success=False,
                    action=BrowserAction.RELOAD,
                    error="No active page. Call navigate() first.",
                )

            async def _run():
                await self._page.reload()

            asyncio.run(_run())
            return BrowserResult(success=True, action=BrowserAction.RELOAD, text="Page reloaded")
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.RELOAD, error=str(e))

    def _do_get_element_text(self, selector: str) -> BrowserResult:
        try:
            import asyncio

            if self._page is None:
                return BrowserResult(
                    success=False,
                    action=BrowserAction.GET_ELEMENT_TEXT,
                    error="No active page. Call navigate() first.",
                )

            async def _run():
                return await self._page.locator(selector).inner_text()

            text = asyncio.run(_run())
            return BrowserResult(success=True, action=BrowserAction.GET_ELEMENT_TEXT, text=text)
        except Exception as e:
            return BrowserResult(success=False, action=BrowserAction.GET_ELEMENT_TEXT, error=str(e))
