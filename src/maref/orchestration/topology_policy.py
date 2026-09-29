"""Topology-as-policy — 多智能体协调拓扑作为安全变量 (P2-9).

MAST（arXiv:2503.13657, NeurIPS 2025）与协调拓扑标度律（180 配置对照实验）：
无协调拓扑把错误放大到单 agent 基线的 **17.2×**；中心化编排 + 验证压到 **4.4×**；
单 agent 准确率超过 ~45% 后加 agent 收益递减甚至为负。→ **拓扑是安全变量**。

本模块把拓扑选择形式化为策略：按风险等级与模型多样性选择拓扑，并把错误放大
倍数暴露为调度代价乘子（供编排器/调度器折算）。角色预设含 Challenger（互挑错）
+ Inspector（独立审查）——报告引用的失败韧性实验中该组合可恢复最多 96.4% 错误。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

FLAT_AMPLIFICATION: float = 17.2
ORCHESTRATOR_VERIFIER_AMPLIFICATION: float = 4.4
CHALLENGER_INSPECTOR_AMPLIFICATION: float = 2.2


class TopologyKind(str, Enum):
    """Coordination topology kinds."""

    FLAT = "flat"
    ORCHESTRATOR_VERIFIER = "orchestrator_verifier"
    CHALLENGER_INSPECTOR = "challenger_inspector"


ERROR_AMPLIFICATION: dict[TopologyKind, float] = {
    TopologyKind.FLAT: FLAT_AMPLIFICATION,
    TopologyKind.ORCHESTRATOR_VERIFIER: ORCHESTRATOR_VERIFIER_AMPLIFICATION,
    TopologyKind.CHALLENGER_INSPECTOR: CHALLENGER_INSPECTOR_AMPLIFICATION,
}

_ROLE_PRESETS: dict[TopologyKind, list[str]] = {
    TopologyKind.FLAT: ["worker"],
    TopologyKind.ORCHESTRATOR_VERIFIER: ["orchestrator", "worker", "verifier"],
    TopologyKind.CHALLENGER_INSPECTOR: ["orchestrator", "worker", "challenger", "inspector"],
}

_HIGH_RISK = {"high", "critical"}
_MEDIUM_RISK = {"medium", "moderate"}


@dataclass
class TopologyRecommendation:
    """A topology choice with its safety/cost implications."""

    topology: TopologyKind
    amplification: float
    reason: str = ""
    roles: list[str] = field(default_factory=list)

    @property
    def cost_multiplier(self) -> float:
        """Error amplification normalized to the uncoordinated baseline."""
        return self.amplification / FLAT_AMPLIFICATION

    def to_dict(self) -> dict[str, Any]:
        return {
            "topology": self.topology.value,
            "amplification": self.amplification,
            "cost_multiplier": self.cost_multiplier,
            "reason": self.reason,
            "roles": list(self.roles),
        }


class TopologyPolicy:
    """Selects a coordination topology from risk and model diversity."""

    def __init__(self, default: TopologyKind = TopologyKind.ORCHESTRATOR_VERIFIER) -> None:
        self._default = TopologyKind(default)

    @property
    def default_topology(self) -> TopologyKind:
        """Default topology when no escalation applies."""
        return self._default

    def amplification(self, topology: TopologyKind | str) -> float:
        """Error amplification factor for ``topology``."""
        return ERROR_AMPLIFICATION[TopologyKind(topology)]

    def cost_multiplier(self, topology: TopologyKind | str) -> float:
        """Cost multiplier (amplification normalized to FLAT)."""
        return self.amplification(topology) / FLAT_AMPLIFICATION

    def select(
        self,
        risk_level: str = "medium",
        agent_count: int = 1,
        model_count: int = 1,
    ) -> TopologyRecommendation:
        """Recommend a topology from risk level, pool size, and model diversity."""
        risk = (risk_level or "").strip().lower()
        if agent_count <= 1:
            return self._recommend(TopologyKind.FLAT, "single agent; coordination not applicable")
        monoculture = model_count <= 1
        if risk in _HIGH_RISK or (monoculture and risk in _MEDIUM_RISK):
            return self._recommend(
                TopologyKind.CHALLENGER_INSPECTOR,
                "high risk or model monoculture — require challenge + independent review",
            )
        return self._recommend(self._default, "default centralized orchestration + verification")

    def _recommend(self, topology: TopologyKind, reason: str) -> TopologyRecommendation:
        return TopologyRecommendation(
            topology=topology,
            amplification=ERROR_AMPLIFICATION[topology],
            reason=reason,
            roles=list(_ROLE_PRESETS[topology]),
        )


def preset_roles(topology: TopologyKind | str) -> list[str]:
    """Role preset for a topology (orchestrator/verifier/challenger/inspector)."""
    return list(_ROLE_PRESETS[TopologyKind(topology)])
