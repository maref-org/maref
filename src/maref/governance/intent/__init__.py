"""G2 动作链意图推理 (v0.52.1 M3) — 检测组合欺骗动作链。

对位 AISI 欺骗测试: 单步动作看似合规, 组合构成欺骗性攻击。

模块组成:
- ``chain_tracker`` — ActionChainTracker 动作链追踪 (C1)
- ``patterns`` — ChainPatternLibrary 恶意链模式库 (C2, 8 个内置 AISI 模式)
- ``hypothesis`` — IntentHypothesisEngine 意图假设引擎 (C3)
- ``aggregator`` — SequentialRiskAggregator 单步风险累积 (C4)
- ``long_horizon`` — LongHorizonAnalyzer 长时程漂移分析 (C5)
- ``gate`` — ChainInterruptGate 链级中断门 (C6)
"""

from __future__ import annotations

from maref.governance.intent.aggregator import (
    ChainRisk,
    SequentialRiskAggregator,
)
from maref.governance.intent.chain_tracker import (
    ActionCategory,
    ActionChainTracker,
    ActionRecord,
    ChainRiskLevel,
)
from maref.governance.intent.factory import build_chain_intent_gate
from maref.governance.intent.gate import (
    ChainDecision,
    ChainInterruptGate,
    IntentVerdict,
)
from maref.governance.intent.hypothesis import (
    IntentHypothesis,
    IntentHypothesisEngine,
)
from maref.governance.intent.long_horizon import (
    HorizonAnalysis,
    LongHorizonAnalyzer,
)
from maref.governance.intent.patterns import (
    ActionMatcher,
    ChainPattern,
    ChainPatternLibrary,
    PatternMatch,
)

__all__ = [
    "ActionCategory",
    "ActionRecord",
    "ActionChainTracker",
    "ChainRiskLevel",
    "ChainRisk",
    "ChainPattern",
    "ChainPatternLibrary",
    "ActionMatcher",
    "PatternMatch",
    "IntentHypothesis",
    "IntentHypothesisEngine",
    "SequentialRiskAggregator",
    "HorizonAnalysis",
    "LongHorizonAnalyzer",
    "ChainDecision",
    "IntentVerdict",
    "ChainInterruptGate",
    "build_chain_intent_gate",
]
