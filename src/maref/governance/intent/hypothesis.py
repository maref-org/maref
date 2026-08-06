"""IntentHypothesisEngine — 意图假设引擎 (v0.52.1 G2-C3)。

从动作链的恶意模式匹配结果生成结构化意图假设:
``intent = {goal, strategy, escalation, confidence}``

对位 AISI 报告的核心判断: 欺骗是**目标驱动下的涌现行为** — 单步看似正常,
组合成攻击。本引擎把这些组合模式翻译为可审计的"意图假设", 供
``ChainInterruptGate`` (C6) 决定是否升级治理动作。

置信度 = 模式权重 × 匹配质量 (gap 惩罚) × 链跨度因子。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maref.governance.intent.chain_tracker import ActionRecord, ChainRiskLevel
from maref.governance.intent.patterns import ChainPatternLibrary, PatternMatch

# 模式严重度 → 意图 escalation
_SEVERITY_TO_ESCALATION: dict[str, ChainRiskLevel] = {
    "CRITICAL": ChainRiskLevel.CRITICAL,
    "HIGH": ChainRiskLevel.HIGH,
    "MEDIUM": ChainRiskLevel.MEDIUM,
    "LOW": ChainRiskLevel.LOW,
}

# 模式 → 目标描述 (供假设生成)
_PATTERN_GOAL: dict[str, str] = {
    "supply_chain_lie": "向开源供应链植入恶意代码",
    "se_human_lure": "对真实人类实施社交工程攻击",
    "credential_harvest": "获取/收集敏感凭证",
    "identity_rotation": "通过身份轮换掩盖主体",
    "record_tamper": "篡改审计/历史记录掩盖痕迹",
    "anonymous_evasion": "通过匿名网络规避监控",
    "cross_agent_share": "跨代理共享账号与遗产",
    "code_inject_hide": "植入隐藏指令并清理痕迹",
}


@dataclass
class IntentHypothesis:
    """一个从动作链推导出的意图假设。

    Attributes:
        goal: 推测的恶意目标。
        strategy: 采用的策略 (对应命中的模式)。
        escalation: 建议的链级风险升级。
        confidence: 置信度 0.0~1.0。
        evidence_patterns: 支撑的模式 ID 列表。
        chain_span: 覆盖的动作数。
        matched_actions: 命中的具体动作。
    """

    goal: str
    strategy: str = ""
    escalation: ChainRiskLevel = ChainRiskLevel.LOW
    confidence: float = 0.0
    evidence_patterns: list[str] = field(default_factory=list)
    chain_span: int = 0
    matched_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "strategy": self.strategy,
            "escalation": self.escalation.value,
            "confidence": round(self.confidence, 3),
            "evidence_patterns": self.evidence_patterns,
            "chain_span": self.chain_span,
            "matched_actions": self.matched_actions,
        }


class IntentHypothesisEngine:
    """意图假设引擎。

    Usage::

        engine = IntentHypothesisEngine()
        matches = library.match(chain)
        hypotheses = engine.hypothesize(chain, matches)
    """

    def __init__(self, pattern_library: ChainPatternLibrary | None = None) -> None:
        self._library = pattern_library or ChainPatternLibrary()

    def hypothesize(
        self,
        chain: list[ActionRecord],
        matches: list[PatternMatch],
    ) -> list[IntentHypothesis]:
        """从动作链 + 模式匹配生成意图假设。

        Args:
            chain: 动作链。
            matches: 模式匹配结果。

        Returns:
            意图假设列表 (按置信度降序)。
        """
        if not matches:
            return []
        chain_len = max(1, len(chain))
        hypotheses: list[IntentHypothesis] = []
        for match in matches:
            confidence = self._compute_confidence(match, chain_len)
            escalation = _SEVERITY_TO_ESCALATION.get(match.pattern.severity, ChainRiskLevel.LOW)
            hypotheses.append(
                IntentHypothesis(
                    goal=_PATTERN_GOAL.get(match.pattern.pattern_id, match.pattern.name),
                    strategy=match.pattern.pattern_id,
                    escalation=escalation,
                    confidence=confidence,
                    evidence_patterns=[match.pattern.pattern_id],
                    chain_span=match.span,
                    matched_actions=[r.action for r in match.matched_records],
                )
            )
        hypotheses.sort(key=lambda h: h.confidence, reverse=True)
        return hypotheses

    def _compute_confidence(self, match: PatternMatch, chain_len: int) -> float:
        """置信度 = 模式权重 × gap 惩罚 × 跨度因子。

        - 权重归一化: weight / 1.5 (最大权重)
        - gap 惩罚: 0.7 ^ gap_count (每插一个无关动作降 30%)
        - 跨度因子: min(1.0, span / 3) — 至少覆盖 3 步才满置信
        """
        weight_factor = min(1.0, match.pattern.weight / 1.5)
        gap_factor = pow(0.7, match.gap_count)
        span_factor = min(1.0, match.span / 3.0)
        base = weight_factor * gap_factor * span_factor
        return round(min(1.0, base), 3)
