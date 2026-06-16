from __future__ import annotations

import re
import urllib.parse
from html.parser import HTMLParser
from typing import Any

import httpx

from maref.integration.mcp_server import MCPServer

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

DEFAULT_MAX_RESULTS = 10
DEFAULT_TIMEOUT = 15
SEARCH_URL = "https://lite.duckduckgo.com/lite"
NEWS_SEARCH_URL = "https://lite.duckduckgo.com/lite"

_DISALLOWED_DOMAINS: set[str] = set()


class QuerySanitizer:
    def __init__(self, max_length: int = 500) -> None:
        self._max_length = max_length

    def sanitize(self, query: str) -> str:
        cleaned = query.strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(r"[^\w\s\-.,?!@#$%^&*()+=[\]{}|;:'\"/`~]", "", cleaned)
        if len(cleaned) > self._max_length:
            cleaned = cleaned[: self._max_length]
        return cleaned


class ResultLimit:
    def __init__(self, max_results: int = DEFAULT_MAX_RESULTS) -> None:
        self._max_results = max_results

    def apply(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return results[: self._max_results]


class DomainBlacklist:
    def __init__(self, domains: set[str] | None = None) -> None:
        self._domains: set[str] = domains or set()

    def add(self, domain: str) -> None:
        self._domains.add(domain.lower())

    def is_blocked(self, url: str) -> bool:
        try:
            parsed = urllib.parse.urlparse(url)
            hostname = parsed.hostname or ""
            if hostname.lower() in self._domains:
                return True
            for blocked in self._domains:
                if hostname.lower().endswith("." + blocked):
                    return True
        except Exception:
            return True
        return False

    def filter(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [r for r in results if not self.is_blocked(r.get("url", ""))]


class _DuckDuckGoResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, Any]] = []
        self._current_result: dict[str, Any] | None = None
        self._current_field: str = ""
        self._in_result_row = False
        self._in_link = False
        self._in_snippet = False
        self._snippet_parts: list[str] = []
        self._link_href: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)

        if tag == "tr" and "result-snippet" in (attrs_dict.get("class", "") or ""):
            self._in_result_row = True

        if self._in_result_row and tag == "a":
            href = attrs_dict.get("href", "")
            if href and not href.startswith("//duckduckgo.com"):
                self._in_link = True
                self._link_href = href
                text_class = attrs_dict.get("class", "") or ""
                if "result-link" in text_class:
                    self._current_field = "link"

        if self._in_result_row and tag == "td":
            td_class = attrs_dict.get("class", "") or ""
            if "result-snippet" in td_class:
                self._in_snippet = True
                self._snippet_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_link:
            self._in_link = False

        if tag == "td" and self._in_snippet:
            self._in_snippet = False
            if self._current_result is not None:
                self._current_result["snippet"] = " ".join(self._snippet_parts).strip()

        if tag == "tr" and self._in_result_row:
            self._in_result_row = False
            if self._current_result is not None and self._current_result.get("title"):
                self.results.append(self._current_result)
            self._current_result = None

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return

        if self._in_link and self._current_field == "link":
            self._current_result = {"title": text, "url": self._link_href, "snippet": ""}
            self._current_field = ""
        elif self._in_link:
            if self._current_result is not None:
                existing = self._current_result.get("snippet", "")
                self._current_result["snippet"] = (existing + " " + text).strip()

        if self._in_snippet:
            self._snippet_parts.append(text)


def _parse_search_results(
    html: str, max_results: int = DEFAULT_MAX_RESULTS
) -> list[dict[str, Any]]:
    parser = _DuckDuckGoResultParser()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.results[:max_results]


def _fallback_parse(html: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    link_pattern = re.compile(
        r'<a[^>]*rel="nofollow"[^>]*href="([^"]*)"[^>]*class="result-link"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>',
        re.DOTALL,
    )
    links = link_pattern.findall(html)
    snippets = snippet_pattern.findall(html)
    for i, (url, title) in enumerate(links):
        title_clean = re.sub(r"<[^>]+>", "", title).strip()
        snippet = ""
        if i < len(snippets):
            snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
        results.append({"title": title_clean, "url": url, "snippet": snippet})
    return results


def _execute_search(
    query: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    search_type: str = "web",
) -> list[dict[str, Any]]:
    sanitizer = QuerySanitizer()
    clean_query = sanitizer.sanitize(query)
    if not clean_query:
        return []

    params: dict[str, str] = {"q": clean_query}
    if search_type == "news":
        params["t"] = "news"

    url = f"{SEARCH_URL}?{urllib.parse.urlencode(params)}"
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            timeout=DEFAULT_TIMEOUT,
            follow_redirects=True,
        )
        response.raise_for_status()
        html = response.text
    except Exception:
        return []

    results = _parse_search_results(html, max_results)
    if not results:
        results = _fallback_parse(html)

    limiter = ResultLimit(max_results)
    results = limiter.apply(results)

    blacklist = DomainBlacklist(_DISALLOWED_DOMAINS)
    results = blacklist.filter(results)

    for i, r in enumerate(results):
        r["rank"] = i + 1

    return results


def create_web_search_server(
    max_results: int = DEFAULT_MAX_RESULTS,
    query_sanitizer: bool = True,
) -> MCPServer:
    def _web_search(args: dict[str, Any]) -> dict[str, Any]:
        query = str(args["query"])
        limit = int(args.get("max_results", max_results))
        results = _execute_search(query, max_results=limit, search_type="web")
        return {
            "query": query,
            "results": results,
            "count": len(results),
            "search_type": "web",
        }

    def _web_search_news(args: dict[str, Any]) -> dict[str, Any]:
        query = str(args["query"])
        limit = int(args.get("max_results", max_results))
        results = _execute_search(query, max_results=limit, search_type="news")
        return {
            "query": query,
            "results": results,
            "count": len(results),
            "search_type": "news",
        }

    server = MCPServer(name="web-search-server", version="0.1.0")

    server.register_tool(
        name="web_search",
        description="Search the web for information using DuckDuckGo",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": max_results},
            },
            "required": ["query"],
        },
        handler=_web_search,
    )

    server.register_tool(
        name="web_search_news",
        description="Search for news articles using DuckDuckGo",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": max_results},
            },
            "required": ["query"],
        },
        handler=_web_search_news,
    )

    return server
