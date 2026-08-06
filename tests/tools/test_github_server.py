from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maref.tools.github_server import (
    TOOL_HANDLERS,
    create_github_server,
    execute_tool,
    get_tool_definition,
)


class TestGetToolDefinition:
    def test_definition_fields(self) -> None:
        t = get_tool_definition()
        assert t.name == "github"
        assert "github_list_repos" in t.tools
        assert "github_get_issue" in t.tools
        assert "EnvVarCheck" in t.security_controls


class TestExecuteTool:
    def _make_mock_client(self, return_data: Any) -> AsyncMock:
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
            result = execute_tool("github_list_repos", {"username": "test"})
            assert result["isError"] is True

    def test_list_repos_success(self) -> None:
        mock_client = self._make_mock_client([
            {
                "name": "repo1",
                "full_name": "user/repo1",
                "description": "Test repo",
                "html_url": "https://github.com/user/repo1",
                "stargazers_count": 10,
                "forks_count": 2,
                "language": "Python",
            }
        ])
        with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("github_list_repos", {"username": "user"})
                assert "isError" not in result or not result["isError"]
                assert result["count"] == 1
                assert result["repos"][0]["name"] == "repo1"

    def test_get_issue_success(self) -> None:
        mock_client = self._make_mock_client({
            "number": 1,
            "title": "Test issue",
            "state": "open",
            "body": "Body text",
            "user": {"login": "user"},
            "labels": [{"name": "bug"}],
            "comments": 3,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-02T00:00:00Z",
            "html_url": "https://github.com/owner/repo/issues/1",
        })
        with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("github_get_issue", {"owner": "o", "repo": "r", "issue_number": 1})
                assert "isError" not in result or not result["isError"]
                assert result["number"] == 1
                assert result["title"] == "Test issue"

    def test_create_issue_success(self) -> None:
        mock_client = self._make_mock_client({
            "number": 42,
            "title": "New issue",
            "state": "open",
            "html_url": "https://github.com/o/r/issues/42",
        })
        with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("github_create_issue", {"owner": "o", "repo": "r", "title": "New", "body": "Body"})
                assert "isError" not in result or not result["isError"]
                assert result["number"] == 42

    def test_search_code_success(self) -> None:
        mock_client = self._make_mock_client({
            "total_count": 1,
            "items": [
                {
                    "name": "main.py",
                    "path": "src/main.py",
                    "repository": {"full_name": "user/repo"},
                    "html_url": "https://github.com/user/repo/blob/main/src/main.py",
                }
            ],
        })
        with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("github_search_code", {"query": "def main"})
                assert "isError" not in result or not result["isError"]
                assert result["total_count"] == 1
                assert result["items"][0]["name"] == "main.py"

    def test_http_error(self) -> None:
        import httpx
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("Forbidden", request=MagicMock(), response=mock_response)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("github_list_repos", {"username": "user"})
                assert result["isError"] is True
                assert "GitHub API error" in str(result)

    def test_request_error(self) -> None:
        import httpx
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection failed", request=MagicMock()))

        with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = execute_tool("github_list_repos", {"username": "user"})
                assert result["isError"] is True
                assert "GitHub request failed" in str(result)

    def test_handler_registered(self) -> None:
        assert "github_list_repos" in TOOL_HANDLERS
        assert "github_get_issue" in TOOL_HANDLERS
        assert "github_create_issue" in TOOL_HANDLERS
        assert "github_search_code" in TOOL_HANDLERS
        assert len(TOOL_HANDLERS) == 4


class TestCreateGithubServer:
    def test_server_info(self) -> None:
        server = create_github_server()
        transport = server.get_inprocess_transport()
        transport.connect()
        resp = transport.send_initialize()
        assert not resp.is_error
        assert resp.result["serverInfo"]["name"] == "maref-github-server"

    def test_tools_list(self) -> None:
        server = create_github_server()
        transport = server.get_inprocess_transport()
        transport.connect()
        resp = transport.send_tools_list()
        assert not resp.is_error
        names = [t["name"] for t in resp.result["tools"]]
        assert "github_list_repos" in names
        assert "github_get_issue" in names
        assert "github_create_issue" in names
        assert "github_search_code" in names
        assert len(names) == 4

    def test_unknown_tool(self) -> None:
        server = create_github_server()
        transport = server.get_inprocess_transport()
        transport.connect()
        resp = transport.send_tool_call("nonexistent", {})
        assert resp.is_error
