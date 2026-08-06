from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from maref.integration.a2a_client import AGENT_ID, A2AClient


@pytest.fixture
def client() -> A2AClient:
    return A2AClient(timeout=5.0)


class TestInit:
    def test_default_timeout(self) -> None:
        c = A2AClient()
        assert c._timeout == 30.0

    def test_custom_timeout(self) -> None:
        c = A2AClient(timeout=10.0)
        assert c._timeout == 10.0

    def test_active_tasks_empty(self, client: A2AClient) -> None:
        assert client._active_tasks == {}


class TestHeaders:
    def test_headers_content_type(self, client: A2AClient) -> None:
        headers = client._headers()
        assert headers["Content-Type"] == "application/json"
        assert headers["X-A2A-Agent-Id"] == AGENT_ID


class TestSendTask:
    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_send_task_success(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "result": {
                "id": "maref-task-abc123",
                "status": {"state": "submitted"},
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response
        mock_async_client.return_value = mock_client_instance

        result = await client.send_task(
            agent_url="http://localhost:8000",
            skill_id="maref-governance",
            input_data="Test task",
            metadata={"priority": "high"},
        )
        assert result is not None
        assert result["result"]["id"] == "maref-task-abc123"
        assert "maref-task-abc123" in client._active_tasks

    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_send_task_active_tracking(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {"id": "task-456", "status": {"state": "submitted"}},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response
        mock_async_client.return_value = mock_client_instance

        await client.send_task("http://host:8000", "skill", "data")
        assert "task-456" in client._active_tasks
        assert client._active_tasks["task-456"]["agent_url"] == "http://host:8000"

    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_send_task_error_returns_none(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.side_effect = Exception("Connection failed")
        mock_async_client.return_value = mock_client_instance

        result = await client.send_task("http://bad:9999", "skill", "data")
        assert result is None

    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_send_task_strips_trailing_slash(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"id": "t1"}}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response
        mock_async_client.return_value = mock_client_instance

        await client.send_task("http://host:8000/", "skill", "data")
        called_url = mock_client_instance.post.call_args[0][0]
        assert called_url == "http://host:8000/api/a2a/task/send"

    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_send_task_without_metadata(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"id": "t1", "status": {}}}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response
        mock_async_client.return_value = mock_client_instance

        result = await client.send_task("http://host:8000", "skill", "data")
        assert result is not None


class TestGetTask:
    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_get_task_success(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "task-1",
            "status": {"state": "working"},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.get.return_value = mock_response
        mock_async_client.return_value = mock_client_instance

        result = await client.get_task("http://host:8000", "task-1")
        assert result is not None
        assert result["id"] == "task-1"
        assert result["status"]["state"] == "working"

    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_get_task_error_returns_none(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.get.side_effect = Exception("Error")
        mock_async_client.return_value = mock_client_instance

        result = await client.get_task("http://bad:9999", "task-1")
        assert result is None

    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_get_task_strips_trailing_slash(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "t1"}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.get.return_value = mock_response
        mock_async_client.return_value = mock_client_instance

        await client.get_task("http://host:8000/", "task-1")
        called_url = mock_client_instance.get.call_args[0][0]
        assert "//api/a2a/task/task-1" not in called_url
        assert called_url == "http://host:8000/api/a2a/task/task-1"


class TestCancelTask:
    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_cancel_success(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        client._active_tasks["task-1"] = {"agent_url": "http://host:8000", "created_at": 0.0, "status": {}}
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response
        mock_async_client.return_value = mock_client_instance

        assert await client.cancel_task("http://host:8000", "task-1") is True
        assert "task-1" not in client._active_tasks

    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_cancel_with_reason(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response
        mock_async_client.return_value = mock_client_instance

        await client.cancel_task("http://host:8000", "task-1", reason="No longer needed")
        call_kwargs = mock_client_instance.post.call_args[1]
        assert call_kwargs["json"]["reason"] == "No longer needed"

    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_cancel_success_not_in_active(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response
        mock_async_client.return_value = mock_client_instance

        assert await client.cancel_task("http://host:8000", "unknown-task") is True

    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_cancel_server_returns_false(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": False}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response
        mock_async_client.return_value = mock_client_instance

        assert await client.cancel_task("http://host:8000", "task-1") is False

    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_cancel_error_returns_false(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.side_effect = Exception("Error")
        mock_async_client.return_value = mock_client_instance

        assert await client.cancel_task("http://bad:9999", "task-1") is False


class TestPushState:
    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_push_state_success(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response
        mock_async_client.return_value = mock_client_instance

        assert await client.push_state("http://host:8000", "task-1", "working") is True

    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_push_state_server_returns_false(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": False}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response
        mock_async_client.return_value = mock_client_instance

        assert await client.push_state("http://host:8000", "task-1", "completed") is False

    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_push_state_error_returns_false(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.side_effect = Exception("Error")
        mock_async_client.return_value = mock_client_instance

        assert await client.push_state("http://bad:9999", "task-1", "working") is False

    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_push_state_strips_trailing_slash(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response
        mock_async_client.return_value = mock_client_instance

        await client.push_state("http://host:8000/", "task-1", "working")
        called_url = mock_client_instance.post.call_args[0][0]
        assert called_url == "http://host:8000/api/a2a/task/state"


class TestDiscoverAgentCard:
    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_discover_success(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "agentCard": {"name": "agent-b", "version": "1.0"},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.get.return_value = mock_response
        mock_async_client.return_value = mock_client_instance

        result = await client.discover_agent_card("http://host:8000")
        assert result is not None
        assert result["agentCard"]["name"] == "agent-b"

    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_discover_error_returns_none(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.get.side_effect = Exception("Error")
        mock_async_client.return_value = mock_client_instance

        result = await client.discover_agent_card("http://bad:9999")
        assert result is None

    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_discover_well_known_url(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"agentCard": {}}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.get.return_value = mock_response
        mock_async_client.return_value = mock_client_instance

        await client.discover_agent_card("http://host:8000")
        called_url = mock_client_instance.get.call_args[0][0]
        assert called_url == "http://host:8000/.well-known/agent-card.json"


class TestActiveTasks:
    def test_get_active_returns_copy(self, client: A2AClient) -> None:
        client._active_tasks["t1"] = {"data": "value"}
        tasks = client.get_active_tasks()
        tasks["new"] = "added"
        assert "new" not in client._active_tasks

    def test_clear_active(self, client: A2AClient) -> None:
        client._active_tasks["t1"] = {"data": "v1"}
        client._active_tasks["t2"] = {"data": "v2"}
        client.clear_active_tasks()
        assert client._active_tasks == {}
        assert client.get_active_tasks() == {}

    def test_empty_active_tasks(self, client: A2AClient) -> None:
        assert client.get_active_tasks() == {}


class TestSubscribe:
    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_subscribe_receives_events(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        call_results: list[str] = []

        async def mock_callback(data: str) -> None:
            call_results.append(data)

        async def mock_aiter_lines() -> Any:
            yield "data: connected"
            yield "data: working"
            yield "data: completed"
            yield "data: [DONE]"

        mock_response = MagicMock()
        mock_response.aiter_lines = mock_aiter_lines

        # Create proper async context manager for stream()
        class StreamContextManager:
            def __init__(self, response):
                self._response = response
            
            async def __aenter__(self):
                return self._response
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None
        
        stream_cm = StreamContextManager(mock_response)

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None
        # stream() must return the context manager directly, not a coroutine
        mock_client_instance.stream = lambda *args, **kwargs: stream_cm
        mock_async_client.return_value = mock_client_instance

        await client.subscribe("http://host:8000", "task-1", mock_callback)
        # Filter: "connected" and "[DONE]" are skipped, "working" and "completed" are kept
        assert call_results == ["working", "completed"]

    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_subscribe_ignores_connected_and_done(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        call_results: list[str] = []

        async def mock_callback(data: str) -> None:
            call_results.append(data)

        async def mock_aiter_lines() -> Any:
            yield "data: connected"
            yield "data: [DONE]"

        mock_response = MagicMock()
        mock_response.aiter_lines = mock_aiter_lines

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.stream.return_value.__aenter__.return_value = mock_response
        mock_async_client.return_value = mock_client_instance

        await client.subscribe("http://host:8000", "task-1", mock_callback)
        assert call_results == []

    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_subscribe_exception_silent(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.stream.side_effect = Exception("Error")
        mock_async_client.return_value = mock_client_instance

        await client.subscribe("http://bad:9999", "task-1", lambda x: None)


class TestIntegrationErrorHandling:
    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_send_task_http_error_returns_none(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        # Mock response that raises HTTPError when raise_for_status() is called
        mock_response = AsyncMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPError("HTTP error")
        
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response
        mock_async_client.return_value = mock_client_instance

        result = await client.send_task("http://host:8000", "skill", "data")
        assert result is None

    @patch("maref.integration.a2a_client.httpx.AsyncClient")
    async def test_get_task_http_error_returns_none(self, mock_async_client: MagicMock, client: A2AClient) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 404")

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.get.return_value = mock_response
        mock_async_client.return_value = mock_client_instance

        result = await client.get_task("http://host:8000", "task-1")
        assert result is None


@pytest.mark.parametrize("url,expected", [
    ("http://host:8000", "http://host:8000/api/a2a/task/send"),
    ("http://host:8000/", "http://host:8000/api/a2a/task/send"),
    ("http://host:8000/path/", "http://host:8000/path/api/a2a/task/send"),
])
@patch("maref.integration.a2a_client.httpx.AsyncClient")
async def test_url_strip_variants(mock_async_client: MagicMock, url: str, expected: str) -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {"result": {"id": "t1", "status": {}}}
    mock_response.raise_for_status = MagicMock()

    mock_client_instance = AsyncMock()
    mock_client_instance.__aenter__.return_value = mock_client_instance
    mock_client_instance.post.return_value = mock_response
    mock_async_client.return_value = mock_client_instance

    client = A2AClient()
    await client.send_task(url, "skill", "data")
    called_url = mock_client_instance.post.call_args[0][0]
    assert called_url == expected
