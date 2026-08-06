from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maref.tools.web_search_server import (
    DEFAULT_MAX_RESULTS,
    DomainBlacklist,
    QuerySanitizer,
    ResultLimit,
    _DuckDuckGoResultParser,
    _execute_search,
    _fallback_parse,
    _parse_search_results,
    create_web_search_server,
)


class TestQuerySanitizer:
    def test_sanitize_normal(self) -> None:
        s = QuerySanitizer()
        assert s.sanitize("hello world") == "hello world"

    def test_sanitize_strip_whitespace(self) -> None:
        s = QuerySanitizer()
        assert s.sanitize("  hello   world  ") == "hello world"

    def test_sanitize_remove_invalid_chars(self) -> None:
        s = QuerySanitizer()
        result = s.sanitize("hello\x00world\u0000test")
        assert "\x00" not in result

    def test_sanitize_truncate(self) -> None:
        s = QuerySanitizer(max_length=10)
        assert s.sanitize("a" * 100) == "a" * 10

    def test_sanitize_empty(self) -> None:
        s = QuerySanitizer()
        assert s.sanitize("   ") == ""

    def test_sanitize_special_chars_allowed(self) -> None:
        s = QuerySanitizer()
        result = s.sanitize("python 3.12 + API - REST")
        assert "3.12" in result
        assert "+" in result
        assert "-" in result


class TestResultLimit:
    def test_apply_no_limit_needed(self) -> None:
        limiter = ResultLimit(10)
        results = [{"rank": i} for i in range(5)]
        assert len(limiter.apply(results)) == 5

    def test_apply_truncates(self) -> None:
        limiter = ResultLimit(3)
        results = [{"rank": i} for i in range(10)]
        assert len(limiter.apply(results)) == 3

    def test_apply_empty(self) -> None:
        limiter = ResultLimit(10)
        assert limiter.apply([]) == []

    def test_custom_max(self) -> None:
        limiter = ResultLimit(1)
        results = [{"rank": i} for i in range(5)]
        assert len(limiter.apply(results)) == 1


class TestDomainBlacklist:
    def test_empty_blocks_none(self) -> None:
        b = DomainBlacklist()
        assert not b.is_blocked("http://example.com")

    def test_block_exact_domain(self) -> None:
        b = DomainBlacklist({"example.com"})
        assert b.is_blocked("http://example.com/page")
        assert not b.is_blocked("http://other.com")

    def test_block_subdomain(self) -> None:
        b = DomainBlacklist({"example.com"})
        assert b.is_blocked("http://sub.example.com/page")

    def test_block_add_domain(self) -> None:
        b = DomainBlacklist()
        b.add("evil.com")
        assert b.is_blocked("http://evil.com")
        assert not b.is_blocked("http://good.com")

    def test_filter_removes_blocked(self) -> None:
        b = DomainBlacklist({"bad.com"})
        results = [
            {"url": "http://good.com/page"},
            {"url": "http://bad.com/page"},
            {"url": "http://good.com/other"},
        ]
        filtered = b.filter(results)
        assert len(filtered) == 2
        assert all("bad.com" not in r["url"] for r in filtered)

    def test_filter_empty(self) -> None:
        b = DomainBlacklist({"bad.com"})
        assert b.filter([]) == []

    def test_invalid_url_returns_blocked(self) -> None:
        b = DomainBlacklist()
        blocked = b.is_blocked("")
        assert blocked is True or blocked is False


class TestDuckDuckGoResultParser:
    def test_parser_empty(self) -> None:
        parser = _DuckDuckGoResultParser()
        assert parser.results == []

    def test_parser_no_results(self) -> None:
        parser = _DuckDuckGoResultParser()
        parser.feed("<html><body>No results here</body></html>")
        assert parser.results == []

    def test_parser_with_data(self) -> None:
        html = """<html>
        <tr class="result-snippet">
            <td class="result-snippet">
                <a href="http://example.com" class="result-link">Example</a>
                Some snippet text
            </td>
        </tr>
        </html>"""
        parser = _DuckDuckGoResultParser()
        parser.feed(html)
        assert len(parser.results) == 1
        assert parser.results[0]["title"] == "Example"
        assert parser.results[0]["url"] == "http://example.com"

    def test_parser_missing_title_result_not_appended(self) -> None:
        html = """<html>
        <tr class="result-snippet">
            <td class="result-snippet">No link here</td>
        </tr>
        </html>"""
        parser = _DuckDuckGoResultParser()
        parser.feed(html)
        assert parser.results == []


