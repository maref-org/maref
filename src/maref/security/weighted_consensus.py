"""
Weighted Consensus Engine — 加权共识引擎

T3: 加权共识引擎
- 实现公式 W_agent = 1/|N_i| * Σ T_ij
- 动态权重更新
- 拜占庭容错（惩罚机制）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ConsensusVote:
    """共识投票"""
    agent_id: str
    value: Any
    weight: float = 1.0


class WeightedConsensusEngine:
    """加权共识引擎

    信任权重计算: W_agent = 1/|N_i| * Σ T_ij
    共识决策: 加权投票最高者
    """

    def __init__(self) -> None:
        self._penalties: dict[str, float] = {}

    def calculate_weight(self, neighbors_trust: dict[str, float]) -> float:
        """计算权重: W = 1/|N| * Σ T_ij

        Args:
            neighbors_trust: 邻居对该agent的信任分数 {neighbor_id: trust_score}

        Returns:
            平均信任权重 0-100
        """
        if not neighbors_trust:
            return 50.0  # 默认中等信任

        total_trust = sum(neighbors_trust.values())
        return total_trust / len(neighbors_trust)

    def decide(self, votes: list[ConsensusVote]) -> Any | None:
        """基于加权投票做共识决策

        Args:
            votes: 投票列表

        Returns:
            得票最高（按权重）的选项，空则 None
        """
        if not votes:
            return None

        # 统计各选项的加权得分
        scores: dict[Any, float] = {}
        for vote in votes:
            effective_weight = vote.weight * self._penalties.get(vote.agent_id, 1.0)
            scores[vote.value] = scores.get(vote.value, 0.0) + effective_weight

        if not scores:
            return None

        # 找出最高分的选项
        max_score = max(scores.values())
        winners = [v for v, s in scores.items() if s == max_score]

        # 平票时按选项值排序取第一个（确定性结果）
        winners.sort(key=lambda x: str(x))
        return winners[0]

    def penalize_agent(self, agent_id: str, penalty: float = 0.5) -> None:
        """惩罚拜占庭 agent（降低其权重）

        Args:
            agent_id: Agent ID
            penalty: 惩罚系数 (0-1)，默认 0.5（权重减半）
        """
        self._penalties[agent_id] = max(0.0, min(1.0, penalty))

    def restore_agent(self, agent_id: str) -> None:
        """恢复 agent 的权重惩罚"""
        self._penalties.pop(agent_id, None)

    def get_penalty(self, agent_id: str) -> float:
        """获取 agent 的当前惩罚系数"""
        return self._penalties.get(agent_id, 1.0)
