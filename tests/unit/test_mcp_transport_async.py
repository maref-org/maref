from __future__ import annotations

import asyncio
import json

import pytest

from maref.integration.mcp_transport import (
    JSONRPCRequest,
    JSONRPCResponse,
    TransportState,
)
from maref.integration.mcp_transport_async import (
    AsyncHTTPTransport,
    AsyncInProcessTransport,
    AsyncMCPTransport,
    AsyncSSETransport,
)


class TestAsyncMCPTransport:
    """Tests for AsyncMCPTransport abstract base."""

    def test_default_state(self) -> None:
        class MinimalTransport(AsyncMCPTransport):
            async def connect(self) -> None: ...
            async def disconnect(self) -> None: ...
            async def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
                return JSONRPCResponse(id=request.id)

        t = MinimalTransport()
        assert t.state == TransportState.DISCONNECTED

    def test_set_state(self) -> None:
        class MinimalTransport(AsyncMCPTransport):
            async def connect(self) -> None: ...
            async def disconnect(self) -> None: ...
            async def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
                return JSONRPCResponse(id=request.id)

        t = MinimalTransport()
        t.set_state(TransportState.CONNECTED)
        assert t.state == TransportState.CONNECTED
        t.set_state(TransportState.ERROR)
        assert t.state == TransportState.ERROR


class TestAsyncSSETransport:
    """Tests for AsyncSSETransport using mock SSE server."""

    @pytest.mark.asyncio
    async def test_default_state(self) -> None:
        transport = AsyncSSETransport("http://localhost:0/sse")
        assert transport.state == TransportState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_connect_refused(self) -> None:
        transport = AsyncSSETransport(
            "http://localhost:1/sse", max_retries=0, timeout=1.0
        )
        with pytest.raises(ConnectionError):
            await transport.connect()
        assert transport.state in (TransportState.DISCONNECTED, TransportState.ERROR)

    @pytest.mark.asyncio
    async def test_send_while_disconnected(self) -> None:
        transport = AsyncSSETransport("http://localhost:0/sse")
        resp = await transport.send(JSONRPCRequest(method="test", id=1))
        assert resp.is_error
        assert "not connected" in (resp.error or {}).get("message", "").lower()

    @pytest.mark.asyncio
    async def test_state_transitions(self) -> None:
        transport = AsyncSSETransport("http://localhost:0/sse")
        assert transport.state == TransportState.DISCONNECTED
        transport.set_state(TransportState.CONNECTING)
        assert transport.state == TransportState.CONNECTING
        transport.set_state(TransportState.CONNECTED)
        assert transport.state == TransportState.CONNECTED
        transport.set_state(TransportState.ERROR)
        assert transport.state == TransportState.ERROR
        transport.set_state(TransportState.DISCONNECTED)
        assert transport.state == TransportState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_on_event_callback(self) -> None:
        transport = AsyncSSETransport("http://localhost:0/sse")
        received: list[str] = []

        transport.on_event("test_event", lambda d: received.append(d))
        transport._process_event("test_event", '{"hello": "world"}')
        assert len(received) == 1
        assert received[0] == '{"hello": "world"}'

    @pytest.mark.asyncio
    async def test_process_endpoint_event(self) -> None:
        transport = AsyncSSETransport("http://localhost:8080/sse")
        transport._process_event("endpoint", "/messages")
        assert transport._message_endpoint == "http://localhost:8080/messages"

    @pytest.mark.asyncio
    async def test_process_session_id_event(self) -> None:
        transport = AsyncSSETransport("http://localhost:8080/sse")
        transport._process_event("session_id", "sess-123")
        assert transport._session_id == "sess-123"

    @pytest.mark.asyncio
    async def test_process_message_event_resolves_pending(self) -> None:
        transport = AsyncSSETransport("http://localhost:8080/sse")

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        transport._pending[42] = future

        msg_data = json.dumps(
            {"jsonrpc": "2.0", "result": {"value": 99}, "id": 42}
        )
        transport._process_event("message", msg_data)

        assert future.done()
        resp = future.result()
        assert resp.id == 42
        assert resp.result == {"value": 99}
        assert not resp.is_error


class TestAsyncHTTPTransport:
    """Tests for AsyncHTTPTransport."""

    @pytest.mark.asyncio
    async def test_default_state(self) -> None:
        transport = AsyncHTTPTransport("http://localhost:0/api")
        assert transport.state == TransportState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_connect_refused(self) -> None:
        transport = AsyncHTTPTransport("http://localhost:1/api", timeout=1.0)
        await transport.connect()
        assert transport.state == TransportState.ERROR

    @pytest.mark.asyncio
    async def test_send_while_disconnected(self) -> None:
        transport = AsyncHTTPTransport("http://localhost:0/api")
        resp = await transport.send(JSONRPCRequest(method="test", id=1))
        assert resp.is_error
        assert "not connected" in (resp.error or {}).get("message", "").lower()

    @pytest.mark.asyncio
    async def test_disconnect_sets_state(self) -> None:
        transport = AsyncHTTPTransport("http://localhost:0/api")
        transport.set_state(TransportState.CONNECTED)
        await transport.disconnect()
        assert transport.state == TransportState.DISCONNECTED


