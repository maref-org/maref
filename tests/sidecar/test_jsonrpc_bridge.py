from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from sidecar.jsonrpc_bridge import (
    JSONRPCError,
    JSONRPCErrorCode,
    JSONRPCRequest,
    JSONRPCResponse,
    SidecarJSONRPCBridge,
    SidecarMethod,
    SidecarRequest,
    SidecarResponse,
)


class TestJSONRPCErrorCode:
    def test_values(self) -> None:
        assert JSONRPCErrorCode.PARSE_ERROR.value == -32700
        assert JSONRPCErrorCode.INVALID_REQUEST.value == -32600
        assert JSONRPCErrorCode.METHOD_NOT_FOUND.value == -32601
        assert JSONRPCErrorCode.INVALID_PARAMS.value == -32602
        assert JSONRPCErrorCode.INTERNAL_ERROR.value == -32603
        assert JSONRPCErrorCode.GOVERNANCE_REJECTED.value == -32001
        assert JSONRPCErrorCode.SAFETY_GATE_BLOCKED.value == -32002


class TestSidecarMethod:
    def test_values(self) -> None:
        assert SidecarMethod.OBSERVE.value == "sidecar.observe"
        assert SidecarMethod.GET_STATE.value == "sidecar.get_state"
        assert SidecarMethod.HEALTH_CHECK.value == "sidecar.health_check"
        assert SidecarMethod.GET_CORRELATION.value == "sidecar.get_correlation"
        assert SidecarMethod.MIGRATE.value == "sidecar.migrate"
        assert SidecarMethod.GET_ENTROPY.value == "sidecar.get_entropy"
        assert SidecarMethod.LIST_AGENTS.value == "sidecar.list_agents"
        assert SidecarMethod.GET_SNAPSHOT.value == "sidecar.get_snapshot"
        assert SidecarMethod.GET_ANOMALIES.value == "sidecar.get_anomalies"
        assert SidecarMethod.GET_OBSERVATIONS.value == "sidecar.get_observations"


class TestJSONRPCRequest:
    def test_default_id_generated(self) -> None:
        req = JSONRPCRequest(method="test.method")
        assert req.id != ""
        assert req.jsonrpc == "2.0"
        assert req.params == {}

    def test_custom_id_preserved(self) -> None:
        req = JSONRPCRequest(method="test.method", id="custom-123")
        assert req.id == "custom-123"

    def test_params_preserved(self) -> None:
        req = JSONRPCRequest(method="test.method", params={"key": "value"})
        assert req.params == {"key": "value"}

    def test_to_dict_with_params(self) -> None:
        req = JSONRPCRequest(method="test.method", params={"a": 1}, id="id1")
        d = req.to_dict()
        assert d == {"jsonrpc": "2.0", "method": "test.method", "params": {"a": 1}, "id": "id1"}

    def test_to_dict_without_params(self) -> None:
        req = JSONRPCRequest(method="test.method", id="id1")
        d = req.to_dict()
        assert "params" not in d

    def test_from_dict(self) -> None:
        data = {"jsonrpc": "2.0", "method": "test.method", "params": {"x": 1}, "id": "id1"}
        req = JSONRPCRequest.from_dict(data)
        assert req.method == "test.method"
        assert req.params == {"x": 1}
        assert req.id == "id1"
        assert req.jsonrpc == "2.0"

    def test_from_dict_defaults(self) -> None:
        req = JSONRPCRequest.from_dict({"method": "m"})
        assert req.params == {}
        assert req.id != ""
        assert req.jsonrpc == "2.0"

    def test_to_json(self) -> None:
        req = JSONRPCRequest(method="test.method", params={"a": 1}, id="id1")
        j = req.to_json()
        parsed = json.loads(j)
        assert parsed["method"] == "test.method"
        assert parsed["params"] == {"a": 1}

    def test_from_json_roundtrip(self) -> None:
        original = JSONRPCRequest(method="test.method", params={"k": "v"}, id="r1")
        json_str = original.to_json()
        restored = JSONRPCRequest.from_json(json_str)
        assert restored.method == original.method
        assert restored.params == original.params
        assert restored.id == original.id
        assert restored.jsonrpc == original.jsonrpc

    def test_from_json_empty_params(self) -> None:
        req = JSONRPCRequest.from_json('{"method": "m", "id": "1"}')
        assert req.params == {}


