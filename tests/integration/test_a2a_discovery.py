from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maref.integration.a2a_discovery import A2ADiscovery


@pytest.fixture
def discovery() -> A2ADiscovery:
    return A2ADiscovery(health_check_interval=0.1)


class TestInit:
    def test_default_interval(self) -> None:
        d = A2ADiscovery()
        assert d._health_check_interval == 60.0

    def test_custom_interval(self) -> None:
        d = A2ADiscovery(health_check_interval=10.0)
        assert d._health_check_interval == 10.0

    def test_agents_empty(self, discovery: A2ADiscovery) -> None:
        assert discovery._agents == {}

    def test_bg_task_none(self, discovery: A2ADiscovery) -> None:
        assert discovery._bg_task is None


class TestRegisterAgent:
    def test_register_basic(self, discovery: A2ADiscovery) -> None:
        discovery.register_agent("agent-1", "http://localhost:8001")
        agent = discovery._agents["agent-1"]
        assert agent["agent_id"] == "agent-1"
        assert agent["agent_url"] == "http://localhost:8001"
        assert agent["capabilities"] == []
        assert agent["healthy"] is True

    def test_register_strips_trailing_slash(self, discovery: A2ADiscovery) -> None:
        discovery.register_agent("agent-1", "http://localhost:8001/")
        assert discovery._agents["agent-1"]["agent_url"] == "http://localhost:8001"

    def test_register_with_capabilities(self, discovery: A2ADiscovery) -> None:
        discovery.register_agent("agent-1", "http://localhost:8001", capabilities=["governance", "audit"])
        assert discovery._agents["agent-1"]["capabilities"] == ["governance", "audit"]

    def test_register_sets_timestamps(self, discovery: A2ADiscovery) -> None:
        discovery.register_agent("agent-1", "http://localhost:8001")
        agent = discovery._agents["agent-1"]
        assert agent["registered_at"] > 0
        assert agent["last_heartbeat"] > 0

    def test_register_overwrites_existing(self, discovery: A2ADiscovery) -> None:
        discovery.register_agent("agent-1", "http://localhost:8001")
        discovery.register_agent("agent-1", "http://localhost:8002", capabilities=["new"])
        assert discovery._agents["agent-1"]["agent_url"] == "http://localhost:8002"
        assert discovery._agents["agent-1"]["capabilities"] == ["new"]


class TestUnregisterAgent:
    def test_unregister_existing(self, discovery: A2ADiscovery) -> None:
        discovery.register_agent("agent-1", "http://localhost:8001")
        assert discovery.unregister_agent("agent-1") is True
        assert "agent-1" not in discovery._agents

    def test_unregister_nonexistent(self, discovery: A2ADiscovery) -> None:
        assert discovery.unregister_agent("nonexistent") is False

    def test_unregister_empty_string(self, discovery: A2ADiscovery) -> None:
        assert discovery.unregister_agent("") is False

    def test_unregister_only_removes_one(self, discovery: A2ADiscovery) -> None:
        discovery.register_agent("a1", "http://localhost:8001")
        discovery.register_agent("a2", "http://localhost:8002")
        discovery.unregister_agent("a1")
        assert "a1" not in discovery._agents
        assert "a2" in discovery._agents


class TestDiscoverAgents:
    def test_discover_all_no_filter(self, discovery: A2ADiscovery) -> None:
        discovery.register_agent("a1", "http://localhost:8001")
        discovery.register_agent("a2", "http://localhost:8002")
        result = discovery.discover_agents()
        assert len(result) == 2

    def test_discover_with_filter_matches(self, discovery: A2ADiscovery) -> None:
        discovery.register_agent("a1", "http://localhost:8001", capabilities=["governance"])
        discovery.register_agent("a2", "http://localhost:8002", capabilities=["audit"])
        result = discovery.discover_agents(capability_filter="governance")
        assert len(result) == 1
        assert result[0]["agent_id"] == "a1"

    def test_discover_with_filter_no_match(self, discovery: A2ADiscovery) -> None:
        discovery.register_agent("a1", "http://localhost:8001", capabilities=["governance"])
        result = discovery.discover_agents(capability_filter="nonexistent")
        assert result == []

    def test_discover_empty(self, discovery: A2ADiscovery) -> None:
        assert discovery.discover_agents() == []

    def test_discover_empty_with_filter(self, discovery: A2ADiscovery) -> None:
        assert discovery.discover_agents(capability_filter="anything") == []

    def test_discover_multiple_capabilities_filter(self, discovery: A2ADiscovery) -> None:
        discovery.register_agent("a1", "http://localhost:8001", capabilities=["governance", "audit"])
        discovery.register_agent("a2", "http://localhost:8002", capabilities=["audit"])
        result = discovery.discover_agents(capability_filter="governance")
        assert len(result) == 1
        assert result[0]["agent_id"] == "a1"


