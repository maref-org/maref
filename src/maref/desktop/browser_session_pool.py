from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from maref.desktop.browser_types import BrowserType

logger = logging.getLogger(__name__)

_SESSION_TIMEOUT = int(os.environ.get("MAREF_BROWSER_SESSION_TIMEOUT", "300"))
_MAX_SESSIONS = int(os.environ.get("MAREF_BROWSER_MAX_SESSIONS", "4"))


class PlaywrightNotAvailableError(RuntimeError):
    pass


@dataclass
class BrowserSession:
    session_id: str
    browser_type: BrowserType
    domain: str = ""
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    ref_count: int = 0
    _playwright: Any = None
    _browser: Any = None
    _pages: list[Any] = field(default_factory=list)
    _closed: bool = False

    @property
    def is_expired(self) -> bool:
        return time.time() - self.last_used > _SESSION_TIMEOUT

    @property
    def active_page(self) -> Any | None:
        if self._pages:
            return self._pages[-1]
        return None

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for page in self._pages:
            try:
                await page.close()
            except Exception as exc:
                logger.debug("page close: %s", exc)
        self._pages.clear()
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception as exc:
                logger.debug("browser close: %s", exc)
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as exc:
                logger.debug("playwright stop: %s", exc)
            self._playwright = None


class BrowserSessionPool:
    _instance: BrowserSessionPool | None = None
    _lock: asyncio.Lock
    _sessions: dict[str, BrowserSession]
    _playwright_available: bool
    _cleanup_task: asyncio.Task[Any] | None

    def __new__(cls) -> BrowserSessionPool:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._sessions = {}
            cls._instance._playwright_available = False
            cls._instance._cleanup_task = None
            cls._lock = asyncio.Lock()
            try:
                import playwright  # noqa: F401

                cls._instance._playwright_available = True
            except ImportError:
                pass
        return cls._instance

    @property
    def is_available(self) -> bool:
        return self._playwright_available

    async def acquire(
        self, session_id: str, browser_type: BrowserType = BrowserType.CHROMIUM
    ) -> BrowserSession:
        if not self._playwright_available:
            raise PlaywrightNotAvailableError("playwright not installed")

        async with self._lock:
            if session_id in self._sessions:
                session = self._sessions[session_id]
                if not session.is_expired:
                    session.last_used = time.time()
                    session.ref_count += 1
                    return session
                await self._evict(session_id)

            if len(self._sessions) >= _MAX_SESSIONS:
                oldest = min(self._sessions.values(), key=lambda s: s.last_used)
                await self._evict(oldest.session_id)

            from playwright.async_api import async_playwright

            p = await async_playwright().start()
            browser = await getattr(p, browser_type.value).launch()
            page = await browser.new_page()

            session = BrowserSession(
                session_id=session_id,
                browser_type=browser_type,
                _playwright=p,
                _browser=browser,
                _pages=[page],
                ref_count=1,
            )
            self._sessions[session_id] = session
            self._start_cleanup()

            if page:
                await self._restore_session_state(session_id, page)

            return session

    async def release(self, session_id: str) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            session.ref_count = max(0, session.ref_count - 1)
            if session.ref_count == 0:
                await self._evict(session_id)

    async def new_page(self, session_id: str) -> Any | None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session._browser is None:
                return None
            page = await session._browser.new_page()
            session._pages.append(page)
            session.last_used = time.time()
            return page

    def get_session(self, session_id: str) -> BrowserSession | None:
        return self._sessions.get(session_id)

    def get_all_sessions(self) -> dict[str, BrowserSession]:
        """Return all sessions dict (for monitoring/probes)."""
        return dict(self._sessions)

    def get_active_page(self, session_id: str) -> Any | None:
        session = self._sessions.get(session_id)
        if session is None or session._closed:
            return None
        return session.active_page

    async def _evict(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session is not None:
            await session.close()

    async def _restore_session_state(self, session_id: str, page: Any) -> None:
        """从 CredentialManager 恢复浏览器会话状态"""
        try:
            from maref.identity.credential_manager import CredentialManager

            manager = CredentialManager()
            sessions = manager.list_browser_sessions()

            for session_record in sessions:
                domain = session_record.domain
                if not domain:
                    continue

                session_data = manager.load_browser_session(domain)
                if not session_data:
                    continue

                cookies = session_data.get("cookies", [])
                if cookies:
                    try:
                        await page.context.add_cookies(cookies)
                        logger.debug(
                            "Restored %d cookies for domain %s",
                            len(cookies),
                            domain,
                        )
                    except Exception as e:
                        logger.debug("Failed to restore cookies for %s: %s", domain, e)

                local_storage = session_data.get("local_storage", {})
                if local_storage:
                    try:
                        await page.evaluate(
                            """(storage) => {
                                for (const [key, value] of Object.entries(storage)) {
                                    localStorage.setItem(key, value);
                                }
                            }""",
                            local_storage,
                        )
                        logger.debug(
                            "Restored %d localStorage items for domain %s",
                            len(local_storage),
                            domain,
                        )
                    except Exception as e:
                        logger.debug(
                            "Failed to restore localStorage for %s: %s",
                            domain,
                            e,
                        )

        except Exception as e:
            logger.debug("Failed to restore session state: %s", e)

    def _start_cleanup(self) -> None:
        if self._cleanup_task is not None and not self._cleanup_task.done():
            return

        async def _loop() -> None:
            while True:
                await asyncio.sleep(30)
                async with self._lock:
                    expired = [
                        sid
                        for sid, s in self._sessions.items()
                        if s.is_expired and s.ref_count == 0
                    ]
                    for sid in expired:
                        logger.debug("cleaning up expired session %s", sid)
                        await self._evict(sid)

        self._cleanup_task = asyncio.ensure_future(_loop())

    async def close_all(self) -> None:
        async with self._lock:
            sids = list(self._sessions.keys())
            for sid in sids:
                await self._evict(sid)
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            self._cleanup_task = None
