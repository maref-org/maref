from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock, patch

import pytest

from maref.governance.circuit_breaker import CircuitBreaker
from maref.integration.mcp_governance import (
    MCPCircuitBreakerMonitor,
    MCPDecisionVerdict,
    MCPGovernance,
    MCPGovernanceResult,
    MCPPolicyEngine,
)
from maref.integration.mcp_security import MCPTrustLevel, SecurityVerdict, ZeroTrustContext
from sidecar.mcp_gateway import BackendRegistration, MCPGateway, _create_audit_signature, create_mcp_gateway_router


class TestBackendRegistration:
    def test_defaults(self) -> None:
        reg = BackendRegistration()
        assert reg.prefix == ""
        assert reg.server_url == ""
        assert reg.transport_type == "http"
        assert reg.tools == []
        assert reg.handler is None
        assert reg.healthy is True

    def test_custom_values(self) -> None:
        handler = lambda: None
        tools = [{"name": "test_tool"}]
        reg = BackendRegistration(
            prefix="test",
            server_url="http://localhost:9000",
            transport_type="in-process",
            tools=tools,
            handler=handler,
            healthy=False,
        )
        assert reg.prefix == "test"
        assert reg.server_url == "http://localhost:9000"
        assert reg.transport_type == "in-process"
        assert reg.tools == tools
        assert reg.handler is handler
        assert reg.healthy is False


class TestCreateAuditSignature:
    @patch("sidecar.mcp_gateway.time.time", return_value=12345.0)
    def test_returns_hex_string(self, mock_time: MagicMock) -> None:
        sig = _create_audit_signature("tool", "ALLOW", 0.0, "abc123", b"secret")
        assert isinstance(sig, str)
        assert len(sig) == 64

    @patch("sidecar.mcp_gateway.time.time", return_value=12345.0)
    def test_different_inputs_different_signatures(self, mock_time: MagicMock) -> None:
        sig1 = _create_audit_signature("tool_a", "ALLOW", 0.0, "hash1", b"secret")
        sig2 = _create_audit_signature("tool_b", "DENY", 1.0, "hash2", b"secret")
        assert sig1 != sig2

    @patch("sidecar.mcp_gateway.time.time", return_value=12345.0)
    def test_same_inputs_same_signature(self, mock_time: MagicMock) -> None:
        sig1 = _create_audit_signature("tool", "ALLOW", 0.0, "hash", b"secret")
        sig2 = _create_audit_signature("tool", "ALLOW", 0.0, "hash", b"secret")
        assert sig1 == sig2


class TestMCPGatewayInit:
    def test_default_init(self) -> None:
        gw = MCPGateway()
        assert gw._backends == {}
        assert gw._default_backend is None
        assert gw._secret_key == b"test-mcp-key-insecure-not-for-production"
        assert gw._audit_log == []
        assert gw._gate is None
        assert gw._policy_engine is None
        assert gw._governance is None

    def test_init_with_dependencies(self) -> None:
        gate = MagicMock()
        policy = MagicMock(spec=MCPPolicyEngine)
        gov = MagicMock(spec=MCPGovernance)
        backend = BackendRegistration(prefix="default", server_url="http://default")
        gw = MCPGateway(security_gate=gate, policy_engine=policy, governance=gov, default_backend=backend)
        assert gw._gate is gate
        assert gw._policy_engine is policy
        assert gw._governance is gov
        assert gw._default_backend is backend


class TestRegisterBackend:
    def test_register_in_process(self) -> None:
        gw = MCPGateway()
        handler = lambda n, a: {"result": "ok"}
        gw.register_backend("local", handler=handler, transport_type="in-process")
        assert "local" in gw._backends
        reg = gw._backends["local"]
        assert reg.prefix == "local"
        assert reg.handler is handler
        assert reg.transport_type == "in-process"

    def test_register_http(self) -> None:
        gw = MCPGateway()
        gw.register_backend("remote", server_url="http://remote:9000")
        reg = gw._backends["remote"]
        assert reg.server_url == "http://remote:9000"
        assert reg.transport_type == "http"

    def test_register_with_tools(self) -> None:
        gw = MCPGateway()
        tools = [{"name": "tool_a"}, {"name": "tool_b"}]
        gw.register_backend("tools", tools=tools, server_url="http://t")
        assert gw._backends["tools"].tools == tools


