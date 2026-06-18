from __future__ import annotations

import time
from typing import Any
from unittest.mock import Mock, patch

from maref.integration.mcp_governance import (
    MCPDecisionVerdict,
    MCPGovernance,
    MCPGovernanceResult,
    MCPPolicyEngine,
    MCPPolicyRule,
)
from maref.integration.mcp_security import (
    OAuthTokenData,
    OAuthTokenProvider,
    ZeroTrustContext,
)
from maref.integration.mcp_server import MCPServer, SamplingHandler
from maref.integration.mcp_transport import (
    JSONRPCRequest,
)
from sidecar.mcp_gateway import (
    BackendRegistration,
    MCPGateway,
    _create_audit_signature,
)


# ============================================================================
# P1-1 Test 1: MCP Sampling Handler
# ============================================================================
class MockSamplingHandler(SamplingHandler):
    def __init__(self) -> None:
        self._last_messages: list[dict[str, Any]] = []

    def create_message(
        self,
        messages: list[dict[str, Any]],
        model_preferences: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        self._last_messages = messages
        return {
            "role": "assistant",
            "content": [{"type": "text", "text": "This is a mock response"}],
            "model": "mock-model",
        }


class TestMCPSamplingHandler:
    def test_sampling_handler_abstract(self):
        handler = MockSamplingHandler()
        result = handler.create_message(
            messages=[{"role": "user", "content": "Hello"}],
            model_preferences={"temperature": 0.7},
            system_prompt="You are a helpful assistant.",
            max_tokens=100,
        )
        assert result["role"] == "assistant"
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert result["model"] == "mock-model"

    def test_sampling_handler_no_system_prompt(self):
        handler = MockSamplingHandler()
        result = handler.create_message(
            messages=[{"role": "user", "content": "Hi"}],
        )
        assert result["role"] == "assistant"

    def test_sampling_via_mcp_server(self):
        handler = MockSamplingHandler()
        server = MCPServer(name="test-server", version="1.0", sampling_handler=handler)
        transport = server.get_inprocess_transport()
        transport.connect()

        request = JSONRPCRequest(
            jsonrpc="2.0",
            method="sampling/createMessage",
            params={
                "messages": [{"role": "user", "content": "Hello"}],
                "systemPrompt": "Be concise.",
                "maxTokens": 50,
            },
            id=1,
        )
        response = transport.send(request)
        assert response.result is not None
        assert response.result["role"] == "assistant"
        assert handler._last_messages == [{"role": "user", "content": "Hello"}]

    def test_sampling_missing_handler(self):
        server = MCPServer(name="test-server", version="1.0")
        transport = server.get_inprocess_transport()
        transport.connect()

        request = JSONRPCRequest(
            jsonrpc="2.0",
            method="sampling/createMessage",
            params={"messages": [{"role": "user", "content": "Hello"}]},
            id=1,
        )
        response = transport.send(request)
        assert response.error is not None
        assert "Sampling not supported" in response.error["message"]

    def test_sampling_handler_tracks_multiple_calls(self):
        handler = MockSamplingHandler()
        server = MCPServer(name="test-server", version="1.0", sampling_handler=handler)
        transport = server.get_inprocess_transport()
        transport.connect()

        for i in range(3):
            request = JSONRPCRequest(
                jsonrpc="2.0",
                method="sampling/createMessage",
                params={"messages": [{"role": "user", "content": f"Call {i}"}]},
                id=i + 1,
            )
            response = transport.send(request)
            assert response.result is not None

        assert len(handler._last_messages) == 1
        assert handler._last_messages[0]["content"] == "Call 2"


# ============================================================================
# P1-1 Test 2: MCP Roots Handler
# ============================================================================
class TestMCPRootsHandler:
    def test_roots_empty_by_default(self):
        server = MCPServer(name="test-server", version="1.0")
        transport = server.get_inprocess_transport()
        transport.connect()

        request = JSONRPCRequest(
            jsonrpc="2.0",
            method="roots/list",
            params={},
            id=1,
        )
        response = transport.send(request)
        assert response.result == {"roots": []}

    def test_roots_with_configured_values(self):
        roots = [
            {"uri": "file:///workspace/project-a", "name": "Project A"},
            {"uri": "file:///workspace/project-b", "name": "Project B"},
        ]
        server = MCPServer(name="test-server", version="1.0", roots=roots)
        transport = server.get_inprocess_transport()
        transport.connect()

        request = JSONRPCRequest(
            jsonrpc="2.0",
            method="roots/list",
            params={},
            id=1,
        )
        response = transport.send(request)
        assert "roots" in response.result
        assert len(response.result["roots"]) == 2
        assert response.result["roots"][0]["uri"] == "file:///workspace/project-a"
        assert response.result["roots"][1]["name"] == "Project B"

    def test_roots_overwrite_on_reinit(self):
        roots_a = [{"uri": "file:///a", "name": "A"}]
        roots_b = [{"uri": "file:///b", "name": "B"}]

        server1 = MCPServer(name="s1", version="1.0", roots=roots_a)
        transport1 = server1.get_inprocess_transport()
        transport1.connect()
        req1 = JSONRPCRequest(jsonrpc="2.0", method="roots/list", params={}, id=1)
        assert transport1.send(req1).result["roots"] == roots_a

        server2 = MCPServer(name="s2", version="1.0", roots=roots_b)
        transport2 = server2.get_inprocess_transport()
        transport2.connect()
        req2 = JSONRPCRequest(jsonrpc="2.0", method="roots/list", params={}, id=1)
        assert transport2.send(req2).result["roots"] == roots_b

    def test_roots_single_entry(self):
        roots = [{"uri": "memory://config", "name": "Config"}]
        server = MCPServer(name="test-server", version="1.0", roots=roots)
        transport = server.get_inprocess_transport()
        transport.connect()

        request = JSONRPCRequest(
            jsonrpc="2.0",
            method="roots/list",
            params={},
            id=1,
        )
        response = transport.send(request)
        assert response.result["roots"] == roots

    def test_roots_no_params(self):
        server = MCPServer(name="test-server", version="1.0")
        transport = server.get_inprocess_transport()
        transport.connect()

        request = JSONRPCRequest(
            jsonrpc="2.0",
            method="roots/list",
            params={},
            id=42,
        )
        response = transport.send(request)
        assert response.id == 42
        assert response.result == {"roots": []}


# ============================================================================
# P1-1 Test 3: OAuth Token Provider
# ============================================================================
class TestOAuthTokenProvider:
    def test_acquire_token_client_credentials(self):
        provider = OAuthTokenProvider(
            token_url="https://auth.example.com/oauth/token",
            client_id="test-client",
            client_secret="test-secret",
            flow="client_credentials",
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "mock-access-token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "maref:mcp",
        }

        with patch("httpx.post", return_value=mock_response):
            token = provider.get_token("https://server.example.com")
            assert token == "mock-access-token"

    def test_refresh_token_flow(self):
        provider = OAuthTokenProvider(
            token_url="https://auth.example.com/oauth/token",
            client_id="test-client",
            client_secret="test-secret",
        )

        stored = OAuthTokenData(
            access_token="expired-token",
            refresh_token="refresh-token-123",
            expires_at=time.time() - 100,
        )
        provider.store_token("https://server.example.com", stored)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "refreshed-token",
            "refresh_token": "new-refresh-token",
            "expires_in": 3600,
        }

        with patch("httpx.post", return_value=mock_response):
            token = provider.get_token("https://server.example.com")
            assert token == "refreshed-token"

    def test_store_and_retrieve_token(self):
        provider = OAuthTokenProvider(
            token_url="https://auth.example.com/oauth/token",
            client_id="test-client",
            client_secret="test-secret",
        )
        token_data = OAuthTokenData(
            access_token="stored-token",
            refresh_token="stored-refresh",
            expires_at=time.time() + 3600,
        )
        provider.store_token("https://server.example.com", token_data)

        result = provider.get_token("https://server.example.com")
        assert result == "stored-token"

    def test_acquire_expired_token(self):
        provider = OAuthTokenProvider(
            token_url="https://auth.example.com/oauth/token",
            client_id="test-client",
            client_secret="test-secret",
        )
        expired = OAuthTokenData(
            access_token="old-token",
            refresh_token="",
            expires_at=time.time() - 100,
        )
        provider.store_token("https://server.example.com", expired)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-token",
            "expires_in": 3600,
        }

        with patch("httpx.post", return_value=mock_response):
            token = provider.get_token("https://server.example.com")
            assert token == "new-token"

    def test_unsupported_flow_raises_error(self):
        provider = OAuthTokenProvider(
            token_url="https://auth.example.com/oauth/token",
            client_id="test-client",
            client_secret="test-secret",
            flow="authorization_code",
        )
        try:
            provider.get_token("https://server.example.com")
            raise AssertionError("Should have raised NotImplementedError")
        except NotImplementedError:
            pass

    def test_invalid_flow_raises_value_error(self):
        provider = OAuthTokenProvider(
            token_url="https://auth.example.com/oauth/token",
            client_id="test-client",
            client_secret="test-secret",
            flow="invalid_flow",
        )
        try:
            provider.get_token("https://server.example.com")
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "Unsupported" in str(e)

    def test_client_credentials_httpx_error(self):
        provider = OAuthTokenProvider(
            token_url="https://auth.example.com/oauth/token",
            client_id="test-client",
            client_secret="test-secret",
        )
        import httpx

        with patch("httpx.post", side_effect=httpx.RequestError("Connection failed")):
            try:
                provider.get_token("https://server.example.com")
                raise AssertionError("Should have raised RuntimeError")
            except RuntimeError as e:
                assert "request failed" in str(e)

    def test_refresh_fallback_to_acquire(self):
        provider = OAuthTokenProvider(
            token_url="https://auth.example.com/oauth/token",
            client_id="test-client",
            client_secret="test-secret",
        )
        expired = OAuthTokenData(
            access_token="old-token",
            refresh_token="",
            expires_at=time.time() - 100,
        )
        provider.store_token("https://server.example.com", expired)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "fresh-token",
            "expires_in": 3600,
        }

        with patch("httpx.post", return_value=mock_response):
            token = provider.refresh_token("https://server.example.com")
            assert token == "fresh-token"

    def test_refresh_with_stored_refresh(self):
        provider = OAuthTokenProvider(
            token_url="https://auth.example.com/oauth/token",
            client_id="test-client",
            client_secret="test-secret",
        )
        stored = OAuthTokenData(
            access_token="current-token",
            refresh_token="valid-refresh",
            expires_at=time.time() + 3600,
        )
        provider.store_token("https://server.example.com", stored)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "refreshed-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
        }

        with patch("httpx.post", return_value=mock_response):
            token = provider.refresh_token("https://server.example.com")
            assert token == "refreshed-access"