class TestHealthCheck:
    @patch("maref.integration.a2a_discovery.httpx.AsyncClient")
    async def test_health_check_success(self, mock_client_cls: MagicMock, discovery: A2ADiscovery) -> None:
        discovery.register_agent("agent-1", "http://localhost:8001")
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.get.return_value = mock_response
        mock_client_cls.return_value = mock_client_instance

        result = await discovery.health_check("agent-1")
        assert result is True
        assert discovery._agents["agent-1"]["healthy"] is True
        assert discovery._agents["agent-1"]["last_heartbeat"] > 0

    @patch("maref.integration.a2a_discovery.httpx.AsyncClient")
    async def test_health_check_failure_status(self, mock_client_cls: MagicMock, discovery: A2ADiscovery) -> None:
        discovery.register_agent("agent-1", "http://localhost:8001")
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.get.return_value = mock_response
        mock_client_cls.return_value = mock_client_instance

        result = await discovery.health_check("agent-1")
        assert result is False
        assert discovery._agents["agent-1"]["healthy"] is False

    @patch("maref.integration.a2a_discovery.httpx.AsyncClient")
    async def test_health_check_marks_unhealthy_on_exception(self, mock_client_cls: MagicMock, discovery: A2ADiscovery) -> None:
        discovery.register_agent("agent-1", "http://localhost:8001")

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.get.side_effect = Exception("Connection error")
        mock_client_cls.return_value = mock_client_instance

        result = await discovery.health_check("agent-1")
        assert result is False
        assert discovery._agents["agent-1"]["healthy"] is False

    @patch("maref.integration.a2a_discovery.httpx.AsyncClient")
    async def test_health_check_uses_correct_url(self, mock_client_cls: MagicMock, discovery: A2ADiscovery) -> None:
        discovery.register_agent("agent-1", "http://localhost:8001")

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.get.return_value = mock_response
        mock_client_cls.return_value = mock_client_instance

        await discovery.health_check("agent-1")
        mock_client_instance.get.assert_called_once_with("http://localhost:8001/api/health")

    async def test_health_check_unknown_agent(self, discovery: A2ADiscovery) -> None:
        result = await discovery.health_check("nonexistent")
        assert result is False

    @patch("maref.integration.a2a_discovery.httpx.AsyncClient")
    async def test_health_check_timeout(self, mock_client_cls: MagicMock, discovery: A2ADiscovery) -> None:
        discovery.register_agent("agent-1", "http://localhost:8001")

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.get.side_effect = asyncio.TimeoutError("Timeout")
        mock_client_cls.return_value = mock_client_instance

        result = await discovery.health_check("agent-1")
        assert result is False
        assert discovery._agents["agent-1"]["healthy"] is False


class TestRefreshAll:
    @patch("maref.integration.a2a_discovery.httpx.AsyncClient")
    async def test_refresh_all_returns_results(self, mock_client_cls: MagicMock, discovery: A2ADiscovery) -> None:
        discovery.register_agent("a1", "http://localhost:8001")
        discovery.register_agent("a2", "http://localhost:8002")

        def side_effect(url: str) -> MagicMock:
            resp = MagicMock()
            resp.status_code = 200 if "8001" in url else 500
            return resp

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.get.side_effect = side_effect
        mock_client_cls.return_value = mock_client_instance

        results = await discovery.refresh_all()
        assert results["a1"] is True
        assert results["a2"] is False

    @patch("maref.integration.a2a_discovery.httpx.AsyncClient")
    async def test_refresh_all_empty(self, mock_client_cls: MagicMock, discovery: A2ADiscovery) -> None:
        results = await discovery.refresh_all()
        assert results == {}

    @patch("maref.integration.a2a_discovery.httpx.AsyncClient")
    async def test_refresh_all_skips_removed_agents(self, mock_client_cls: MagicMock, discovery: A2ADiscovery) -> None:
        discovery.register_agent("a1", "http://localhost:8001")
        discovery.unregister_agent("a1")

        results = await discovery.refresh_all()
        assert results == {}


