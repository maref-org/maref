from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from maref.desktop.browser_session_pool import BrowserSession, BrowserSessionPool
from maref.observation.probes import BaseProbe


@pytest.fixture(autouse=True)
def _reset_pool() -> None:
    BrowserSessionPool._instance = None
    yield
    BrowserSessionPool._instance = None


class TestDesktopProbe:
    def test_name_and_description(self) -> None:
        from maref.observation.probes.desktop_probe import DesktopProbe

        probe = DesktopProbe()
        assert probe.name == "desktop"
        assert len(probe.description) > 0

    def test_probe_inherits_base_probe(self) -> None:
        from maref.observation.probes.desktop_probe import DesktopProbe

        probe = DesktopProbe()
        assert isinstance(probe, BaseProbe)

    @patch.object(BrowserSessionPool, "is_available", new_callable=PropertyMock)
    def test_measure_when_pool_unavailable(
        self, mock_is_available: PropertyMock
    ) -> None:
        from maref.observation.probes.desktop_probe import DesktopProbe

        mock_is_available.return_value = False
        probe = DesktopProbe()
        reading = probe.measure()
        assert reading.probe_name == "desktop"
        assert reading.value == 0.0
        assert reading.context["pool_available"] is False
        assert reading.context["error"] == "playwright_not_available"

    @patch.object(BrowserSessionPool, "get_all_sessions", return_value={}, create=True)
    @patch.object(BrowserSessionPool, "is_available", new_callable=PropertyMock)
    def test_measure_when_pool_idle(
        self,
        mock_is_available: PropertyMock,
        mock_get_all_sessions: MagicMock,
    ) -> None:
        from maref.observation.probes.desktop_probe import DesktopProbe

        mock_is_available.return_value = True
        probe = DesktopProbe()
        reading = probe.measure()
        assert reading.value == 0.5
        assert reading.context["pool_available"] is True
        assert reading.context["active_sessions"] == 0
        assert reading.context["session_pool_size"] == 0

    @patch.object(BrowserSessionPool, "get_all_sessions", create=True)
    @patch.object(BrowserSessionPool, "is_available", new_callable=PropertyMock)
    def test_measure_when_pool_active(
        self,
        mock_is_available: PropertyMock,
        mock_get_all_sessions: MagicMock,
    ) -> None:
        from maref.observation.probes.desktop_probe import DesktopProbe

        mock_is_available.return_value = True
        active = MagicMock(spec=BrowserSession)
        type(active).is_expired = PropertyMock(return_value=False)
        active.ref_count = 1
        mock_get_all_sessions.return_value = {"s1": active}

        probe = DesktopProbe()
        reading = probe.measure()
        assert reading.value == 1.0
        assert reading.context["active_sessions"] == 1
        assert reading.context["session_pool_size"] == 1

    @patch.object(BrowserSessionPool, "get_all_sessions", create=True)
    @patch.object(BrowserSessionPool, "is_available", new_callable=PropertyMock)
    def test_measure_counts_expired_sessions(
        self,
        mock_is_available: PropertyMock,
        mock_get_all_sessions: MagicMock,
    ) -> None:
        from maref.observation.probes.desktop_probe import DesktopProbe

        mock_is_available.return_value = True
        expired = MagicMock(spec=BrowserSession)
        type(expired).is_expired = PropertyMock(return_value=True)
        expired.ref_count = 0

        active = MagicMock(spec=BrowserSession)
        type(active).is_expired = PropertyMock(return_value=False)
        active.ref_count = 1

        mock_get_all_sessions.return_value = {"expired": expired, "active": active}

        probe = DesktopProbe()
        reading = probe.measure()
        assert reading.value == 1.0
        assert reading.context["active_sessions"] == 1
        assert reading.context["session_pool_size"] == 2
        assert reading.context["expired_sessions"] == 1
