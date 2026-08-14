"""Chain intent 组件工厂 (v0.52.1 G2-C1 生产接线)。

为生产管线 (GaaS GovernanceRouter / GovernedPipeline) 提供统一的
动作链意图推理组件装配, 使链级评估在生产运行时生效。

用法::

    from maref.governance.intent.factory import build_chain_intent_gate

    tracker, gate = build_chain_intent_gate()
    pipeline = GovernancePipeline(intent_tracker=tracker, intent_gate=gate, ...)
"""

from __future__ import annotations

from maref.governance.intent.chain_tracker import ActionChainTracker
from maref.governance.intent.gate import ChainInterruptGate
from maref.governance.intent.long_horizon import LongHorizonAnalyzer
from maref.governance.intent.patterns import ChainPatternLibrary


def build_chain_intent_gate(
    window_seconds: float = 3600.0,
    max_gap: int = 2,
) -> tuple[ActionChainTracker, ChainInterruptGate]:
    """装配动作链追踪器与链级中断门。

    Args:
        window_seconds: 动作链滑动窗口时长 (秒, 默认 1 小时)。
        max_gap: 模式匹配允许的最大 gap。

    Returns:
        (tracker, gate): 注入 GovernancePipeline 的 intent_tracker / intent_gate。
    """
    library = ChainPatternLibrary(max_gap=max_gap)
    library.register_builtin_patterns()
    tracker = ActionChainTracker(window_seconds=window_seconds)
    # G2-I7: 装配长时程漂移分析器, 使 34.5h 慢漂移在生产运行时获得治理响应。
    horizon = LongHorizonAnalyzer(pattern_library=library)
    gate = ChainInterruptGate(pattern_library=library, long_horizon_analyzer=horizon)
    return tracker, gate