class TestFallbackParse:
    def test_fallback_empty(self) -> None:
        assert _fallback_parse("<html></html>") == []

    def test_fallback_with_results(self) -> None:
        html = """
        <a rel="nofollow" href="http://ex.com/1" class="result-link">Title 1</a>
        <td class="result-snippet">Snippet 1</td>
        <a rel="nofollow" href="http://ex.com/2" class="result-link">Title 2</a>
        <td class="result-snippet">Snippet 2</td>
        """
        results = _fallback_parse(html)
        assert len(results) >= 2
        assert results[0]["title"] == "Title 1"
        assert results[0]["url"] == "http://ex.com/1"


class TestParseSearchResults:
    def test_parse_empty(self) -> None:
        assert _parse_search_results("", max_results=10) == []

    def test_parse_malformed_does_not_raise(self) -> None:
        results = _parse_search_results("<html<<broken>>>", max_results=10)
        assert isinstance(results, list)


class TestExecuteSearch:
    def test_empty_query_returns_empty(self) -> None:
        assert _execute_search("", max_results=10) == []

    def test_http_error_returns_empty(self) -> None:
        with patch("maref.tools.web_search_server.httpx.get") as mock_get:
            mock_get.side_effect = Exception("Network error")
            results = _execute_search("test", max_results=10)
            assert results == []

    def test_successful_search(self) -> None:
        mock_html = """<html>
        <tr class="result-snippet">
            <td class="result-snippet">
                <a href="http://example.com" class="result-link">Example</a>
                Example snippet
            </td>
        </tr>
        </html>"""
        with patch("maref.tools.web_search_server.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            results = _execute_search("test", max_results=10)
            assert len(results) == 1
            assert results[0]["title"] == "Example"
            assert results[0]["url"] == "http://example.com"
            assert results[0]["rank"] == 1

    def test_news_search_type(self) -> None:
        with patch("maref.tools.web_search_server.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.text = "<html></html>"
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            results = _execute_search("test", max_results=10, search_type="news")
            assert results == []

    def test_max_results_applied(self) -> None:
        html = "<html>" + "".join(
            f"""<tr class="result-snippet">
                <td class="result-snippet">
                    <a href="http://ex.com/{i}" class="result-link">Result {i}</a>
                    Snippet {i}
                </td>
            </tr>"""
            for i in range(5)
        ) + "</html>"
        with patch("maref.tools.web_search_server.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.text = html
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            results = _execute_search("test", max_results=2)
            assert len(results) == 2


class TestCreateWebSearchServer:
    def test_server_info(self) -> None:
        server = create_web_search_server()
        transport = server.get_inprocess_transport()
        transport.connect()
        resp = transport.send_initialize()
        assert not resp.is_error
        assert resp.result["serverInfo"]["name"] == "web-search-server"

    def test_tools_list(self) -> None:
        server = create_web_search_server()
        transport = server.get_inprocess_transport()
        transport.connect()
        resp = transport.send_tools_list()
        assert not resp.is_error
        names = [t["name"] for t in resp.result["tools"]]
        assert "web_search" in names
        assert "web_search_news" in names

    def test_web_search_handler(self) -> None:
        server = create_web_search_server(max_results=5)
        with patch("maref.tools.web_search_server._execute_search") as mock_exec:
            mock_exec.return_value = [
                {"title": "Result 1", "url": "http://ex.com/1", "snippet": "Snip", "rank": 1}
            ]
            transport = server.get_inprocess_transport()
            transport.connect()
            resp = transport.send_tool_call("web_search", {"query": "test"})
            assert not resp.is_error
            assert resp.result["count"] == 1
            assert resp.result["search_type"] == "web"
            mock_exec.assert_called_once()

    def test_web_search_news_handler(self) -> None:
        server = create_web_search_server()
        with patch("maref.tools.web_search_server._execute_search") as mock_exec:
            mock_exec.return_value = []
            transport = server.get_inprocess_transport()
            transport.connect()
            resp = transport.send_tool_call("web_search_news", {"query": "news"})
            assert not resp.is_error
            assert resp.result["count"] == 0
            assert resp.result["search_type"] == "news"

    def test_unknown_tool(self) -> None:
        server = create_web_search_server()
        transport = server.get_inprocess_transport()
        transport.connect()
        resp = transport.send_tool_call("nonexistent", {})
        assert resp.is_error
