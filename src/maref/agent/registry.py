from __future__ import annotations

from maref.agent.base import AgentDefinition


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentDefinition] = {}

    def register(self, agent: AgentDefinition) -> None:
        self._agents[agent.agent_type] = agent

    def get(self, agent_type: str) -> AgentDefinition | None:
        return self._agents.get(agent_type)

    def list_agents(self) -> list[AgentDefinition]:
        return list(self._agents.values())

    def remove(self, agent_type: str) -> None:
        self._agents.pop(agent_type, None)

    def clear(self) -> None:
        self._agents.clear()

    @property
    def count(self) -> int:
        return len(self._agents)