class TestJSONRPCError:
    def test_construction(self) -> None:
        err = JSONRPCError(JSONRPCErrorCode.METHOD_NOT_FOUND, "Not found")
        assert err.code == JSONRPCErrorCode.METHOD_NOT_FOUND
        assert err.message == "Not found"


class TestJSONRPCResponse:
    def test_success_response(self) -> None:
        resp = JSONRPCResponse.success({"status": "ok"}, "req1")
        assert resp.result == {"status": "ok"}
        assert resp.id == "req1"
        assert resp.is_error is False
        assert resp.error is None

    def test_error_response(self) -> None:
        resp = JSONRPCResponse.error_response(JSONRPCErrorCode.INTERNAL_ERROR, "Something broke", "req2")
        assert resp.is_error is True
        assert resp.error is not None
        assert resp.error.code == JSONRPCErrorCode.INTERNAL_ERROR
        assert resp.error.message == "Something broke"
        assert resp.id == "req2"

    def test_to_dict_success(self) -> None:
        resp = JSONRPCResponse.success("result_data", "id1")
        d = resp.to_dict()
        assert d["jsonrpc"] == "2.0"
        assert d["id"] == "id1"
        assert d["result"] == "result_data"
        assert "error" not in d

    def test_to_dict_error(self) -> None:
        resp = JSONRPCResponse.error_response(JSONRPCErrorCode.PARSE_ERROR, "Parse failed", "id2")
        d = resp.to_dict()
        assert d["jsonrpc"] == "2.0"
        assert d["id"] == "id2"
        assert "result" not in d
        assert d["error"]["code"] == -32700
        assert d["error"]["message"] == "Parse failed"

    def test_to_json_success(self) -> None:
        resp = JSONRPCResponse.success("ok", "id1")
        j = json.loads(resp.to_json())
        assert j["result"] == "ok"

    def test_to_json_error(self) -> None:
        resp = JSONRPCResponse.error_response(JSONRPCErrorCode.METHOD_NOT_FOUND, "No method", "id1")
        j = json.loads(resp.to_json())
        assert "error" in j
        assert j["error"]["code"] == -32601


class TestSidecarRequest:
    def test_create_observe(self) -> None:
        req = SidecarRequest.create(SidecarMethod.OBSERVE, {"agent": "a1"})
        assert isinstance(req, JSONRPCRequest)
        assert req.method == "sidecar.observe"
        assert req.params == {"agent": "a1"}
        assert req.id != ""

    def test_create_health_check(self) -> None:
        req = SidecarRequest.create(SidecarMethod.HEALTH_CHECK)
        assert req.method == "sidecar.health_check"
        assert req.params == {}

    def test_create_with_custom_id(self) -> None:
        req = SidecarRequest.create(SidecarMethod.LIST_AGENTS, req_id="custom-id")
        assert req.id == "custom-id"


class TestSidecarResponse:
    def test_from_json_rpc_success(self) -> None:
        json_str = '{"jsonrpc": "2.0", "result": {"status": "ok"}, "id": "1"}'
        resp = SidecarResponse.from_json_rpc(json_str)
        assert resp.result == {"status": "ok"}
        assert resp.is_error is False
        assert resp.error is None

    def test_from_json_rpc_error(self) -> None:
        json_str = '{"jsonrpc": "2.0", "error": {"code": -32601, "message": "Not found"}, "id": "1"}'
        resp = SidecarResponse.from_json_rpc(json_str)
        assert resp.is_error is True
        assert resp.error is not None
        assert resp.error.code == JSONRPCErrorCode.METHOD_NOT_FOUND
        assert resp.error.message == "Not found"

    def test_from_json_rpc_unknown_code(self) -> None:
        json_str = '{"jsonrpc": "2.0", "error": {"code": -99999, "message": "Weird"}, "id": "1"}'
        with pytest.raises(ValueError):
            SidecarResponse.from_json_rpc(json_str)

    def test_from_json_rpc_no_error(self) -> None:
        json_str = '{"jsonrpc": "2.0", "id": "1"}'
        resp = SidecarResponse.from_json_rpc(json_str)
        assert resp.result is None
        assert resp.error is None


