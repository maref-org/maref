"""
Trust API — 信任管理接口

T4: 信任API
- trust_score(agent_id)
- get_trust_history(agent_id)
- set_trust(agent_id, score)
"""

from __future__ import annotations

import time
from typing import Any

from maref.security.trust_graph import TrustGraph


class TrustAPI:
    """信任管理 API"""

    def __init__(self, graph: TrustGraph) -> None:
        self.graph = graph
        self._history: dict[str, list[dict[str, Any]]] = {}

    def trust_score(self, agent_id: str) -> float | None:
        """获取 agent 的当前信任分数"""
        if agent_id not in self.graph.agents:
            return None
        return self.graph.get_trust(agent_id)

    def set_trust(self, agent_id: str, score: float, reason: str = "") -> None:
        """设置 agent 的信任分数（会记录历史）"""
        if agent_id not in self.graph.agents:
            self.graph.add_agent(agent_id, initial_trust=score)
        else:
            self.graph.update_trust(agent_id, score)

        self._record_history(agent_id, score, reason or "manual_set")

    def update_trust(self, agent_id: str, score: float, reason: str = "") -> None:
        """更新信任分数（同 set_trust）"""
        self.set_trust(agent_id, score, reason)

    def get_trust_history(self, agent_id: str) -> list[dict[str, Any]]:
        """获取 agent 的信任分数历史"""
        return list(self._history.get(agent_id, []))

    def list_agents(self) -> list[str]:
        """列出所有 agent"""
        return list(self.graph.agents.keys())

    def get_trust_report(self, agent_id: str) -> dict[str, Any]:
        """获取 agent 的完整信任报告"""
        if agent_id not in self.graph.agents:
            return {"error": f"Agent {agent_id} not found"}

        score = self.graph.get_trust(agent_id)
        neighbors = self.graph.get_neighbors(agent_id)
        history = self.get_trust_history(agent_id)

        return {
            "agent_id": agent_id,
            "trust_score": score,
            "trust_tier": self._calculate_tier(score),
            "neighbors": neighbors,
            "neighbor_count": len(neighbors),
            "history_count": len(history),
            "last_updated": history[-1]["timestamp"] if history else None,
        }

    def _record_history(self, agent_id: str, score: float, reason: str) -> None:
        if agent_id not in self._history:
            self._history[agent_id] = []
        self._history[agent_id].append(
            {
                "timestamp": time.time(),
                "score": score,
                "reason": reason,
            }
        )

    @staticmethod
    def _calculate_tier(score: float) -> str:
        if score >= 90:
            return "HIGH"
        elif score >= 70:
            return "MEDIUM"
        elif score >= 50:
            return "LOW"
        else:
            return "UNTRUSTED"
