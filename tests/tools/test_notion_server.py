from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from maref.tools.notion_server import (
    TOOL_HANDLERS,
    create_notion_server,
    execute_tool,
    get_tool_definition,
)


class TestGetToolDefinition:
    def test_definition_fields(self) -> None:
        t = get_tool_definition()
        assert t.name == "notion"
        assert "notion_query_database" in t.tools
        assert "notion_create_page" in t.tools
        assert "notion_search" in t.tools
        assert "EnvVarCheck" in t.security_controls


class TestExecuteTool:
    def test_unknown_tool(self) -> None:
        result = execute_tool("nonexistent", {})
        assert result["isError"] is True

    def test_missing_token(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = execute_tool("notion_query_database", {"database_id": "123"})
            assert result["isError"] is True

    def _make_mock_client(self, return_data: dict[str, Any]) -> AsyncMock:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.json.return_value = return_data
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        return mock_client

    def test_query_database_success(self) -> None:
        mock_client = self._make_mock_client({
            "results": [
                {
                    "id": "page-1",
                    "url": "https://notion.so/page-1",
                    "created_time": "2024-01-01T00:00:00Z",
                    "last_edited_time": "2024-01-02T00:00:00Z",
                    "properties": {
                        "Name": {"type": "title", "title": {"plain_text": "Test Page"}},
                        "Description": {"type": "rich_text", "rich_text": [{"plain_text": "A description"}]},
                        "Status": {"type": "select", "select": {"name": "Done"}},
                    },
                }
            ],
            "has_more": False,
        })

        with patch.dict("os.environ", {"NOTION_TOKEN": "test-token"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("notion_query_database", {"database_id": "db-1"})
                assert "isError" not in result or not result["isError"]
                assert result["count"] == 1
                assert result["has_more"] is False

    def test_create_page_success(self) -> None:
        mock_client = self._make_mock_client({
            "id": "new-page-1",
            "url": "https://notion.so/new-page-1",
            "created_time": "2024-01-01T00:00:00Z",
        })

        with patch.dict("os.environ", {"NOTION_TOKEN": "test-token"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("notion_create_page", {"database_id": "db-1", "title": "New", "content": "Body"})
                assert "isError" not in result or not result["isError"]
                assert result["id"] == "new-page-1"

    def test_search_success(self) -> None:
        mock_client = self._make_mock_client({
            "results": [
                {"id": "page-1", "object": "page", "url": "https://notion.so/page-1"}
            ]
        })

        with patch.dict("os.environ", {"NOTION_TOKEN": "test-token"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("notion_search", {"query": "test"})
                assert "isError" not in result or not result["isError"]
                assert result["count"] == 1

    def test_http_error(self) -> None:
        import httpx
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"NOTION_TOKEN": "test-token"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("notion_query_database", {"database_id": "db-1"})
                assert result["isError"] is True
                assert "Notion API error" in str(result)

    def test_request_error(self) -> None:
        import httpx
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(side_effect=httpx.RequestError("Timeout", request=MagicMock()))

        with patch.dict("os.environ", {"NOTION_TOKEN": "test-token"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("notion_query_database", {"database_id": "db-1"})
                assert result["isError"] is True
                assert "Notion request failed" in str(result)

    def test_handler_registered(self) -> None:
        assert "notion_query_database" in TOOL_HANDLERS
        assert "notion_create_page" in TOOL_HANDLERS
        assert "notion_search" in TOOL_HANDLERS
        assert len(TOOL_HANDLERS) == 3


class TestCreateNotionServer:
    def test_server_info(self) -> None:
        server = create_notion_server()
        transport = server.get_inprocess_transport()
        transport.connect()
        resp = transport.send_initialize()
        assert not resp.is_error
        assert resp.result["serverInfo"]["name"] == "maref-notion-server"

    def test_tools_list(self) -> None:
        server = create_notion_server()
        transport = server.get_inprocess_transport()
        transport.connect()
        resp = transport.send_tools_list()
        assert not resp.is_error
        names = [t["name"] for t in resp.result["tools"]]
        assert "notion_query_database" in names
        assert "notion_create_page" in names
        assert "notion_search" in names
        assert len(names) == 3

    def test_unknown_tool(self) -> None:
        server = create_notion_server()
        transport = server.get_inprocess_transport()
        transport.connect()
        resp = transport.send_tool_call("nonexistent", {})
        assert resp.is_error