class TestSidecarJSONRPCBridge:
    def test_init_registers_default_handlers(self) -> None:
        bridge = SidecarJSONRPCBridge()
        assert bridge.handler_count == len(SidecarMethod)

    def test_register_handler(self) -> None:
        bridge = SidecarJSONRPCBridge()
        handler = lambda params: {"custom": "value"}
        bridge.register_handler("custom.method", handler)
        assert bridge.handler_count == len(SidecarMethod) + 1

    def test_handle_jsonrpc_request_success(self) -> None:
        bridge = SidecarJSONRPCBridge()
        req = JSONRPCRequest(method="sidecar.health_check", id="h1")
        resp = bridge.handle(req)
        assert resp.is_error is False
        assert resp.result["method"] == "sidecar.health_check"
        assert resp.id == "h1"

    def test_handle_json_string(self) -> None:
        bridge = SidecarJSONRPCBridge()
        json_str = '{"jsonrpc": "2.0", "method": "sidecar.observe", "id": "o1"}'
        resp = bridge.handle(json_str)
        assert resp.is_error is False
        assert resp.result["method"] == "sidecar.observe"

    def test_handle_invalid_json_parse_error(self) -> None:
        bridge = SidecarJSONRPCBridge()
        resp = bridge.handle("not json at all")
        assert resp.is_error is True
        assert resp.error is not None
        assert resp.error.code == JSONRPCErrorCode.PARSE_ERROR

    def test_handle_wrong_version(self) -> None:
        bridge = SidecarJSONRPCBridge()
        req = JSONRPCRequest(method="test", id="id1", jsonrpc="1.0")
        resp = bridge.handle(req)
        assert resp.is_error is True
        assert resp.error is not None
        assert resp.error.code == JSONRPCErrorCode.INVALID_REQUEST

    def test_handle_unknown_method(self) -> None:
        bridge = SidecarJSONRPCBridge()
        req = JSONRPCRequest(method="unknown.method", id="id1")
        resp = bridge.handle(req)
        assert resp.is_error is True
        assert resp.error is not None
        assert resp.error.code == JSONRPCErrorCode.METHOD_NOT_FOUND

    def test_handle_custom_handler(self) -> None:
        bridge = SidecarJSONRPCBridge()
        bridge.register_handler("custom.echo", lambda p: p)
        req = JSONRPCRequest(method="custom.echo", params={"msg": "hello"}, id="e1")
        resp = bridge.handle(req)
        assert resp.result == {"msg": "hello"}

    def test_handle_handler_raises_exception(self) -> None:
        def failing_handler(params):
            raise RuntimeError("Unexpected error")

        bridge = SidecarJSONRPCBridge()
        bridge.register_handler("failing.method", failing_handler)
        req = JSONRPCRequest(method="failing.method", id="f1")
        resp = bridge.handle(req)
        assert resp.is_error is True
        assert resp.error is not None
        assert resp.error.code == JSONRPCErrorCode.INTERNAL_ERROR

    def test_response_history_tracks_calls(self) -> None:
        bridge = SidecarJSONRPCBridge()
        assert bridge.response_history == []
        req = JSONRPCRequest(method="sidecar.health_check", id="h1")
        bridge.handle(req)
        assert len(bridge.response_history) == 1
        assert bridge.response_history[0].id == "h1"

    def test_clear_history(self) -> None:
        bridge = SidecarJSONRPCBridge()
        req = JSONRPCRequest(method="sidecar.health_check", id="h1")
        bridge.handle(req)
        assert len(bridge.response_history) == 1
        bridge.clear_history()
        assert bridge.response_history == []

    def test_error_response_added_to_history(self) -> None:
        bridge = SidecarJSONRPCBridge()
        bridge.handle("bad json {{{")
        assert len(bridge.response_history) == 1
        assert bridge.response_history[0].is_error is True

    def test_to_dict_includes_params_only_when_present(self) -> None:
        req = JSONRPCRequest(method="test", id="1")
        d = req.to_dict()
        assert "params" not in d
        req2 = JSONRPCRequest(method="test", params={"p": 1}, id="1")
        d2 = req2.to_dict()
        assert d2["params"] == {"p": 1}
