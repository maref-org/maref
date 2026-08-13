from __future__ import annotations

import json
import subprocess
import threading
import time as _time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.parse import urljoin

import httpx

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
    """Real SSE transport using httpx for client-side SSE streaming.

    Follows the MCP Streamable HTTP specification:
    - Client connects via GET to an SSE endpoint
    - Receives JSON-RPC messages as SSE events
    - Sends JSON-RPC requests via POST to a message endpoint
    """

    def __init__(
        self,
        url: str,
        max_retries: int = 3,
        timeout: float = 30.0,
    ) -> None:
        super().__init__()
        self._sse_url = url
        self._max_retries = max_retries
        self._timeout = timeout
        self._base_url = url

        self._message_endpoint: str | None = None
        self._session_id: str = ""

        self._client: httpx.Client | None = None
        self._sse_thread: threading.Thread | None = None
        self._running = threading.Event()
        self._endpoint_received = threading.Event()
        self._retry_count = 0

        self._responses: dict[int | str, JSONRPCResponse] = {}
        self._response_events: dict[int | str, threading.Event] = {}
        self._lock = threading.Lock()
        self._event_callbacks: dict[str, list[Callable[[str], None]]] = {}

    def connect(self) -> None:
        if self._state == TransportState.CONNECTED:
            return
        self.set_state(TransportState.CONNECTING)
        self._client = httpx.Client(timeout=self._timeout)
        self._running.set()
        self._retry_count = 0

        self._sse_thread = threading.Thread(
            target=self._sse_reader, daemon=True, name="maref-sse-reader"
        )
        self._sse_thread.start()

        if not self._endpoint_received.wait(timeout=self._timeout):
            self.disconnect()
            raise ConnectionError(
                f"SSE connection timeout to {self._sse_url} — no endpoint event received"
            )
        self.set_state(TransportState.CONNECTED)

    def disconnect(self) -> None:
        self._running.clear()
        self._endpoint_received.clear()

        if self._client:
            self._client.close()
        if self._sse_thread:
            self._sse_thread.join(timeout=5)
        self._sse_thread = None
        self._client = None

        self._message_endpoint = None
        self._session_id = ""
        self._retry_count = 0

        with self._lock:
            self._responses.clear()
            for evt in self._response_events.values():
                evt.set()
            self._response_events.clear()

        self.set_state(TransportState.DISCONNECTED)

    def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
        if self._state != TransportState.CONNECTED or not self._message_endpoint:
            return JSONRPCResponse(
                error={"code": -32000, "message": "SSE transport not connected"},
                id=request.id,
            )
        if not self._client:
            return JSONRPCResponse(
                error={"code": -32000, "message": "SSE client not available"},
                id=request.id,
            )

        try:
            response_event = threading.Event()
            with self._lock:
                self._response_events[request.id] = response_event

            body: dict[str, Any] = {
                "jsonrpc": request.jsonrpc,
                "method": request.method,
                "id": request.id,
            }
            if request.params is not None:
                body["params"] = request.params

            r = self._client.post(
                self._message_endpoint,
                json=body,
                timeout=self._timeout,
            )

            ct = r.headers.get("content-type", "")

            # Direct JSON response (non-streaming path)
            if r.is_success and "application/json" in ct:
                data = r.json()
                json_resp = JSONRPCResponse(
                    jsonrpc=data.get("jsonrpc", MCP_JSONRPC_VERSION),
                    result=data.get("result", {}),
                    error=data.get("error"),
                    id=data.get("id", request.id),
                )
                with self._lock:
                    self._response_events.pop(request.id, None)
                return json_resp

            # Wait for SSE-delivered response
            if response_event.wait(timeout=self._timeout):
                with self._lock:
                    resp = self._responses.get(request.id)
                    if resp is not None:
                        self._responses.pop(request.id)
                    self._response_events.pop(request.id, None)
                    if resp is not None:
                        return resp

            return JSONRPCResponse(
                error={
                    "code": -32000,
                    "message": "SSE response timeout — no response event received",
                },
                id=request.id,
            )

        except httpx.TimeoutException:
            self._handle_error()
            return JSONRPCResponse(
                error={"code": -32000, "message": "SSE request timeout"},
                id=request.id,
            )
        except httpx.ConnectError:
            self._handle_error()
            return JSONRPCResponse(
                error={"code": -32000, "message": "SSE connection refused"},
                id=request.id,
            )
        except Exception as e:
            self._handle_error()
            return JSONRPCResponse(
                error={"code": -32000, "message": f"SSE transport error: {e}"},
                id=request.id,
            )

    def on_event(self, event_type: str, callback: Callable[[str], None]) -> None:
        """Register a callback for a specific SSE event type."""
        if event_type not in self._event_callbacks:
            self._event_callbacks[event_type] = []
        self._event_callbacks[event_type].append(callback)

    def _sse_reader(self) -> None:
        """Background thread: connect to SSE endpoint and process events."""
        while self._running.is_set() and self._retry_count <= self._max_retries:
            try:
                if not self._client:
                    return

                with self._client.stream("GET", self._sse_url) as response:
                    current_event: str = ""
                    current_data: list[str] = []

                    for line in response.iter_lines():
                        if not self._running.is_set():
                            return

                        if line == "":
                            if current_event and current_data:
                                self._process_event(current_event, "\n".join(current_data))
                            current_event = ""
                            current_data = []
                        elif line.startswith("event:"):
                            current_event = line[6:].strip()
                        elif line.startswith("data:"):
                            current_data.append(line[5:].strip())

                    if current_event and current_data:
                        self._process_event(current_event, "\n".join(current_data))

                # Connection closed cleanly — reconnect if still running
                if self._running.is_set():
                    self._retry_count += 1

            except httpx.RemoteProtocolError:
                if not self._running.is_set():
                    return
                self._retry_count += 1
            except httpx.ConnectError:
                if not self._running.is_set():
                    return
                self._retry_count += 1
                _time.sleep(1)
            except httpx.StreamError:
                if not self._running.is_set():
                    return
                self._retry_count += 1
            except Exception:
                if not self._running.is_set():
                    return
                self._retry_count += 1

        if self._retry_count > self._max_retries:
            self._handle_error()

    def _process_event(self, event_type: str, data: str) -> None:
        """Dispatch a single SSE event."""
        if event_type == "endpoint":
            self._message_endpoint = urljoin(self._base_url, data)
            self._endpoint_received.set()
        elif event_type == "session_id":
            self._session_id = data
        elif event_type == "message":
            try:
                msg = json.loads(data)
                resp = JSONRPCResponse(
                    jsonrpc=msg.get("jsonrpc", MCP_JSONRPC_VERSION),
                    result=msg.get("result"),
                    error=msg.get("error"),
                    id=msg.get("id", 0),
                )
                with self._lock:
                    rid = resp.id
                    self._responses[rid] = resp
                    if rid in self._response_events:
                        self._response_events[rid].set()
            except json.JSONDecodeError:
                pass

        if event_type in self._event_callbacks:
            for cb in self._event_callbacks[event_type]:
                try:
                    cb(data)
                except Exception:
                    pass

    def _handle_error(self) -> None:
        self.set_state(TransportState.ERROR)


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
