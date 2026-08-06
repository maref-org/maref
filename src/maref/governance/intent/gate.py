"""ChainInterruptGate — 链级意图中断门 (v0.52.1 G2-C6)。

G2 的决策输出点: 综合 模式匹配 (C2) + 意图假设 (C3) + 链风险聚合 (C4),
输出链级裁决并触发治理动作。

四态裁决:
    CONTINUE  链风险 LOW   → 继续
    WATCH     链风险 MEDIUM → 记录 + 持续监控
    ESCALATE  链风险 HIGH   → 升级人工 (HITL) / 信任降级
    HALT      链风险 CRITICAL → 熔断 / 隔离 / 强制停机

``evaluate_agent`` 一站式串起 C1-C6 全流程, 供管道挂接 (C7) 调用。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.governance.intent.aggregator import ChainRisk, SequentialRiskAggregator
from maref.governance.intent.chain_tracker import (
    ActionChainTracker,
    ActionRecord,
    ChainRiskLevel,
)
from maref.governance.intent.hypothesis import IntentHypothesis, IntentHypothesisEngine
from maref.governance.intent.patterns import ChainPatternLibrary, PatternMatch


class ChainDecision(str, Enum):
    """链级裁决四态。"""

    CONTINUE = "continue"
    WATCH = "watch"
    ESCALATE = "escalate"
    HALT = "halt"

    @property
    def label(self) -> str:
        return {
            ChainDecision.CONTINUE: "继续",
            ChainDecision.WATCH: "监控",
            ChainDecision.ESCALATE: "升级人工",
            ChainDecision.HALT: "熔断/隔离",
        }[self]


@dataclass
class IntentVerdict:
    """链级意图裁决结果。

    Attributes:
        decision: 四态裁决。
        level: 链风险级。
        hypotheses: 命中的意图假设。
        chain_risk: 聚合链风险。
        matches: 模式匹配结果。
        actions: 建议治理动作列表。
        agent_id: 被裁决的 agent。
        reason: 裁决理由。
        checked_at: 裁决时间。
    """

    decision: ChainDecision = ChainDecision.CONTINUE
    level: ChainRiskLevel = ChainRiskLevel.LOW
    hypotheses: list[IntentHypothesis] = field(default_factory=list)
    chain_risk: ChainRisk = field(default_factory=ChainRisk)
    matches: list[PatternMatch] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    agent_id: str = ""
    reason: str = ""
    checked_at: float = field(default_factory=time.time)

    @property
    def needs_action(self) -> bool:
        return self.decision in (ChainDecision.ESCALATE, ChainDecision.HALT)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "decision_label": self.decision.label,
            "level": self.level.value,
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "chain_risk": self.chain_risk.to_dict(),
            "actions": self.actions,
            "agent_id": self.agent_id,
            "reason": self.reason,
        }


class ChainInterruptGate:
    """链级意图中断门。

    Usage::

        gate = ChainInterruptGate()
        verdict = gate.evaluate_agent(tracker, "agent-01")
        if verdict.decision == ChainDecision.HALT:
            circuit_breaker.force_halt(reason=verdict.reason)

    Attributes:
        handlers: 治理动作回调列表 (force_halt / trust_demote / hitl...)。
    """

    def __init__(
        self,
        pattern_library: ChainPatternLibrary | None = None,
        hypothesis_engine: IntentHypothesisEngine | None = None,
        aggregator: SequentialRiskAggregator | None = None,
        long_horizon_analyzer: Any | None = None,
    ) -> None:
        self._library = pattern_library or ChainPatternLibrary()
        self._engine = hypothesis_engine or IntentHypothesisEngine(self._library)
        self._aggregator = aggregator or SequentialRiskAggregator()
        # G2-I7: 长时程漂移分析器 (34.5h 慢漂移检测)。可配置; 未配置则跳过。
        self._long_horizon = long_horizon_analyzer
        self._handlers: list[Callable[[IntentVerdict], None]] = []
        self._history: list[IntentVerdict] = []

    # -- 主裁决 --

    def evaluate(
        self,
        chain: list[ActionRecord],
        agent_id: str = "",
    ) -> IntentVerdict:
        """对动作链执行完整链级裁决 (C2→C3→C4→决策)。

        Args:
            chain: 动作链。
            agent_id: agent 标识。

        Returns:
            IntentVerdict。
        """
        matches = self._library.match(chain)
        hypotheses = self._engine.hypothesize(chain, matches)
        chain_risk = self._aggregator.aggregate(chain, matches)

        verdict = self._decide(
            chain_risk=chain_risk,
            hypotheses=hypotheses,
            matches=matches,
            agent_id=agent_id,
        )
        self._history.append(verdict)
        self._notify(verdict)
        return verdict

    def evaluate_agent(
        self,
        tracker: ActionChainTracker,
        agent_id: str,
    ) -> IntentVerdict:
        """一站式评估: 从 tracker 取链 → evaluate (含长时程漂移分析)。

        G2-I7: 配置 ``long_horizon_analyzer`` 时, 若检测到慢速漂移
        (前期 LOW → 后期 HIGH 的渐进越权), 将裁决升级到 WATCH —
        "34.5h 问题"在运行时获得治理响应。

        Args:
            tracker: 动作链追踪器。
            agent_id: 目标 agent。

        Returns:
            IntentVerdict。
        """
        chain = tracker.chain(agent_id)
        verdict = self.evaluate(chain, agent_id=agent_id)

        if self._long_horizon is not None and len(chain) >= 2:
            try:
                analysis = self._long_horizon.analyze(tracker, agent_id)
                if analysis.drift_detected:
                    # 慢速漂移 → 至少 WATCH (观察); 已有更高裁决 (ESCALATE/HALT) 保持
                    if verdict.decision in (ChainDecision.CONTINUE, ChainDecision.WATCH):
                        verdict.decision = ChainDecision.WATCH
                        if verdict.level in (ChainRiskLevel.LOW, ChainRiskLevel.MEDIUM):
                            verdict.level = ChainRiskLevel.MEDIUM
                        verdict.reason = f"{verdict.reason}; {analysis.drift_signal}"
                        verdict.actions = list(dict.fromkeys(verdict.actions + ["observe"]))
            except Exception:  # noqa: BLE001 — 漂移分析失败不阻断
                pass

        return verdict

    # -- 治理动作注册 --

    def on_verdict(self, handler: Callable[[IntentVerdict], None]) -> None:
        """注册治理动作处理器 (熔断/信任降级/HITL 等)。

        Args:
            handler: 接收 IntentVerdict 的回调。
        """
        self._handlers.append(handler)

    @property
    def history(self) -> list[IntentVerdict]:
        return list(self._history)

    # -- 内部 --

    def _decide(
        self,
        chain_risk: ChainRisk,
        hypotheses: list[IntentHypothesis],
        matches: list[PatternMatch],
        agent_id: str,
    ) -> IntentVerdict:
        # CRITICAL: 链风险 CRITICAL 或存在 CRITICAL 意图假设 → HALT
        if chain_risk.level == ChainRiskLevel.CRITICAL:
            return IntentVerdict(
                decision=ChainDecision.HALT,
                level=ChainRiskLevel.CRITICAL,
                hypotheses=hypotheses,
                chain_risk=chain_risk,
                matches=matches,
                actions=["force_halt", "quarantine"],
                agent_id=agent_id,
                reason=f"链风险 CRITICAL: {', '.join(chain_risk.signals)}",
            )
        critical_hypothesis = any(
            h.escalation == ChainRiskLevel.CRITICAL for h in hypotheses
        )
        if critical_hypothesis:
            return IntentVerdict(
                decision=ChainDecision.HALT,
                level=ChainRiskLevel.CRITICAL,
                hypotheses=hypotheses,
                chain_risk=chain_risk,
                matches=matches,
                actions=["force_halt", "quarantine"],
                agent_id=agent_id,
                reason=f"CRITICAL 意图假设: {hypotheses[0].strategy}",
            )

        # HIGH: 链风险 HIGH 或 HIGH 假设 → ESCALATE (HITL/信任降级)
        if chain_risk.level == ChainRiskLevel.HIGH or any(
            h.escalation == ChainRiskLevel.HIGH for h in hypotheses
        ):
            return IntentVerdict(
                decision=ChainDecision.ESCALATE,
                level=ChainRiskLevel.HIGH,
                hypotheses=hypotheses,
                chain_risk=chain_risk,
                matches=matches,
                actions=["hitl_approval", "trust_demote"],
                agent_id=agent_id,
                reason="链风险 HIGH 或检测到 HIGH 意图假设",
            )

        # MEDIUM → WATCH
        if chain_risk.level == ChainRiskLevel.MEDIUM:
            return IntentVerdict(
                decision=ChainDecision.WATCH,
                level=ChainRiskLevel.MEDIUM,
                hypotheses=hypotheses,
                chain_risk=chain_risk,
                matches=matches,
                actions=["observe"],
                agent_id=agent_id,
                reason=f"链风险 MEDIUM: {', '.join(chain_risk.signals)}",
            )

        return IntentVerdict(
            decision=ChainDecision.CONTINUE,
            level=ChainRiskLevel.LOW,
            hypotheses=hypotheses,
            chain_risk=chain_risk,
            matches=matches,
            actions=[],
            agent_id=agent_id,
            reason="链风险 LOW",
        )

    def _notify(self, verdict: IntentVerdict) -> None:
        if not verdict.needs_action:
            return
        for handler in self._handlers:
            try:
                handler(verdict)
            except Exception:  # noqa: BLE001 — 处理器异常不阻断主流程
                continue