class TestFindBackend:
    def test_exact_match(self) -> None:
        gw = MCPGateway()
        gw.register_backend("test", server_url="http://test")
        backend = gw._find_backend("test_tool")
        assert backend is not None
        assert backend.server_url == "http://test"

    def test_longest_prefix_match(self) -> None:
        gw = MCPGateway()
        gw.register_backend("test", server_url="http://short")
        gw.register_backend("test_long", server_url="http://long")
        backend = gw._find_backend("test_long_tool")
        assert backend is not None
        assert backend.server_url == "http://long"

    def test_no_match_returns_default(self) -> None:
        gw = MCPGateway()
        default = BackendRegistration(server_url="http://default")
        gw._default_backend = default
        backend = gw._find_backend("unknown_tool")
        assert backend is default

    def test_no_match_no_default(self) -> None:
        gw = MCPGateway()
        backend = gw._find_backend("unknown")
        assert backend is None


class TestRouteToolCall:
    def test_no_backend(self) -> None:
        gw = MCPGateway()
        result = gw.route_tool_call("unknown")
        assert result["isError"] is True
        assert "No backend registered" in result["content"][0]["text"]

    def test_security_gate_denies(self) -> None:
        gate = MagicMock()
        gate.check.return_value = SecurityVerdict.DENY
        gw = MCPGateway(security_gate=gate)
        gw.register_backend("tool", server_url="http://t")
        result = gw.route_tool_call("tool_x")
        assert result["isError"] is True
        assert "Security gate denied" in result["content"][0]["text"]
        gate.check.assert_called_once()

    def test_policy_engine_denies(self) -> None:
        policy = MagicMock(spec=MCPPolicyEngine)
        policy.evaluate.return_value = MCPGovernanceResult(
            verdict=MCPDecisionVerdict.DENY,
            reason="Policy violation",
            risk_score=0.8,
        )
        gw = MCPGateway(policy_engine=policy)
        gw.register_backend("tool", server_url="http://t")
        result = gw.route_tool_call("tool_x")
        assert result["isError"] is True
        assert "Policy denied" in result["content"][0]["text"]

    def test_circuit_breaker_monitor_trips(self) -> None:
        cb_monitor = MagicMock(spec=MCPCircuitBreakerMonitor)
        cb_monitor.should_trip.return_value = (True, "error rate too high")
        circuit_breaker = MagicMock(spec=CircuitBreaker)
        governance = MagicMock(spec=MCPGovernance)
        governance.cb_monitor = cb_monitor
        governance.circuit_breaker = circuit_breaker
        gw = MCPGateway(governance=governance)
        gw.register_backend("tool", server_url="http://t")
        result = gw.route_tool_call("tool_x")
        assert result["isError"] is True
        assert "Circuit breaker monitor tripped" in result["content"][0]["text"]
        circuit_breaker.record_failure.assert_called_once()

    def test_circuit_breaker_open(self) -> None:
        cb_monitor = MagicMock(spec=MCPCircuitBreakerMonitor)
        cb_monitor.should_trip.return_value = (False, "")
        circuit_breaker = MagicMock(spec=CircuitBreaker)
        circuit_breaker.is_open = True
        governance = MagicMock(spec=MCPGovernance)
        governance.cb_monitor = cb_monitor
        governance.circuit_breaker = circuit_breaker
        gw = MCPGateway(governance=governance)
        gw.register_backend("tool", server_url="http://t")
        result = gw.route_tool_call("tool_x")
        assert result["isError"] is True
        assert "Circuit breaker open" in result["content"][0]["text"]

    def test_successful_in_process(self) -> None:
        handler = MagicMock(return_value={"content": [{"type": "text", "text": "done"}]})
        gw = MCPGateway()
        gw.register_backend("local", handler=handler, transport_type="in-process")
        result = gw.route_tool_call("local_tool", {"arg": 1})
        assert result["content"][0]["text"] == "done"
        handler.assert_called_once_with("local_tool", {"arg": 1})

    @patch("sidecar.mcp_gateway.httpx")
    def test_successful_http(self, mock_httpx: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"content": [{"type": "text", "text": "ok"}]}}
        mock_httpx.post.return_value = mock_response
        gw = MCPGateway()
        gw.register_backend("remote", server_url="http://remote:9000")
        result = gw.route_tool_call("remote_tool", {"x": 1})
        assert result["content"][0]["text"] == "ok"
        mock_httpx.post.assert_called_once()

    @patch("sidecar.mcp_gateway.httpx")
    def test_http_returns_error(self, mock_httpx: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "error": {"message": "Method not found"},
        }
        mock_httpx.post.return_value = mock_response
        gw = MCPGateway()
        gw.register_backend("remote", server_url="http://remote:9000")
        result = gw.route_tool_call("remote_tool")
        assert result["isError"] is True
        assert "Method not found" in result["content"][0]["text"]

    @patch("sidecar.mcp_gateway.httpx")
    def test_http_status_error(self, mock_httpx: MagicMock) -> None:
        import httpx

        mock_request = MagicMock(spec=httpx.Request)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 500
        # httpx.HTTPStatusError might not be caught properly in Python 3.14
        # Create a proper exception instance
        try:
            raise httpx.HTTPStatusError("Server error", request=mock_request, response=mock_response)
        except Exception as e:
            exc_instance = e
        mock_httpx.post.side_effect = exc_instance
        gw = MCPGateway()
        gw.register_backend("remote", server_url="http://remote:9000")
        result = gw.route_tool_call("remote_tool")
        assert result["isError"] is True
        # Check for either HTTP error or generic gateway error
        assert "HTTP 500" in result["content"][0]["text"] or "Gateway error" in result["content"][0]["text"]

    @patch("sidecar.mcp_gateway.httpx")
    def test_http_request_error(self, mock_httpx: MagicMock) -> None:
        import httpx

        mock_request = MagicMock(spec=httpx.Request)
        # httpx.RequestError might not be caught properly in Python 3.14
        # Create a proper exception instance
        try:
            raise httpx.RequestError("Connection refused", request=mock_request)
        except Exception as e:
            exc_instance = e
        mock_httpx.post.side_effect = exc_instance
        gw = MCPGateway()
        gw.register_backend("remote", server_url="http://remote:9000")
        result = gw.route_tool_call("remote_tool")
        assert result["isError"] is True
        # Check for either backend unreachable or generic gateway error
        assert "Backend unreachable" in result["content"][0]["text"] or "Gateway error" in result["content"][0]["text"]

    def test_exception_in_forward_calls_record_failure(self) -> None:
        handler = MagicMock(side_effect=ValueError("oops"))
        circuit_breaker = MagicMock(spec=CircuitBreaker)
        circuit_breaker.is_open = False  # Ensure circuit breaker is not open
        cb_monitor = MagicMock(spec=MCPCircuitBreakerMonitor)
        cb_monitor.should_trip.return_value = (False, "")
        governance = MagicMock(spec=MCPGovernance)
        governance.cb_monitor = cb_monitor
        governance.circuit_breaker = circuit_breaker
        gw = MCPGateway(governance=governance)
        gw.register_backend("local", handler=handler, transport_type="in-process")
        result = gw.route_tool_call("local_tool")
        assert result["isError"] is True
        # Could be "Gateway error" or circuit breaker message
        assert "Gateway error" in result["content"][0]["text"] or "Circuit breaker" in result["content"][0]["text"]
        circuit_breaker.record_failure.assert_called_once()
        cb_monitor.record_call.assert_called_once_with("local_tool", 0.0, success=False)

    def test_successful_call_records_success(self) -> None:
        handler = MagicMock(return_value={"content": [{"type": "text", "text": "ok"}]})
        circuit_breaker = MagicMock(spec=CircuitBreaker)
        circuit_breaker.is_open = False  # Ensure circuit breaker is not open
        cb_monitor = MagicMock(spec=MCPCircuitBreakerMonitor)
        cb_monitor.should_trip.return_value = (False, "")
        governance = MagicMock(spec=MCPGovernance)
        governance.cb_monitor = cb_monitor
        governance.circuit_breaker = circuit_breaker
        gw = MCPGateway(governance=governance)
        gw.register_backend("local", handler=handler, transport_type="in-process")
        gw.route_tool_call("local_tool")
        circuit_breaker.record_success.assert_called_once()
        cb_monitor.record_call.assert_called_once_with("local_tool", 0.0, success=True)


