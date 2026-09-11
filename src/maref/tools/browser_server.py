from __future__ import annotations

import base64
import ipaddress
import re
import threading
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx

from maref.integration.mcp_server import MCPServer

# Module-level BrowserController singleton for navigation control tools
_BROWSER_CONTROLLER: Any | None = None
_BROWSER_LOCK = threading.Lock()


def _ensure_browser_controller() -> Any | None:
    global _BROWSER_CONTROLLER
    if _BROWSER_CONTROLLER is None:
        with _BROWSER_LOCK:
            if _BROWSER_CONTROLLER is None:
                try:
                    from maref.desktop.browser_controller import BrowserController

                    _BROWSER_CONTROLLER = BrowserController(safe_domains=["*"], dry_run=True)
                except ImportError:
                    pass
    return _BROWSER_CONTROLLER


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
DEFAULT_MAX_CONTENT_SIZE = 5242880


class DomainWhitelist:
    def __init__(self, domains: list[str] | None = None) -> None:
        self._patterns: list[re.Pattern[str]] = []
        if domains is not None:
            for domain in domains:
                self.add(domain)

    def add(self, domain: str) -> None:
        escaped = re.escape(domain).replace(r"\*", "[^/]+")
        self._patterns.append(re.compile(f"^{escaped}$"))

    def is_allowed(self, hostname: str) -> bool:
        if not self._patterns:
            return True
        return any(p.search(hostname) for p in self._patterns)


def _validate_url(url: str, whitelist: DomainWhitelist | None = None) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Only http/https URLs are allowed, got: {parsed.scheme}")

    hostname = parsed.hostname or ""

    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        addr = None

    if addr is not None:
        if addr.is_loopback or addr == ipaddress.IPv4Address("0.0.0.0"):
            if whitelist is not None and whitelist.is_allowed(hostname):
                return url
            raise ValueError(f"Loopback URLs are not allowed: {url}")
        if whitelist is not None and whitelist.is_allowed(hostname):
            return url
        raise ValueError(f"IP-based URLs are not allowed: {url}")

    if hostname in ("localhost", "::1") or hostname.endswith(".local"):
        if whitelist is not None and whitelist.is_allowed(hostname):
            return url
        raise ValueError(f"Localhost URLs are not allowed: {url}")

    if whitelist is not None and not whitelist.is_allowed(hostname):
        raise ValueError(f"Domain not in whitelist: {hostname}")

    return url


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._in_link = False
        self._current_link: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = None
            for name, value in attrs:
                if name == "href":
                    href = value
            if href is not None:
                self._current_link = {"href": href, "text": ""}
                self._in_link = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current_link is not None:
            self.links.append(self._current_link)
            self._current_link = None
            self._in_link = False

    def handle_data(self, data: str) -> None:
        if self._in_link and self._current_link is not None:
            self._current_link["text"] += data.strip()


def _extract_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else ""


def _fetch_url(url: str, max_size: int = DEFAULT_MAX_CONTENT_SIZE) -> tuple[bytes, dict[str, Any]]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    with (
        httpx.Client(timeout=30, follow_redirects=True, headers=headers) as client,
        client.stream("GET", url) as resp,
    ):
        resp.raise_for_status()
        content = b""
        for chunk in resp.iter_bytes():
            content += chunk
            if len(content) > max_size:
                raise ValueError(f"Content exceeds maximum size of {max_size} bytes")
        return content, dict(resp.headers)


def _decode_content(content: bytes, headers: dict[str, Any]) -> str:
    charset = "utf-8"
    ct = headers.get("Content-Type", "")
    m = re.search(r"charset=([\w-]+)", ct)
    if m:
        charset = m.group(1)
    try:
        return content.decode(charset)
    except (UnicodeDecodeError, LookupError):
        return content.decode("utf-8", errors="replace")


