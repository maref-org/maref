from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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
    """Tests for the abstract AsyncMCPTransport convenience methods."""

    async def test_concrete_instantiation_fails(self):
        with pytest.raises(TypeError):
            AsyncMCPTransport()

    async def test_state_defaults_to_disconnected(self):
        transport = AsyncInProcessTransport()
        assert transport.state == TransportState.DISCONNECTED

    async def test_set_state_updates_state(self):
        transport = AsyncInProcessTransport()
        transport.set_state(TransportState.CONNECTED)
        assert transport.state == TransportState.CONNECTED

    async def test_send_initialize(self):
        transport = AsyncInProcessTransport()
        await transport.connect()
        resp = await transport.send_initialize("test-client")

        assert resp.result == {
            "status": "ok",
            "method": "initialize",
            "via": "async-inprocess",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "test-client", "version": "0.9.0"},
            },
        }
        assert resp.id == 1
        assert resp.error is None

        requests = transport.get_pending_requests()
        assert len(requests) == 1
        assert requests[0].method == "initialize"
        assert requests[0].id == 1

    async def test_send_initialize_default_client_name(self):
        transport = AsyncInProcessTransport()
        await transport.connect()
        resp = await transport.send_initialize()

        assert resp.result["params"]["clientInfo"]["name"] == "maref"
        assert resp.id == 1

    async def test_send_tools_list(self):
        transport = AsyncInProcessTransport()
        await transport.connect()
        resp = await transport.send_tools_list()

        assert resp.result == {
            "status": "ok",
            "method": "tools/list",
            "via": "async-inprocess",
        }
        assert resp.id == 2

        requests = transport.get_pending_requests()
        assert requests[0].method == "tools/list"
        assert requests[0].id == 2

    async def test_send_tool_call(self):
        transport = AsyncInProcessTransport()
        await transport.connect()
        resp = await transport.send_tool_call("test_tool", {"arg1": "value1", "arg2": 42})

        assert resp.result["status"] == "ok"
        assert resp.result["method"] == "tools/call"
        assert resp.result["via"] == "async-inprocess"
        resp_params = resp.result["params"]
        assert resp_params["name"] == "test_tool"
        assert resp_params["arguments"] == {"arg1": "value1", "arg2": 42}
        assert resp.id == 3

        requests = transport.get_pending_requests()
        assert requests[0].method == "tools/call"
        assert requests[0].id == 3
        req_params = requests[0].params
        assert req_params["name"] == "test_tool"
        assert req_params["arguments"] == {"arg1": "value1", "arg2": 42}
        # 宪法第十五-A条: 工具调用请求需带 MCP 消息信封
        assert req_params["trace_id"]
        assert req_params["source_agent"]
        assert req_params["timestamp"]

    async def test_send_resources_list(self):
        transport = AsyncInProcessTransport()
        await transport.connect()
        resp = await transport.send_resources_list()

        assert resp.result == {
            "status": "ok",
            "method": "resources/list",
            "via": "async-inprocess",
        }
        assert resp.id == 4

        requests = transport.get_pending_requests()
        assert requests[0].method == "resources/list"
        assert requests[0].id == 4


