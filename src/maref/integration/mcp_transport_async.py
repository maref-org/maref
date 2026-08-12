from __future__ import annotations

import asyncio
import json
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from maref.integration.mcp_transport import (
    MCP_JSONRPC_VERSION,
    JSONRPCRequest,
    JSONRPCResponse,
    TransportState,
)


class AsyncMCPTransport(ABC):
    """Abstract base class for async MCP transports."""

    def __init__(self) -> None:
        self._state: TransportState = TransportState.DISCONNECTED

    @property
    def state(self) -> TransportState:
        return self._state

    def set_state(self, state: TransportState) -> None:
        self._state = state

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def send(self, request: JSONRPCRequest) -> JSONRPCResponse: ...

    async def send_initialize(
        self, client_name: str = "maref"
    ) -> JSONRPCResponse:
        return await self.send(
            JSONRPCRequest(
                method="initialize",
                params={
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": client_name, "version": "0.9.0"},
                },
                id=1,
                trace_id=str(uuid.uuid4()),
                source_agent=client_name,
                timestamp=time.time(),
            )
        )

    async def send_tools_list(self) -> JSONRPCResponse:
        return await self.send(JSONRPCRequest(method="tools/list", id=2))

    async def send_tool_call(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> JSONRPCResponse:
        return await self.send(
            JSONRPCRequest(
                method="tools/call",
                params={"name": tool_name, "arguments": arguments},
                id=3,
                trace_id=str(uuid.uuid4()),
                source_agent="maref-client",
                timestamp=time.time(),
            )
        )

    async def send_resources_list(self) -> JSONRPCResponse:
        return await self.send(JSONRPCRequest(method="resources/list", id=4))


class AsyncSSETransport(AsyncMCPTransport):
    """Async SSE transport using httpx.AsyncClient.

    Follows the MCP Streamable HTTP specification:
    - Connects via GET to an SSE endpoint
    - Receives JSON-RPC messages as SSE events
    - Sends JSON-RPC requests via POST to a message endpoint
    - Uses asyncio for non-blocking I/O
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

        self._message_endpoint: str | None = None
        self._session_id: str = ""

        self._client: httpx.AsyncClient | None = None
        self._sse_task: asyncio.Task[None] | None = None
        self._running = asyncio.Event()
        self._endpoint_received = asyncio.Event()
        self._retry_count = 0
        self._base_url: str = ""

        self._pending: dict[int | str, asyncio.Future[JSONRPCResponse]] = {}
        self._event_callbacks: dict[str, list[Callable[[str], None]]] = {}

    async def connect(self) -> None:
        if self._state == TransportState.CONNECTED:
            return
        self.set_state(TransportState.CONNECTING)
        self._client = httpx.AsyncClient(timeout=self._timeout)
        self._base_url = self._sse_url
        self._running.set()
        self._retry_count = 0

        self._sse_task = asyncio.ensure_future(self._sse_reader())

        try:
            await asyncio.wait_for(
                self._endpoint_received.wait(), timeout=self._timeout
            )
        except asyncio.TimeoutError as exc:
            await self.disconnect()
            raise ConnectionError(
                f"SSE connection timeout to {self._sse_url} "
                f"— no endpoint event received"
            ) from exc

        self.set_state(TransportState.CONNECTED)

    async def disconnect(self) -> None:
        self._running.clear()
        self._endpoint_received.clear()

        if self._sse_task is not None:
            self._sse_task.cancel()
            try:
                await self._sse_task
            except (asyncio.CancelledError, Exception):
                pass
            self._sse_task = None

        if self._client is not None:
            await self._client.aclose()
            self._client = None

        self._message_endpoint = None
        self._session_id = ""
        self._retry_count = 0

        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

        self.set_state(TransportState.DISCONNECTED)

    async def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
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

        loop = asyncio.get_running_loop()
        future: asyncio.Future[JSONRPCResponse] = loop.create_future()
        self._pending[request.id] = future

        try:
            body: dict[str, Any] = {
                "jsonrpc": request.jsonrpc,
                "method": request.method,
                "id": request.id,
            }
            if request.params is not None:
                body["params"] = request.params

            r = await self._client.post(
                self._message_endpoint,
                json=body,
                timeout=self._timeout,
            )

            ct = r.headers.get("content-type", "")

            # Direct JSON response (non-streaming path)
            if r.is_success and "application/json" in ct:
                data = r.json()
                self._pending.pop(request.id, None)
                return JSONRPCResponse(
                    jsonrpc=data.get("jsonrpc", MCP_JSONRPC_VERSION),
                    result=data.get("result", {}),
                    error=data.get("error"),
                    id=data.get("id", request.id),
                )

            # Wait for SSE-delivered response
            try:
                resp = await asyncio.wait_for(future, timeout=self._timeout)
                self._pending.pop(request.id, None)
                return resp
            except asyncio.TimeoutError:
                self._pending.pop(request.id, None)
                return JSONRPCResponse(
                    error={
                        "code": -32000,
                        "message": "SSE response timeout — "
                        "no response event received",
                    },
                    id=request.id,
                )

        except httpx.TimeoutException:
            self._pending.pop(request.id, None)
            await self._handle_error()
            return JSONRPCResponse(
                error={"code": -32000, "message": "SSE request timeout"},
                id=request.id,
            )
        except httpx.ConnectError:
            self._pending.pop(request.id, None)
            await self._handle_error()
            return JSONRPCResponse(
                error={"code": -32000, "message": "SSE connection refused"},
                id=request.id,
            )
        except Exception as e:
            self._pending.pop(request.id, None)
            await self._handle_error()
            return JSONRPCResponse(
                error={"code": -32000, "message": f"SSE transport error: {e}"},
                id=request.id,
            )

    def on_event(self, event_type: str, callback: Callable[[str], None]) -> None:
        """Register a callback for a specific SSE event type."""
        if event_type not in self._event_callbacks:
            self._event_callbacks[event_type] = []
        self._event_callbacks[event_type].append(callback)

    async def reconnect(self) -> None:
        """Attempt to reconnect the SSE transport."""
        await self.disconnect()
        await self.connect()

    async def _sse_reader(self) -> None:
        """Background coroutine: connect to SSE endpoint and process events."""
        while self._running.is_set() and self._retry_count <= self._max_retries:
            try:
                if not self._client:
                    return

                async with self._client.stream("GET", self._sse_url) as response:
                    current_event: str = ""
                    current_data: list[str] = []

                    async for line in response.aiter_lines():
                        if not self._running.is_set():
                            return

                        if line == "":
                            if current_event and current_data:
                                self._process_event(
                                    current_event, "\n".join(current_data)
                                )
                            current_event = ""
                            current_data = []
                        elif line.startswith("event:"):
                            current_event = line[6:].strip()
                        elif line.startswith("data:"):
                            current_data.append(line[5:].strip())

                    if current_event and current_data:
                        self._process_event(
                            current_event, "\n".join(current_data)
                        )

                # Connection closed cleanly — reconnect if still running
                if self._running.is_set():
                    self._retry_count += 1

            except asyncio.CancelledError:
                return
            except httpx.RemoteProtocolError:
                if not self._running.is_set():
                    return
                self._retry_count += 1
            except httpx.ConnectError:
                if not self._running.is_set():
                    return
                self._retry_count += 1
                await asyncio.sleep(1)
            except httpx.StreamError:
                if not self._running.is_set():
                    return
                self._retry_count += 1
            except Exception:
                if not self._running.is_set():
                    return
                self._retry_count += 1

        if self._retry_count > self._max_retries:
            await self._handle_error()

    def _process_event(self, event_type: str, data: str) -> None:
        from urllib.parse import urljoin

        if event_type == "endpoint":
            base = self._base_url or self._sse_url
            self._message_endpoint = urljoin(base, data)
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
                future = self._pending.get(resp.id)
                if future is not None and not future.done():
                    future.set_result(resp)
            except json.JSONDecodeError:
                pass

        if event_type in self._event_callbacks:
            for cb in self._event_callbacks[event_type]:
                try:
                    cb(data)
                except Exception:
                    pass

    async def _handle_error(self) -> None:
        self.set_state(TransportState.ERROR)


class AsyncHTTPTransport(AsyncMCPTransport):
    """Async HTTP transport using httpx.AsyncClient for JSON-RPC over HTTP."""

    def __init__(
        self,
        endpoint_url: str,
        timeout: float = 10.0,
    ) -> None:
        super().__init__()
        self._endpoint_url = endpoint_url
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        self.set_state(TransportState.CONNECTING)
        self._client = httpx.AsyncClient(timeout=self._timeout)
        try:
            r = await self._client.get(self._endpoint_url, timeout=self._timeout)
            if r.status_code < 400:
                self.set_state(TransportState.CONNECTED)
            else:
                self.set_state(TransportState.ERROR)
        except Exception:
            await self._handle_error()

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self.set_state(TransportState.DISCONNECTED)

    async def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
        if self._state != TransportState.CONNECTED or not self._client:
            return JSONRPCResponse(
                error={"code": -32000, "message": "HTTP transport not connected"},
                id=request.id,
            )
        try:
            body: dict[str, Any] = {
                "jsonrpc": request.jsonrpc,
                "method": request.method,
                "id": request.id,
            }
            if request.params is not None:
                body["params"] = request.params

            r = await self._client.post(self._endpoint_url, json=body)
            data = r.json()
            return JSONRPCResponse(
                jsonrpc=data.get("jsonrpc", MCP_JSONRPC_VERSION),
                result=data.get("result"),
                error=data.get("error"),
                id=data.get("id", 0),
            )
        except httpx.TimeoutException:
            await self._handle_error()
            return JSONRPCResponse(
                error={"code": -32000, "message": "HTTP request timeout"},
                id=request.id,
            )
        except Exception as e:
            await self._handle_error()
            return JSONRPCResponse(
                error={"code": -32000, "message": str(e)},
                id=request.id,
            )

    async def _handle_error(self) -> None:
        self.set_state(TransportState.ERROR)


class AsyncInProcessTransport(AsyncMCPTransport):
    """Async in-process MCP transport — zero-latency within the same process.

    Messages are passed directly via callable instead of network I/O.
    Useful for testing and sub-agent communication.
    """

    def __init__(
        self,
        message_handler: Callable[
            [JSONRPCRequest], JSONRPCResponse | Awaitable[JSONRPCResponse]
        ]
        | None = None,
    ) -> None:
        super().__init__()
        self._handler = message_handler or self._default_handler
        self._message_queue: list[JSONRPCRequest] = []
        self._response_queue: list[JSONRPCResponse] = []

    async def connect(self) -> None:
        self.set_state(TransportState.CONNECTED)

    async def disconnect(self) -> None:
        self.set_state(TransportState.DISCONNECTED)

    async def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
        if self._state != TransportState.CONNECTED:
            return JSONRPCResponse(
                error={
                    "code": -32000,
                    "message": "AsyncInProcess transport not connected",
                },
                id=request.id,
            )
        self._message_queue.append(request)
        result = self._handler(request)
        if isinstance(result, Awaitable):
            result = await result
        self._response_queue.append(result)
        return result

    def get_pending_requests(self) -> list[JSONRPCRequest]:
        return list(self._message_queue)

    def get_responses(self) -> list[JSONRPCResponse]:
        return list(self._response_queue)

    def clear(self) -> None:
        self._message_queue.clear()
        self._response_queue.clear()

    @staticmethod
    def _default_handler(request: JSONRPCRequest) -> JSONRPCResponse:
        result: dict[str, Any] = {"status": "ok", "method": request.method, "via": "async-inprocess"}
        if request.params is not None:
            result["params"] = request.params
        return JSONRPCResponse(
            result=result,
            id=request.id,
        )
