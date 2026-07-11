import argparse
import json
import logging
import sys
import http.server
from typing import Any, Dict
from maref.integration.mcp_security import MCPSecurityManager
from maref.integration.mcp_server import MCPServer
from maref.integration.mcp_transport import MCPTransport
from sidecar.exfiltration_probe import ExfiltrationProbe
from sidecar.mcp_bridge import MCPBridge
logger = logging.getLogger(__name__)

class MCPHTTPHandler(http.server.BaseHTTPRequestHandler):

    def __init__(self, *args: Any, server: Any=None, **kwargs: Any) -> None:
        self.server = server
        super().__init__(*args, **kwargs)

    def do_POST(self) -> None:
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
            response = self.server.mcp_server.handle_request(data)
            self._send_json(response)
        except Exception as e:
            logger.error(f'POST error: {e}')
            self._send_error(500, str(e))

    def do_GET(self) -> None:
        try:
            response = {'status': 'ok', 'server': 'MAREF MCP'}
            self._send_json(response)
        except Exception as e:
            logger.error(f'GET error: {e}')
            self._send_error(500, str(e))

    def _send_json(self, data: Dict[str, Any]) -> None:
        try:
            body = json.dumps(data).encode('utf-8')
            self._send_response(200, body, 'application/json')
        except Exception as e:
            logger.error(f'JSON send error: {e}')
            self._send_error(500, str(e))

    def _send_response(self, status: int, body: bytes, content_type: str='text/plain') -> None:
        try:
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            logger.error(f'Response send error: {e}')

    def _send_error(self, status: int, message: str) -> None:
        try:
            body = json.dumps({'error': message}).encode('utf-8')
            self._send_response(status, body, 'application/json')
        except Exception as e:
            logger.error(f'Error send error: {e}')

    def log_message(self, format: str, *args: Any) -> None:
        logger.info(f'{self.client_address[0]} - {format % args}')

def create_server(host: str='localhost', port: int=8080) -> http.server.HTTPServer:
    try:
        mcp_server = MCPServer()
        mcp_transport = MCPTransport()
        security_manager = MCPSecurityManager()
        exfiltration_probe = ExfiltrationProbe()
        mcp_bridge = MCPBridge()

        class Handler(MCPHTTPHandler):

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, server=server, **kwargs)
        server = http.server.HTTPServer((host, port), Handler)
        server.mcp_server = mcp_server
        server.mcp_transport = mcp_transport
        server.security_manager = security_manager
        server.exfiltration_probe = exfiltration_probe
        server.mcp_bridge = mcp_bridge
        return server
    except Exception as e:
        logger.error(f'Server creation error: {e}')
        raise

def run_http_server(host: str='localhost', port: int=8080) -> None:
    try:
        server = create_server(host, port)
        logger.info(f'Starting HTTP server on {host}:{port}')
        server.serve_forever()
    except Exception as e:
        logger.error(f'HTTP server error: {e}')
        raise

def run_stdio_server() -> None:
    try:
        mcp_server = MCPServer()
        mcp_transport = MCPTransport()
        security_manager = MCPSecurityManager()
        exfiltration_probe = ExfiltrationProbe()
        mcp_bridge = MCPBridge()
        for line in sys.stdin:
            try:
                data = json.loads(line.strip())
                response = mcp_server.handle_request(data)
                print(json.dumps(response), flush=True)
            except Exception as e:
                logger.error(f'STDIO processing error: {e}')
                error_response = {'error': str(e)}
                print(json.dumps(error_response), flush=True)
    except Exception as e:
        logger.error(f'STDIO server error: {e}')
        raise

def main() -> None:
    try:
        parser = argparse.ArgumentParser(description='MAREF MCP Server')
        parser.add_argument('--http', action='store_true', help='Run as HTTP server')
        parser.add_argument('--host', default='localhost', help='Host to bind to')
        parser.add_argument('--port', type=int, default=8080, help='Port to bind to')
        args = parser.parse_args()
        if args.http:
            run_http_server(args.host, args.port)
        else:
            run_stdio_server()
    except Exception as e:
        logger.error(f'Main error: {e}')
        sys.exit(1)
if __name__ == '__main__':
    main()