class TestAsyncInProcessTransport:
    """Tests for AsyncInProcessTransport."""

    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self) -> None:
        transport = AsyncInProcessTransport()
        assert transport.state == TransportState.DISCONNECTED
        await transport.connect()
        assert transport.state == TransportState.CONNECTED
        await transport.disconnect()
        assert transport.state == TransportState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_send_while_connected(self) -> None:
        transport = AsyncInProcessTransport()
        await transport.connect()
        resp = await transport.send(JSONRPCRequest(method="ping", id=1))
        assert not resp.is_error
        assert resp.result["method"] == "ping"

    @pytest.mark.asyncio
    async def test_send_while_disconnected(self) -> None:
        transport = AsyncInProcessTransport()
        resp = await transport.send(JSONRPCRequest(method="ping", id=1))
        assert resp.is_error

    @pytest.mark.asyncio
    async def test_custom_handler(self) -> None:
        def handler(req: JSONRPCRequest) -> JSONRPCResponse:
            return JSONRPCResponse(
                result={"custom": True, "original_method": req.method}, id=req.id
            )

        transport = AsyncInProcessTransport(message_handler=handler)
        await transport.connect()
        resp = await transport.send(JSONRPCRequest(method="custom", id=99))
        assert resp.result["custom"] is True
        assert resp.result["original_method"] == "custom"
        assert resp.id == 99

    @pytest.mark.asyncio
    async def test_async_handler(self) -> None:
        async def async_handler(req: JSONRPCRequest) -> JSONRPCResponse:
            return JSONRPCResponse(result={"async": True}, id=req.id)

        transport = AsyncInProcessTransport(message_handler=async_handler)
        await transport.connect()
        resp = await transport.send(JSONRPCRequest(method="async", id=7))
        assert resp.result["async"] is True
        assert resp.id == 7

    @pytest.mark.asyncio
    async def test_message_queue(self) -> None:
        transport = AsyncInProcessTransport()
        await transport.connect()
        await transport.send(JSONRPCRequest(method="a", id=1))
        await transport.send(JSONRPCRequest(method="b", id=2))
        pending = transport.get_pending_requests()
        assert len(pending) == 2
        assert pending[0].method == "a"
        assert pending[1].method == "b"

    @pytest.mark.asyncio
    async def test_response_queue(self) -> None:
        transport = AsyncInProcessTransport()
        await transport.connect()
        await transport.send(JSONRPCRequest(method="x", id=10))
        await transport.send(JSONRPCRequest(method="y", id=20))
        responses = transport.get_responses()
        assert len(responses) == 2
        assert responses[0].id == 10
        assert responses[1].id == 20

    @pytest.mark.asyncio
    async def test_clear(self) -> None:
        transport = AsyncInProcessTransport()
        await transport.connect()
        await transport.send(JSONRPCRequest(method="a", id=1))
        transport.clear()
        assert len(transport.get_pending_requests()) == 0
        assert len(transport.get_responses()) == 0

    @pytest.mark.asyncio
    async def test_convenience_methods(self) -> None:
        transport = AsyncInProcessTransport()
        await transport.connect()

        resp = await transport.send_initialize()
        assert resp.result["method"] == "initialize"

        resp = await transport.send_tools_list()
        assert resp.result["method"] == "tools/list"

        resp = await transport.send_tool_call("search", {"q": "test"})
        assert resp.result["params"]["name"] == "search"

        resp = await transport.send_resources_list()
        assert resp.result["method"] == "resources/list"


class TestAsyncTransportStateTransitions:
    """State transition tests across all async transports."""

    @pytest.mark.asyncio
    async def test_diagram_all_transports(self) -> None:
        transports: list[AsyncMCPTransport] = [
            AsyncSSETransport("http://localhost:0/sse"),
            AsyncHTTPTransport("http://localhost:0/api"),
            AsyncInProcessTransport(),
        ]
        for t in transports:
            assert t.state == TransportState.DISCONNECTED
            t.set_state(TransportState.CONNECTING)
            assert t.state == TransportState.CONNECTING
            t.set_state(TransportState.CONNECTED)
            assert t.state == TransportState.CONNECTED
            t.set_state(TransportState.ERROR)
            assert t.state == TransportState.ERROR
            t.set_state(TransportState.DISCONNECTED)
            assert t.state == TransportState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_error_state_persists(self) -> None:
        transport = AsyncInProcessTransport()
        transport.set_state(TransportState.ERROR)
        assert transport.state == TransportState.ERROR
        resp = await transport.send(JSONRPCRequest(method="test", id=1))
        assert resp.is_error
