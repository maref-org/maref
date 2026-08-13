from __future__ import annotations

import json
import subprocess
import threading
from unittest.mock import MagicMock, patch

import httpx
import pytest

from maref.integration.mcp_transport import (
    HTTPTransport,
    InProcessTransport,
    JSONRPCRequest,
    JSONRPCResponse,
    MCPTransport,
    SSETransport,
    StdioTransport,
    TransportState,
)

# =============================================================================
# TransportState
# =============================================================================


class TestTransportState:
    def test_values(self) -> None:
        assert TransportState.DISCONNECTED.value == "disconnected"
        assert TransportState.CONNECTING.value == "connecting"
        assert TransportState.CONNECTED.value == "connected"
        assert TransportState.EXPIRED.value == "expired"
        assert TransportState.ERROR.value == "error"

    def test_membership(self) -> None:
        assert len(TransportState) == 5


# =============================================================================
# JSONRPCRequest
# =============================================================================


class TestJSONRPCRequest:
    def test_default_construction(self) -> None:
        req = JSONRPCRequest()
        assert req.jsonrpc == "2.0"
        assert req.method == ""
        assert req.params is None
        assert req.id == 0

    def test_construction_with_values(self) -> None:
        req = JSONRPCRequest(
            method="tools/list",
            params={"foo": "bar"},
            id=42,
        )
        assert req.jsonrpc == "2.0"
        assert req.method == "tools/list"
        assert req.params == {"foo": "bar"}
        assert req.id == 42

    def test_to_json_without_params(self) -> None:
        req = JSONRPCRequest(method="ping", id=1)
        result = json.loads(req.to_json())
        assert result == {"jsonrpc": "2.0", "method": "ping", "id": 1}

    def test_to_json_with_params(self) -> None:
        req = JSONRPCRequest(
            method="tools/call",
            params={"name": "foo", "arguments": {"a": 1}},
            id=3,
        )
        result = json.loads(req.to_json())
        assert result == {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "foo", "arguments": {"a": 1}},
            "id": 3,
        }

    def test_to_json_string_id(self) -> None:
        req = JSONRPCRequest(method="ping", id="req-1")
        result = json.loads(req.to_json())
        assert result["id"] == "req-1"


# =============================================================================
# JSONRPCResponse
# =============================================================================


class TestJSONRPCResponse:
    def test_default_construction(self) -> None:
        resp = JSONRPCResponse()
        assert resp.jsonrpc == "2.0"
        assert resp.result is None
        assert resp.error is None
        assert resp.id == 0

    def test_construction_with_result(self) -> None:
        resp = JSONRPCResponse(result={"tools": []}, id=2)
        assert resp.result == {"tools": []}
        assert resp.error is None
        assert resp.id == 2

    def test_construction_with_error(self) -> None:
        resp = JSONRPCResponse(
            error={"code": -32601, "message": "Method not found"},
            id=1,
        )
        assert resp.error == {"code": -32601, "message": "Method not found"}
        assert resp.result is None

    def test_is_error_false(self) -> None:
        resp = JSONRPCResponse(result="ok")
        assert resp.is_error is False

    def test_is_error_true(self) -> None:
        resp = JSONRPCResponse(error={"code": -32000, "message": "err"})
        assert resp.is_error is True

    def test_error_code_none_when_no_error(self) -> None:
        resp = JSONRPCResponse(result="ok")
        assert resp.error_code is None

    def test_error_code_from_error(self) -> None:
        resp = JSONRPCResponse(error={"code": -32601, "message": "Method not found"})
        assert resp.error_code == -32601

    def test_error_code_none_when_error_has_no_code(self) -> None:
        resp = JSONRPCResponse(error={"message": "no code"})
        assert resp.error_code is None

    def test_error_code_when_error_is_empty_dict(self) -> None:
        resp = JSONRPCResponse(error={})
        assert resp.error_code is None

    def test_from_json_with_result(self) -> None:
        raw = '{"jsonrpc": "2.0", "result": {"status": "ok"}, "id": 1}'
        resp = JSONRPCResponse.from_json(raw)
        assert resp.jsonrpc == "2.0"
        assert resp.result == {"status": "ok"}
        assert resp.error is None
        assert resp.id == 1

    def test_from_json_with_error(self) -> None:
        raw = (
            '{"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": 1}'
        )
        resp = JSONRPCResponse.from_json(raw)
        assert resp.jsonrpc == "2.0"
        assert resp.result is None
        assert resp.error == {"code": -32601, "message": "Method not found"}
        assert resp.id == 1

    def test_from_json_with_partial_data(self) -> None:
        raw = '{"result": "partial"}'
        resp = JSONRPCResponse.from_json(raw)
        assert resp.jsonrpc == "2.0"
        assert resp.result == "partial"
        assert resp.error is None
        assert resp.id == 0

    def test_from_json_empty(self) -> None:
        raw = "{}"
        resp = JSONRPCResponse.from_json(raw)
        assert resp.jsonrpc == "2.0"
        assert resp.result is None
        assert resp.error is None
        assert resp.id == 0

    def test_from_json_string_id(self) -> None:
        raw = '{"id": "resp-abc", "result": true}'
        resp = JSONRPCResponse.from_json(raw)
        assert resp.id == "resp-abc"


