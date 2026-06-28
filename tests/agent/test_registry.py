from __future__ import annotations

from maref.agent.base import AgentDefinition
from maref.agent.registry import AgentRegistry


class TestAgentRegistry:
    def test_register_and_get(self) -> None:
        registry = AgentRegistry()
        agent = AgentDefinition(agent_type="TestAgent", description="test", when_to_use="testing")
        registry.register(agent)
        assert registry.get("TestAgent") is agent

    def test_get_nonexistent(self) -> None:
        registry = AgentRegistry()
        assert registry.get("nonexistent") is None

    def test_list_agents(self) -> None:
        registry = AgentRegistry()
        registry.register(AgentDefinition(agent_type="A", description="a", when_to_use="a"))
        registry.register(AgentDefinition(agent_type="B", description="b", when_to_use="b"))
        assert len(registry.list_agents()) == 2

    def test_remove(self) -> None:
        registry = AgentRegistry()
        agent = AgentDefinition(agent_type="X", description="x", when_to_use="x")
        registry.register(agent)
        registry.remove("X")
        assert registry.get("X") is None

    def test_clear(self) -> None:
        registry = AgentRegistry()
        registry.register(AgentDefinition(agent_type="Y", description="y", when_to_use="y"))
        registry.clear()
        assert registry.count == 0

    def test_count(self) -> None:
        registry = AgentRegistry()
        assert registry.count == 0
        registry.register(AgentDefinition(agent_type="Z", description="z", when_to_use="z"))
        assert registry.count == 1
