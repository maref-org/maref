"""Standalone MAREF Governance MCP Server.

Starts an MCP-compatible JSON-RPC 2.0 server with all sidecar
observation + governance tools registered.

Usage:
    # HTTP server mode (default standalone)
    python -m maref --standalone --port 8941

    # Stdio mode (for opencode/Claude Desktop integration)
    python -m maref --stdio
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from maref.integration.mcp_security import MCPSecurityGate, MCPTrustLevel
from maref.integration.mcp_server import MCPServer
from maref.integration.mcp_transport import JSONRPCRequest, JSONRPCResponse
from sidecar.exfiltration_probe import DataExfiltrationProbe
from sidecar.mcp_bridge import (
    SIDECAR_MCP_RESOURCES,
    SIDECAR_MCP_TOOLS,
    SidecarMCPBridge,
)

logger = logging.getLogger("maref-governance-mcp")


def create_server() -> MCPServer:
    """Create and configure the MCP server with all tools and resources."""
    probe = DataExfiltrationProbe()
    bridge = SidecarMCPBridge(exfiltration_probe=probe)
    security_gate = MCPSecurityGate()

    server = MCPServer(
        name="maref-governance-mcp",
        version="0.27.0",
        security_gate=security_gate,
    )

    for tool_def in SIDECAR_MCP_TOOLS:
        tool_name = tool_def.name

        def make_handler(name: str = tool_name) -> Any:
            def handler(args: dict[str, Any]) -> Any:
                return bridge.handle_tool_call(name, args)

            return handler

        server.register_tool(
            name=tool_def.name,
            description=tool_def.description,
            input_schema=tool_def.input_schema,
            handler=make_handler(),
        )

    for res in SIDECAR_MCP_RESOURCES:
        uri = res["uri"]
        mime = res.get("mimeType", "application/json")

        def make_resource_handler(
            resource_uri: str = uri,
            mime_type: str = mime,
            sidecar_bridge: SidecarMCPBridge = bridge,
        ) -> Any:
            def handler(_uri: str) -> dict[str, Any]:
                return {
                    "uri": resource_uri,
                    "mimeType": mime_type,
                    "text": json.dumps(
                        {
                            "resource": resource_uri,
                            "available": True,
                            "note": "Resource available via tool calls",
                        }
                    ),
                }

            return handler

        server.register_resource(
            uri=uri,
            name=res["name"],
            mime_type=mime,
            handler=make_resource_handler(),
        )

    return server


# ── HTTP Transport ────────────────────────────────────────────────────


class MCPHTTPHandler(BaseHTTPRequestHandler):
    """HTTP handler for MCP JSON-RPC requests.

    NOTE: The MCPServer instance is stored as a *class* attribute named
    ``mcp_core`` to avoid collision with ``BaseServer.server`` (which
    refers to the ``HTTPServer`` instance).
    """

    mcp_core: MCPServer  # class-level, set before serve_forever

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        try:
            data = json.loads(body)
            request = JSONRPCRequest(
                jsonrpc=data.get("jsonrpc", "2.0"),
                method=data.get("method", ""),
                params=data.get("params"),
                id=data.get("id", 0),
            )
        except (json.JSONDecodeError, KeyError) as e:
            self._send_json(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32700, "message": f"Parse error: {e}"},
                    "id": None,
                }
            )
            return

        response = type(self).mcp_core.handle_request(
            request, trust_level=MCPTrustLevel.TRUSTED
        )
        self._send_response(response)

    def _send_response(self, response: JSONRPCResponse) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": response.id}
        if response.error:
            payload["error"] = response.error
        else:
            payload["result"] = response.result
        self._send_json(payload)

    def _send_json(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(
                {"status": "ok", "server": "maref-governance-mcp", "version": "0.27.0"}
            )
        elif self.path == "/":
            self._send_json(
                {
                    "server": "maref-governance-mcp",
                    "tools": len(SIDECAR_MCP_TOOLS),
                    "resources": len(SIDECAR_MCP_RESOURCES),
                }
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("MCP %s - %s", self.client_address[0], format % args)


def run_http_server(host: str, port: int, mcp_server: MCPServer) -> None:
    """Run the MCP server in HTTP mode."""
    MCPHTTPHandler.mcp_core = mcp_server
    httpd = HTTPServer((host, port), MCPHTTPHandler)

    logger.info(
        "MAREF Governance MCP Server (HTTP) starting on %s:%d", host, port
    )
    logger.info(
        "Tools: %d, Resources: %d",
        len(SIDECAR_MCP_TOOLS),
        len(SIDECAR_MCP_RESOURCES),
    )

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        httpd.server_close()


# ── Stdio Transport ───────────────────────────────────────────────────


def run_stdio_server(mcp_server: MCPServer) -> None:
    """Run the MCP server in stdio mode.

    Reads JSON-RPC 2.0 requests (one per line) from stdin and writes
    responses (one per line) to stdout.  Stderr is reserved for logging.
    This is the standard transport used by opencode, Claude Desktop,
    and other MCP hosts.
    """
    # Route our logger to stderr so we don't pollute stdout
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(stderr_handler)

    logger.info(
        "MAREF Governance MCP Server (stdio) starting -- reading from stdin"
    )
    logger.info(
        "Tools: %d, Resources: %d",
        len(SIDECAR_MCP_TOOLS),
        len(SIDECAR_MCP_RESOURCES),
    )

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            data = json.loads(line)
            request = JSONRPCRequest(
                jsonrpc=data.get("jsonrpc", "2.0"),
                method=data.get("method", ""),
                params=data.get("params"),
                id=data.get("id", 0),
            )
        except (json.JSONDecodeError, KeyError) as e:
            error_resp = {
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": f"Parse error: {e}"},
                "id": None,
            }
            sys.stdout.write(json.dumps(error_resp) + "\n")
            sys.stdout.flush()
            continue

        response = mcp_server.handle_request(
            request, trust_level=MCPTrustLevel.TRUSTED
        )
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": response.id}
        if response.error:
            payload["error"] = response.error
        else:
            payload["result"] = response.result

        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()


# ── Entry Point ───────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="MAREF Governance MCP Server")
    parser.add_argument(
        "--standalone", action="store_true", help="Run as standalone HTTP server"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8941,
        help="HTTP server port (default: 8941)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="HTTP bind address (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Run in stdio mode (read JSON-RPC from stdin, write to stdout)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Enable verbose logging"
    )
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not args.standalone and not args.stdio:
        parser.print_help()
        return

    mcp_server = create_server()

    if args.stdio:
        run_stdio_server(mcp_server)
    else:
        run_http_server(args.host, args.port, mcp_server)


if __name__ == "__main__":
    main()
