"""SequentialRiskAggregator — 单步风险跨动作累积 (v0.52.1 G2-C4)。

核心治理缺口 G2 的直接解法: **单步 LOW 的组合攻击**。
AISI 观察: 每个动作单独看都无害 (创建账号/发评论/提 PR), 组合成供应链攻击。

聚合信号:
1. **模式命中** — 直接采用模式严重度 (最高优先级)
2. **累积计分** — 单步风险加权累加 (LOW=0/MEDIUM=1/HIGH=3/CRITICAL=6)
3. **密集度** — 短窗口内动作数量 (密集推进 → 有计划性)
4. **敏感多样性** — 链中涉及的敏感动作类别数 (credential/identity/network/execute)
5. **风险递增** — 链后半段风险均值 > 前半段 (渐进越权)

输出 ``ChainRisk``: level + score + signals, 供 ChainInterruptGate (C6) 决策。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maref.governance.intent.chain_tracker import ActionRecord, ChainRiskLevel
from maref.governance.intent.patterns import PatternMatch

# 单步风险计分
_STEP_SCORE: dict[ChainRiskLevel, int] = {
    ChainRiskLevel.LOW: 0,
    ChainRiskLevel.MEDIUM: 1,
    ChainRiskLevel.HIGH: 3,
    ChainRiskLevel.CRITICAL: 6,
}

# 敏感动作类别 (组合攻击常见)
_SENSITIVE_CATEGORIES = (
    "credential",
    "identity",
    "network",
    "execute",
    "external",
    "delete",
)

# 分级阈值
_MEDIUM_THRESHOLD = 3
_HIGH_THRESHOLD = 6
_CRITICAL_THRESHOLD = 10


@dataclass
class ChainRisk:
    """链级风险聚合结果。

    Attributes:
        level: 链级风险分级。
        score: 聚合评分。
        signals: 触发信号列表。
        chain_length: 链长度。
        window_seconds: 时间跨度。
    """

    level: ChainRiskLevel = ChainRiskLevel.LOW
    score: float = 0.0
    signals: list[str] = field(default_factory=list)
    chain_length: int = 0
    window_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "score": round(self.score, 2),
            "signals": self.signals,
            "chain_length": self.chain_length,
            "window_seconds": round(self.window_seconds, 1),
        }


class SequentialRiskAggregator:
    """顺序风险聚合器。

    Usage::

        aggregator = SequentialRiskAggregator()
        risk = aggregator.aggregate(chain, matches)
    """

    def aggregate(
        self,
        chain: list[ActionRecord],
        matches: list[PatternMatch] | None = None,
    ) -> ChainRisk:
        """对动作链聚合链级风险。

        Args:
            chain: 动作链 (时间升序)。
            matches: 模式匹配结果 (可选)。

        Returns:
            ChainRisk。
        """
        matches = matches or []
        signals: list[str] = []
        score = 0.0

        # 1. 模式命中 → 直接采用最高模式严重度
        if matches:
            highest = max(
                matches,
                key=lambda m: _SEVERITY_ORDER.get(m.pattern.severity, 0),
            )
            signals.append(f"pattern_match:{highest.pattern.pattern_id}")
            score = max(score, float(_SEVERITY_SCORE.get(highest.pattern.severity, 0)))

        # 2. 累积计分
        step_sum = sum(_STEP_SCORE.get(r.risk_level, 0) for r in chain)
        if step_sum > 0:
            score += step_sum * 0.3
            signals.append(f"accumulated_step_risk:{step_sum}")

        # 3. 密集度 (短窗口多动作)
        if len(chain) >= 4:
            span = (chain[-1].timestamp - chain[0].timestamp) or 1.0
            density = len(chain) / max(1.0, span / 60.0)
            if density > 1.0:  # > 1 动作/分钟
                score += 1.0
                signals.append(f"high_density:{round(density, 1)}")

        # 4. 敏感多样性
        categories = {r.category.value for r in chain}
        sensitive_hit = sum(1 for c in categories if c in _SENSITIVE_CATEGORIES)
        if sensitive_hit >= 3:
            score += 2.0
            signals.append(f"sensitive_categories:{sensitive_hit}")

        # 5. 风险递增 (后段风险 > 前段)
        if len(chain) >= 4:
            mid = len(chain) // 2
            front = sum(_STEP_SCORE.get(r.risk_level, 0) for r in chain[:mid])
            back = sum(_STEP_SCORE.get(r.risk_level, 0) for r in chain[mid:])
            if back > front:
                score += 1.5
                signals.append("risk_escalation_trend")

        level = self._level_from_score(score)
        return ChainRisk(
            level=level,
            score=score,
            signals=signals,
            chain_length=len(chain),
            window_seconds=(chain[-1].timestamp - chain[0].timestamp) if chain else 0.0,
        )

    def _level_from_score(self, score: float) -> ChainRiskLevel:
        if score >= _CRITICAL_THRESHOLD:
            return ChainRiskLevel.CRITICAL
        if score >= _HIGH_THRESHOLD:
            return ChainRiskLevel.HIGH
        if score >= _MEDIUM_THRESHOLD:
            return ChainRiskLevel.MEDIUM
        return ChainRiskLevel.LOW


_SEVERITY_ORDER = {
    "CRITICAL": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
}

_SEVERITY_SCORE = {
    "CRITICAL": 12.0,
    "HIGH": 8.0,
    "MEDIUM": 4.0,
    "LOW": 0.0,
}
