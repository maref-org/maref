from __future__ import annotations

from typing import Any

from maref.integration.a2a_bridge import A2ABridge
from maref.integration.a2a_types import A2ASkillDefinition
from maref.integration.mcp_envelope import inject_envelope  # trace_id, timestamp, source_agent
from maref.integration.mcp_server import MCPServer


class MCPToA2ABridge:
    """MCP ↔ A2A 协议桥接。

    将 MCP Server 的 Tools/Resources 导出为 A2A Skills，
    并将 A2A Task 调用路由到 MCP Tool 执行。
    """

    def __init__(
        self,
        mcp_server: MCPServer,
        a2a_bridge: A2ABridge,
    ) -> None:
        self.mcp_server = mcp_server
        self.a2a_bridge = a2a_bridge
        self._skill_registry: dict[str, str] = {}  # skill_id -> mcp_name

    def export_tools_as_skills(self) -> list[A2ASkillDefinition]:
        """将 MCP Tools 导出为 A2A Skills，注册到 A2A Bridge。"""
        skills: list[A2ASkillDefinition] = []

        # 导出 Tools
        for tool in self.mcp_server._tools.values():
            skill_id = f"mcp-tool-{tool.name}"
            skill = A2ASkillDefinition(
                id=skill_id,
                name=tool.name,
                description=tool.description,
                tags=["mcp", "tool"],
                examples=[f"Call MCP tool: {tool.name}"],
            )
            self.a2a_bridge.register_capability(skill)
            self._skill_registry[skill_id] = tool.name
            skills.append(skill)

        # 导出 Resources
        for resource in self.mcp_server._resources.values():
            skill_id = f"mcp-resource-{resource.uri.replace('://', '-').replace('/', '-')}"
            skill = A2ASkillDefinition(
                id=skill_id,
                name=resource.name,
                description=f"MCP Resource: {resource.uri}",
                tags=["mcp", "resource"],
                examples=[f"Read MCP resource: {resource.uri}"],
            )
            self.a2a_bridge.register_capability(skill)
            self._skill_registry[skill_id] = resource.uri
            skills.append(skill)

        return skills

    def route_a2a_task_to_mcp_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """将 A2A Task 路由到 MCP Tool 执行。

        Args:
            tool_name: MCP Tool 名称
            arguments: Tool 参数

        Returns:
            A2A Task ID
        """
        from maref.integration.mcp_transport import JSONRPCRequest

        # 1. 创建 A2A Task
        task_id = self.a2a_bridge.create_task(
            task_description=f"MCP Tool Call: {tool_name}",
            context={"mcp_tool": tool_name, "arguments": arguments},
        )

        # 2. 调用 MCP Tool — 宪法第十五-A条: 注入 MCP 消息信封
        req = JSONRPCRequest(
            method="tools/call",
            params=inject_envelope(
                {"name": tool_name, "arguments": arguments}, source_agent="protocol-bridge"
            ),
            id=1,
        )
        resp = self.mcp_server.handle_request(req)

        # 3. 更新 A2A Task 状态
        if resp.is_error:
            self.a2a_bridge.sync_state_from_a2a(task_id, "failed")
            task = self.a2a_bridge.get_task(task_id)
            if task:
                task.context["mcp_error"] = resp.error
        else:
            self.a2a_bridge.sync_state_from_a2a(task_id, "completed")
            task = self.a2a_bridge.get_task(task_id)
            if task:
                task.context["mcp_result"] = resp.result

        return task_id

    def build_combined_agent_card(self) -> dict[str, Any]:
        """构建包含 MCP 和 A2A 能力的合并 Agent Card。"""
        base_card = self.a2a_bridge.build_agent_card()

        # 添加 MCP 能力到 capabilities
        mcp_capabilities = {
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                }
                for tool in self.mcp_server._tools.values()
            ],
            "resources": [
                {
                    "uri": res.uri,
                    "name": res.name,
                }
                for res in self.mcp_server._resources.values()
            ],
        }

        if "mcp" not in base_card:
            base_card["mcp"] = mcp_capabilities
        else:
            base_card["mcp"].update(mcp_capabilities)

        return base_card