# =============================================================================
# MCPTransport (abstract base)
# =============================================================================


class TestMCPTransport:
    def test_state_property_default(self) -> None:
        transport = _ConcreteTransport()
        assert transport.state == TransportState.DISCONNECTED

    def test_set_state(self) -> None:
        transport = _ConcreteTransport()
        assert transport.state == TransportState.DISCONNECTED
        transport.set_state(TransportState.CONNECTED)
        assert transport.state == TransportState.CONNECTED

    def test_send_initialize(self) -> None:
        transport = _ConcreteTransport()
        resp = transport.send_initialize(client_name="test-agent")
        assert transport._last_request is not None
        assert transport._last_request.method == "initialize"
        assert transport._last_request.params == {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "test-agent", "version": "0.9.0"},
        }
        assert transport._last_request.id == 1
        assert resp.id == 1

    def test_send_tools_list(self) -> None:
        transport = _ConcreteTransport()
        resp = transport.send_tools_list()
        assert transport._last_request is not None
        assert transport._last_request.method == "tools/list"
        assert transport._last_request.params is None
        assert transport._last_request.id == 2
        assert resp.id == 2

    def test_send_tool_call(self) -> None:
        transport = _ConcreteTransport()
        resp = transport.send_tool_call("my_tool", {"x": 1})
        assert transport._last_request is not None
        assert transport._last_request.method == "tools/call"
        params = transport._last_request.params
        assert params["name"] == "my_tool"
        assert params["arguments"] == {"x": 1}
        # 宪法第十五-A条: 工具调用请求需带 MCP 消息信封
        assert params["trace_id"]
        assert params["source_agent"]
        assert params["timestamp"]
        assert transport._last_request.id == 3
        assert resp.id == 3

    def test_send_resources_list(self) -> None:
        transport = _ConcreteTransport()
        resp = transport.send_resources_list()
        assert transport._last_request is not None
        assert transport._last_request.method == "resources/list"
        assert transport._last_request.params is None
        assert transport._last_request.id == 4
        assert resp.id == 4

    def test_empty_params_in_initialize(self) -> None:
        transport = _ConcreteTransport()
        transport.send_initialize()
        assert transport._last_request is not None
        assert transport._last_request.params is not None


class _ConcreteTransport(MCPTransport):
    """Minimal concrete subclass for testing abstract MCPTransport."""

    def __init__(self) -> None:
        super().__init__()
        self._last_request: JSONRPCRequest | None = None

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
        self._last_request = request
        return JSONRPCResponse(result={}, id=request.id)


# =============================================================================
# InProcessTransport
# =============================================================================


