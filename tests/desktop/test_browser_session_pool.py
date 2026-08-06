from __future__ import annotations

import builtins

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maref.desktop.browser_session_pool import BrowserSessionPool, PlaywrightNotAvailableError
from maref.desktop.browser_types import BrowserType

_real_import = builtins.__import__


def _block_playwright(name: str, *args: object, **kwargs: object) -> object:
    if name == "playwright":
        raise ImportError("No module named 'playwright'")
    return _real_import(name, *args, **kwargs)


class TestBrowserSessionPoolNoPlaywright:
    @pytest.fixture(autouse=True)
    def _reset_pool(self) -> None:
        BrowserSessionPool._instance = None

    def test_playwright_not_available(self) -> None:
        with patch("builtins.__import__", side_effect=_block_playwright):
            pool = BrowserSessionPool()
            assert pool.is_available is False

    @pytest.mark.asyncio
    async def test_acquire_raises_without_playwright(self) -> None:
        with patch("builtins.__import__", side_effect=_block_playwright):
            pool = BrowserSessionPool()
            with pytest.raises(PlaywrightNotAvailableError):
                await pool.acquire("test-session")

    def test_get_session_returns_none(self) -> None:
        pool = BrowserSessionPool()
        assert pool.get_session("nonexistent") is None

    def test_get_active_page_returns_none(self) -> None:
        pool = BrowserSessionPool()
        assert pool.get_active_page("nonexistent") is None

    @pytest.mark.asyncio
    async def test_release_nonexistent_is_noop(self) -> None:
        pool = BrowserSessionPool()
        await pool.release("nonexistent")

    @pytest.mark.asyncio
    async def test_close_all_is_safe(self) -> None:
        pool = BrowserSessionPool()
        await pool.close_all()


class TestBrowserSessionPoolMocked:
    @pytest.fixture(autouse=True)
    def _reset_pool(self) -> None:
        BrowserSessionPool._instance = None

    @pytest.fixture
    def pool(self) -> BrowserSessionPool:
        return BrowserSessionPool()

    @pytest.mark.asyncio
    async def test_session_lifecycle(self, pool: BrowserSessionPool) -> None:
        mock_page = MagicMock()
        mock_browser = MagicMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch("playwright.async_api.async_playwright") as mock_async_pw:
            mock_async_pw.return_value.start = AsyncMock(return_value=mock_playwright)

            session = await pool.acquire("s1", BrowserType.CHROMIUM)
            assert session.session_id == "s1"
            assert session.ref_count == 1
            assert not session.is_expired
            assert session.active_page is not None

            reuse = await pool.acquire("s1", BrowserType.CHROMIUM)
            assert reuse.session_id == "s1"
            assert reuse.ref_count == 2

            await pool.release("s1")
            assert pool.get_session("s1").ref_count == 1

    @pytest.mark.asyncio
    async def test_evict_expired_session(self, pool: BrowserSessionPool) -> None:
        mock_page = MagicMock()
        mock_browser = MagicMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch("playwright.async_api.async_playwright") as mock_async_pw:
            mock_async_pw.return_value.start = AsyncMock(return_value=mock_playwright)

            session = await pool.acquire("exp-s1")
            assert pool.get_session("exp-s1") is not None

            await pool.release("exp-s1")
            session.ref_count = 0

    @pytest.mark.asyncio
    async def test_max_sessions_evicts_oldest(self, pool: BrowserSessionPool) -> None:
        pool._sessions.clear()
        mock_page = MagicMock()
        mock_browser = MagicMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch("playwright.async_api.async_playwright") as mock_async_pw, \
             patch("maref.desktop.browser_session_pool._MAX_SESSIONS", 2):
            mock_async_pw.return_value.start = AsyncMock(return_value=mock_playwright)

            s1 = await pool.acquire("s1")
            s1.last_used = 100.0
            s2 = await pool.acquire("s2")
            s2.last_used = 200.0
            s3 = await pool.acquire("s3")
            s3.last_used = 300.0

            assert pool.get_session("s1") is None
            assert pool.get_session("s2") is not None
            assert pool.get_session("s3") is not None

    def test_singleton(self) -> None:
        p1 = BrowserSessionPool()
        p2 = BrowserSessionPool()
        assert p1 is p2