class TestAsyncInProcessTransport:
    """Tests for AsyncInProcessTransport."""

    async def test_connect_sets_state_to_connected(self):
        transport = AsyncInProcessTransport()
        assert transport.state == TransportState.DISCONNECTED
        await transport.connect()
        assert transport.state == TransportState.CONNECTED

    async def test_disconnect_sets_state_to_disconnected(self):
        transport = AsyncInProcessTransport()
        await transport.connect()
        await transport.disconnect()
        assert transport.state == TransportState.DISCONNECTED

    async def test_send_returns_response_from_handler(self):
        transport = AsyncInProcessTransport()
        await transport.connect()
        resp = await transport.send(JSONRPCRequest(method="ping", id=1))
        assert resp.result == {
            "status": "ok",
            "method": "ping",
            "via": "async-inprocess",
        }
        assert resp.id == 1
        assert resp.error is None

    async def test_send_appends_to_message_and_response_queues(self):
        transport = AsyncInProcessTransport()
        await transport.connect()
        await transport.send(JSONRPCRequest(method="foo", id=1))
        await transport.send(JSONRPCRequest(method="bar", id=2))

        assert len(transport.get_pending_requests()) == 2
        assert len(transport.get_responses()) == 2
        assert transport.get_pending_requests()[0].method == "foo"
        assert transport.get_pending_requests()[1].method == "bar"

    async def test_send_returns_error_when_disconnected(self):
        transport = AsyncInProcessTransport()
        resp = await transport.send(JSONRPCRequest(method="ping", id=1))
        assert resp.error == {
            "code": -32000,
            "message": "AsyncInProcess transport not connected",
        }
        assert resp.id == 1

    async def test_clear_empties_queues(self):
        transport = AsyncInProcessTransport()
        await transport.connect()
        await transport.send(JSONRPCRequest(method="foo", id=1))
        assert len(transport.get_pending_requests()) == 1
        assert len(transport.get_responses()) == 1

        transport.clear()
        assert len(transport.get_pending_requests()) == 0
        assert len(transport.get_responses()) == 0

    async def test_custom_sync_handler(self):
        def handler(request: JSONRPCRequest) -> JSONRPCResponse:
            return JSONRPCResponse(result={"custom": True, "method": request.method}, id=request.id)

        transport = AsyncInProcessTransport(message_handler=handler)
        await transport.connect()
        resp = await transport.send(JSONRPCRequest(method="custom", id=5))
        assert resp.result == {"custom": True, "method": "custom"}
        assert resp.id == 5

    async def test_custom_async_handler(self):
        async def handler(request: JSONRPCRequest) -> JSONRPCResponse:
            await asyncio.sleep(0.01)
            return JSONRPCResponse(result={"async": True, "method": request.method}, id=request.id)

        transport = AsyncInProcessTransport(message_handler=handler)
        await transport.connect()
        resp = await transport.send(JSONRPCRequest(method="async-handler", id=7))
        assert resp.result == {"async": True, "method": "async-handler"}
        assert resp.id == 7

    async def test_handler_awaited_when_awaitable(self):
        future_resp = JSONRPCResponse(result={"from": "awaitable"}, id=10)
        mock_handler = MagicMock()
        mock_handler.return_value = asyncio.Future()
        mock_handler.return_value.set_result(future_resp)
        assert isinstance(mock_handler(JSONRPCRequest(method="test", id=10)), asyncio.Future)

        transport = AsyncInProcessTransport(message_handler=mock_handler)
        await transport.connect()
        resp = await transport.send(JSONRPCRequest(method="test", id=10))
        assert resp.result == {"from": "awaitable"}

    async def test_default_handler_returns_ok_with_params(self):
        transport = AsyncInProcessTransport()
        await transport.connect()
        req = JSONRPCRequest(
            method="test",
            params={"key": "value"},
            id=42,
        )
        resp = await transport.send(req)
        assert resp.result["status"] == "ok"
        assert resp.result["method"] == "test"
        assert resp.result["params"] == {"key": "value"}

    async def test_get_pending_requests_returns_copy(self):
        transport = AsyncInProcessTransport()
        await transport.connect()
        await transport.send(JSONRPCRequest(method="foo", id=1))
        requests = transport.get_pending_requests()
        requests.append(JSONRPCRequest(method="bar", id=2))
        assert len(transport.get_pending_requests()) == 1

    async def test_get_responses_returns_copy(self):
        transport = AsyncInProcessTransport()
        await transport.connect()
        await transport.send(JSONRPCRequest(method="foo", id=1))
        responses = transport.get_responses()
        responses.append(JSONRPCResponse(result={"extra": True}, id=99))
        assert len(transport.get_responses()) == 1

    async def test_send_after_disconnect_returns_error(self):
        transport = AsyncInProcessTransport()
        await transport.connect()
        await transport.disconnect()
        resp = await transport.send(JSONRPCRequest(method="fail", id=1))
        assert resp.is_error
        assert resp.error["code"] == -32000