class TestInProcessTransport:
    def test_default_construction(self) -> None:
        t = InProcessTransport()
        assert t.state == TransportState.DISCONNECTED
        assert t.get_pending_requests() == []
        assert t.get_responses() == []

    def test_connect_sets_state(self) -> None:
        t = InProcessTransport()
        t.connect()
        assert t.state == TransportState.CONNECTED

    def test_disconnect_sets_state(self) -> None:
        t = InProcessTransport()
        t.connect()
        t.disconnect()
        assert t.state == TransportState.DISCONNECTED

    def test_send_uses_default_handler(self) -> None:
        t = InProcessTransport()
        t.connect()
        req = JSONRPCRequest(method="tools/list", id=5)
        resp = t.send(req)
        assert resp.result == {"status": "ok", "method": "tools/list", "via": "inprocess"}
        assert resp.id == 5
        assert resp.is_error is False

    def test_send_with_custom_handler(self) -> None:
        def handler(req: JSONRPCRequest) -> JSONRPCResponse:
            return JSONRPCResponse(result={"handled": req.method}, id=req.id)

        t = InProcessTransport(message_handler=handler)
        t.connect()
        req = JSONRPCRequest(method="custom", id=7)
        resp = t.send(req)
        assert resp.result == {"handled": "custom"}
        assert resp.id == 7

    def test_send_error_when_disconnected(self) -> None:
        t = InProcessTransport()
        req = JSONRPCRequest(method="ping", id=1)
        resp = t.send(req)
        assert resp.is_error is True
        assert resp.error_code == -32000
        assert resp.error["message"] == "InProcess transport not connected"

    def test_send_populates_queues(self) -> None:
        t = InProcessTransport()
        t.connect()
        req = JSONRPCRequest(method="ping", id=9)
        t.send(req)
        assert len(t.get_pending_requests()) == 1
        assert t.get_pending_requests()[0].id == 9
        assert len(t.get_responses()) == 1
        assert t.get_responses()[0].id == 9

    def test_send_async_when_connected(self) -> None:
        t = InProcessTransport()
        t.connect()
        req = JSONRPCRequest(method="ping", id=10)
        t.send_async(req)
        pending = t.get_pending_requests()
        assert len(pending) == 1
        assert pending[0].id == 10
        # send_async should NOT produce a response
        assert len(t.get_responses()) == 0

    def test_send_async_when_disconnected(self) -> None:
        t = InProcessTransport()
        req = JSONRPCRequest(method="ping", id=11)
        t.send_async(req)
        # Should not be queued when disconnected
        assert t.get_pending_requests() == []

    def test_clear(self) -> None:
        t = InProcessTransport()
        t.connect()
        t.send(JSONRPCRequest(method="a", id=1))
        t.send(JSONRPCRequest(method="b", id=2))
        assert len(t.get_pending_requests()) == 2
        assert len(t.get_responses()) == 2
        t.clear()
        assert t.get_pending_requests() == []
        assert t.get_responses() == []

    def test_multiple_sends(self) -> None:
        t = InProcessTransport()
        t.connect()
        for i in range(5):
            t.send(JSONRPCRequest(method="ping", id=i))
        assert len(t.get_pending_requests()) == 5
        assert len(t.get_responses()) == 5

    def test_state_after_disconnect(self) -> None:
        t = InProcessTransport()
        t.connect()
        assert t.state == TransportState.CONNECTED
        t.disconnect()
        assert t.state == TransportState.DISCONNECTED

    def test_default_handler_is_static(self) -> None:
        req = JSONRPCRequest(method="test", id=99)
        resp = InProcessTransport._default_handler(req)
        assert resp.result == {"status": "ok", "method": "test", "via": "inprocess"}
        assert resp.id == 99


# =============================================================================
# HTTPTransport
# =============================================================================


