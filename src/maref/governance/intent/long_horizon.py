"""LongHorizonAnalyzer — 长时程动作链分析 (v0.52.1 G2-C5)。

解决 AISI 报告的"34.5h 问题": 缓慢而稳定的越界在短窗口 (滑动窗口) 内
可能不触发异常 — 因为基线会跟着漂移, 且每段窗口内动作量都不大。

本模块把 agent 的完整历史链按时间切片, 逐段聚合风险, 检测**慢速漂移**:
早期 LOW → 后期 HIGH 的渐进越权模式, 或跨窗口持续累积到临界。

输出 ``HorizonAnalysis``: 分段风险 + 趋势信号 + 综合评估。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maref.governance.intent.aggregator import ChainRisk, SequentialRiskAggregator
from maref.governance.intent.chain_tracker import ActionChainTracker, ActionRecord, ChainRiskLevel
from maref.governance.intent.patterns import ChainPatternLibrary


@dataclass
class HorizonAnalysis:
    """长时程分析结果。

    Attributes:
        agent_id: 被分析的 agent。
        segment_risks: 各时间分段的风险列表。
        drift_detected: 是否检测到慢速漂移。
        drift_signal: 漂移描述。
        peak_level: 全链最高分段风险级。
        total_actions: 全链动作总数。
    """

    agent_id: str = ""
    segment_risks: list[ChainRisk] = field(default_factory=list)
    drift_detected: bool = False
    drift_signal: str = ""
    peak_level: ChainRiskLevel = ChainRiskLevel.LOW
    total_actions: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "segment_risks": [r.to_dict() for r in self.segment_risks],
            "drift_detected": self.drift_detected,
            "drift_signal": self.drift_signal,
            "peak_level": self.peak_level.value,
            "total_actions": self.total_actions,
        }


class LongHorizonAnalyzer:
    """长时程漂移分析器。

    Usage::

        analyzer = LongHorizonAnalyzer()
        analysis = analyzer.analyze(tracker, "agent-01")

    Attributes:
        segment_seconds: 时间切片时长 (默认 15 分钟)。
        min_segments: 至少多少段才做趋势判定。
    """

    def __init__(
        self,
        segment_seconds: float = 900.0,
        min_segments: int = 2,
        pattern_library: ChainPatternLibrary | None = None,
    ) -> None:
        self.segment_seconds = segment_seconds
        self.min_segments = min_segments
        self._aggregator = SequentialRiskAggregator()
        self._library = pattern_library or ChainPatternLibrary()

    def analyze(
        self,
        tracker: ActionChainTracker,
        agent_id: str,
        pattern_matches: dict[int, list] | None = None,
    ) -> HorizonAnalysis:
        """分析 agent 的完整动作历史。

        Args:
            tracker: 动作链追踪器。
            agent_id: 目标 agent。
            pattern_matches: 可选, 段索引 -> 该段模式匹配列表 (预留)。

        Returns:
            HorizonAnalysis。
        """
        chain = tracker.chain(agent_id)
        total = len(chain)
        if total == 0:
            return HorizonAnalysis(agent_id=agent_id)

        segments = self._slice(chain)
        segment_risks: list[ChainRisk] = []
        for seg in segments:
            matches = self._library.match(seg)
            segment_risks.append(self._aggregator.aggregate(seg, matches))

        peak = max(
            segment_risks,
            key=lambda r: _LEVEL_ORDER.get(r.level, 0),
            default=ChainRisk(level=ChainRiskLevel.LOW),
        )

        analysis = HorizonAnalysis(
            agent_id=agent_id,
            segment_risks=segment_risks,
            peak_level=peak.level,
            total_actions=total,
        )

        if len(segment_risks) >= self.min_segments:
            # early 取前 min_segments 段, late 取后 min_segments 段; 确保不重叠
            early = segment_risks[: self.min_segments]
            late = segment_risks[-self.min_segments :]
            if len(segment_risks) < 2 * self.min_segments:
                mid = len(segment_risks) // 2
                early = segment_risks[:mid]
                late = segment_risks[mid:]
            early_max = max(_LEVEL_ORDER.get(r.level, 0) for r in early)
            late_max = max(_LEVEL_ORDER.get(r.level, 0) for r in late)
            if late_max > early_max and late_max >= _LEVEL_ORDER[ChainRiskLevel.MEDIUM]:
                analysis.drift_detected = True
                analysis.drift_signal = (
                    f"慢速漂移: 早期段峰 {_reverse_level(early_max)} → "
                    f"后期段峰 {_reverse_level(late_max)}"
                )

        return analysis

    def _slice(self, chain: list[ActionRecord]) -> list[list[ActionRecord]]:
        """按时间切片动作链。"""
        if not chain:
            return []
        segments: list[list[ActionRecord]] = []
        current: list[ActionRecord] = []
        base_ts = chain[0].timestamp
        for record in chain:
            if record.timestamp - base_ts > self.segment_seconds and current:
                segments.append(current)
                current = []
                base_ts = record.timestamp
            current.append(record)
        if current:
            segments.append(current)
        return segments


_LEVEL_ORDER = {
    ChainRiskLevel.LOW: 0,
    ChainRiskLevel.MEDIUM: 1,
    ChainRiskLevel.HIGH: 2,
    ChainRiskLevel.CRITICAL: 3,
}


def _reverse_level(order: int) -> str:
    for level, o in _LEVEL_ORDER.items():
        if o == order:
            return level.value
    return "LOW"