class TestAsyncHTTPTransport:
    """Tests for AsyncHTTPTransport."""

    @pytest.fixture
    def mock_async_client(self):
        RealAsyncClient = httpx.AsyncClient
        with patch("maref.integration.mcp_transport_async.httpx.AsyncClient") as m:
            instance = AsyncMock(spec=RealAsyncClient)
            m.return_value = instance
            yield instance

    async def test_connect_success_sets_connected(self, mock_async_client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_async_client.get.return_value = mock_response

        transport = AsyncHTTPTransport("http://localhost:8080/api")
        await transport.connect()

        assert transport.state == TransportState.CONNECTED

    async def test_connect_http_error_sets_error(self, mock_async_client):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_async_client.get.return_value = mock_response

        transport = AsyncHTTPTransport("http://localhost:8080/api")
        await transport.connect()

        assert transport.state == TransportState.ERROR

    async def test_connect_exception_sets_error(self, mock_async_client):
        mock_async_client.get.side_effect = httpx.ConnectError("Connection refused")

        transport = AsyncHTTPTransport("http://localhost:8080/api")
        await transport.connect()

        assert transport.state == TransportState.ERROR

    async def test_disconnect_closes_client_and_sets_disconnected(self):
        transport = AsyncHTTPTransport("http://localhost:8080/api")
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        transport._client = mock_client
        transport._state = TransportState.CONNECTED

        await transport.disconnect()

        mock_client.aclose.assert_awaited_once()
        assert transport._client is None
        assert transport.state == TransportState.DISCONNECTED

    async def test_disconnect_without_client(self):
        transport = AsyncHTTPTransport("http://localhost:8080/api")
        transport._state = TransportState.CONNECTED
        await transport.disconnect()
        assert transport.state == TransportState.DISCONNECTED

    async def test_send_success(self):
        transport = AsyncHTTPTransport("http://localhost:8080/api")
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "result": {"status": "ok"},
            "id": 1,
        }
        mock_client.post.return_value = mock_response
        transport._client = mock_client
        transport._state = TransportState.CONNECTED

        resp = await transport.send(JSONRPCRequest(method="ping", id=1))

        assert resp.result == {"status": "ok"}
        assert resp.id == 1
        assert resp.error is None
        mock_client.post.assert_awaited_once_with(
            "http://localhost:8080/api",
            json={"jsonrpc": "2.0", "method": "ping", "id": 1},
        )

    async def test_send_with_params(self):
        transport = AsyncHTTPTransport("http://localhost:8080/api")
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "result": {"status": "ok"},
            "id": 2,
        }
        mock_client.post.return_value = mock_response
        transport._client = mock_client
        transport._state = TransportState.CONNECTED

        req = JSONRPCRequest(
            method="tools/call",
            params={"name": "foo", "arguments": {"x": 1}},
            id=2,
        )
        resp = await transport.send(req)

        assert resp.result == {"status": "ok"}
        mock_client.post.assert_awaited_once_with(
            "http://localhost:8080/api",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "foo", "arguments": {"x": 1}},
                "id": 2,
            },
        )

    async def test_send_not_connected_returns_error(self):
        transport = AsyncHTTPTransport("http://localhost:8080/api")
        transport._state = TransportState.DISCONNECTED

        resp = await transport.send(JSONRPCRequest(method="ping", id=1))

        assert resp.is_error
        assert resp.error["code"] == -32000
        assert resp.error["message"] == "HTTP transport not connected"

    async def test_send_no_client_returns_error(self):
        transport = AsyncHTTPTransport("http://localhost:8080/api")
        transport._state = TransportState.CONNECTED
        transport._client = None

        resp = await transport.send(JSONRPCRequest(method="ping", id=1))

        assert resp.is_error
        assert resp.error["code"] == -32000

    async def test_send_timeout_returns_error_and_sets_error_state(self):
        transport = AsyncHTTPTransport("http://localhost:8080/api")
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.TimeoutException(
            "Request timed out", request=MagicMock()
        )
        transport._client = mock_client
        transport._state = TransportState.CONNECTED

        resp = await transport.send(JSONRPCRequest(method="ping", id=1))

        assert resp.is_error
        assert resp.error["code"] == -32000
        assert resp.error["message"] == "HTTP request timeout"
        assert transport.state == TransportState.ERROR

    async def test_send_exception_returns_error_and_sets_error_state(self):
        transport = AsyncHTTPTransport("http://localhost:8080/api")
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = RuntimeError("Something went wrong")
        transport._client = mock_client
        transport._state = TransportState.CONNECTED

        resp = await transport.send(JSONRPCRequest(method="ping", id=1))

        assert resp.is_error
        assert resp.error["code"] == -32000
        assert resp.error["message"] == "Something went wrong"
        assert transport.state == TransportState.ERROR

    async def test_send_connect_error_sets_error_state(self):
        transport = AsyncHTTPTransport("http://localhost:8080/api")
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        transport._client = mock_client
        transport._state = TransportState.CONNECTED

        resp = await transport.send(JSONRPCRequest(method="ping", id=1))

        assert resp.is_error
        assert resp.error["code"] == -32000
        assert transport.state == TransportState.ERROR


