from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FrameworkType(Enum):
    AUTOGEN = "autogen"
    DIFY = "dify"
    COZE = "coze"


@dataclass
class FederatedAgent:
    agent_id: str
    framework: FrameworkType
    role: str = ""
    trust_score: float = 50.0
    status: str = "ACTIVE"


@dataclass
class FederationReport:
    framework_stats: dict[str, dict[str, int]] = field(default_factory=dict)
    total_agents: int = 0
    fault_isolation_tests: dict[str, bool] = field(default_factory=dict)
    trust_comparisons: dict[str, float] = field(default_factory=dict)


class FederationCoordinator:
    def __init__(self) -> None:
        self._agents: dict[str, FederatedAgent] = {}

    def register(self, agent_id: str, framework: FrameworkType,
                 role: str = "", trust_score: float = 50.0) -> FederatedAgent:
        agent = FederatedAgent(
            agent_id=agent_id,
            framework=framework,
            role=role,
            trust_score=trust_score,
        )
        self._agents[agent_id] = agent
        return agent

    def register_across_frameworks(self, agents_per_framework:
                                    dict[str, list[str]]) -> list[FederatedAgent]:
        registered: list[FederatedAgent] = []
        framework_map = {
            "autogen": FrameworkType.AUTOGEN,
            "dify": FrameworkType.DIFY,
            "coze": FrameworkType.COZE,
        }
        for fw_name, agent_ids in agents_per_framework.items():
            fw_type = framework_map.get(fw_name)
            if fw_type is None:
                continue
            for agent_id in agent_ids:
                agent = self.register(agent_id, fw_type,
                                       trust_score=50.0 + hash(agent_id + fw_name) % 50)
                registered.append(agent)
        return registered

    def agent_count(self) -> int:
        return len(self._agents)

    def agents_by_framework(self, framework: FrameworkType) -> list[FederatedAgent]:
        return [a for a in self._agents.values() if a.framework == framework]

    def framework_breakdown(self) -> dict[str, int]:
        breakdown: dict[str, int] = {}
        for agent in self._agents.values():
            key = agent.framework.value
            breakdown[key] = breakdown.get(key, 0) + 1
        return breakdown

    def cross_framework_trust_comparison(self) -> dict[
            str, dict[str, float | int]]:
        result: dict[str, dict[str, float | int]] = {}
        for fw in FrameworkType:
            agents = self.agents_by_framework(fw)
            if not agents:
                continue
            scores = [a.trust_score for a in agents]
            result[fw.value] = {
                "avg_trust": sum(scores) / len(scores),
                "count": len(scores),
            }
        return result

    def fault_isolation_check(self, source_framework:
                               FrameworkType) -> bool:
        source_agents = self.agents_by_framework(source_framework)
        other_count = sum(
            1 for a in self._agents.values()
            if a.framework != source_framework
        )
        return len(source_agents) > 0 and other_count > 0

    def set_agent_status(self, agent_id: str, status: str) -> bool:
        agent = self._agents.get(agent_id)
        if agent is None:
            return False
        agent.status = status
        return True

    def generate_report(self) -> FederationReport:
        return FederationReport(
            framework_stats={
                fw.value: {"count": len(self.agents_by_framework(fw))}
                for fw in FrameworkType
            },
            total_agents=self.agent_count(),
            trust_comparisons={
                agent.agent_id: agent.trust_score
                for agent in self._agents.values()
            },
        )
