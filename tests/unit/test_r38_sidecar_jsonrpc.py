from __future__ import annotations

import json

from sidecar.jsonrpc_bridge import (
    JSONRPCErrorCode,
    JSONRPCRequest,
    JSONRPCResponse,
    SidecarJSONRPCBridge,
    SidecarMethod,
    SidecarRequest,
    SidecarResponse,
)


class TestJSONRPCRequest:
    def test_create_request(self) -> None:
        req = JSONRPCRequest(
            method="sidecar.observe",
            params={"agent_id": "test"},
        )
        assert req.jsonrpc == "2.0"
        assert req.method == "sidecar.observe"
        assert req.params["agent_id"] == "test"
        assert req.id != ""

    def test_to_dict(self) -> None:
        req = JSONRPCRequest(
            method="sidecar.get_state",
            params={"namespace": "default"},
            id="req_1",
        )
        d = req.to_dict()
        assert d["jsonrpc"] == "2.0"
        assert d["method"] == "sidecar.get_state"
        assert d["id"] == "req_1"
        assert d["params"]["namespace"] == "default"

    def test_from_dict(self) -> None:
        data = {
            "jsonrpc": "2.0",
            "method": "sidecar.health_check",
            "params": {"verbose": True},
            "id": "hc_1",
        }
        req = JSONRPCRequest.from_dict(data)
        assert req.method == "sidecar.health_check"
        assert req.params["verbose"] is True
        assert req.id == "hc_1"

    def test_to_json_and_back(self) -> None:
        req = JSONRPCRequest(
            method="sidecar.list_agents",
            params={"namespace": "prod"},
            id="la_1",
        )
        json_str = req.to_json()
        parsed = JSONRPCRequest.from_json(json_str)
        assert parsed.method == req.method
        assert parsed.id == req.id
        assert parsed.params == req.params

    def test_default_id_generated(self) -> None:
        req = JSONRPCRequest(method="test.method")
        assert req.id != ""
        assert isinstance(req.id, str)


class TestJSONRPCResponse:
    def test_success_response(self) -> None:
        resp = JSONRPCResponse.success({"status": "healthy"}, req_id="r_1")
        assert resp.is_error is False
        assert resp.result["status"] == "healthy"
        assert resp.id == "r_1"

    def test_error_response(self) -> None:
        resp = JSONRPCResponse.error_response(
            JSONRPCErrorCode.METHOD_NOT_FOUND,
            "Method 'bad' not found",
            req_id="r_2",
        )
        assert resp.is_error is True
        assert resp.error is not None
        assert resp.error.code == JSONRPCErrorCode.METHOD_NOT_FOUND
        assert resp.error.message == "Method 'bad' not found"

    def test_success_to_dict(self) -> None:
        resp = JSONRPCResponse.success({"foo": "bar"}, req_id="s_1")
        d = resp.to_dict()
        assert d["jsonrpc"] == "2.0"
        assert d["id"] == "s_1"
        assert d["result"]["foo"] == "bar"
        assert "error" not in d

    def test_error_to_dict(self) -> None:
        resp = JSONRPCResponse.error_response(
            JSONRPCErrorCode.INTERNAL_ERROR,
            "Something broke",
            req_id="e_1",
        )
        d = resp.to_dict()
        assert "error" in d
        assert d["error"]["code"] == -32603
        assert d["error"]["message"] == "Something broke"

    def test_success_to_json(self) -> None:
        resp = JSONRPCResponse.success([1, 2, 3], req_id="j_1")
        json_str = resp.to_json()
        data = json.loads(json_str)
        assert data["result"] == [1, 2, 3]

    def test_error_to_json(self) -> None:
        resp = JSONRPCResponse.error_response(
            JSONRPCErrorCode.SAFETY_GATE_BLOCKED,
            "Threat detected",
            req_id="j_e",
        )
        json_str = resp.to_json()
        data = json.loads(json_str)
        assert data["error"]["code"] == -32002


class TestSidecarMethod:
    def test_all_methods(self) -> None:
        methods = list(SidecarMethod)
        assert len(methods) == 10

    def test_method_values(self) -> None:
        assert SidecarMethod.OBSERVE.value == "sidecar.observe"
        assert SidecarMethod.GET_STATE.value == "sidecar.get_state"
        assert SidecarMethod.HEALTH_CHECK.value == "sidecar.health_check"
        assert SidecarMethod.GET_CORRELATION.value == "sidecar.get_correlation"
        assert SidecarMethod.MIGRATE.value == "sidecar.migrate"


