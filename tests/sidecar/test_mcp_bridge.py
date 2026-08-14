from __future__ import annotations

from typing import Any

import pytest

from sidecar.mcp_bridge import (
    MCPBridge,
    MCPGovernanceInterceptor,
    MCPResourceURI,
    MCPToolDefinition,
    SIDECAR_MCP_RESOURCES,
    SIDECAR_MCP_TOOLS,
    SidecarMCPBridge,
)
from sidecar.protocol import AgentId, Observation, ObservationType


class TestMCPResourceURI:
    def test_default_construction(self) -> None:
        uri = MCPResourceURI()
        assert uri.scheme == "maref"
        assert uri.resource_type == "agents"
        assert uri.namespace == "default"
        assert uri.name == ""
        assert uri.instance == ""

    def test_to_uri_without_instance(self) -> None:
        uri = MCPResourceURI(name="agent-1")
        assert uri.to_uri() == "maref://agents/default/agent-1"

    def test_to_uri_with_instance(self) -> None:
        uri = MCPResourceURI(name="agent-1", instance="v2")
        assert uri.to_uri() == "maref://agents/default/agent-1#v2"

    def test_to_uri_custom_scheme(self) -> None:
        uri = MCPResourceURI(scheme="custom", resource_type="tools", namespace="ns", name="cmd")
        assert uri.to_uri() == "custom://tools/ns/cmd"

    def test_from_agent_id(self) -> None:
        agent = AgentId(namespace="ns", name="worker", instance="i1")
        uri = MCPResourceURI.from_agent_id(agent)
        assert uri.namespace == "ns"
        assert uri.name == "worker"
        assert uri.instance == "i1"
        assert uri.to_uri() == "maref://agents/ns/worker#i1"

    def test_from_agent_id_empty_instance(self) -> None:
        agent = AgentId(namespace="ns", name="worker")
        uri = MCPResourceURI.from_agent_id(agent)
        assert uri.instance == ""
        assert uri.to_uri() == "maref://agents/ns/worker"

    def test_from_observation(self) -> None:
        obs = Observation(obs_type=ObservationType.ENTROPY_METRIC, source="agent-a")
        uri = MCPResourceURI.from_observation(obs)
        assert uri.resource_type == "observations/entropy_metric"
        assert uri.name == "agent-a"
        assert uri.to_uri() == "maref://observations/entropy_metric/default/agent-a"

    def test_from_observation_unknown_type(self) -> None:
        obs = Observation(source="src")
        obs.obs_type = None  # type: ignore[assignment]
        uri = MCPResourceURI.from_observation(obs)
        assert uri.resource_type == "observations/unknown"

    def test_from_observation_with_none_type(self) -> None:
        obs = Observation(source="src")
        obs.obs_type = None  # type: ignore[assignment]
        uri = MCPResourceURI.from_observation(obs)
        assert uri.resource_type == "observations/unknown"


class TestMCPToolDefinition:
    def test_default_construction(self) -> None:
        tool = MCPToolDefinition()
        assert tool.name == ""
        assert tool.description == ""
        assert tool.input_schema == {"type": "object", "properties": {}}

    def test_to_dict(self) -> None:
        tool = MCPToolDefinition(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {"arg": {"type": "string"}}},
        )
        d = tool.to_dict()
        assert d["name"] == "test_tool"
        assert d["description"] == "A test tool"
        assert d["inputSchema"] == {"type": "object", "properties": {"arg": {"type": "string"}}}


class TestSIDECAR_MCP_TOOLS:
    def test_has_expected_tools(self) -> None:
        names = {t.name for t in SIDECAR_MCP_TOOLS}
        expected = {
            "maref_observe_agent",
            "maref_read_entropy",
            "maref_read_observations",
            "maref_read_anomalies",
            "maref_compliance_check",
            "maref_ingest_signal",
            "maref_list_agents",
            "maref_get_snapshot",
            "maref_health_check",
            "maref_get_correlation",
            "maref_migrate",
            "maref_verifier_list",
            "maref_verifier_check",
            "maref_verifier_history",
            "maref_run_evolution",
            "maref_get_evolution_status",
            "maref_list_evolution_results",
            "maref_pty_exec",
            "gov_check_phase_gate",
            "gov_verify_output",
        }
        assert names == expected

    def test_each_has_name_and_description(self) -> None:
        for tool in SIDECAR_MCP_TOOLS:
            assert tool.name != ""
            assert tool.description != ""

    def test_each_has_input_schema(self) -> None:
        for tool in SIDECAR_MCP_TOOLS:
            assert "type" in tool.input_schema
            assert "properties" in tool.input_schema


