from __future__ import annotations

from unittest.mock import MagicMock, patch

from maref.tools.web_search_server import (
    DomainBlacklist,
    QuerySanitizer,
    ResultLimit,
    _execute_search,
    create_web_search_server,
)


class TestQuerySanitizer:
    def test_basic_sanitize(self) -> None:
        sanitizer = QuerySanitizer()
        result = sanitizer.sanitize("  hello world  ")
        assert result == "hello world"

    def test_removes_special_chars(self) -> None:
        sanitizer = QuerySanitizer()
        result = sanitizer.sanitize("hello<script>world")
        assert result == "helloscriptworld"

    def test_truncates_long_query(self) -> None:
        sanitizer = QuerySanitizer(max_length=10)
        result = sanitizer.sanitize("this is a very long search query")
        assert len(result) <= 10

    def test_empty_query(self) -> None:
        sanitizer = QuerySanitizer()
        result = sanitizer.sanitize("   ")
        assert result == ""


class TestResultLimit:
    def test_applies_limit(self) -> None:
        limiter = ResultLimit(max_results=3)
        results = [
            {"title": f"Result {i}", "url": f"http://example.com/{i}", "snippet": ""}
            for i in range(10)
        ]
        limited = limiter.apply(results)
        assert len(limited) == 3

    def test_no_limit_when_fewer_results(self) -> None:
        limiter = ResultLimit(max_results=10)
        results = [{"title": "Only", "url": "http://example.com", "snippet": ""}]
        limited = limiter.apply(results)
        assert len(limited) == 1


class TestDomainBlacklist:
    def test_blocks_exact_domain(self) -> None:
        blacklist = DomainBlacklist({"blocked.com"})
        assert blacklist.is_blocked("https://blocked.com/page") is True
        assert blacklist.is_blocked("https://allowed.com/page") is False

    def test_blocks_subdomain(self) -> None:
        blacklist = DomainBlacklist({"blocked.com"})
        assert blacklist.is_blocked("https://sub.blocked.com/page") is True

    def test_filter_removes_blocked(self) -> None:
        blacklist = DomainBlacklist({"blocked.com"})
        results = [
            {"title": "A", "url": "https://allowed.com/a", "snippet": ""},
            {"title": "B", "url": "https://blocked.com/b", "snippet": ""},
            {"title": "C", "url": "https://allowed.com/c", "snippet": ""},
        ]
        filtered = blacklist.filter(results)
        assert len(filtered) == 2
        assert all("blocked.com" not in r["url"] for r in filtered)


class TestWebSearchServer:
    def test_server_creation(self) -> None:
        server = create_web_search_server()
        assert server.name == "web-search-server"
        assert server.version == "0.1.0"

    def test_web_search_tool_registered(self) -> None:
        server = create_web_search_server()
        assert "web_search" in server._tools
        assert "web_search_news" in server._tools

    @patch("maref.tools.web_search_server.httpx.get")
    def test_web_search_e2e(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.text = """
        <html>
        <body>
        <table>
        <tr class="result-snippet">
        <td><a rel="nofollow" href="https://example.com" class="result-link">Example Site</a></td>
        <td class="result-snippet">This is an example website</td>
        </tr>
        </table>
        </body>
        </html>
        """
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        results = _execute_search("test query", max_results=5)
        assert isinstance(results, list)

    @patch("maref.tools.web_search_server.httpx.get")
    def test_web_search_news_e2e(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.text = """
        <html>
        <body>
        <table>
        <tr class="result-snippet">
        <td><a rel="nofollow" href="https://news.example.com" class="result-link">News Article</a></td>
        <td class="result-snippet">Breaking news content</td>
        </tr>
        </table>
        </body>
        </html>
        """
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        results = _execute_search("news query", max_results=5, search_type="news")
        assert isinstance(results, list)

    @patch("maref.tools.web_search_server.httpx.get")
    def test_web_search_empty_query(self, mock_get: MagicMock) -> None:
        results = _execute_search("   ", max_results=5)
        assert results == []
        mock_get.assert_not_called()


class TestWebResearchE2E:
    @patch("maref.tools.web_search_server.httpx.get")
    def test_full_research_flow(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.text = """
        <html>
        <body>
        <table>
        <tr class="result-snippet">
        <td><a rel="nofollow" href="https://python.org" class="result-link">Python</a></td>
        <td class="result-snippet">Python programming language</td>
        </tr>
        <tr class="result-snippet">
        <td><a rel="nofollow" href="https://docs.python.org" class="result-link">Python Docs</a></td>
        <td class="result-snippet">Official documentation</td>
        </tr>
        </table>
        </body>
        </html>
        """
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        server = create_web_search_server(max_results=5)

        search_result = server._tools["web_search"].handler(
            {"query": "Python programming", "max_results": 3}
        )
        assert "query" in search_result
        assert "results" in search_result
        assert "count" in search_result
        assert search_result["search_type"] == "web"

        blacklist = DomainBlacklist()
        filtered = blacklist.filter(search_result["results"])
        assert len(filtered) == len(search_result["results"])