class TestGetAgent:
    def test_get_existing(self, discovery: A2ADiscovery) -> None:
        discovery.register_agent("agent-1", "http://localhost:8001")
        agent = discovery.get_agent("agent-1")
        assert agent is not None
        assert agent["agent_id"] == "agent-1"

    def test_get_nonexistent(self, discovery: A2ADiscovery) -> None:
        assert discovery.get_agent("nonexistent") is None

    def test_get_empty_string(self, discovery: A2ADiscovery) -> None:
        assert discovery.get_agent("") is None

    def test_get_returns_dict(self, discovery: A2ADiscovery) -> None:
        discovery.register_agent("agent-1", "http://localhost:8001")
        agent = discovery.get_agent("agent-1")
        assert agent is not None
        assert agent["healthy"] is True


class TestListAgents:
    def test_list_empty(self, discovery: A2ADiscovery) -> None:
        assert discovery.list_agents() == []

    def test_list_multiple(self, discovery: A2ADiscovery) -> None:
        discovery.register_agent("a1", "http://localhost:8001")
        discovery.register_agent("a2", "http://localhost:8002")
        agents = discovery.list_agents()
        assert len(agents) == 2
        agent_ids = {a["agent_id"] for a in agents}
        assert agent_ids == {"a1", "a2"}

    def test_list_after_unregister(self, discovery: A2ADiscovery) -> None:
        discovery.register_agent("a1", "http://localhost:8001")
        discovery.register_agent("a2", "http://localhost:8002")
        discovery.unregister_agent("a1")
        assert len(discovery.list_agents()) == 1

    def test_list_returns_copy(self, discovery: A2ADiscovery) -> None:
        discovery.register_agent("a1", "http://localhost:8001")
        agents = discovery.list_agents()
        agents.append({"agent_id": "fake"})
        assert len(discovery.list_agents()) == 1


class TestBackgroundHealthChecks:
    @patch("maref.integration.a2a_discovery.httpx.AsyncClient")
    async def test_start_stop(self, mock_client_cls: MagicMock, discovery: A2ADiscovery) -> None:
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client_instance.get.return_value = mock_response
        mock_client_cls.return_value = mock_client_instance

        discovery.register_agent("a1", "http://localhost:8001")

        await discovery.start_background_health_checks()
        assert discovery._bg_task is not None
        assert not discovery._bg_task.done()

        await discovery.stop_background_health_checks()
        assert discovery._bg_task is None

    @patch("maref.integration.a2a_discovery.httpx.AsyncClient")
    async def test_stop_without_start(self, mock_client_cls: MagicMock, discovery: A2ADiscovery) -> None:
        await discovery.stop_background_health_checks()
        assert discovery._bg_task is None

    @patch("maref.integration.a2a_discovery.httpx.AsyncClient")
    async def test_double_stop(self, mock_client_cls: MagicMock, discovery: A2ADiscovery) -> None:
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client_instance.get.return_value = mock_response
        mock_client_cls.return_value = mock_client_instance

        await discovery.start_background_health_checks()
        await discovery.stop_background_health_checks()
        await discovery.stop_background_health_checks()
        assert discovery._bg_task is None

    @patch("maref.integration.a2a_discovery.httpx.AsyncClient")
    async def test_bg_check_runs_health_check(self, mock_client_cls: MagicMock, discovery: A2ADiscovery) -> None:
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client_instance.get.return_value = mock_response
        mock_client_cls.return_value = mock_client_instance

        discovery.register_agent("a1", "http://localhost:8001")
        discovery._health_check_interval = 0.05

        await discovery.start_background_health_checks()
        await asyncio.sleep(0.12)
        await discovery.stop_background_health_checks()

        assert mock_client_instance.get.call_count >= 1