class TestSIDECAR_MCP_RESOURCES:
    def test_has_expected_count(self) -> None:
        assert len(SIDECAR_MCP_RESOURCES) == 4

    def test_each_has_uri_and_name(self) -> None:
        for res in SIDECAR_MCP_RESOURCES:
            assert "uri" in res
            assert "name" in res
            assert "mimeType" in res
            assert res["mimeType"] == "application/json"

    def test_uris_use_maref_scheme(self) -> None:
        for res in SIDECAR_MCP_RESOURCES:
            assert res["uri"].startswith("maref://")


class TestMCPBridge:
    @pytest.mark.asyncio
    async def test_handle_request(self) -> None:
        bridge = MCPBridge()
        result = await bridge.handle_request({"method": "test"})
        assert result == {"status": "ok"}


class TestMCPGovernanceInterceptor:
    @pytest.mark.asyncio
    async def test_intercept_passthrough(self) -> None:
        interceptor = MCPGovernanceInterceptor()
        result = await interceptor.intercept({"method": "test"})
        assert result == {"method": "test"}

    @pytest.mark.asyncio
    async def test_intercept_modifies_request(self) -> None:
        interceptor = MCPGovernanceInterceptor()
        req: dict[str, Any] = {"key": "value"}
        result = await interceptor.intercept(req)
        assert result is req


class TestSidecarMCPBridge:
    def test_init_defaults(self) -> None:
        bridge = SidecarMCPBridge()
        assert bridge._probe is None

    def test_init_with_probe(self) -> None:
        probe = MagicMock()
        bridge = SidecarMCPBridge(exfiltration_probe=probe)
        assert bridge._probe is probe

    def test_get_server_info(self) -> None:
        bridge = SidecarMCPBridge()
        info = bridge.get_server_info()
        assert info["protocolVersion"] == "2024-11-05"
        assert info["serverInfo"]["name"] == "MAREF Sidecar"
        assert info["serverInfo"]["version"] == "0.35.0-beta"
        assert "capabilities" in info

    def test_get_capabilities(self) -> None:
        bridge = SidecarMCPBridge()
        caps = bridge.get_capabilities()
        assert caps == {"tools": {}, "resources": {}, "prompts": {}}

    def test_list_tools(self, monkeypatch: pytest.MonkeyPatch) -> None:
        bridge = SidecarMCPBridge()
        # claude-mem backend.start() / codedepth build() 在 CI 上会阻塞或超时，
        # mock 掉延迟初始化，只验证 sidecar 工具集合本身。
        monkeypatch.setattr(bridge, "_get_cm_backend", lambda: None)
        monkeypatch.setattr(bridge, "_get_cd_indexer", lambda: None)
        tools = bridge.list_tools()
        # 18 sidecar tools + 5 codedepth tools + 1 claude-mem tool (if available)
        # Minimum is 18 sidecar tools
        assert len(tools) >= 18
        for t in tools:
            assert "name" in t
            assert "description" in t
            assert "inputSchema" in t

    def test_list_resources(self) -> None:
        bridge = SidecarMCPBridge()
        resources = bridge.list_resources()
        assert resources is SIDECAR_MCP_RESOURCES

    def test_list_prompts(self) -> None:
        bridge = SidecarMCPBridge()
        prompts = bridge.list_prompts()
        assert len(prompts) == 2
        names = {p["name"] for p in prompts}
        assert names == {"maref_compliance_snapshot", "maref_governance_overview"}

    def test_handle_tool_call_known_tool(self) -> None:
        bridge = SidecarMCPBridge()
        result = bridge.handle_tool_call("maref_health_check", {"detail": True})
        # Note: handle_tool_call doesn't add "isError": False for successful calls
        assert "isError" not in result
        assert result["content"][0]["text"] == "Tool maref_health_check executed"

    def test_handle_tool_call_unknown_tool(self) -> None:
        bridge = SidecarMCPBridge()
        result = bridge.handle_tool_call("unknown_tool", {})
        assert result["isError"] is True
        assert "Unknown tool" in result["content"][0]["text"]

    def test_handle_tool_call_with_trace_id(self) -> None:
        bridge = SidecarMCPBridge()
        result = bridge.handle_tool_call("maref_list_agents", {}, trace_id="trace-123")
        assert result["_trace_id"] == "trace-123"

    def test_handle_tool_call_without_trace_id(self) -> None:
        bridge = SidecarMCPBridge()
        result = bridge.handle_tool_call("maref_list_agents", {})
        assert "_trace_id" not in result

    def test_handle_tool_call_each_tool(self) -> None:
        bridge = SidecarMCPBridge()
        # Skip tools with custom handlers that return different results
        custom_handlers = {
            "maref_observe_agent",
            "maref_run_evolution",
            "maref_get_evolution_status",
            "maref_list_evolution_results",
            "maref_health_check",
            "maref_pty_exec",
            "gov_check_phase_gate",
            "gov_verify_output",
        }
        for tool_def in SIDECAR_MCP_TOOLS:
            if tool_def.name in custom_handlers:
                continue
            result = bridge.handle_tool_call(tool_def.name, {})
            assert result["content"][0]["text"] == f"Tool {tool_def.name} executed"