class TestAsyncSSETransport:
    """Tests for AsyncSSETransport."""

    @pytest.fixture
    def transport(self):
        return AsyncSSETransport("http://localhost:8080/sse")

    async def test_initial_state(self, transport):
        assert transport.state == TransportState.DISCONNECTED
        assert transport._message_endpoint is None
        assert transport._session_id == ""

    async def test_get_state(self, transport):
        assert transport.state == TransportState.DISCONNECTED
        transport.set_state(TransportState.CONNECTING)
        assert transport.state == TransportState.CONNECTING
        transport.set_state(TransportState.CONNECTED)
        assert transport.state == TransportState.CONNECTED

    async def test_connect_sets_correct_state(self, transport):
        async def fake_sse_reader():
            transport._process_event("endpoint", "http://localhost:8080/messages")

        transport._sse_reader = fake_sse_reader
        await transport.connect()

        assert transport.state == TransportState.CONNECTED
        assert transport._message_endpoint == "http://localhost:8080/messages"

    async def test_connect_already_connected_returns_early(self, transport):
        transport._state = TransportState.CONNECTED
        transport._client = AsyncMock(spec=httpx.AsyncClient)

        await transport.connect()

        assert transport.state == TransportState.CONNECTED

    async def test_connect_timeout_raises_connection_error(self, transport):
        async def never_set():
            await asyncio.sleep(10)

        transport._sse_reader = never_set
        transport._timeout = 0.05

        with pytest.raises(ConnectionError, match="SSE connection timeout"):
            await transport.connect()

    async def test_connect_timeout_sets_disconnected(self, transport):
        async def never_set():
            await asyncio.sleep(10)

        transport._sse_reader = never_set
        transport._timeout = 0.05

        with pytest.raises(ConnectionError):
            await transport.connect()

        assert transport.state == TransportState.DISCONNECTED

    async def test_disconnect_cleans_up(self, transport):
        transport._state = TransportState.CONNECTED
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        transport._client = mock_client
        transport._message_endpoint = "http://localhost:8080/messages"
        transport._session_id = "sess-123"

        await transport.disconnect()

        assert transport.state == TransportState.DISCONNECTED
        assert transport._message_endpoint is None
        assert transport._session_id == ""
        mock_client.aclose.assert_awaited_once()

    async def test_disconnect_cancels_pending_futures(self, transport):
        transport._state = TransportState.CONNECTED
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        transport._pending[1] = fut

        await transport.disconnect()

        assert fut.done()
        assert fut.cancelled()
        assert len(transport._pending) == 0

    async def test_disconnect_without_client(self, transport):
        transport._state = TransportState.CONNECTED
        await transport.disconnect()
        assert transport.state == TransportState.DISCONNECTED

    async def test_send_not_connected_returns_error(self, transport):
        resp = await transport.send(JSONRPCRequest(method="ping", id=1))

        assert resp.is_error
        assert resp.error["code"] == -32000
        assert resp.error["message"] == "SSE transport not connected"

    async def test_send_no_message_endpoint_returns_error(self, transport):
        transport._state = TransportState.CONNECTED
        resp = await transport.send(JSONRPCRequest(method="ping", id=1))

        assert resp.is_error
        assert resp.error["code"] == -32000
        assert resp.error["message"] == "SSE transport not connected"

    async def test_send_no_client_returns_error(self, transport):
        transport._state = TransportState.CONNECTED
        transport._message_endpoint = "http://localhost:8080/messages"
        resp = await transport.send(JSONRPCRequest(method="ping", id=1))

        assert resp.is_error
        assert resp.error["code"] == -32000
        assert resp.error["message"] == "SSE client not available"

    async def test_send_direct_json_response(self, transport):
        transport._state = TransportState.CONNECTED
        transport._message_endpoint = "http://localhost:8080/messages"
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "result": {"status": "direct"},
            "id": 1,
        }
        mock_client.post.return_value = mock_response
        transport._client = mock_client
        transport._running.set()

        resp = await transport.send(JSONRPCRequest(method="ping", id=1))

        assert resp.result == {"status": "direct"}
        assert resp.id == 1
        assert resp.error is None
        assert len(transport._pending) == 0

    async def test_send_sse_delivered_response(self, transport):
        transport._state = TransportState.CONNECTED
        transport._message_endpoint = "http://localhost:8080/messages"
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.headers = {"content-type": "text/event-stream"}
        mock_client.post.return_value = mock_response
        transport._client = mock_client
        transport._running.set()

        async def deliver():
            await asyncio.sleep(0.02)
            transport._process_event(
                "message",
                '{"jsonrpc": "2.0", "result": {"status": "sse"}, "id": 1}',
            )

        task = asyncio.ensure_future(deliver())
        resp = await transport.send(JSONRPCRequest(method="ping", id=1))
        await task

        assert resp.result == {"status": "sse"}
        assert resp.id == 1
        assert resp.error is None

    async def test_send_sse_timeout(self, transport):
        transport._state = TransportState.CONNECTED
        transport._message_endpoint = "http://localhost:8080/messages"
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.headers = {"content-type": "text/event-stream"}
        mock_client.post.return_value = mock_response
        transport._client = mock_client
        transport._running.set()
        transport._timeout = 0.05

        resp = await transport.send(JSONRPCRequest(method="ping", id=1))

        assert resp.is_error
        assert "SSE response timeout" in resp.error["message"]

    async def test_send_httpx_timeout(self, transport):
        transport._state = TransportState.CONNECTED
        transport._message_endpoint = "http://localhost:8080/messages"
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.TimeoutException("timed out", request=MagicMock())
        transport._client = mock_client
        transport._running.set()

        resp = await transport.send(JSONRPCRequest(method="ping", id=1))

        assert resp.is_error
        assert resp.error["code"] == -32000
        assert resp.error["message"] == "SSE request timeout"

    async def test_send_httpx_connect_error(self, transport):
        transport._state = TransportState.CONNECTED
        transport._message_endpoint = "http://localhost:8080/messages"
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.ConnectError("refused")
        transport._client = mock_client
        transport._running.set()

        resp = await transport.send(JSONRPCRequest(method="ping", id=1))

        assert resp.is_error
        assert resp.error["code"] == -32000
        assert resp.error["message"] == "SSE connection refused"

    async def test_send_generic_exception(self, transport):
        transport._state = TransportState.CONNECTED
        transport._message_endpoint = "http://localhost:8080/messages"
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = RuntimeError("Unexpected error")
        transport._client = mock_client
        transport._running.set()

        resp = await transport.send(JSONRPCRequest(method="ping", id=1))

        assert resp.is_error
        assert resp.error["code"] == -32000
        assert "Unexpected error" in resp.error["message"]

    async def test_send_error_clears_pending(self, transport):
        transport._state = TransportState.CONNECTED
        transport._message_endpoint = "http://localhost:8080/messages"
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = RuntimeError("fail")
        transport._client = mock_client
        transport._running.set()

        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        transport._pending[1] = fut

        resp = await transport.send(JSONRPCRequest(method="ping", id=1))

        assert 1 not in transport._pending

    async def test_handle_error_sets_error_state(self, transport):
        assert transport.state == TransportState.DISCONNECTED
        await transport._handle_error()
        assert transport.state == TransportState.ERROR

    @pytest.mark.parametrize(
        "event_type,data,expected_endpoint,expected_session_id",
        [
            (
                "endpoint",
                "http://localhost:8080/messages",
                "http://localhost:8080/messages",
                "",
            ),
            ("session_id", "sess-abc-123", None, "sess-abc-123"),
        ],
    )
    async def test_process_event_sets_metadata(
        self, transport, event_type, data, expected_endpoint, expected_session_id
    ):
        transport._base_url = "http://localhost:8080"

        transport._process_event(event_type, data)

        if expected_endpoint is not None:
            assert transport._message_endpoint == expected_endpoint
        if expected_session_id:
            assert transport._session_id == expected_session_id

    async def test_process_endpoint_event_sets_event(self, transport):
        transport._base_url = "http://localhost:8080"
        assert not transport._endpoint_received.is_set()

        transport._process_event("endpoint", "/messages")
        assert transport._endpoint_received.is_set()
        assert transport._message_endpoint == "http://localhost:8080/messages"

    async def test_process_message_event_resolves_pending_future(self, transport):
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        transport._pending[42] = fut

        transport._process_event(
            "message",
            '{"jsonrpc": "2.0", "result": {"data": "hello"}, "id": 42}',
        )

        assert fut.done()
        result = fut.result()
        assert result.result == {"data": "hello"}
        assert result.id == 42

    async def test_process_message_event_ignores_no_pending(self, transport):
        transport._process_event(
            "message",
            '{"jsonrpc": "2.0", "result": {}, "id": 99}',
        )

    async def test_process_invalid_json_does_not_raise(self, transport):
        transport._process_event("message", "not json")
        transport._process_event("message", "{broken")

    async def test_process_unknown_event_type(self, transport):
        transport._process_event("unknown_event", "some_data")

    async def test_on_event_callback_registered_and_called(self, transport):
        callback = MagicMock()
        transport.on_event("endpoint", callback)
        assert callback in transport._event_callbacks["endpoint"]

        transport._process_event("endpoint", "http://localhost:8080/messages")
        callback.assert_called_once_with("http://localhost:8080/messages")

    async def test_on_event_multiple_callbacks(self, transport):
        cb1 = MagicMock()
        cb2 = MagicMock()
        transport.on_event("message", cb1)
        transport.on_event("message", cb2)

        assert len(transport._event_callbacks["message"]) == 2

    async def test_on_event_callback_exception_does_not_propagate(self, transport):
        failing_cb = MagicMock(side_effect=RuntimeError("callback failed"))
        healthy_cb = MagicMock()
        transport.on_event("message", failing_cb)
        transport.on_event("message", healthy_cb)

        transport._process_event("message", '{"result": {}, "id": 1}')

        failing_cb.assert_called_once()
        healthy_cb.assert_called_once()

    async def test_reconnect_calls_disconnect_and_connect(self, transport):
        async def fake_sse_reader():
            transport._process_event("endpoint", "http://localhost:8080/messages")

        transport._sse_reader = fake_sse_reader

        with (
            patch.object(transport, "disconnect", wraps=transport.disconnect) as mock_dc,
            patch.object(transport, "connect", wraps=transport.connect) as mock_c,
        ):
            await transport.reconnect()
            mock_dc.assert_awaited_once()
            mock_c.assert_awaited_once()

    async def test_connect_sets_connecting_during_process(self, transport):
        connect_started = False

        async def slow_sse_reader():
            nonlocal connect_started
            connect_started = True
            assert transport.state == TransportState.CONNECTING
            transport._process_event("endpoint", "http://localhost:8080/messages")

        transport._sse_reader = slow_sse_reader
        await transport.connect()
        assert connect_started
        assert transport.state == TransportState.CONNECTED

    async def test_connect_creates_httpx_client(self, transport):
        async def fake_sse_reader():
            transport._process_event("endpoint", "http://localhost:8080/messages")

        transport._sse_reader = fake_sse_reader
        await transport.connect()

        assert transport._client is not None
        assert isinstance(transport._client, httpx.AsyncClient)

    async def test_send_with_params_includes_them(self, transport):
        transport._state = TransportState.CONNECTED
        transport._message_endpoint = "http://localhost:8080/messages"
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "result": {"status": "ok"},
            "id": 3,
        }
        mock_client.post.return_value = mock_response
        transport._client = mock_client
        transport._running.set()

        req = JSONRPCRequest(
            method="tools/call",
            params={"name": "test_tool", "arguments": {"x": 1}},
            id=3,
        )
        await transport.send(req)

        mock_client.post.assert_awaited_once_with(
            "http://localhost:8080/messages",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "test_tool", "arguments": {"x": 1}},
                "id": 3,
            },
            timeout=30.0,
        )

    async def test_send_sse_timeout_clears_pending(self, transport):
        transport._state = TransportState.CONNECTED
        transport._message_endpoint = "http://localhost:8080/messages"
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.headers = {"content-type": "text/event-stream"}
        mock_client.post.return_value = mock_response
        transport._client = mock_client
        transport._running.set()
        transport._timeout = 0.05

        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        transport._pending[1] = fut

        await transport.send(JSONRPCRequest(method="ping", id=1))

        assert 1 not in transport._pending

    async def test_multiple_send_requests(self, transport):
        transport._state = TransportState.CONNECTED
        transport._message_endpoint = "http://localhost:8080/messages"
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        def mock_post(*args, **kwargs):
            resp = MagicMock()
            resp.is_success = True
            resp.headers = {"content-type": "application/json"}
            resp.json.return_value = {
                "jsonrpc": "2.0",
                "result": {"method": kwargs.get("json", {}).get("method")},
                "id": kwargs.get("json", {}).get("id"),
            }
            return resp

        mock_client.post.side_effect = mock_post
        transport._client = mock_client
        transport._running.set()

        r1 = await transport.send(JSONRPCRequest(method="a", id=1))
        r2 = await transport.send(JSONRPCRequest(method="b", id=2))
        r3 = await transport.send(JSONRPCRequest(method="c", id=3))

        assert r1.result["method"] == "a"
        assert r2.result["method"] == "b"
        assert r3.result["method"] == "c"

    async def test_cleanup_running_event_on_disconnect(self, transport):
        transport._running.set()
        assert transport._running.is_set()

        await transport.disconnect()

        assert not transport._running.is_set()

    async def test_send_sse_delivered_response_cleans_pending(self, transport):
        transport._state = TransportState.CONNECTED
        transport._message_endpoint = "http://localhost:8080/messages"
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.headers = {"content-type": "text/event-stream"}
        mock_client.post.return_value = mock_response
        transport._client = mock_client
        transport._running.set()

        async def deliver():
            await asyncio.sleep(0.02)
            transport._process_event(
                "message",
                '{"jsonrpc": "2.0", "result": {"done": true}, "id": 1}',
            )

        task = asyncio.ensure_future(deliver())
        await transport.send(JSONRPCRequest(method="ping", id=1))
        await task

        assert 1 not in transport._pending

    async def test_reconnect_creates_new_client(self, transport):
        async def fake_sse_reader():
            transport._process_event("endpoint", "http://localhost:8080/messages")

        transport._sse_reader = fake_sse_reader

        # First connect to establish a client
        await transport.connect()
        old_client = transport._client

        # Reconnect should create a new client
        await transport.reconnect()
        new_client = transport._client

        assert new_client is not None
        assert new_client is not old_client