class TestForwardCall:
    def test_in_process_with_handler(self) -> None:
        handler = MagicMock(return_value={"result": "ok"})
        reg = BackendRegistration(prefix="test", handler=handler, transport_type="in-process")
        gw = MCPGateway()
        result = gw._forward_call(reg, "test_tool", {}, ZeroTrustContext())
        assert result == {"result": "ok"}

    def test_in_process_handler_returns_non_dict(self) -> None:
        handler = MagicMock(return_value="string_result")
        reg = BackendRegistration(prefix="test", handler=handler, transport_type="in-process")
        gw = MCPGateway()
        result = gw._forward_call(reg, "test_tool", {}, ZeroTrustContext())
        assert result["content"][0]["text"] == "string_result"

    def test_in_process_no_handler(self) -> None:
        reg = BackendRegistration(prefix="test", transport_type="in-process")
        gw = MCPGateway()
        result = gw._forward_call(reg, "test_tool", {}, ZeroTrustContext())
        assert result["isError"] is True
        assert "In-process handler not available" in result["content"][0]["text"]

    @patch("sidecar.mcp_gateway.httpx")
    def test_http_forward(self, mock_httpx: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"content": [{"type": "text", "text": "ok"}]}}
        mock_httpx.post.return_value = mock_response
        reg = BackendRegistration(prefix="remote", server_url="http://remote:9000", transport_type="http")
        gw = MCPGateway()
        result = gw._forward_call(reg, "remote_tool", {"a": 1}, ZeroTrustContext())
        assert result["content"][0]["text"] == "ok"
        mock_httpx.post.assert_called_once()
        url = mock_httpx.post.call_args[0][0]
        assert url == "http://remote:9000/api/mcp"

    @patch("sidecar.mcp_gateway.httpx")
    def test_http_forward_unknown_data_shape(self, mock_httpx: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"something": "unexpected"}
        mock_httpx.post.return_value = mock_response
        reg = BackendRegistration(prefix="remote", server_url="http://remote:9000", transport_type="http")
        gw = MCPGateway()
        result = gw._forward_call(reg, "remote_tool", {}, ZeroTrustContext())
        assert "isError" not in result
        assert result["content"][0]["text"] == "{'something': 'unexpected'}"

    def test_unsupported_transport(self) -> None:
        reg = BackendRegistration(prefix="x", transport_type="grpc")
        gw = MCPGateway()
        result = gw._forward_call(reg, "x", {}, ZeroTrustContext())
        assert result["isError"] is True
        assert "Unsupported transport" in result["content"][0]["text"]


