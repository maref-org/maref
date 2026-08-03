"""Tests for protocol adapter layer and bridge delegation (Plan A D4)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from maref.integration.a2a_bridge import A2ABridge
from maref.integration.a2a_types import A2ASkillDefinition
from maref.governance.audit import AuditLogger
from maref.governance.state_machine import GovernanceStateMachine
from maref.protocols import (
    ASLAdapter,
    A2AToMCPAdapter,
    MCPToA2AAdapter,
    ProtocolAdapter,
    ProtocolKind,
    create_adapter,
    create_protocol_bridge,
    register_adapter,
)
from maref.protocols.protocol_bridge import A2ATask, MCPMessage


@pytest.fixture
def audit_logger() -> AuditLogger:
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        return AuditLogger(Path(f.name))


def _mcp_message(method: str = "tools/call") -> MCPMessage:
    return MCPMessage(
        message_id="msg-1",
        method=method,
        params={"name": "lookup", "arguments": {"q": "x"}},
    )


def _a2a_task(status: str = "completed") -> A2ATask:
    return A2ATask(
        task_id="task-msg-1",
        agent_id="agent-alice",
        action="execute_task",
        input_data={"original_method": "tools/call"},
        status=status,
        output_data={"ok": True} if status == "completed" else None,
    )


class TestMCPToA2AAdapter:
    def test_tool_call_maps_to_execute_task(self) -> None:
        adapter = MCPToA2AAdapter()
        task = adapter.convert(_mcp_message("tools/call"), target_agent="agent-bob")
        assert task.action == "execute_task"
        assert task.agent_id == "agent-bob"
        assert task.metadata["adapter"] == "mcp-to-a2a"

    def test_resource_read_maps_to_fetch_artifact(self) -> None:
        adapter = MCPToA2AAdapter()
        task = adapter.convert(_mcp_message("resources/read"), target_agent="a")
        assert task.action == "fetch_artifact"

    def test_prompt_get_maps_to_send_message(self) -> None:
        adapter = MCPToA2AAdapter()
        task = adapter.convert(_mcp_message("prompts/get"), target_agent="a")
        assert task.action == "send_message"


class TestA2AToMCPAdapter:
    def test_completed_to_result(self) -> None:
        adapter = A2AToMCPAdapter()
        resp = adapter.convert(_a2a_task("completed"), message_id="msg-1")
        assert resp.is_error is False
        assert resp.result["task_status"] == "completed"

    def test_failed_to_error(self) -> None:
        adapter = A2AToMCPAdapter()
        resp = adapter.convert(_a2a_task("failed"), message_id="msg-1")
        assert resp.is_error is True
        assert resp.error["code"] == -32000

    def test_pending_status(self) -> None:
        adapter = A2AToMCPAdapter()
        resp = adapter.convert(_a2a_task("pending"), message_id="msg-1")
        assert resp.result["status"] == "pending"

    def test_empty_output_dict_serialized(self) -> None:
        adapter = A2AToMCPAdapter()
        task = A2ATask(
            task_id="task-empty",
            agent_id="agent-alice",
            action="execute_task",
            input_data={},
            status="completed",
            output_data={},
        )
        resp = adapter.convert(task, message_id="msg-1")
        assert resp.result["content"][0]["text"] == "{}"

    def test_none_output_fallback_text(self) -> None:
        adapter = A2AToMCPAdapter()
        task = A2ATask(
            task_id="task-none",
            agent_id="agent-alice",
            action="execute_task",
            input_data={},
            status="completed",
            output_data=None,
        )
        resp = adapter.convert(task, message_id="msg-1")
        assert resp.result["content"][0]["text"] == "Task completed"


class TestASLAdapter:
    def test_placeholder_raises(self) -> None:
        adapter = ASLAdapter()
        assert adapter.name == "asl"
        assert adapter.source == ProtocolKind.ASL
        with pytest.raises(NotImplementedError):
            adapter.convert({})


class TestAdapterFactory:
    def test_create_default_adapter(self) -> None:
        assert isinstance(create_adapter("mcp-to-a2a"), MCPToA2AAdapter)
        assert isinstance(create_adapter("a2a-to-mcp"), A2AToMCPAdapter)
        assert isinstance(create_adapter("asl"), ASLAdapter)

    def test_create_unknown_raises(self) -> None:
        with pytest.raises(KeyError):
            create_adapter("nope")

    def test_register_custom_adapter(self) -> None:
        class CustomAdapter(ProtocolAdapter):
            name = "custom"
            source = ProtocolKind.MCP
            target = ProtocolKind.MCP

            def convert(self, message, **context):  # type: ignore[no-untyped-def]
                return message

        register_adapter(CustomAdapter())
        assert isinstance(create_adapter("custom"), CustomAdapter)


class TestBridgeDelegation:
    def test_bridge_delegates_to_adapter(self) -> None:
        bridge = create_protocol_bridge()
        task = bridge.convert_mcp_to_a2a(_mcp_message(), "agent-bob")
        assert task.metadata["adapter"] == "mcp-to-a2a"
        resp = bridge.convert_a2a_to_mcp(task)
        assert resp.result is not None

    def test_adapter_lookup(self) -> None:
        bridge = create_protocol_bridge()
        assert isinstance(bridge.adapter("a2a-to-mcp"), A2AToMCPAdapter)
        assert isinstance(bridge.adapter("asl"), ASLAdapter)

    def test_list_adapters(self) -> None:
        bridge = create_protocol_bridge()
        names = bridge.list_adapters()
        assert "mcp-to-a2a" in names
        assert "a2a-to-mcp" in names
        assert "asl" in names

    def test_unknown_adapter_raises(self) -> None:
        bridge = create_protocol_bridge()
        with pytest.raises(KeyError):
            bridge.adapter("nope")


class TestA2ABridgeMCPWiring:
    def _bridge(self, audit_logger: AuditLogger, with_bridge: bool) -> A2ABridge:
        from maref.protocols import create_protocol_bridge

        return A2ABridge(
            state_machine=GovernanceStateMachine(),
            audit_logger=audit_logger,
            protocol_bridge=create_protocol_bridge() if with_bridge else None,
        )

    def test_no_bridge_returns_empty(self, audit_logger: AuditLogger) -> None:
        br = self._bridge(audit_logger, with_bridge=False)
        assert br.build_mcp_tools() == []

    def test_with_bridge_maps_capabilities(self, audit_logger: AuditLogger) -> None:
        br = self._bridge(audit_logger, with_bridge=True)
        br.register_capability(
            A2ASkillDefinition(
                id="search",
                name="Search",
                description="Search documents",
                input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
            )
        )
        tools = br.build_mcp_tools()
        assert len(tools) > 0  # 默认能力 + 注册的 search
        tool = next(t for t in tools if t["name"] == "search")
        assert tool["sourceProtocol"] == "a2a"
        assert tool["targetA2AAction"] == "execute_task"

    def test_with_bridge_respects_custom_a2a_action(
        self, audit_logger: AuditLogger
    ) -> None:
        br = self._bridge(audit_logger, with_bridge=True)
        br.register_capability(
            A2ASkillDefinition(
                id="fetch",
                name="Fetch Artifact",
                description="Fetch an artifact",
                a2a_action="fetch_artifact",
            )
        )
        tool = next(t for t in br.build_mcp_tools() if t["name"] == "fetch")
        assert tool["targetA2AAction"] == "fetch_artifact"