from unittest.mock import MagicMock, patch


class TestMCPBridgeEdgeCases:
    def test_build_cm_tool_map_skips_empty_name(self) -> None:
        from sidecar.mcp_bridge import _build_cm_tool_map
        raw = [{"name": ""}, {"name": "valid_tool", "description": "desc"}]
        result = _build_cm_tool_map(raw)
        assert "claude_mem_valid_tool" in result
        assert len(result) == 1

    def test_strip_cm_prefix_no_prefix(self) -> None:
        from sidecar.mcp_bridge import _strip_cm_prefix
        assert _strip_cm_prefix("maref_health_check") == "maref_health_check"

    def test_handle_tool_call_cm_backend_unavailable(self) -> None:
        bridge = SidecarMCPBridge()
        result = bridge.handle_tool_call("claude_mem_read", {})
        assert result["isError"] is True
        assert "unavailable" in result["content"][0]["text"]

    @patch.object(SidecarMCPBridge, "_get_cd_indexer", return_value=None)
    def test_handle_tool_call_cd_indexer_unavailable(self, _) -> None:
        bridge = SidecarMCPBridge()
        result = bridge.handle_tool_call("depth_stats", {})
        assert result["isError"] is True
        assert "CodeDepth indexer unavailable" in result["content"][0]["text"]

    def test_get_cm_backend_populates_tool_map(self) -> None:
        mock_backend = MagicMock()
        mock_backend.available = True
        mock_backend.list_tools.return_value = [{"name": "read"}]
        from sidecar.mcp_bridge import _build_cm_tool_map
        raw = mock_backend.list_tools()
        result = _build_cm_tool_map(raw)
        assert "claude_mem_read" in result
        assert len(result) == 1

    @patch.object(SidecarMCPBridge, "_get_cm_backend")
    def test_handle_tool_call_cm_success(self, mock_get_cm) -> None:
        mock_backend = MagicMock()
        mock_backend.available = True
        mock_backend.call_tool.return_value = {"content": [{"type": "text", "text": "ok"}]}
        mock_get_cm.return_value = mock_backend
        bridge = SidecarMCPBridge()
        result = bridge.handle_tool_call("claude_mem_read", {"arg": 1}, trace_id="t1")
        assert result["content"][0]["text"] == "ok"
        assert result["_trace_id"] == "t1"

    @patch("maref.codedepth.indexer.CodeIndexer")
    def test_get_cd_indexer_success(self, MockIndexer) -> None:
        mock_idx = MockIndexer.return_value
        mock_idx.is_built = False
        mock_idx.build.return_value = {"files": 5}
        bridge = SidecarMCPBridge(repo_path="/tmp")
        idx = bridge._get_cd_indexer()
        assert idx is mock_idx

    @patch.object(SidecarMCPBridge, "_get_cd_indexer")
    def test_route_cd_stats(self, mock_get_idx) -> None:
        mock_idx = MagicMock()
        mock_idx.get_stats.return_value = {"files": 42}
        mock_get_idx.return_value = mock_idx
        bridge = SidecarMCPBridge()
        bridge._cd_indexer = mock_idx
        result = bridge._route_cd("depth_stats", {})
        assert '"files": 42' in result

    def test_close_releases_resources(self) -> None:
        bridge = SidecarMCPBridge()
        mock_cm = MagicMock()
        mock_cd = MagicMock()
        bridge._cm_backend = mock_cm
        bridge._cd_indexer = mock_cd
        bridge.close()
        mock_cm.stop.assert_called_once()
        mock_cd.close.assert_called_once()
        assert bridge._cm_backend is None
        assert bridge._cd_indexer is None