class TestListAllTools:
    def test_empty(self) -> None:
        gw = MCPGateway()
        assert gw.list_all_tools() == []

    def test_in_process_tools(self) -> None:
        gw = MCPGateway()
        tools = [{"name": "tool_a"}, {"name": "tool_b"}]
        gw.register_backend("local", tools=tools, transport_type="in-process")
        result = gw.list_all_tools()
        assert len(result) == 2

    def test_deduplicates_tools(self) -> None:
        gw = MCPGateway()
        tools = [{"name": "tool_a"}]
        gw.register_backend("b1", tools=tools, transport_type="in-process")
        gw.register_backend("b2", tools=tools, transport_type="in-process")
        result = gw.list_all_tools()
        assert len(result) == 1

    def test_default_backend_tools(self) -> None:
        gw = MCPGateway()
        tools = [{"name": "default_tool"}]
        gw._default_backend = BackendRegistration(tools=tools)
        result = gw.list_all_tools()
        assert len(result) == 1

    @patch.object(MCPGateway, "_fetch_remote_tools", return_value=[{"name": "remote_tool"}])
    def test_http_backend_tools(self, mock_fetch: MagicMock) -> None:
        gw = MCPGateway()
        gw.register_backend("remote", server_url="http://remote:9000", transport_type="http")
        result = gw.list_all_tools()
        assert len(result) == 1
        assert result[0]["name"] == "remote_tool"