class TestSidecarRequest:
    def test_create(self) -> None:
        req = SidecarRequest.create(
            SidecarMethod.GET_ENTROPY,
            params={"source": "agent_1"},
            req_id="se_1",
        )
        assert req.method == "sidecar.get_entropy"
        assert req.id == "se_1"
        assert req.params["source"] == "agent_1"

    def test_default_id(self) -> None:
        req = SidecarRequest.create(SidecarMethod.LIST_AGENTS)
        assert req.method == "sidecar.list_agents"
        assert req.id != ""


class TestSidecarResponse:
    def test_from_success_json(self) -> None:
        json_str = json.dumps(
            {
                "jsonrpc": "2.0",
                "result": {"agents": 5},
                "id": "sr_1",
            }
        )
        resp = SidecarResponse.from_json_rpc(json_str)
        assert resp.is_error is False
        assert resp.result["agents"] == 5

    def test_from_error_json(self) -> None:
        json_str = json.dumps(
            {
                "jsonrpc": "2.0",
                "error": {"code": -32001, "message": "Governance rejected"},
                "id": "sr_err",
            }
        )
        resp = SidecarResponse.from_json_rpc(json_str)
        assert resp.is_error is True


class TestSidecarJSONRPCBridge:
    def setup_method(self) -> None:
        self.bridge = SidecarJSONRPCBridge()

    def test_default_handlers_registered(self) -> None:
        assert self.bridge.handler_count >= len(SidecarMethod)

    def test_handle_valid_request(self) -> None:
        req = JSONRPCRequest(
            method="sidecar.health_check",
            params={"detail": True},
            id="b_1",
        )
        resp = self.bridge.handle(req)
        assert resp.is_error is False
        assert "sidecar_version" in resp.result

    def test_handle_invalid_json(self) -> None:
        resp = self.bridge.handle("not json")
        assert resp.is_error is True
        assert resp.error is not None
        assert resp.error.code == JSONRPCErrorCode.PARSE_ERROR

    def test_handle_wrong_version(self) -> None:
        req = JSONRPCRequest(
            jsonrpc="1.0",
            method="sidecar.observe",
            id="bad_ver",
        )
        resp = self.bridge.handle(req)
        assert resp.is_error is True
        assert resp.id == "bad_ver"

    def test_handle_unknown_method(self) -> None:
        req = JSONRPCRequest(
            method="sidecar.unknown_method",
            id="um_1",
        )
        resp = self.bridge.handle(req)
        assert resp.is_error is True
        assert resp.error.code == JSONRPCErrorCode.METHOD_NOT_FOUND

    def test_custom_handler(self) -> None:
        def custom_handler(params: dict) -> dict:
            return {"custom": params.get("key", "default")}

        self.bridge.register_handler("custom.method", custom_handler)
        req = JSONRPCRequest(
            method="custom.method",
            params={"key": "value"},
            id="c_1",
        )
        resp = self.bridge.handle(req)
        assert resp.is_error is False
        assert resp.result["custom"] == "value"

    def test_handler_with_exception(self) -> None:
        def fault_handler(params: dict) -> None:
            raise ValueError("Simulated error")

        self.bridge.register_handler("fault.method", fault_handler)
        req = JSONRPCRequest(
            method="fault.method",
            id="f_1",
        )
        resp = self.bridge.handle(req)
        assert resp.is_error is True
        assert resp.error.code == JSONRPCErrorCode.INTERNAL_ERROR

    def test_response_history(self) -> None:
        req = JSONRPCRequest(
            method="sidecar.get_state",
            id="hist_1",
        )
        self.bridge.handle(req)
        assert len(self.bridge.response_history) == 1

    def test_clear_history(self) -> None:
        req = JSONRPCRequest(method="sidecar.get_state", id="cl_1")
        self.bridge.handle(req)
        self.bridge.clear_history()
        assert len(self.bridge.response_history) == 0

    def test_handle_all_sidecar_methods(self) -> None:
        for method in SidecarMethod:
            req = JSONRPCRequest(
                method=method.value,
                params={},
                id=f"all_{method.name}",
            )
            resp = self.bridge.handle(req)
            assert resp.is_error is False
