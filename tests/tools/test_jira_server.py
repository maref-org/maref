from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from maref.tools.jira_server import (
    TOOL_HANDLERS,
    create_jira_server,
    execute_tool,
    get_tool_definition,
)


class TestGetToolDefinition:
    def test_definition_fields(self) -> None:
        t = get_tool_definition()
        assert t.name == "jira"
        assert "jira_get_issue" in t.tools
        assert "jira_search_issues" in t.tools
        assert "jira_create_issue" in t.tools
        assert "EnvVarCheck" in t.security_controls


class TestExecuteTool:
    def _make_mock_client(self, return_data: dict[str, Any]) -> AsyncMock:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.json.return_value = return_data
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.post = AsyncMock(return_value=mock_response)
        return mock_client

    def test_unknown_tool(self) -> None:
        result = execute_tool("nonexistent", {})
        assert result["isError"] is True

    def test_missing_token(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = execute_tool("jira_get_issue", {"issue_key": "PROJ-1"})
            assert result["isError"] is True

    def test_missing_url(self) -> None:
        with patch.dict("os.environ", {"JIRA_TOKEN": "test-token"}, clear=True):
            result = execute_tool("jira_get_issue", {"issue_key": "PROJ-1"})
            assert result["isError"] is True

    def test_get_issue_success(self) -> None:
        mock_client = self._make_mock_client({
            "key": "PROJ-1",
            "fields": {
                "summary": "Test issue",
                "description": "Description",
                "status": {"name": "In Progress"},
                "assignee": {"displayName": "Alice"},
                "reporter": {"displayName": "Bob"},
                "priority": {"name": "High"},
                "issuetype": {"name": "Bug"},
                "created": "2024-01-01T00:00:00Z",
                "updated": "2024-01-02T00:00:00Z",
            },
        })
        with patch.dict("os.environ", {"JIRA_TOKEN": "test-token", "JIRA_URL": "https://jira.example.com"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("jira_get_issue", {"issue_key": "PROJ-1"})
                assert "isError" not in result or not result["isError"]
                assert result["key"] == "PROJ-1"
                assert result["summary"] == "Test issue"
                assert result["status"] == "In Progress"

    def test_get_issue_no_assignee(self) -> None:
        mock_client = self._make_mock_client({
            "key": "PROJ-2",
            "fields": {
                "summary": "Unassigned",
                "status": {"name": "Open"},
                "reporter": {"displayName": "Bob"},
                "priority": {"name": "Medium"},
                "issuetype": {"name": "Task"},
                "created": "2024-01-01T00:00:00Z",
                "updated": "2024-01-02T00:00:00Z",
                "assignee": None,
            },
        })
        with patch.dict("os.environ", {"JIRA_TOKEN": "test-token", "JIRA_URL": "https://jira.example.com"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("jira_get_issue", {"issue_key": "PROJ-2"})
                assert "isError" not in result or not result["isError"]
                assert result["assignee"] is None

    def test_search_issues_success(self) -> None:
        mock_client = self._make_mock_client({
            "total": 2,
            "issues": [
                {"key": "PROJ-1", "fields": {"summary": "Bug 1", "status": {"name": "Open"}, "priority": {"name": "High"}, "assignee": None}},
                {"key": "PROJ-2", "fields": {"summary": "Bug 2", "status": {"name": "In Progress"}, "priority": {"name": "Medium"}, "assignee": {"displayName": "Alice"}}},
            ],
        })
        with patch.dict("os.environ", {"JIRA_TOKEN": "test-token", "JIRA_URL": "https://jira.example.com"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("jira_search_issues", {"jql": "project = PROJ"})
                assert "isError" not in result or not result["isError"]
                assert result["total"] == 2
                assert result["count"] == 2

    def test_create_issue_success(self) -> None:
        mock_client = self._make_mock_client({
            "key": "PROJ-42",
        })
        with patch.dict("os.environ", {"JIRA_TOKEN": "test-token", "JIRA_URL": "https://jira.example.com"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("jira_create_issue", {"project": "PROJ", "summary": "New bug", "description": "Details"})
                assert "isError" not in result or not result["isError"]
                assert result["key"] == "PROJ-42"

    def test_http_error(self) -> None:
        import httpx
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("Not found", request=MagicMock(), response=mock_response)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"JIRA_TOKEN": "test-token", "JIRA_URL": "https://jira.example.com"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("jira_get_issue", {"issue_key": "UNKNOWN-1"})
                assert result["isError"] is True
                assert "Jira API error" in str(result)

    def test_request_error(self) -> None:
        import httpx
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection error", request=MagicMock()))

        with patch.dict("os.environ", {"JIRA_TOKEN": "test-token", "JIRA_URL": "https://jira.example.com"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("jira_get_issue", {"issue_key": "PROJ-1"})
                assert result["isError"] is True
                assert "Jira request failed" in str(result)

    def test_handler_registered(self) -> None:
        assert "jira_get_issue" in TOOL_HANDLERS
        assert "jira_search_issues" in TOOL_HANDLERS
        assert "jira_create_issue" in TOOL_HANDLERS
        assert len(TOOL_HANDLERS) == 3


class TestCreateJiraServer:
    def test_server_info(self) -> None:
        server = create_jira_server()
        transport = server.get_inprocess_transport()
        transport.connect()
        resp = transport.send_initialize()
        assert not resp.is_error
        assert resp.result["serverInfo"]["name"] == "maref-jira-server"

    def test_tools_list(self) -> None:
        server = create_jira_server()
        transport = server.get_inprocess_transport()
        transport.connect()
        resp = transport.send_tools_list()
        assert not resp.is_error
        names = [t["name"] for t in resp.result["tools"]]
        assert "jira_get_issue" in names
        assert "jira_search_issues" in names
        assert "jira_create_issue" in names
        assert len(names) == 3

    def test_unknown_tool(self) -> None:
        server = create_jira_server()
        transport = server.get_inprocess_transport()
        transport.connect()
        resp = transport.send_tool_call("nonexistent", {})
        assert resp.is_error