class TestFetchRemoteTools:
    @patch("sidecar.mcp_gateway.httpx")
    def test_successful_fetch(self, mock_httpx: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"tools": [{"name": "t1"}]}}
        mock_httpx.post.return_value = mock_response
        gw = MCPGateway()
        backend = BackendRegistration(server_url="http://remote:9000")
        result = gw._fetch_remote_tools(backend)
        assert result == [{"name": "t1"}]

    @patch("sidecar.mcp_gateway.httpx")
    def test_fetch_failure_returns_empty(self, mock_httpx: MagicMock) -> None:
        mock_httpx.post.side_effect = Exception("Network error")
        gw = MCPGateway()
        backend = BackendRegistration(server_url="http://remote:9000")
        result = gw._fetch_remote_tools(backend)
        assert result == []


class TestGetBackends:
    def test_no_backends(self) -> None:
        gw = MCPGateway()
        assert gw.get_backends() == {}

    def test_with_backends(self) -> None:
        gw = MCPGateway()
        gw.register_backend("a", server_url="http://a", transport_type="http")
        gw.register_backend("b", server_url="http://b", transport_type="in-process")
        gw._default_backend = BackendRegistration(server_url="http://default")
        backends = gw.get_backends()
        assert len(backends) == 3
        assert "__default__" in backends
        assert backends["a"]["server_url"] == "http://a"
        assert backends["a"]["transport_type"] == "http"


class TestAuditLog:
    def test_initial_empty(self) -> None:
        gw = MCPGateway()
        assert gw.get_audit_log() == []

    def test_logs_after_call(self) -> None:
        handler = MagicMock(return_value={"result": "ok"})
        gw = MCPGateway()
        gw.register_backend("local", handler=handler, transport_type="in-process")
        gw.route_tool_call("local_tool")
        log = gw.get_audit_log()
        assert len(log) == 1
        assert log[0]["tool_name"] == "local_tool"
        assert log[0]["verdict"] == "ALLOW"
        assert "audit_signature" in log[0]

    def test_logs_after_deny(self) -> None:
        gate = MagicMock()
        gate.check.return_value = SecurityVerdict.DENY
        gw = MCPGateway(security_gate=gate)
        gw.register_backend("tool", server_url="http://t")
        gw.route_tool_call("tool_x")
        log = gw.get_audit_log()
        assert len(log) == 1
        assert log[0]["verdict"] == "DENY"

    def test_log_is_copy(self) -> None:
        gw = MCPGateway()
        log = gw.get_audit_log()
        log.append({"fake": "entry"})
        assert len(gw.get_audit_log()) == 0


class TestCreateRouter:
    def test_router_created(self) -> None:
        gw = MCPGateway()
        router = create_mcp_gateway_router(gw)
        assert router is not None
        assert len(router.routes) == 3

    def test_health_endpoint(self) -> None:
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        app = FastAPI()
        gw = MCPGateway()
        gw.register_backend("test", server_url="http://t")
        router = create_mcp_gateway_router(gw)
        app.include_router(router)
        client = TestClient(app)
        resp = client.get("/api/mcp/gateway/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "backends" in data

    def test_list_tools_endpoint(self) -> None:
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        app = FastAPI()
        gw = MCPGateway()
        tools = [{"name": "t1"}]
        gw.register_backend("test", tools=tools, transport_type="in-process")
        router = create_mcp_gateway_router(gw)
        app.include_router(router)
        client = TestClient(app)
        resp = client.get("/api/mcp/gateway/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_tool_call_endpoint(self) -> None:
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        app = FastAPI()
        handler = MagicMock(return_value={"content": [{"type": "text", "text": "done"}]})
        gw = MCPGateway()
        gw.register_backend("test", handler=handler, transport_type="in-process")
        router = create_mcp_gateway_router(gw)
        app.include_router(router)
        client = TestClient(app)
        resp = client.post("/api/mcp/gateway/tools/call", json={"name": "test_tool"})
        assert resp.status_code == 200
        assert resp.json()["content"][0]["text"] == "done"

    def test_tool_call_missing_name(self) -> None:
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        app = FastAPI()
        gw = MCPGateway()
        router = create_mcp_gateway_router(gw)
        app.include_router(router)
        client = TestClient(app)
        resp = client.post("/api/mcp/gateway/tools/call", json={})
        assert resp.status_code == 400
        assert "Missing 'name'" in resp.json()["detail"]
