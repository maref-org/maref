"""Unit tests for sidecar MCP bridge and protocol serialization."""

from __future__ import annotations

import pytest

from sidecar.mcp_bridge import (
    SIDECAR_MCP_TOOLS,
    MCPResourceURI,
    MCPToolDefinition,
    SidecarMCPBridge,
)
from sidecar.protocol import (
    AgentId,
    AgentState,
    EntropyReading,
    GovernanceDecision,
    Observation,
    ObservationType,
    StateSnapshot,
)


class TestMCPResourceURI:
    def test_to_uri_without_instance(self) -> None:
        uri = MCPResourceURI(namespace="test-ns", name="agent-1")
        assert uri.to_uri() == "maref://agents/test-ns/agent-1"

    def test_to_uri_with_instance(self) -> None:
        uri = MCPResourceURI(namespace="test-ns", name="agent-1", instance="i1")
        assert uri.to_uri() == "maref://agents/test-ns/agent-1#i1"

    def test_from_agent_id(self) -> None:
        agent = AgentId(name="worker", namespace="prod", instance="v2")
        uri = MCPResourceURI.from_agent_id(agent)
        assert uri.to_uri() == "maref://agents/prod/worker#v2"

    def test_from_agent_id_no_instance(self) -> None:
        agent = AgentId(name="worker", namespace="prod")
        uri = MCPResourceURI.from_agent_id(agent)
        assert uri.to_uri() == "maref://agents/prod/worker"

    def test_from_observation(self) -> None:
        obs = Observation(
            obs_type=ObservationType.ENTROPY_METRIC,
            source="test-agent",
            payload=None,
        )
        uri = MCPResourceURI.from_observation(obs)
        assert "observations" in uri.to_uri()
        assert "entropy" in uri.to_uri().lower()

    def test_default_values(self) -> None:
        uri = MCPResourceURI()
        assert uri.scheme == "maref"
        assert uri.resource_type == "agents"
        assert uri.namespace == "default"
        assert uri.name == ""
        assert uri.instance == ""


class TestMCPToolDefinition:
    def test_to_dict(self) -> None:
        tool = MCPToolDefinition(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
        )
        result = tool.to_dict()
        assert result["name"] == "test_tool"
        assert result["description"] == "A test tool"
        assert result["inputSchema"] == {"type": "object", "properties": {}}

    def test_default_input_schema(self) -> None:
        tool = MCPToolDefinition(name="minimal", description="Minimal tool")
        result = tool.to_dict()
        assert result["inputSchema"]["type"] == "object"

    def test_sidemcp_tools_list(self) -> None:
        assert len(SIDECAR_MCP_TOOLS) >= 10
        tool_names = [t.name for t in SIDECAR_MCP_TOOLS]
        assert "maref_observe_agent" in tool_names
        assert "maref_read_entropy" in tool_names
        assert "maref_read_observations" in tool_names
        assert "maref_read_anomalies" in tool_names
        assert "maref_compliance_check" in tool_names
        assert "maref_ingest_signal" in tool_names

    def test_each_tool_has_required_fields(self) -> None:
        for tool in SIDECAR_MCP_TOOLS:
            assert tool.name
            assert tool.description


class TestSidecarMCPBridge:
    @pytest.fixture
    def bridge(self) -> SidecarMCPBridge:
        return SidecarMCPBridge()

    def test_get_server_info(self, bridge: SidecarMCPBridge) -> None:
        info = bridge.get_server_info()
        assert info["protocolVersion"] == "2024-11-05"
        assert info["serverInfo"]["name"] == "MAREF Sidecar"
        assert "capabilities" in info

    def test_get_capabilities(self, bridge: SidecarMCPBridge) -> None:
        caps = bridge.get_capabilities()
        assert "tools" in caps
        assert "resources" in caps
        assert "prompts" in caps

    def test_list_tools(self, bridge: SidecarMCPBridge) -> None:
        tools = bridge.list_tools()
        assert len(tools) >= 21
        assert all("name" in t for t in tools)
        assert all("description" in t for t in tools)
        assert all("inputSchema" in t for t in tools)

    def test_list_resources(self, bridge: SidecarMCPBridge) -> None:
        resources = bridge.list_resources()
        assert len(resources) >= 3
        assert all("uri" in r for r in resources)
        assert all("name" in r for r in resources)

    def test_list_prompts(self, bridge: SidecarMCPBridge) -> None:
        prompts = bridge.list_prompts()
        assert len(prompts) >= 2
        prompt_names = [p["name"] for p in prompts]
        assert "maref_compliance_snapshot" in prompt_names
        assert "maref_governance_overview" in prompt_names

    def test_unknown_tool_call(self, bridge: SidecarMCPBridge) -> None:
        result = bridge.handle_tool_call("nonexistent_tool", {})
        assert result["isError"] is True
        assert "Unknown tool" in result["content"][0]["text"]

    def test_handle_tool_call_with_trace_id(self, bridge: SidecarMCPBridge) -> None:
        result = bridge.handle_tool_call(
            "maref_ingest_signal",
            {"signal_type": "ROUTE_DECISION", "payload": {}, "source": "test"},
            trace_id="test-trace-123",
        )
        assert result["_trace_id"] == "test-trace-123"