# ============================================================================
# P1-1 Test 4: MCPGateway Routing
# ============================================================================
class TestMCPGatewayRouting:
    def test_register_backend(self):
        gateway = MCPGateway()
        gateway.register_backend(
            prefix="github_",
            server_url="http://localhost:9001",
            transport_type="http",
            tools=[{"name": "github_list_repos", "description": "List repos"}],
        )
        backends = gateway.get_backends()
        assert "github_" in backends
        assert backends["github_"]["server_url"] == "http://localhost:9001"

    def test_route_tool_call_finds_backend_by_prefix(self):
        gateway = MCPGateway()
        gateway.register_backend(
            prefix="github_",
            server_url="http://localhost:9001",
        )

        result = gateway.route_tool_call("github_list_repos", {"username": "test"})
        assert "isError" in result

    def test_route_tool_call_no_backend(self):
        gateway = MCPGateway()
        result = gateway.route_tool_call("nonexistent_tool")
        assert result["isError"] is True
        assert "No backend registered" in result["content"][0]["text"]

    def test_route_tool_call_default_backend(self):
        default_backend = BackendRegistration(
            prefix="",
            server_url="http://localhost:9999",
            transport_type="in-process",
            handler=lambda name, args: {"content": [{"type": "text", "text": "default handler"}]},
        )
        gateway = MCPGateway(default_backend=default_backend)
        result = gateway.route_tool_call("any_tool")
        assert result["content"][0]["text"] == "default handler"

    def test_in_process_handler(self):
        def _handler(name: str, args: dict) -> dict[str, Any]:
            return {"content": [{"type": "text", "text": f"Handled {name} with {args}"}]}

        gateway = MCPGateway()
        gateway.register_backend(
            prefix="test_",
            transport_type="in-process",
            handler=_handler,
            tools=[{"name": "test_tool"}],
        )
        result = gateway.route_tool_call("test_tool", {"key": "value"})
        assert result["content"][0]["text"] == "Handled test_tool with {'key': 'value'}"

    def test_route_tool_call_produces_audit_log(self):
        def _handler(name: str, args: dict) -> dict[str, Any]:
            return {"content": [{"type": "text", "text": "ok"}]}

        gateway = MCPGateway()
        gateway.register_backend(
            prefix="safe_",
            transport_type="in-process",
            handler=_handler,
        )
        gateway.route_tool_call("safe_tool", {})
        log = gateway.get_audit_log()
        assert len(log) == 1
        assert log[0]["tool_name"] == "safe_tool"
        assert log[0]["verdict"] == "ALLOW"

    def test_audit_log_has_hmac_signature(self):
        def _handler(name: str, args: dict) -> dict[str, Any]:
            return {"content": [{"type": "text", "text": "ok"}]}

        gateway = MCPGateway()
        gateway.register_backend(
            prefix="safe_",
            transport_type="in-process",
            handler=_handler,
        )
        gateway.route_tool_call("safe_tool", {"a": 1})
        log = gateway.get_audit_log()
        assert "audit_signature" in log[0]
        assert len(log[0]["audit_signature"]) == 64

    def test_hmac_signature_verification(self):
        sig = _create_audit_signature(
            tool_name="test_tool",
            verdict="ALLOW",
            risk_score=0.0,
            args_hash="abc123",
            secret_key=b"test-key",
        )
        assert isinstance(sig, str)
        assert len(sig) == 64

    def test_security_gate_denies_call(self):
        class DenyAllGate:
            def check(self, tool_name, trust_level, args, context):
                from maref.integration.mcp_security import SecurityVerdict
                return SecurityVerdict.DENY

        gateway = MCPGateway(security_gate=DenyAllGate())
        gateway.register_backend(
            prefix="test_",
            transport_type="in-process",
            handler=lambda n, a: {"content": [{"type": "text", "text": "should not reach"}]},
        )
        result = gateway.route_tool_call("test_tool", {})
        assert result["isError"] is True
        assert "denied" in result["content"][0]["text"].lower()

    def test_policy_engine_denies_call(self):
        class DenyAllPolicy(MCPPolicyRule):
            def __init__(self):
                super().__init__(rule_id="deny-all", description="Deny all", priority=999)

            def evaluate(self, context):
                return MCPGovernanceResult(
                    verdict=MCPDecisionVerdict.DENY,
                    reason="Policy deny all",
                    risk_score=1.0,
                )

        engine = MCPPolicyEngine()
        engine._rules = []
        engine.add_rule(DenyAllPolicy())
        gateway = MCPGateway(policy_engine=engine)
        gateway.register_backend(
            prefix="test_",
            transport_type="in-process",
            handler=lambda n, a: {"content": [{"type": "text", "text": "should not reach"}]},
        )
        result = gateway.route_tool_call("test_tool", {})
        assert result["isError"] is True

    def test_gateway_circuit_breaker_integration(self):
        gov = MCPGovernance()
        gateway = MCPGateway(governance=gov)
        gateway.register_backend(
            prefix="test_",
            transport_type="in-process",
            handler=lambda n, a: {"content": [{"type": "text", "text": "ok"}]},
        )

        result = gateway.route_tool_call("test_tool", {})
        assert result is not None

    def test_route_tool_call_with_zero_trust_context(self):
        def _handler(name: str, args: dict) -> dict[str, Any]:
            return {"content": [{"type": "text", "text": "context-aware"}]}

        gateway = MCPGateway()
        gateway.register_backend(
            prefix="ctx_",
            transport_type="in-process",
            handler=_handler,
        )
        ctx = ZeroTrustContext(agent_id="agent-42", session_id="session-99")
        result = gateway.route_tool_call("ctx_tool", {}, context=ctx)
        assert result["content"][0]["text"] == "context-aware"
        log = gateway.get_audit_log()
        assert log[0]["agent_id"] == "agent-42"

    def test_list_all_tools(self):
        gateway = MCPGateway()
        gateway.register_backend(
            prefix="a_",
            transport_type="in-process",
            tools=[{"name": "a_tool"}, {"name": "b_tool"}],
            handler=lambda n, a: {"content": [{"type": "text", "text": "ok"}]},
        )
        gateway.register_backend(
            prefix="c_",
            transport_type="in-process",
            tools=[{"name": "c_tool"}],
            handler=lambda n, a: {"content": [{"type": "text", "text": "ok"}]},
        )
        all_tools = gateway.list_all_tools()
        names = [t["name"] for t in all_tools]
        assert "a_tool" in names
        assert "b_tool" in names
        assert "c_tool" in names

    def test_http_backend_failure_returns_error(self):
        gateway = MCPGateway()
        gateway.register_backend(
            prefix="http_",
            server_url="http://localhost:1",
            transport_type="http",
        )
        result = gateway.route_tool_call("http_tool", {"x": 1})
        assert result["isError"] is True

    def test_unsupported_transport(self):
        gateway = MCPGateway()
        gateway.register_backend(
            prefix="bad_",
            transport_type="grpc",
            handler=lambda n, a: {"content": [{"type": "text", "text": "should not reach"}]},
        )
        result = gateway.route_tool_call("bad_tool", {})
        assert result["isError"] is True
        assert "Unsupported transport" in result["content"][0]["text"]

    def test_gateway_health(self):
        gateway = MCPGateway()
        gateway.register_backend(prefix="test_", server_url="http://localhost:9000")
        from sidecar.mcp_gateway import create_mcp_gateway_router

        router = create_mcp_gateway_router(gateway)
        routes = [r.path for r in router.routes]
        assert "/api/mcp/gateway/health" in routes
        assert "/api/mcp/gateway/tools/call" in routes
        assert "/api/mcp/gateway/tools" in routes
