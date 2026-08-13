import argparse
import http.server
import json
import logging
import sys
from typing import Any

from maref.integration.mcp_security import MCPSecurityGate
from maref.integration.mcp_server import MCPServer
from maref.integration.mcp_transport import MCPTransport
from sidecar.exfiltration_probe import DataExfiltrationProbe
from sidecar.mcp_bridge import MCPBridge

logger = logging.getLogger(__name__)


class MCPHTTPHandler(http.server.BaseHTTPRequestHandler):
    def __init__(self, *args: Any, server: Any = None, **kwargs: Any) -> None:
        self.server = server
        super().__init__(*args, **kwargs)

    def do_POST(self) -> None:
        try:
            from maref.integration.mcp_transport import JSONRPCRequest

            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            raw = json.loads(body)
            request = JSONRPCRequest(
                jsonrpc=raw.get("jsonrpc", "2.0"),
                method=raw.get("method", ""),
                params=raw.get("params"),
                id=raw.get("id", 0),
            )
            response = self.server.mcp_server.handle_request(request)  # type: ignore[attr-defined]
            self._send_json(response.__dict__)
        except Exception as e:
            logger.error(f"POST error: {e}")
            self._send_error(500, str(e))

    def do_GET(self) -> None:
        try:
            response = {"status": "ok", "server": "MAREF MCP"}
            self._send_json(response)
        except Exception as e:
            logger.error(f"GET error: {e}")
            self._send_error(500, str(e))

    def _send_json(self, data: Any) -> None:
        try:
            if hasattr(data, "__dict__"):
                data = data.__dict__
            body = json.dumps(data, default=str).encode("utf-8")
            self._send_response(200, body, "application/json")
        except Exception as e:
            logger.error(f"JSON send error: {e}")
            self._send_error(500, str(e))

    def _send_response(self, status: int, body: bytes, content_type: str = "text/plain") -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            logger.error(f"Response send error: {e}")

    def _send_error(self, status: int, message: str) -> None:
        try:
            body = json.dumps({"error": message}).encode("utf-8")
            self._send_response(status, body, "application/json")
        except Exception as e:
            logger.error(f"Error send error: {e}")

    def log_message(self, format: str, *args: Any) -> None:
        logger.info(f"{self.client_address[0]} - {format % args}")


def create_server(host: str = "localhost", port: int = 8080) -> http.server.HTTPServer:
    try:
        mcp_server = MCPServer()
        mcp_transport = MCPTransport()  # type: ignore[abstract]
        security_manager = MCPSecurityGate(allow_unverified_tokens=True)
        exfiltration_probe = DataExfiltrationProbe()
        mcp_bridge = MCPBridge()

        class Handler(MCPHTTPHandler):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, server=server, **kwargs)

        server = http.server.HTTPServer((host, port), Handler)
        server.mcp_server = mcp_server  # type: ignore[attr-defined]
        server.mcp_transport = mcp_transport  # type: ignore[attr-defined]
        server.security_manager = security_manager  # type: ignore[attr-defined]
        server.exfiltration_probe = exfiltration_probe  # type: ignore[attr-defined]
        server.mcp_bridge = mcp_bridge  # type: ignore[attr-defined]
        return server
    except Exception as e:
        logger.error(f"Server creation error: {e}")
        raise


def run_http_server(host: str = "localhost", port: int = 8080) -> None:
    try:
        server = create_server(host, port)
        logger.info(f"Starting HTTP server on {host}:{port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"HTTP server error: {e}")
        raise


def run_stdio_server() -> None:
    try:
        from maref.integration.mcp_transport import JSONRPCRequest

        mcp_server = MCPServer()
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
                request = JSONRPCRequest(
                    jsonrpc=raw.get("jsonrpc", "2.0"),
                    method=raw.get("method", ""),
                    params=raw.get("params"),
                    id=raw.get("id", 0),
                )
                response = mcp_server.handle_request(request)
                print(json.dumps(response.__dict__, default=str), flush=True)
            except Exception as e:
                logger.error(f"STDIO processing error: {e}")
                error_response = {"error": str(e)}
                print(json.dumps(error_response), flush=True)
    except Exception as e:
        logger.error(f"STDIO server error: {e}")
        raise


def main() -> None:
    try:
        parser = argparse.ArgumentParser(description="MAREF MCP Server")
        parser.add_argument("--http", action="store_true", help="Run as HTTP server")
        parser.add_argument("--host", default="localhost", help="Host to bind to")
        parser.add_argument("--port", type=int, default=8080, help="Port to bind to")
        args = parser.parse_args()
        if args.http:
            run_http_server(args.host, args.port)
        else:
            run_stdio_server()
    except Exception as e:
        logger.error(f"Main error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
