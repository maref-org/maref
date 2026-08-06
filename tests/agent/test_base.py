from __future__ import annotations

from maref.agent.base import AgentDefinition


class TestAgentDefinition:
    def test_default_values(self) -> None:
        agent = AgentDefinition(agent_type="TestAgent", description="test", when_to_use="testing")
        assert agent.max_turns == 50
        assert agent.model == "inherit"
        assert agent.permission_mode == "default"
        assert agent.allowed_tools == []
        assert agent.disallowed_tools == []

    def test_custom_values(self) -> None:
        agent = AgentDefinition(
            agent_type="CustomAgent",
            description="Custom agent",
            when_to_use="Custom tasks",
            allowed_tools=["ToolA", "ToolB"],
            disallowed_tools=["ToolC"],
            max_turns=10,
            model="claude-sonnet-4",
            permission_mode="read_only",
        )
        assert agent.agent_type == "CustomAgent"
        assert agent.max_turns == 10
        assert agent.model == "claude-sonnet-4"
        assert "ToolA" in agent.allowed_tools
