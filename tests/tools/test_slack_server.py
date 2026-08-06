from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from maref.tools.slack_server import (
    TOOL_HANDLERS,
    create_slack_server,
    execute_tool,
    get_tool_definition,
)


class TestGetToolDefinition:
    def test_definition_fields(self) -> None:
        t = get_tool_definition()
        assert t.name == "slack"
        assert "slack_send_message" in t.tools
        assert "slack_list_channels" in t.tools
        assert "slack_search_messages" in t.tools
        assert "EnvVarCheck" in t.security_controls


class TestExecuteTool:
    def _make_mock_client(self) -> tuple[AsyncMock, MagicMock]:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.get = AsyncMock(return_value=mock_response)
        return mock_client, mock_response

    def test_unknown_tool(self) -> None:
        result = execute_tool("nonexistent", {})
        assert result["isError"] is True

    def test_missing_token(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = execute_tool("slack_send_message", {"channel": "general", "text": "Hi"})
            assert result["isError"] is True

    def test_send_message_success(self) -> None:
        mock_client, mock_resp = self._make_mock_client()
        mock_resp.json.return_value = {
            "ok": True,
            "channel": "C123",
            "ts": "1700000000.000001",
            "message": {"text": "Hi"},
        }
        with patch.dict("os.environ", {"SLACK_TOKEN": "test-token"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("slack_send_message", {"channel": "general", "text": "Hi"})
                assert "isError" not in result or not result["isError"]
                assert result["channel"] == "C123"

    def test_send_message_not_ok(self) -> None:
        mock_client, mock_resp = self._make_mock_client()
        mock_resp.json.return_value = {"ok": False, "error": "not_in_channel"}
        with patch.dict("os.environ", {"SLACK_TOKEN": "test-token"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("slack_send_message", {"channel": "general", "text": "Hi"})
                assert result["isError"] is True
                assert "not_in_channel" in result["content"][0]["text"]

    def test_list_channels_success(self) -> None:
        mock_client, mock_resp = self._make_mock_client()
        mock_resp.json.return_value = {
            "ok": True,
            "channels": [
                {"id": "C1", "name": "general", "is_channel": True, "is_private": False, "num_members": 10, "topic": {"value": "General chat"}},
            ],
        }
        with patch.dict("os.environ", {"SLACK_TOKEN": "test-token"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("slack_list_channels", {})
                assert "isError" not in result or not result["isError"]
                assert result["count"] == 1

    def test_list_channels_not_ok(self) -> None:
        mock_client, mock_resp = self._make_mock_client()
        mock_resp.json.return_value = {"ok": False, "error": "invalid_auth"}
        with patch.dict("os.environ", {"SLACK_TOKEN": "test-token"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("slack_list_channels", {})
                assert result["isError"] is True

    def test_search_messages_success(self) -> None:
        mock_client, mock_resp = self._make_mock_client()
        mock_resp.json.return_value = {
            "ok": True,
            "messages": {
                "matches": [
                    {"channel": {"name": "general"}, "username": "alice", "text": "Hello!", "ts": "123", "permalink": "https://slack.com/archives/123"},
                ]
            },
        }
        with patch.dict("os.environ", {"SLACK_TOKEN": "test-token"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("slack_search_messages", {"query": "hello"})
                assert "isError" not in result or not result["isError"]
                assert result["count"] == 1
                assert result["messages"][0]["text"] == "Hello!"

    def test_search_messages_not_ok(self) -> None:
        mock_client, mock_resp = self._make_mock_client()
        mock_resp.json.return_value = {"ok": False, "error": "no_results"}
        with patch.dict("os.environ", {"SLACK_TOKEN": "test-token"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("slack_search_messages", {"query": "hello"})
                assert result["isError"] is True

    def test_http_error(self) -> None:
        import httpx
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("Rate limited", request=MagicMock(), response=mock_response)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"SLACK_TOKEN": "test-token"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("slack_send_message", {"channel": "general", "text": "Hi"})
                assert result["isError"] is True
                assert "Slack API error" in str(result)

    def test_request_error(self) -> None:
        import httpx
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(side_effect=httpx.RequestError("Timeout", request=MagicMock()))

        with patch.dict("os.environ", {"SLACK_TOKEN": "test-token"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("slack_send_message", {"channel": "general", "text": "Hi"})
                assert result["isError"] is True

    def test_handler_registered(self) -> None:
        assert "slack_send_message" in TOOL_HANDLERS
        assert "slack_list_channels" in TOOL_HANDLERS
        assert "slack_search_messages" in TOOL_HANDLERS
        assert len(TOOL_HANDLERS) == 3


class TestCreateSlackServer:
    def test_server_info(self) -> None:
        server = create_slack_server()
        transport = server.get_inprocess_transport()
        transport.connect()
        resp = transport.send_initialize()
        assert not resp.is_error
        assert resp.result["serverInfo"]["name"] == "maref-slack-server"

    def test_tools_list(self) -> None:
        server = create_slack_server()
        transport = server.get_inprocess_transport()
        transport.connect()
        resp = transport.send_tools_list()
        assert not resp.is_error
        names = [t["name"] for t in resp.result["tools"]]
        assert "slack_send_message" in names
        assert "slack_list_channels" in names
        assert "slack_search_messages" in names
        assert len(names) == 3

    def test_unknown_tool(self) -> None:
        server = create_slack_server()
        transport = server.get_inprocess_transport()
        transport.connect()
        resp = transport.send_tool_call("nonexistent", {})
        assert resp.is_error