class TestProtocolSerialization:
    def test_agent_id_str(self) -> None:
        agent = AgentId(name="agent-1", namespace="ns1")
        assert str(agent) == "ns1/agent-1"

    def test_agent_id_str_with_instance(self) -> None:
        agent = AgentId(name="agent-1", namespace="ns1", instance="i1")
        assert str(agent) == "ns1/agent-1#i1"

    def test_agent_id_str_default_namespace(self) -> None:
        agent = AgentId(name="agent-1")
        assert str(agent) == "default/agent-1"

    def test_state_snapshot_to_dict(self) -> None:
        agent = AgentId(name="worker")
        snapshot = StateSnapshot(
            agent_id=agent,
            state=AgentState.RUNNING,
            current_task="test-task",
            task_progress=0.5,
            pending_messages=3,
        )
        d = snapshot.to_dict()
        assert d["agent_id"] == "default/worker"
        assert d["state"] == "RUNNING"
        assert d["current_task"] == "test-task"
        assert d["task_progress"] == 0.5
        assert d["pending_messages"] == 3
        assert "timestamp" in d

    def test_state_snapshot_defaults(self) -> None:
        agent = AgentId(name="worker")
        snapshot = StateSnapshot(agent_id=agent)
        d = snapshot.to_dict()
        assert d["state"] == "UNKNOWN"
        assert d["current_task"] == ""
        assert d["task_progress"] == 0.0
        assert d["pending_messages"] == 0
        assert isinstance(d["metadata"], dict)

    def test_entropy_reading_to_dict(self) -> None:
        reading = EntropyReading(source="agent-1", value=2.5, level="warning", threshold=2.0)
        d = reading.to_dict()
        assert d["source"] == "agent-1"
        assert d["value"] == 2.5
        assert d["level"] == "warning"
        assert d["threshold"] == 2.0
        assert "timestamp" in d

    def test_entropy_reading_default_level(self) -> None:
        reading = EntropyReading(source="agent-1", value=0.5)
        assert reading.level == "normal"

    def test_observation_to_dict_with_payload(self) -> None:
        reading = EntropyReading(source="agent-1", value=3.0, level="critical")
        obs = Observation(
            obs_type=ObservationType.ENTROPY_METRIC,
            payload=reading,
            source="test-src",
        )
        d = obs.to_dict()
        assert d["type"] == "ENTROPY_METRIC"
        assert d["source"] == "test-src"
        assert d["payload"]["source"] == "agent-1"
        assert d["payload"]["value"] == 3.0

    def test_observation_to_dict_raw_payload(self) -> None:
        obs = Observation(
            obs_type=ObservationType.MESSAGE_FLOW,
            payload={"raw": "data"},
            source="test",
        )
        d = obs.to_dict()
        assert d["payload"] == {"raw": "data"}

    def test_governance_decision_to_dict(self) -> None:
        agent = AgentId(name="agent-1")
        decision = GovernanceDecision(
            target=agent,
            action="approve",
            reason="All checks passed",
            priority=5,
        )
        d = decision.to_dict()
        assert d["target"] == "default/agent-1"
        assert d["action"] == "approve"
        assert d["reason"] == "All checks passed"
        assert d["priority"] == 5
        assert "timestamp" in d

    def test_governance_decision_default_priority(self) -> None:
        agent = AgentId(name="agent-1")
        decision = GovernanceDecision(target=agent, action="deny", reason="Risk high")
        assert decision.priority == 0

    def test_agent_state_values(self) -> None:
        assert AgentState.UNKNOWN.name == "UNKNOWN"
        assert AgentState.IDLE.name == "IDLE"
        assert AgentState.RUNNING.name == "RUNNING"
        assert AgentState.WAITING.name == "WAITING"
        assert AgentState.ERROR.name == "ERROR"
        assert AgentState.TERMINATED.name == "TERMINATED"

    def test_observation_type_values(self) -> None:
        assert ObservationType.STATE_SNAPSHOT.name == "STATE_SNAPSHOT"
        assert ObservationType.ENTROPY_METRIC.name == "ENTROPY_METRIC"
        assert ObservationType.MESSAGE_FLOW.name == "MESSAGE_FLOW"
        assert ObservationType.RESOURCE_USAGE.name == "RESOURCE_USAGE"
        assert ObservationType.EXCEPTION_EVENT.name == "EXCEPTION_EVENT"
