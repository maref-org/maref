from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from maref.integration.mcp_transport_async import (
    AsyncHTTPTransport,
    AsyncInProcessTransport,
    AsyncMCPTransport,
    AsyncSSETransport,
)


class TestAsyncMCPTransport:
    def test_abstract_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            AsyncMCPTransport()  # type: ignore[abstract]

    def test_concrete_subclass(self) -> None:
        class ConcreteTransport(AsyncMCPTransport):
            async def connect(self) -> None: ...
            async def disconnect(self) -> None: ...
            async def send(self, request: object) -> object:
                return type("resp", (), {})()  # dummy

        t = ConcreteTransport()
        assert t.state.value == "disconnected"
        t.set_state(type("st", (), {"value": "connected"})())  # mock state
        assert t.state is not None


class TestAsyncSSETransport:
    def test_init(self) -> None:
        transport = AsyncSSETransport(url="http://localhost:8080/sse")
        assert transport.state.value == "disconnected"
        assert transport._sse_url == "http://localhost:8080/sse"
        assert transport._max_retries == 3
        assert transport._timeout == 30.0

    def test_init_custom(self) -> None:
        transport = AsyncSSETransport(
            url="http://example.com/sse", max_retries=5, timeout=60.0
        )
        assert transport._max_retries == 5
        assert transport._timeout == 60.0


class TestAsyncHTTPTransport:
    def test_init(self) -> None:
        transport = AsyncHTTPTransport(endpoint_url="http://localhost:8080/mcp")
        assert transport.state.value == "disconnected"
        assert transport._endpoint_url == "http://localhost:8080/mcp"
        assert transport._timeout == 10.0

    def test_init_custom(self) -> None:
        transport = AsyncHTTPTransport(endpoint_url="http://example.com", timeout=15.0)
        assert transport._timeout == 15.0


class TestAsyncInProcessTransport:
    def test_init(self) -> None:
        transport = AsyncInProcessTransport()
        assert transport.state.value == "disconnected"
        assert transport.get_pending_requests() == []
        assert transport.get_responses() == []

    def test_init_with_handler(self) -> None:
        async def handler(_: object) -> object:
            return {}

        transport = AsyncInProcessTransport(message_handler=handler)
        assert transport._handler is handler

    @pytest.mark.asyncio
    async def test_connect_disconnect(self) -> None:
        transport = AsyncInProcessTransport()
        await transport.connect()
        assert transport.state.value == "connected"
        await transport.disconnect()
        assert transport.state.value == "disconnected"

    @pytest.mark.asyncio
    async def test_send_with_handler(self) -> None:
        async def handler(req: object) -> dict:
            return {"result": "ok"}

        transport = AsyncInProcessTransport(message_handler=handler)
        await transport.connect()

        request = type("Req", (), {
            "method": "ping",
            "params": {},
            "id": 1,
        })()
        response = await transport.send(request)
        # handler should have been called
        assert response is not None

    @pytest.mark.asyncio
    async def test_send_without_handler_returns_default(self) -> None:
        transport = AsyncInProcessTransport()
        await transport.connect()

        request = type("Req", (), {
            "method": "ping",
            "params": {},
            "id": 1,
        })()
        response = await transport.send(request)
        assert response is not None

    @pytest.mark.asyncio
    async def test_send_initialize(self) -> None:
        async def handler(req: object) -> dict:
            return {"jsonrpc": "2.0", "result": {"serverInfo": {"name": "test"}}, "id": 1}

        transport = AsyncInProcessTransport(message_handler=handler)
        await transport.connect()
        response = await transport.send_initialize(client_name="test-agent")
        assert response is not None

    @pytest.mark.asyncio
    async def test_send_tools_list(self) -> None:
        async def handler(req: object) -> dict:
            return {"jsonrpc": "2.0", "result": {"tools": []}, "id": 2}

        transport = AsyncInProcessTransport(message_handler=handler)
        await transport.connect()
        response = await transport.send_tools_list()
        assert response is not None

    @pytest.mark.asyncio
    async def test_send_tool_call(self) -> None:
        async def handler(req: object) -> dict:
            return {"jsonrpc": "2.0", "result": {"content": []}, "id": 3}

        transport = AsyncInProcessTransport(message_handler=handler)
        await transport.connect()
        response = await transport.send_tool_call("test_tool", {})
        assert response is not None

    @pytest.mark.asyncio
    async def test_send_resources_list(self) -> None:
        async def handler(req: object) -> dict:
            return {"jsonrpc": "2.0", "result": {"resources": []}, "id": 4}

        transport = AsyncInProcessTransport(message_handler=handler)
        await transport.connect()
        response = await transport.send_resources_list()
        assert response is not None
