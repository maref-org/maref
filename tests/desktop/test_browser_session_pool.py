from __future__ import annotations

import builtins
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maref.desktop.browser_session_pool import BrowserSessionPool, PlaywrightNotAvailableError, _reset_credential_manager
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


class TestBrowserSessionPoolSessionRestore:
    """测试浏览器会话状态恢复"""

    @pytest.fixture(autouse=True)
    def _reset_pool(self) -> None:
        BrowserSessionPool._instance = None
        _reset_credential_manager()

    @pytest.fixture
    def pool(self) -> BrowserSessionPool:
        return BrowserSessionPool()

    @pytest.mark.asyncio
    async def test_restore_session_state_with_cookies(
        self, pool: BrowserSessionPool, tmp_path: Path
    ) -> None:
        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_context.add_cookies = AsyncMock()
        mock_page.context = mock_context

        mock_browser = MagicMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch("playwright.async_api.async_playwright") as mock_async_pw, \
             patch("maref.identity.credential_manager.CredentialManager") as MockManager:
            mock_async_pw.return_value.start = AsyncMock(return_value=mock_playwright)

            cookies = [{"name": "sid", "value": "123", "domain": ".test.com"}]

            mock_manager_instance = MockManager.return_value
            mock_manager_instance.load_browser_session.return_value = {
                "cookies": cookies,
                "local_storage": {},
            }

            session = await pool.acquire("restore-s1")
            session.domain = "test.com"

            await pool._restore_session_state("restore-s1", mock_page)

            mock_manager_instance.load_browser_session.assert_called_once_with("test.com")
            mock_context.add_cookies.assert_called_once_with(cookies)

    @pytest.mark.asyncio
    async def test_restore_session_state_with_local_storage(
        self, pool: BrowserSessionPool, tmp_path: Path
    ) -> None:
        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_context.add_cookies = AsyncMock()
        mock_page.context = mock_context
        mock_page.evaluate = AsyncMock()

        mock_browser = MagicMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch("playwright.async_api.async_playwright") as mock_async_pw, \
             patch("maref.identity.credential_manager.CredentialManager") as MockManager:
            mock_async_pw.return_value.start = AsyncMock(return_value=mock_playwright)

            local_storage = {"token": "xyz", "user_id": "123"}

            mock_manager_instance = MockManager.return_value
            mock_manager_instance.load_browser_session.return_value = {
                "cookies": [],
                "local_storage": local_storage,
            }

            session = await pool.acquire("restore-ls1")
            session.domain = "test.com"

            await pool._restore_session_state("restore-ls1", mock_page)

            mock_page.evaluate.assert_called_once()

    @pytest.mark.asyncio
    async def test_restore_session_state_graceful_failure(
        self, pool: BrowserSessionPool, tmp_path: Path
    ) -> None:
        mock_page = MagicMock()
        mock_browser = MagicMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch("playwright.async_api.async_playwright") as mock_async_pw, \
             patch("maref.identity.credential_manager.CredentialManager") as MockManager:
            mock_async_pw.return_value.start = AsyncMock(return_value=mock_playwright)

            mock_manager_instance = MockManager.return_value
            mock_manager_instance.load_browser_session.side_effect = Exception("DB error")

            session = await pool.acquire("restore-fail1")
            session.domain = "test.com"

            await pool._restore_session_state("restore-fail1", mock_page)

            assert session.session_id == "restore-fail1"
            assert session.active_page is not None

    @pytest.mark.asyncio
    async def test_restore_session_state_no_sessions(
        self, pool: BrowserSessionPool, tmp_path: Path
    ) -> None:
        mock_page = MagicMock()
        mock_browser = MagicMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch("playwright.async_api.async_playwright") as mock_async_pw, \
             patch("maref.identity.credential_manager.CredentialManager") as MockManager:
            mock_async_pw.return_value.start = AsyncMock(return_value=mock_playwright)

            mock_manager_instance = MockManager.return_value
            mock_manager_instance.load_browser_session.return_value = None

            session = await pool.acquire("restore-empty1")
            session.domain = "test.com"

            await pool._restore_session_state("restore-empty1", mock_page)

            assert session.session_id == "restore-empty1"

    @pytest.mark.asyncio
    async def test_restore_session_state_cookie_error(
        self, pool: BrowserSessionPool, tmp_path: Path
    ) -> None:
        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_context.add_cookies = AsyncMock(side_effect=Exception("Invalid cookie"))
        mock_page.context = mock_context

        mock_browser = MagicMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch("playwright.async_api.async_playwright") as mock_async_pw, \
             patch("maref.identity.credential_manager.CredentialManager") as MockManager:
            mock_async_pw.return_value.start = AsyncMock(return_value=mock_playwright)

            cookies = [{"name": "bad", "value": "cookie", "domain": ".test.com"}]

            mock_manager_instance = MockManager.return_value
            mock_manager_instance.load_browser_session.return_value = {
                "cookies": cookies,
                "local_storage": {},
            }

            session = await pool.acquire("restore-cookie-err1")
            session.domain = "test.com"

            await pool._restore_session_state("restore-cookie-err1", mock_page)

            assert session.session_id == "restore-cookie-err1"

    def test_browser_session_has_domain_field(self) -> None:
        from maref.desktop.browser_session_pool import BrowserSession
        from maref.desktop.browser_types import BrowserType

        session = BrowserSession(
            session_id="test",
            browser_type=BrowserType.CHROMIUM,
            domain="example.com",
        )
        assert session.domain == "example.com"

    def test_browser_session_default_domain_empty(self) -> None:
        from maref.desktop.browser_session_pool import BrowserSession
        from maref.desktop.browser_types import BrowserType

        session = BrowserSession(
            session_id="test",
            browser_type=BrowserType.CHROMIUM,
        )
        assert session.domain == ""

    @pytest.mark.asyncio
    async def test_restore_skips_when_no_domain(
        self, pool: BrowserSessionPool, tmp_path: Path
    ) -> None:
        mock_page = MagicMock()
        mock_browser = MagicMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch("playwright.async_api.async_playwright") as mock_async_pw, \
             patch("maref.identity.credential_manager.CredentialManager") as MockManager:
            mock_async_pw.return_value.start = AsyncMock(return_value=mock_playwright)

            mock_manager_instance = MockManager.return_value

            session = await pool.acquire("no-domain-s1")
            assert session.domain == ""

            await pool._restore_session_state("no-domain-s1", mock_page)

            mock_manager_instance.load_browser_session.assert_not_called()
