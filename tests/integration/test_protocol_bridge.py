from __future__ import annotations

from maref.governance.audit import AuditLogger
from maref.governance.state_machine import GovernanceStateMachine
from maref.integration.a2a_bridge import A2ABridge
from maref.integration.a2a_types import A2ATaskState
from maref.integration.mcp_server import MCPServer
from maref.integration.protocol_bridge import MCPToA2ABridge


class TestProtocolBridgeBasics:
    """P7.1: 协议转换中间件基础测试"""

    def setup_mcp_and_a2a(self):
        mcp = MCPServer(name="test-mcp")
        audit = AuditLogger()
        sm = GovernanceStateMachine()
        a2a = A2ABridge(state_machine=sm, audit_logger=audit, agent_name="test-agent")
        bridge = MCPToA2ABridge(mcp_server=mcp, a2a_bridge=a2a)
        return mcp, a2a, bridge

    def test_export_tools_as_skills(self):
        mcp, a2a, bridge = self.setup_mcp_and_a2a()

        def calc_handler(args):
            return {"content": [{"type": "text", "text": str(args.get("x", 0) + args.get("y", 0))}]}

        mcp.register_tool(
            name="calculator",
            description="Add two numbers",
            input_schema={
                "type": "object",
                "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
                "required": ["x", "y"],
            },
            handler=calc_handler,
        )

        skills = bridge.export_tools_as_skills()
        assert len(skills) == 1
        assert skills[0].id == "mcp-tool-calculator"
        assert skills[0].name == "calculator"
        assert "add" in skills[0].description.lower()

    def test_mcp_tool_call_creates_a2a_task(self):
        mcp, a2a, bridge = self.setup_mcp_and_a2a()

        def echo_handler(args):
            return {"content": [{"type": "text", "text": args.get("msg", "")}]}

        mcp.register_tool(
            name="echo",
            description="Echo message",
            input_schema={"type": "object", "properties": {"msg": {"type": "string"}}, "required": ["msg"]},
            handler=echo_handler,
        )

        # 导出为 A2A skill
        bridge.export_tools_as_skills()

        # 模拟 A2A 调用 MCP tool
        task_id = bridge.route_a2a_task_to_mcp_tool("echo", {"msg": "hello bridge"})
        assert task_id is not None
        assert task_id.startswith("maref-task-")

        # 验证 A2A task 被创建
        task = a2a.get_task(task_id)
        assert task is not None
        assert "echo" in task.description

    def test_mcp_resource_exported_as_a2a_skill(self):
        mcp, a2a, bridge = self.setup_mcp_and_a2a()

        def readme_handler(uri):
            return {"contents": [{"uri": uri, "mimeType": "text/plain", "text": "# MAREF"}]}

        mcp.register_resource(
            uri="doc://readme",
            name="README",
            mime_type="text/markdown",
            handler=readme_handler,
        )

        skills = bridge.export_tools_as_skills()
        # Resources 也作为 skills 导出
        resource_skill = next((s for s in skills if s.id == "mcp-resource-doc-readme"), None)
        assert resource_skill is not None
        assert "readme" in resource_skill.name.lower()

    def test_a2a_state_sync_to_mcp(self):
        mcp, a2a, bridge = self.setup_mcp_and_a2a()

        def slow_handler(args):
            return {"content": [{"type": "text", "text": "done"}]}

        mcp.register_tool(
            name="slow_op",
            description="Slow operation",
            input_schema={"type": "object", "properties": {}},
            handler=slow_handler,
        )

        bridge.export_tools_as_skills()
        task_id = bridge.route_a2a_task_to_mcp_tool("slow_op", {})

        # 模拟 A2A 状态变更
        a2a.sync_state_from_a2a(task_id, "completed")

        # 验证 MCP 侧状态也同步
        task = a2a.get_task(task_id)
        assert task.a2a_state == A2ATaskState.COMPLETED

    def test_bridge_agent_card_includes_mcp_capabilities(self):
        mcp, a2a, bridge = self.setup_mcp_and_a2a()

        def tool_handler(args):
            return {"content": [{"type": "text", "text": "ok"}]}

        mcp.register_tool(
            name="analyzer",
            description="Analyze data",
            input_schema={"type": "object", "properties": {}},
            handler=tool_handler,
        )

        bridge.export_tools_as_skills()
        card = bridge.build_combined_agent_card()

        assert "skills" in card
        skill_ids = [s["id"] for s in card["skills"]]
        assert "mcp-tool-analyzer" in skill_ids
        assert "maref-governance" in skill_ids  # A2A 默认 skill

    def test_bridge_error_handling(self):
        mcp, a2a, bridge = self.setup_mcp_and_a2a()

        def error_handler(args):
            raise ValueError("Simulated error")

        mcp.register_tool(
            name="error_tool",
            description="Always fails",
            input_schema={"type": "object", "properties": {}},
            handler=error_handler,
        )

        bridge.export_tools_as_skills()
        result = bridge.route_a2a_task_to_mcp_tool("error_tool", {})

        # 应该返回错误信息而不是抛出
        assert result is not None
        task = a2a.get_task(result)
        assert task is not None