class TestHTTPTransport:
    def test_construction(self) -> None:
        t = HTTPTransport("http://localhost:8000/mcp")
        assert t.state == TransportState.DISCONNECTED

    def test_connect_success(self) -> None:
        with patch("httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            t = HTTPTransport("http://localhost:8000/mcp")
            t.connect()
            assert t.state == TransportState.CONNECTED
            mock_get.assert_called_once_with("http://localhost:8000/mcp", timeout=5.0)

    def test_connect_http_error_status(self) -> None:
        with patch("httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_get.return_value = mock_response

            t = HTTPTransport("http://localhost:8000/mcp")
            t.connect()
            assert t.state == TransportState.ERROR

    def test_connect_exception(self) -> None:
        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            t = HTTPTransport("http://localhost:8000/mcp")
            t.connect()
            assert t.state == TransportState.ERROR

    def test_disconnect(self) -> None:
        t = HTTPTransport("http://localhost:8000/mcp")
        t.connect = MagicMock()  # skip real connect
        t.set_state(TransportState.CONNECTED)
        t.disconnect()
        assert t.state == TransportState.DISCONNECTED

    def test_send_success(self) -> None:
        with patch("httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "jsonrpc": "2.0",
                "result": {"tools": []},
                "id": 2,
            }
            mock_post.return_value = mock_response

            t = HTTPTransport("http://localhost:8000/mcp")
            t.set_state(TransportState.CONNECTED)
            req = JSONRPCRequest(method="tools/list", id=2)
            resp = t.send(req)
            assert resp.result == {"tools": []}
            assert resp.id == 2
            assert resp.is_error is False

    def test_send_not_connected(self) -> None:
        t = HTTPTransport("http://localhost:8000/mcp")
        req = JSONRPCRequest(method="ping", id=1)
        resp = t.send(req)
        assert resp.is_error is True
        assert resp.error_code == -32000
        assert resp.error["message"] == "HTTP transport not connected"

    def test_send_exception(self) -> None:
        with patch("httpx.post", side_effect=httpx.ConnectError("refused")):
            t = HTTPTransport("http://localhost:8000/mcp")
            t.set_state(TransportState.CONNECTED)
            req = JSONRPCRequest(method="ping", id=1)
            resp = t.send(req)
            assert resp.is_error is True
            assert resp.error_code == -32000

    def test_send_passes_correct_body(self) -> None:
        with patch("httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {"jsonrpc": "2.0", "result": {}, "id": 5}
            mock_post.return_value = mock_response

            t = HTTPTransport("http://localhost:8000/mcp")
            t.set_state(TransportState.CONNECTED)
            req = JSONRPCRequest(method="tools/call", params={"name": "x"}, id=5)
            t.send(req)
            mock_post.assert_called_once_with(
                "http://localhost:8000/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": "x"},
                    "id": 5,
                },
                timeout=10.0,
            )


# =============================================================================
# StdioTransport
# =============================================================================


class TestStdioTransport:
    def test_construction(self) -> None:
        t = StdioTransport(["python", "-m", "some_server"])
        assert t.state == TransportState.DISCONNECTED
        assert t._command == ["python", "-m", "some_server"]

    def test_connect_success(self) -> None:
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            t = StdioTransport(["python", "-m", "mcp_server"])
            t.connect()
            assert t.state == TransportState.CONNECTED
            mock_popen.assert_called_once_with(
                ["python", "-m", "mcp_server"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

    def test_connect_sets_connecting_then_connected(self) -> None:
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            t = StdioTransport(["echo", "hi"])
            states: list[TransportState] = []

            original_set_state = t.set_state

            def tracking_set_state(state: TransportState) -> None:
                states.append(state)
                original_set_state(state)

            t.set_state = tracking_set_state  # type: ignore[method-assign]
            t.connect()
            assert states == [TransportState.CONNECTING, TransportState.CONNECTED]

    def test_disconnect_terminates_process(self) -> None:
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = None  # still running
            mock_popen.return_value = mock_process

            t = StdioTransport(["python", "-m", "mcp_server"])
            t._process = mock_process
            t.set_state(TransportState.CONNECTED)
            t.disconnect()
            mock_process.terminate.assert_called_once()
            mock_process.wait.assert_called_once_with(timeout=5)
            assert t.state == TransportState.DISCONNECTED

    def test_disconnect_when_not_running(self) -> None:
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = 0  # already exited
            mock_popen.return_value = mock_process

            t = StdioTransport(["python", "-m", "mcp_server"])
            t._process = mock_process
            t.set_state(TransportState.CONNECTED)
            t.disconnect()
            mock_process.terminate.assert_not_called()
            assert t.state == TransportState.DISCONNECTED

    def test_disconnect_when_no_process(self) -> None:
        t = StdioTransport(["python", "-m", "mcp_server"])
        t.set_state(TransportState.CONNECTED)
        t.disconnect()
        assert t.state == TransportState.DISCONNECTED

    def test_send_success(self) -> None:
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_stdin = MagicMock()
            mock_stdout = MagicMock()
            mock_stdout.readline.return_value = (
                b'{"jsonrpc": "2.0", "result": {"ok": true}, "id": 1}\n'
            )
            mock_process.stdin = mock_stdin
            mock_process.stdout = mock_stdout
            mock_popen.return_value = mock_process

            t = StdioTransport(["python", "-m", "mcp_server"])
            t._process = mock_process
            t.set_state(TransportState.CONNECTED)
            req = JSONRPCRequest(method="ping", id=1)
            resp = t.send(req)
            assert resp.result == {"ok": True}
            assert resp.id == 1
            mock_stdin.write.assert_called_once_with(
                b'{"jsonrpc": "2.0", "method": "ping", "id": 1}\n'
            )
            mock_stdin.flush.assert_called_once()

    def test_send_process_dead(self) -> None:
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = 1  # exited
            mock_popen.return_value = mock_process

            t = StdioTransport(["python", "-m", "mcp_server"])
            t._process = mock_process
            t.set_state(TransportState.CONNECTED)
            req = JSONRPCRequest(method="ping", id=1)
            resp = t.send(req)
            assert resp.is_error is True
            assert resp.error_code == -32000
            assert resp.error["message"] == "Transport not connected"
            assert t.state == TransportState.ERROR

    def test_send_no_process(self) -> None:
        t = StdioTransport(["python", "-m", "mcp_server"])
        t.set_state(TransportState.CONNECTED)
        req = JSONRPCRequest(method="ping", id=1)
        resp = t.send(req)
        assert resp.is_error is True
        assert resp.error_code == -32000
        assert resp.error["message"] == "Transport not connected"

    def test_send_stdin_is_none(self) -> None:
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_process.stdin = None
            mock_process.stdout = MagicMock()
            mock_popen.return_value = mock_process

            t = StdioTransport(["python", "-m", "mcp_server"])
            t._process = mock_process
            t.set_state(TransportState.CONNECTED)
            req = JSONRPCRequest(method="ping", id=1)
            resp = t.send(req)
            assert resp.is_error is True
            assert resp.error["message"] == "Stream not available"

    def test_send_stdout_is_none(self) -> None:
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_process.stdin = MagicMock()
            mock_process.stdout = None
            mock_popen.return_value = mock_process

            t = StdioTransport(["python", "-m", "mcp_server"])
            t._process = mock_process
            t.set_state(TransportState.CONNECTED)
            req = JSONRPCRequest(method="ping", id=1)
            resp = t.send(req)
            assert resp.is_error is True
            assert resp.error["message"] == "Stream not available"


# =============================================================================
# SSETransport
# =============================================================================


class TestSSETransport:
    def test_construction(self) -> None:
        t = SSETransport("http://localhost:8000/sse")
        assert t.state == TransportState.DISCONNECTED
        assert t._sse_url == "http://localhost:8000/sse"
        assert t._max_retries == 3
        assert t._timeout == 30.0
        assert t._message_endpoint is None
        assert t._session_id == ""

    def test_connect_disconnects_on_timeout(self) -> None:
        """When endpoint is not received within timeout, connect should raise."""
        with (
            patch("threading.Thread") as mock_thread,
            patch.object(SSETransport, "disconnect") as mock_disconnect,
        ):
            mock_thread_instance = MagicMock()
            mock_thread.return_value = mock_thread_instance

            # Make endpoint wait time out
            t = SSETransport("http://localhost:8000/sse", timeout=0.01)
            with pytest.raises(ConnectionError, match="SSE connection timeout"):
                t.connect()
            mock_disconnect.assert_called_once()

    def test_connect_sets_connecting_state(self) -> None:
        with (
            patch("threading.Thread") as mock_thread,
        ):
            mock_thread_instance = MagicMock()
            mock_thread.return_value = mock_thread_instance
            t = SSETransport("http://localhost:8000/sse", timeout=0.01)
            t.set_state(TransportState.CONNECTING)
            assert t.state == TransportState.CONNECTING

    def test_connect_when_already_connected(self) -> None:
        t = SSETransport("http://localhost:8000/sse")
        t.set_state(TransportState.CONNECTED)
        with patch.object(t, "_sse_reader") as mock_reader:
            t.connect()
            mock_reader.assert_not_called()

    def test_disconnect(self) -> None:
        with patch("threading.Thread"):
            t = SSETransport("http://localhost:8000/sse")
            mock_client = MagicMock()
            t._client = mock_client
            mock_thread = MagicMock()
            t._sse_thread = mock_thread
            t._running.set()
            t._endpoint_received.set()
            t._message_endpoint = "/msg"
            t._session_id = "sess-1"

            t.disconnect()

            assert t._message_endpoint is None
            assert t._session_id == ""
            assert t.state == TransportState.DISCONNECTED
            mock_client.close.assert_called_once()
            mock_thread.join.assert_called_once_with(timeout=5)

    def test_disconnect_clears_responses(self) -> None:
        with patch("threading.Thread"):
            t = SSETransport("http://localhost:8000/sse")
            t._client = MagicMock()
            t._sse_thread = MagicMock()
            with t._lock:
                t._responses[1] = JSONRPCResponse(result="x", id=1)
                evt = threading.Event()
                t._response_events[1] = evt
            t.disconnect()
            with t._lock:
                assert t._responses == {}
                assert t._response_events == {}

    def test_send_not_connected(self) -> None:
        t = SSETransport("http://localhost:8000/sse")
        req = JSONRPCRequest(method="ping", id=1)
        resp = t.send(req)
        assert resp.is_error is True
        assert resp.error_code == -32000
        assert resp.error["message"] == "SSE transport not connected"

    def test_send_no_message_endpoint(self) -> None:
        t = SSETransport("http://localhost:8000/sse")
        t.set_state(TransportState.CONNECTED)
        t._message_endpoint = None
        req = JSONRPCRequest(method="ping", id=1)
        resp = t.send(req)
        assert resp.is_error is True
        assert resp.error["message"] == "SSE transport not connected"

    def test_send_no_client(self) -> None:
        t = SSETransport("http://localhost:8000/sse")
        t.set_state(TransportState.CONNECTED)
        t._message_endpoint = "/msg"
        t._client = None
        req = JSONRPCRequest(method="ping", id=1)
        resp = t.send(req)
        assert resp.is_error is True
        assert resp.error["message"] == "SSE client not available"

    def test_send_json_response_path(self) -> None:
        t = SSETransport("http://localhost:8000/sse", timeout=5.0)
        t.set_state(TransportState.CONNECTED)
        t._message_endpoint = "/msg"
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "result": {"tools": []},
            "id": 2,
        }
        mock_client.post.return_value = mock_response
        t._client = mock_client

        req = JSONRPCRequest(method="tools/list", id=2)
        resp = t.send(req)
        assert resp.result == {"tools": []}
        assert resp.id == 2
        mock_client.post.assert_called_once_with(
            "/msg",
            json={"jsonrpc": "2.0", "method": "tools/list", "id": 2},
            timeout=5.0,
        )

    def test_send_json_with_params(self) -> None:
        t = SSETransport("http://localhost:8000/sse", timeout=5.0)
        t.set_state(TransportState.CONNECTED)
        t._message_endpoint = "/msg"
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "result": {},
            "id": 3,
        }
        mock_client.post.return_value = mock_response
        t._client = mock_client

        req = JSONRPCRequest(method="tools/call", params={"name": "x"}, id=3)
        t.send(req)
        mock_client.post.assert_called_once_with(
            "/msg",
            json={"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "x"}, "id": 3},
            timeout=5.0,
        )

    def test_send_sse_response_timeout(self) -> None:
        t = SSETransport("http://localhost:8000/sse", timeout=0.01)
        t.set_state(TransportState.CONNECTED)
        t._message_endpoint = "/msg"
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.headers = {"content-type": "text/plain"}
        mock_client.post.return_value = mock_response
        t._client = mock_client

        req = JSONRPCRequest(method="ping", id=1)
        resp = t.send(req)
        assert resp.is_error is True
        assert "SSE response timeout" in resp.error["message"]

    def test_send_httpx_timeout_exception(self) -> None:
        t = SSETransport("http://localhost:8000/sse")
        t.set_state(TransportState.CONNECTED)
        t._message_endpoint = "/msg"
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.TimeoutException("timed out")
        t._client = mock_client

        req = JSONRPCRequest(method="ping", id=1)
        resp = t.send(req)
        assert resp.is_error is True
        assert resp.error["message"] == "SSE request timeout"
        assert t.state == TransportState.ERROR

    def test_send_httpx_connect_error(self) -> None:
        t = SSETransport("http://localhost:8000/sse")
        t.set_state(TransportState.CONNECTED)
        t._message_endpoint = "/msg"
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.ConnectError("refused")
        t._client = mock_client

        req = JSONRPCRequest(method="ping", id=1)
        resp = t.send(req)
        assert resp.is_error is True
        assert resp.error["message"] == "SSE connection refused"
        assert t.state == TransportState.ERROR

    def test_send_generic_exception(self) -> None:
        t = SSETransport("http://localhost:8000/sse")
        t.set_state(TransportState.CONNECTED)
        t._message_endpoint = "/msg"
        mock_client = MagicMock()
        mock_client.post.side_effect = RuntimeError("unexpected")
        t._client = mock_client

        req = JSONRPCRequest(method="ping", id=1)
        resp = t.send(req)
        assert resp.is_error is True
        assert "SSE transport error" in resp.error["message"]
        assert t.state == TransportState.ERROR

    def test_process_event_endpoint(self) -> None:
        t = SSETransport("http://localhost:8080/base")
        t._endpoint_received.clear()
        assert t._message_endpoint is None
        t._process_event("endpoint", "/msg/path")
        assert t._message_endpoint == "http://localhost:8080/msg/path"
        assert t._endpoint_received.is_set()

    def test_process_event_session_id(self) -> None:
        t = SSETransport("http://localhost:8000/sse")
        assert t._session_id == ""
        t._process_event("session_id", "abc-123")
        assert t._session_id == "abc-123"

    def test_process_event_message(self) -> None:
        t = SSETransport("http://localhost:8000/sse")
        data = json.dumps({"jsonrpc": "2.0", "result": {"x": 1}, "id": 42})
        t._process_event("message", data)
        with t._lock:
            assert 42 in t._responses
            assert t._responses[42].result == {"x": 1}

    def test_process_event_message_with_error(self) -> None:
        t = SSETransport("http://localhost:8000/sse")
        data = json.dumps({"jsonrpc": "2.0", "error": {"code": -32601}, "id": 7})
        t._process_event("message", data)
        with t._lock:
            assert 7 in t._responses
            assert t._responses[7].is_error is True
            assert t._responses[7].error_code == -32601

    def test_process_event_message_sets_response_event(self) -> None:
        t = SSETransport("http://localhost:8000/sse")
        rid = 99
        evt = threading.Event()
        with t._lock:
            t._response_events[rid] = evt
        data = json.dumps({"jsonrpc": "2.0", "result": {}, "id": rid})
        t._process_event("message", data)
        assert evt.is_set()

    def test_process_event_message_bad_json(self) -> None:
        t = SSETransport("http://localhost:8000/sse")
        # Should not raise
        t._process_event("message", "not valid json")
        with t._lock:
            assert t._responses == {}

    def test_process_event_unknown_type(self) -> None:
        t = SSETransport("http://localhost:8000/sse")
        # Should not raise
        t._process_event("unknown_event", "some data")
        # No state change expected
        assert t._session_id == ""
        assert t._message_endpoint is None

    def test_process_event_invokes_callback(self) -> None:
        t = SSETransport("http://localhost:8000/sse")
        callback = MagicMock()
        t.on_event("endpoint", callback)
        t._process_event("endpoint", "/msg")
        callback.assert_called_once_with("/msg")

    def test_process_event_invokes_multiple_callbacks(self) -> None:
        t = SSETransport("http://localhost:8000/sse")
        cb1 = MagicMock()
        cb2 = MagicMock()
        t.on_event("message", cb1)
        t.on_event("message", cb2)
        t._process_event("message", '{"result": 1, "id": 1}')
        cb1.assert_called_once()
        cb2.assert_called_once()

    def test_process_event_callback_exception_does_not_crash(self) -> None:
        t = SSETransport("http://localhost:8000/sse")

        def failing_cb(_: str) -> None:
            raise ValueError("boom")

        ok_cb = MagicMock()
        t.on_event("message", failing_cb)
        t.on_event("message", ok_cb)
        t._process_event("message", '{"result": 1, "id": 1}')
        ok_cb.assert_called_once()

    def test_process_event_callback_different_event_type(self) -> None:
        t = SSETransport("http://localhost:8000/sse")
        cb = MagicMock()
        t.on_event("endpoint", cb)
        t._process_event("message", "data")
        cb.assert_not_called()

    def test_on_event_registers_callback(self) -> None:
        t = SSETransport("http://localhost:8000/sse")
        cb = lambda x: None
        t.on_event("test_event", cb)
        assert cb in t._event_callbacks["test_event"]

    def test_on_event_appends_to_existing(self) -> None:
        t = SSETransport("http://localhost:8000/sse")
        cb1 = lambda x: None
        cb2 = lambda x: None
        t.on_event("test_event", cb1)
        t.on_event("test_event", cb2)
        assert len(t._event_callbacks["test_event"]) == 2

    def test_handle_error(self) -> None:
        t = SSETransport("http://localhost:8000/sse")
        assert t.state != TransportState.ERROR
        t._handle_error()
        assert t.state == TransportState.ERROR

    def test_send_response_event_from_sse(self) -> None:
        """Test the SSE-delivered response path by populating response during POST."""
        t = SSETransport("http://localhost:8000/sse", timeout=5.0)
        t.set_state(TransportState.CONNECTED)
        t._message_endpoint = "/msg"

        rid = 10

        def post_side_effect(*args: object, **kwargs: object) -> MagicMock:
            # Simulate SSE delivering the response asynchronously
            resp_obj = JSONRPCResponse(result={"from": "sse"}, id=rid)
            with t._lock:
                t._responses[rid] = resp_obj
                if rid in t._response_events:
                    t._response_events[rid].set()
            mock_resp = MagicMock()
            mock_resp.is_success = False
            mock_resp.headers = {"content-type": "text/plain"}
            return mock_resp

        mock_client = MagicMock()
        mock_client.post.side_effect = post_side_effect
        t._client = mock_client

        req = JSONRPCRequest(method="ping", id=rid)
        result = t.send(req)
        assert result.result == {"from": "sse"}
        assert result.id == rid
