"""
Trust Graph — 跨Agent信任关系图谱

T2: 信任传播实现
- 图数据结构设计（Agent为节点，信任关系为边）
- 信任传播算法（带衰减的迭代传播）
- 传递信任计算
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TrustEdge:
    """信任边"""

    source: str
    target: str
    trust_score: float  # 0-100
    weight: float = 1.0
    timestamp: float = field(default_factory=lambda: __import__("time").time())


@dataclass
class TrustAgent:
    """信任节点（Agent）"""

    agent_id: str
    trust_score: float = 50.0  # 0-100
    metadata: dict[str, Any] = field(default_factory=dict)


class TrustGraph:
    """信任关系图谱（有向图）"""

    def __init__(self) -> None:
        self.agents: dict[str, TrustAgent] = {}
        self._edges: dict[tuple[str, str], TrustEdge] = {}
        self._outgoing: dict[str, set[str]] = {}
        self._incoming: dict[str, set[str]] = {}

    def add_agent(
        self, agent_id: str, initial_trust: float = 50.0, metadata: dict[str, Any] | None = None
    ) -> None:
        if agent_id not in self.agents:
            self.agents[agent_id] = TrustAgent(
                agent_id=agent_id,
                trust_score=max(0.0, min(100.0, initial_trust)),
                metadata=metadata or {},
            )
            self._outgoing[agent_id] = set()
            self._incoming[agent_id] = set()

    def remove_agent(self, agent_id: str) -> None:
        if agent_id in self.agents:
            del self.agents[agent_id]
            # 删除相关边
            for target in list(self._outgoing.get(agent_id, [])):
                self._remove_edge(agent_id, target)
            for source in list(self._incoming.get(agent_id, [])):
                self._remove_edge(source, agent_id)
            self._outgoing.pop(agent_id, None)
            self._incoming.pop(agent_id, None)

    def add_edge(self, source: str, target: str, trust_score: float, weight: float = 1.0) -> None:
        if source not in self.agents:
            self.add_agent(source)
        if target not in self.agents:
            self.add_agent(target)

        edge = TrustEdge(
            source=source,
            target=target,
            trust_score=max(0.0, min(100.0, trust_score)),
            weight=weight,
        )
        self._edges[(source, target)] = edge
        self._outgoing[source].add(target)
        self._incoming[target].add(source)

    def get_edge(self, source: str, target: str) -> TrustEdge | None:
        return self._edges.get((source, target))

    def _remove_edge(self, source: str, target: str) -> None:
        self._edges.pop((source, target), None)
        self._outgoing.get(source, set()).discard(target)
        self._incoming.get(target, set()).discard(source)

    def get_neighbors(self, agent_id: str) -> list[str]:
        return list(self._outgoing.get(agent_id, set()))

    def get_trust(self, agent_id: str) -> float:
        agent = self.agents.get(agent_id)
        return agent.trust_score if agent else 0.0

    def update_trust(self, agent_id: str, score: float) -> None:
        if agent_id in self.agents:
            self.agents[agent_id].trust_score = max(0.0, min(100.0, score))

    def to_dict(self) -> dict[str, Any]:
        return {
            "agents": {
                aid: {"trust_score": a.trust_score, "metadata": a.metadata}
                for aid, a in self.agents.items()
            },
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "trust_score": e.trust_score,
                    "weight": e.weight,
                }
                for e in self._edges.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrustGraph:
        graph = cls()
        for aid, info in data.get("agents", {}).items():
            graph.add_agent(
                aid, initial_trust=info.get("trust_score", 50.0), metadata=info.get("metadata", {})
            )
        for edge_data in data.get("edges", []):
            graph.add_edge(
                edge_data["source"],
                edge_data["target"],
                edge_data.get("trust_score", 50.0),
                edge_data.get("weight", 1.0),
            )
        return graph


class TrustPropagation:
    """信任传播算法"""

    def __init__(self, graph: TrustGraph, decay_factor: float = 0.5) -> None:
        self.graph = graph
        self.decay_factor = decay_factor

    def propagate(self, iterations: int = 5) -> dict[str, float]:
        """迭代传播信任分数"""
        scores = {aid: agent.trust_score for aid, agent in self.graph.agents.items()}

        for _ in range(iterations):
            new_scores = dict(scores)
            for agent_id in self.graph.agents:
                incoming = self.graph._incoming.get(agent_id, set())
                if not incoming:
                    continue

                total_boost = 0.0
                total_weight = 0.0
                for source_id in incoming:
                    edge = self.graph.get_edge(source_id, agent_id)
                    if edge:
                        # 源agent的信任度 × 边信任分数 = 有效投票值
                        source_trust = scores[source_id]
                        vote = (source_trust / 100.0) * edge.trust_score
                        boost = (vote - scores[agent_id]) * edge.weight * self.decay_factor
                        total_boost += boost
                        total_weight += edge.weight

                if total_weight > 0:
                    avg_boost = total_boost / total_weight
                    new_scores[agent_id] = scores[agent_id] + avg_boost
                    new_scores[agent_id] = max(0.0, min(100.0, new_scores[agent_id]))

            scores = new_scores

        return scores

    def calculate_transitive_trust(self, source: str, target: str) -> float:
        """计算从 source 到 target 的传递信任"""
        if source == target:
            return 100.0

        # BFS 找最短路径
        visited = {source: 1.0}
        queue = [source]

        while queue:
            current = queue.pop(0)
            if current == target:
                return visited[current] * 100.0

            for neighbor in self.graph.get_neighbors(current):
                if neighbor not in visited:
                    edge = self.graph.get_edge(current, neighbor)
                    if edge:
                        visited[neighbor] = (
                            visited[current] * (edge.trust_score / 100.0) * self.decay_factor
                        )
                        queue.append(neighbor)

        return 0.0