def create_browser_server(
    domain_whitelist: list[str] | None = None,
    max_content_size: int = DEFAULT_MAX_CONTENT_SIZE,
) -> MCPServer:
    whitelist = DomainWhitelist(domain_whitelist) if domain_whitelist is not None else None

    def _browser_open(args: dict[str, Any]) -> dict[str, Any]:
        url = _validate_url(str(args["url"]), whitelist)
        content_bytes, headers = _fetch_url(url, max_content_size)
        text = _decode_content(content_bytes, headers)
        title = _extract_title(text)
        return {
            "url": url,
            "title": title,
            "content": text,
            "text_length": len(text),
        }

    def _browser_screenshot(args: dict[str, Any]) -> dict[str, Any]:
        url = _validate_url(str(args["url"]), whitelist)
        placeholder = base64.b64encode(b"placeholder_png_data").decode("ascii")
        return {"url": url, "screenshot": placeholder, "format": "png"}

    def _browser_get_html(args: dict[str, Any]) -> dict[str, Any]:
        url = _validate_url(str(args["url"]), whitelist)
        content_bytes, headers = _fetch_url(url, max_content_size)
        html = _decode_content(content_bytes, headers)
        return {"url": url, "html": html, "size": len(content_bytes)}

    def _browser_get_links(args: dict[str, Any]) -> dict[str, Any]:
        url = _validate_url(str(args["url"]), whitelist)
        filter_domain = args.get("filter_domain")
        content_bytes, headers = _fetch_url(url, max_content_size)
        html = _decode_content(content_bytes, headers)
        extractor = _LinkExtractor()
        extractor.feed(html)
        links = extractor.links
        if filter_domain is not None:
            base_netloc = urlparse(url).netloc
            links = [
                l
                for l in links
                if urlparse(l["href"]).netloc == filter_domain
                or (not urlparse(l["href"]).netloc and filter_domain == base_netloc)
            ]
        return {"url": url, "links": links, "count": len(links)}

    # ── 导航控制工具（依赖 Playwright BrowserController） ────────────────

    def _browser_go_back(args: dict[str, Any]) -> dict[str, Any]:
        controller = _ensure_browser_controller()
        if controller is None:
            return {"success": False, "error": "Playwright not available"}
        result = controller.go_back()
        return {"success": result.success, "error": result.error if not result.success else ""}

    def _browser_go_forward(args: dict[str, Any]) -> dict[str, Any]:
        controller = _ensure_browser_controller()
        if controller is None:
            return {"success": False, "error": "Playwright not available"}
        result = controller.go_forward()
        return {"success": result.success, "error": result.error if not result.success else ""}

    def _browser_refresh(args: dict[str, Any]) -> dict[str, Any]:
        controller = _ensure_browser_controller()
        if controller is None:
            return {"success": False, "error": "Playwright not available"}
        result = controller.reload_page()
        return {"success": result.success, "error": result.error if not result.success else ""}

    def _browser_get_element_text(args: dict[str, Any]) -> dict[str, Any]:
        selector = str(args["selector"])
        controller = _ensure_browser_controller()
        if controller is None:
            return {"success": False, "error": "Playwright not available"}
        result = controller.get_element_text(selector)
        if not result.success:
            return {"success": False, "selector": selector, "error": result.error}
        return {"success": True, "selector": selector, "text": result.text}

    server = MCPServer(name="browser-server", version="0.1.0")

    server.register_tool(
        name="browser_open",
        description="Open a URL and return its text content",
        input_schema={
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
        handler=_browser_open,
    )

    server.register_tool(
        name="browser_screenshot",
        description="Take a screenshot of a URL (placeholder implementation)",
        input_schema={
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
        handler=_browser_screenshot,
    )

    server.register_tool(
        name="browser_get_html",
        description="Get the raw HTML content of a URL",
        input_schema={
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
        handler=_browser_get_html,
    )

    server.register_tool(
        name="browser_get_links",
        description="Extract all links from a URL, optionally filtering by domain",
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "filter_domain": {"type": "string"},
            },
            "required": ["url"],
        },
        handler=_browser_get_links,
    )

    # ── 导航控制工具 ─────────────────────────────────────────────

    server.register_tool(
        name="browser_go_back",
        description="Navigate back to the previous page",
        input_schema={"type": "object", "properties": {}},
        handler=_browser_go_back,
    )

    server.register_tool(
        name="browser_go_forward",
        description="Navigate forward to the next page",
        input_schema={"type": "object", "properties": {}},
        handler=_browser_go_forward,
    )

    server.register_tool(
        name="browser_refresh",
        description="Refresh the current page",
        input_schema={"type": "object", "properties": {}},
        handler=_browser_refresh,
    )

    server.register_tool(
        name="browser_get_element_text",
        description="Get the text content of an element matching a CSS selector",
        input_schema={
            "type": "object",
            "properties": {"selector": {"type": "string"}},
            "required": ["selector"],
        },
        handler=_browser_get_element_text,
    )

    return server
