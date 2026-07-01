from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from maref.integration.mcp_transport import JSONRPCRequest
from maref.tools.browser_server import (
    DomainWhitelist,
    _validate_url,
    create_browser_server,
)

TEST_HTML = """<html>
<head><title>Test Page</title></head>
<body>
    <h1>Hello World</h1>
    <a href="https://example.com/page1">Link 1</a>
    <a href="https://example.com/page2">Link 2</a>
    <a href="https://other.com/page">Other Site</a>
    <a href="/relative/path">Relative Link</a>
</body>
</html>"""

LARGE_BODY = b"x" * 6_000_000


class _TestHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/":
            self._send_bytes(200, TEST_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/large":
            self._send_bytes(200, LARGE_BODY, "text/plain")
        elif self.path == "/user-agent":
            ua = self.headers.get("User-Agent", "unknown")
            body = json.dumps({"user_agent": ua}).encode("utf-8")
            self._send_bytes(200, body, "application/json")
        elif self.path == "/no-title":
            self._send_bytes(200, b"<html><body>no title here</body></html>", "text/html")
        else:
            self.send_error(404)

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture(scope="module")
def test_server_port() -> Any:
    server = HTTPServer(("127.0.0.1", 0), _TestHTTPHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    yield port
    server.shutdown()


class TestDomainWhitelist:
    def test_empty_allows_all(self) -> None:
        wl = DomainWhitelist()
        assert wl.is_allowed("example.com")
        assert wl.is_allowed("127.0.0.1")
        assert wl.is_allowed("localhost")

    def test_exact_domain_match(self) -> None:
        wl = DomainWhitelist(["example.com"])
        assert wl.is_allowed("example.com")
        assert not wl.is_allowed("evil.com")

    def test_wildcard_match(self) -> None:
        wl = DomainWhitelist(["*.example.com"])
        assert wl.is_allowed("sub.example.com")
        assert wl.is_allowed("deep.sub.example.com")
        assert not wl.is_allowed("example.com")
        assert not wl.is_allowed("evil.com")

    def test_no_domains_allowed_when_whitelist_populated(self) -> None:
        wl = DomainWhitelist(["allowed.com"])
        assert not wl.is_allowed("other.com")
        assert not wl.is_allowed("example.org")

    def test_add_domain_dynamically(self) -> None:
        wl = DomainWhitelist()
        assert wl.is_allowed("anything.com")
        wl.add("specific.com")
        assert wl.is_allowed("specific.com")
        assert not wl.is_allowed("other.com")


class TestURLValidation:
    def test_reject_ftp(self) -> None:
        with pytest.raises(ValueError, match="Only http/https"):
            _validate_url("ftp://example.com/file")

    def test_reject_ip_based_url(self) -> None:
        with pytest.raises(ValueError, match="IP-based URLs"):
            _validate_url("http://192.168.1.1/path")

    def test_reject_localhost(self) -> None:
        with pytest.raises(ValueError, match="Localhost URLs"):
            _validate_url("http://localhost:8080/path")

    def test_reject_local_domain(self) -> None:
        with pytest.raises(ValueError, match="Localhost URLs"):
            _validate_url("http://myhost.local/page")

    def test_reject_private_ip(self) -> None:
        with pytest.raises(ValueError, match="IP-based URLs"):
            _validate_url("http://10.0.0.1/path")

    def test_reject_loopback_ipv6(self) -> None:
        with pytest.raises(ValueError, match="Loopback URLs"):
            _validate_url("http://[::1]/path")

    def test_allow_valid_domain(self) -> None:
        result = _validate_url("http://example.com/path")
        assert result == "http://example.com/path"

    def test_allow_https_domain(self) -> None:
        result = _validate_url("https://docs.python.org/3/")
        assert result == "https://docs.python.org/3/"

    def test_allow_ip_when_whitelisted(self) -> None:
        wl = DomainWhitelist(["127.0.0.1"])
        result = _validate_url("http://127.0.0.1:8080/path", wl)
        assert result == "http://127.0.0.1:8080/path"

    def test_allow_private_ip_when_whitelisted(self) -> None:
        wl = DomainWhitelist(["10.0.0.1"])
        result = _validate_url("http://10.0.0.1/path", wl)
        assert result == "http://10.0.0.1/path"

    def test_allow_localhost_when_whitelisted(self) -> None:
        wl = DomainWhitelist(["localhost"])
        result = _validate_url("http://localhost:3000/", wl)
        assert result == "http://localhost:3000/"

    def test_domain_not_in_whitelist(self) -> None:
        wl = DomainWhitelist(["allowed.com"])
        with pytest.raises(ValueError, match="not in whitelist"):
            _validate_url("http://evil.com/path", wl)

    def test_domain_in_whitelist(self) -> None:
        wl = DomainWhitelist(["example.com"])
        result = _validate_url("http://example.com/path", wl)
        assert result == "http://example.com/path"

    def test_wildcard_whitelist(self) -> None:
        wl = DomainWhitelist(["*.example.com"])
        result = _validate_url("http://sub.example.com/path", wl)
        assert result == "http://sub.example.com/path"
        with pytest.raises(ValueError, match="not in whitelist"):
            _validate_url("http://other.com/path", wl)


class TestBrowserServerTools:
    def test_browser_open(self, test_server_port: int) -> None:
        server = create_browser_server(domain_whitelist=["127.0.0.1"])
        req = JSONRPCRequest(
            method="tools/call",
            params={
                "name": "browser_open",
                "arguments": {"url": f"http://127.0.0.1:{test_server_port}/"},
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error, f"Error: {resp.error}"
        assert resp.result["url"] == f"http://127.0.0.1:{test_server_port}/"
        assert resp.result["title"] == "Test Page"
        assert "Hello World" in resp.result["content"]
        assert resp.result["text_length"] > 0

    def test_browser_open_no_title(self, test_server_port: int) -> None:
        server = create_browser_server(domain_whitelist=["127.0.0.1"])
        req = JSONRPCRequest(
            method="tools/call",
            params={
                "name": "browser_open",
                "arguments": {"url": f"http://127.0.0.1:{test_server_port}/no-title"},
            },
            id=2,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["title"] == ""

    def test_browser_screenshot_not_placeholder(self, test_server_port: int) -> None:
        server = create_browser_server(domain_whitelist=["127.0.0.1"])
        req = JSONRPCRequest(
            method="tools/call",
            params={
                "name": "browser_screenshot",
                "arguments": {"url": f"http://127.0.0.1:{test_server_port}/"},
            },
            id=3,
        )
        resp = server.handle_request(req)
        assert not resp.is_error, f"Error: {resp.error}"
        result_text = str(resp.result)
        assert "placeholder" not in result_text, "Screenshot should not be placeholder data"
        if "screenshot" in resp.result:
            assert len(resp.result["screenshot"]) > 100, "Screenshot should be a real image"

    def test_browser_get_html(self, test_server_port: int) -> None:
        server = create_browser_server(domain_whitelist=["127.0.0.1"])
        req = JSONRPCRequest(
            method="tools/call",
            params={
                "name": "browser_get_html",
                "arguments": {"url": f"http://127.0.0.1:{test_server_port}/"},
            },
            id=4,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["url"] == f"http://127.0.0.1:{test_server_port}/"
        assert "html" in resp.result["html"].lower()
        assert resp.result["size"] > 0

    def test_browser_get_links(self, test_server_port: int) -> None:
        server = create_browser_server(domain_whitelist=["127.0.0.1"])
        req = JSONRPCRequest(
            method="tools/call",
            params={
                "name": "browser_get_links",
                "arguments": {"url": f"http://127.0.0.1:{test_server_port}/"},
            },
            id=5,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["url"] == f"http://127.0.0.1:{test_server_port}/"
        assert resp.result["count"] == 4
        hrefs = [l["href"] for l in resp.result["links"]]
        assert "https://example.com/page1" in hrefs
        assert "https://example.com/page2" in hrefs
        assert "https://other.com/page" in hrefs
        assert "/relative/path" in hrefs

    def test_get_links_filter_domain(self, test_server_port: int) -> None:
        server = create_browser_server(domain_whitelist=["127.0.0.1"])
        req = JSONRPCRequest(
            method="tools/call",
            params={
                "name": "browser_get_links",
                "arguments": {
                    "url": f"http://127.0.0.1:{test_server_port}/",
                    "filter_domain": "example.com",
                },
            },
            id=6,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["count"] == 2
        hrefs = [l["href"] for l in resp.result["links"]]
        assert "https://example.com/page1" in hrefs
        assert "https://example.com/page2" in hrefs

    def test_get_links_filter_relative_matches_base(self, test_server_port: int) -> None:
        server = create_browser_server(domain_whitelist=["127.0.0.1"])
        base_url = f"http://127.0.0.1:{test_server_port}/"
        req = JSONRPCRequest(
            method="tools/call",
            params={
                "name": "browser_get_links",
                "arguments": {
                    "url": base_url,
                    "filter_domain": f"127.0.0.1:{test_server_port}",
                },
            },
            id=7,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["count"] == 1
        assert resp.result["links"][0]["href"] == "/relative/path"

    def test_max_content_size_enforcement(self, test_server_port: int) -> None:
        server = create_browser_server(
            domain_whitelist=["127.0.0.1"],
            max_content_size=100,
        )
        req = JSONRPCRequest(
            method="tools/call",
            params={
                "name": "browser_open",
                "arguments": {"url": f"http://127.0.0.1:{test_server_port}/"},
            },
            id=8,
        )
        resp = server.handle_request(req)
        assert resp.is_error
        assert "exceeds maximum size" in resp.error["message"]

    def test_user_agent_header(self, test_server_port: int) -> None:
        server = create_browser_server(domain_whitelist=["127.0.0.1"])
        req = JSONRPCRequest(
            method="tools/call",
            params={
                "name": "browser_open",
                "arguments": {"url": f"http://127.0.0.1:{test_server_port}/user-agent"},
            },
            id=9,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert "Chrome/125" in resp.result["content"]

    def test_domain_whitelist_blocks(self, test_server_port: int) -> None:
        server = create_browser_server(domain_whitelist=["allowed.com"])
        req = JSONRPCRequest(
            method="tools/call",
            params={
                "name": "browser_open",
                "arguments": {"url": "http://evil.com/page"},
            },
            id=10,
        )
        resp = server.handle_request(req)
        assert resp.is_error
        assert "not in whitelist" in resp.error["message"]

    def test_tool_not_found(self) -> None:
        server = create_browser_server()
        req = JSONRPCRequest(
            method="tools/call",
            params={"name": "nonexistent", "arguments": {}},
            id=11,
        )
        resp = server.handle_request(req)
        assert resp.is_error
        assert resp.error_code == -32602

    def test_server_info(self) -> None:
        server = create_browser_server()
        req = JSONRPCRequest(method="initialize", id=12)
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["serverInfo"]["name"] == "browser-server"

    def test_list_tools(self) -> None:
        server = create_browser_server()
        req = JSONRPCRequest(method="tools/list", id=13)
        resp = server.handle_request(req)
        assert not resp.is_error
        tool_names = [t["name"] for t in resp.result["tools"]]
        assert "browser_open" in tool_names
        assert "browser_screenshot" in tool_names
        assert "browser_get_html" in tool_names
        assert "browser_get_links" in tool_names
        assert len(tool_names) == 4
