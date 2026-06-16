from __future__ import annotations

import json
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

MCP_JSONRPC_VERSION = "2.0"


class TransportState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    EXPIRED = "expired"
    ERROR = "error"


@dataclass
class JSONRPCRequest:
    jsonrpc: str = MCP_JSONRPC_VERSION
    method: str = ""
    params: dict[str, Any] | None = None
    id: int | str = 0

    def to_json(self) -> str:
        payload: dict[str, Any] = {
            "jsonrpc": self.jsonrpc,
            "method": self.method,
            "id": self.id,
        }
        if self.params is not None:
            payload["params"] = self.params
        return json.dumps(payload)


@dataclass
class JSONRPCResponse:
    jsonrpc: str = MCP_JSONRPC_VERSION
    result: Any = None
    error: dict[str, Any] | None = None
    id: int | str = 0

    @property
    def is_error(self) -> bool:
        return self.error is not None

    @property
    def error_code(self) -> int | None:
        if self.error:
            return self.error.get("code")
        return None

    @staticmethod
    def from_json(raw: str) -> JSONRPCResponse:
        data = json.loads(raw)
        return JSONRPCResponse(
            jsonrpc=data.get("jsonrpc", MCP_JSONRPC_VERSION),
            result=data.get("result"),
            error=data.get("error"),
            id=data.get("id", 0),
        )


class MCPTransport(ABC):
    def __init__(self) -> None:
        self._state: TransportState = TransportState.DISCONNECTED

    @property
    def state(self) -> TransportState:
        return self._state

    def set_state(self, state: TransportState) -> None:
        self._state = state

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def send(self, request: JSONRPCRequest) -> JSONRPCResponse: ...

    def send_initialize(self, client_name: str = "maref") -> JSONRPCResponse:
        return self.send(
            JSONRPCRequest(
                method="initialize",
                params={
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": client_name, "version": "0.9.0"},
                },
                id=1,
            )
        )

    def send_tools_list(self) -> JSONRPCResponse:
        return self.send(JSONRPCRequest(method="tools/list", id=2))

    def send_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> JSONRPCResponse:
        return self.send(
            JSONRPCRequest(
                method="tools/call",
                params={"name": tool_name, "arguments": arguments},
                id=3,
            )
        )

    def send_resources_list(self) -> JSONRPCResponse:
        return self.send(JSONRPCRequest(method="resources/list", id=4))


class StdioTransport(MCPTransport):
    def __init__(self, command: list[str]) -> None:
        super().__init__()
        self._command = command
        self._process: subprocess.Popen[bytes] | None = None

    def connect(self) -> None:
        self.set_state(TransportState.CONNECTING)
        self._process = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.set_state(TransportState.CONNECTED)

    def disconnect(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.terminate()
            self._process.wait(timeout=5)
        self.set_state(TransportState.DISCONNECTED)

    def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
        if not self._process or self._process.poll() is not None:
            self.set_state(TransportState.ERROR)
            return JSONRPCResponse(
                error={"code": -32000, "message": "Transport not connected"},
                id=request.id,
            )
        stdin = self._process.stdin
        stdout = self._process.stdout
        if stdin is None or stdout is None:
            return JSONRPCResponse(
                error={"code": -32000, "message": "Stream not available"},
                id=request.id,
            )
        payload = (request.to_json() + "\n").encode("utf-8")
        stdin.write(payload)
        stdin.flush()
        raw_response = stdout.readline()
        return JSONRPCResponse.from_json(raw_response.decode("utf-8"))


class SSETransport(MCPTransport):
    def __init__(self, url: str) -> None:
        super().__init__()
        self._url = url
        self._session_id: str = ""

    def connect(self) -> None:
        self.set_state(TransportState.CONNECTING)
        self._session_id = f"sse-session-{id(self)}"
        self.set_state(TransportState.CONNECTED)

    def disconnect(self) -> None:
        self._session_id = ""
        self.set_state(TransportState.DISCONNECTED)

    def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
        if self._state != TransportState.CONNECTED:
            return JSONRPCResponse(
                error={"code": -32000, "message": "SSE transport not connected"},
                id=request.id,
            )
        return JSONRPCResponse(
            result={"status": "ok", "via": "sse", "session": self._session_id},
            id=request.id,
        )


class HTTPTransport(MCPTransport):
    def __init__(self, endpoint_url: str) -> None:
        super().__init__()
        self._endpoint_url = endpoint_url

    def connect(self) -> None:
        self.set_state(TransportState.CONNECTING)
        try:
            import httpx

            r = httpx.get(self._endpoint_url, timeout=5.0)
            if r.status_code < 400:
                self.set_state(TransportState.CONNECTED)
            else:
                self.set_state(TransportState.ERROR)
        except Exception:
            self.set_state(TransportState.ERROR)

    def disconnect(self) -> None:
        self.set_state(TransportState.DISCONNECTED)

    def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
        if self._state != TransportState.CONNECTED:
            return JSONRPCResponse(
                error={"code": -32000, "message": "HTTP transport not connected"},
                id=request.id,
            )
        try:
            import httpx

            r = httpx.post(
                self._endpoint_url,
                json={
                    "jsonrpc": request.jsonrpc,
                    "method": request.method,
                    "params": request.params,
                    "id": request.id,
                },
                timeout=10.0,
            )
            data = r.json()
            return JSONRPCResponse(
                jsonrpc=data.get("jsonrpc", MCP_JSONRPC_VERSION),
                result=data.get("result"),
                error=data.get("error"),
                id=data.get("id", 0),
            )
        except Exception as e:
            return JSONRPCResponse(
                error={"code": -32000, "message": str(e)},
                id=request.id,
            )


class InProcessTransport(MCPTransport):
    """In-process MCP transport — zero-latency communication within the same Python process.

    Claude Code's 6th transport type. Useful for:
    - Desktop agent ↔ internal MCP servers
    - Sub-Agent ↔ parent Agent communication
    - Testing without network overhead
    """

    def __init__(
        self, message_handler: Callable[[JSONRPCRequest], JSONRPCResponse] | None = None
    ) -> None:
        super().__init__()
        self._handler = message_handler or self._default_handler
        self._message_queue: list[JSONRPCRequest] = []
        self._response_queue: list[JSONRPCResponse] = []

    def connect(self) -> None:
        self.set_state(TransportState.CONNECTED)

    def disconnect(self) -> None:
        self.set_state(TransportState.DISCONNECTED)

    def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
        if self._state != TransportState.CONNECTED:
            return JSONRPCResponse(
                error={"code": -32000, "message": "InProcess transport not connected"},
                id=request.id,
            )
        self._message_queue.append(request)
        response = self._handler(request)
        self._response_queue.append(response)
        return response

    def send_async(self, request: JSONRPCRequest) -> None:
        if self._state == TransportState.CONNECTED:
            self._message_queue.append(request)

    def get_pending_requests(self) -> list[JSONRPCRequest]:
        return list(self._message_queue)

    def get_responses(self) -> list[JSONRPCResponse]:
        return list(self._response_queue)

    def clear(self) -> None:
        self._message_queue.clear()
        self._response_queue.clear()

    @staticmethod
    def _default_handler(request: JSONRPCRequest) -> JSONRPCResponse:
        return JSONRPCResponse(
            result={"status": "ok", "method": request.method, "via": "inprocess"},
            id=request.id,
        )
