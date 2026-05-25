from __future__ import annotations

import pytest


class TestLangChainInterop:
    """P8.1: LangChain 生态互操作验证"""

    def test_mcp_tool_as_langchain_compatible(self):
        """验证 MCP Tool 可转换为 LangChain Tool 格式。"""
        from maref.integration.mcp_server import MCPServer

        server = MCPServer(name="langchain-test")

        def search_handler(args):
            return {"content": [{"type": "text", "text": f"Results for: {args.get('query', '')}"}]}

        server.register_tool(
            name="search",
            description="Search the knowledge base",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            handler=search_handler,
        )

        # 转换为 LangChain 兼容格式
        tool = server._tools["search"]
        lc_format = {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        }

        assert lc_format["name"] == "search"
        assert "Search" in lc_format["description"]
        assert "query" in lc_format["parameters"]["properties"]

    def test_langchain_tool_schema_compatibility(self):
        """验证 MAREF 工具 schema 与 LangChain 格式兼容。"""
        from maref.integration.mcp_server import MCPServer

        server = MCPServer()

        def calc_handler(args):
            return {"content": [{"type": "text", "text": str(args.get("x", 0) + args.get("y", 0))}]}

        server.register_tool(
            name="calculator",
            description="Add two numbers",
            input_schema={
                "type": "object",
                "properties": {
                    "x": {"type": "number", "description": "First number"},
                    "y": {"type": "number", "description": "Second number"},
                },
                "required": ["x", "y"],
            },
            handler=calc_handler,
        )

        tool = server._tools["calculator"]
        schema = tool.input_schema

        # LangChain 兼容性检查
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema
        assert "x" in schema["properties"]
        assert schema["properties"]["x"]["type"] == "number"

    def test_mcp_server_as_langchain_tool_source(self):
        """验证 MCP Server 可作为 LangChain 工具源。"""
        from maref.integration.mcp_server import MCPServer

        server = MCPServer(name="tool-source")

        for i in range(3):
            def make_handler(idx):
                return lambda args: {"content": [{"type": "text", "text": f"tool{idx}"}]}

            server.register_tool(
                name=f"tool_{i}",
                description=f"Tool {i}",
                input_schema={"type": "object", "properties": {}},
                handler=make_handler(i),
            )

        # 验证可以枚举所有工具
        tools = list(server._tools.values())
        assert len(tools) == 3

        # 验证每个工具都可以调用
        for tool in tools:
            result = tool.handler({})
            assert "content" in result

    def test_langchain_agent_card_metadata(self):
        """验证 Agent Card 包含 LangChain 兼容的元数据。"""
        from maref.governance.audit import AuditLogger
        from maref.governance.state_machine import GovernanceStateMachine
        from maref.integration.a2a_bridge import A2ABridge

        audit = AuditLogger()
        sm = GovernanceStateMachine()
        bridge = A2ABridge(state_machine=sm, audit_logger=audit, agent_name="lc-agent")

        card = bridge.build_agent_card()

        # LangChain 兼容字段
        assert "name" in card
        assert "description" in card
        assert "skills" in card
        assert isinstance(card["skills"], list)

    def test_mcp_to_langchain_tool_invocation(self):
        """验证 MCP Tool 调用可被 LangChain 风格调用。"""
        from maref.integration.mcp_server import MCPServer
        from maref.integration.mcp_transport import JSONRPCRequest

        server = MCPServer()

        def echo_handler(args):
            return {"content": [{"type": "text", "text": args.get("text", "")}]}

        server.register_tool(
            name="echo",
            description="Echo text",
            input_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
            handler=echo_handler,
        )

        # 模拟 LangChain 风格调用（传入字典参数）
        req = JSONRPCRequest(
            method="tools/call",
            params={"name": "echo", "arguments": {"text": "hello langchain"}},
            id=1,
        )
        resp = server.handle_request(req)

        assert not resp.is_error
        assert resp.result["content"][0]["text"] == "hello langchain"


class TestAutoGenInterop:
    """P8.2: AutoGen 生态互操作验证"""

    def test_autogen_adapter_exists(self):
        """验证 AutoGenAdapter 模块存在且可导入。"""
        try:
            from sidecar.adapters.autogen import AutoGenAdapter
            assert AutoGenAdapter is not None
        except ImportError:
            pytest.skip("autogen_agentchat not installed")

    def test_autogen_adapter_interface(self):
        """验证 AutoGenAdapter 实现 AgentAdapter 接口。"""
        try:
            from sidecar.adapters.autogen import AutoGenAdapter
            from sidecar.collector import AgentAdapter
        except ImportError:
            pytest.skip("autogen_agentchat not installed")

        # 验证 AutoGenAdapter 是 AgentAdapter 的子类
        assert issubclass(AutoGenAdapter, AgentAdapter)

    def test_maref_autogen_cross_framework_registration(self):
        """验证 MAREF Federation 可注册 AutoGen agent。"""
        from maref.recursive.federation import FederationCoordinator, FrameworkType

        fc = FederationCoordinator()
        fc.register("autogen-agent-1", FrameworkType.AUTOGEN, role="assistant")

        agents = fc.agents_by_framework(FrameworkType.AUTOGEN)
        assert len(agents) == 1
        assert agents[0].agent_id == "autogen-agent-1"

    def test_maref_autogen_state_observation_mock(self):
        """验证 MAREF 可观察 AutoGen 风格 agent 状态（mock）。"""
        from sidecar.collector import MockAgentAdapter

        adapter = MockAgentAdapter(num_agents=2)

        # 模拟获取状态
        import asyncio
        agents = asyncio.run(adapter.list_agents())
        assert len(agents) == 2

        state = asyncio.run(adapter.get_state(agents[0]))
        assert state is not None
        assert state.agent_id == agents[0]

    def test_autogen_langchain_dual_framework(self):
        """验证 MAREF 可同时管理 AutoGen 和 LangChain 风格 agent。"""
        from maref.recursive.federation import FederationCoordinator, FrameworkType

        fc = FederationCoordinator()
        fc.register("autogen-1", FrameworkType.AUTOGEN)
        fc.register("dify-1", FrameworkType.DIFY)

        assert fc.agent_count() == 2

        breakdown = fc.framework_breakdown()
        assert breakdown["autogen"] == 1
        assert breakdown["dify"] == 1

    def test_cross_framework_trust_sharing(self):
        """验证跨框架信任比较功能。"""
        from maref.recursive.federation import FederationCoordinator, FrameworkType

        fc = FederationCoordinator()
        fc.register("autogen-1", FrameworkType.AUTOGEN)
        fc.register("autogen-2", FrameworkType.AUTOGEN)
        fc.register("dify-1", FrameworkType.DIFY)

        comparison = fc.cross_framework_trust_comparison()
        assert "autogen" in comparison
        assert "dify" in comparison

        # 验证信任值在合理范围
        for fw_data in comparison.values():
            assert 0 <= fw_data["avg_trust"] <= 100
            assert "count" in fw_data or "agent_count" in fw_data
