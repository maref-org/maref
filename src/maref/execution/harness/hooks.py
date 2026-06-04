"""Harness 生命周期钩子系统。

封装 recursive/hook_registry.py 的 HookRegistry + HookChain，
定义 6 个 harness.* 话题，在 UnifiedHarness 各生命周期阶段触发。
"""

from __future__ import annotations

from typing import Any

from maref.recursive.hook_chain import ChainResult, HookChain
from maref.recursive.hook_registry import HookHandler, HookRegistry

# Harness 生命周期 6 大话题
HARNESS_TOPICS: list[str] = [
    "harness.start",
    "harness.preflight",
    "harness.step",
    "harness.stop",
    "harness.fail",
    "harness.validate",
    "harness.tool_call",
]


class HarnessHookRegistry:
    """包装 HookRegistry，统一管理 harness 生命周期钩子。"""

    def __init__(self, registry: HookRegistry | None = None) -> None:
        self._registry = registry or HookRegistry()

    @property
    def registry(self) -> HookRegistry:
        return self._registry

    def register(self, topic: str, handler: HookHandler, priority: int = 0, handler_id: str | None = None) -> str:
        """注册一个钩子处理器到指定话题。"""
        if topic not in self._valid_topics():
            raise ValueError(f"Unknown harness topic: {topic}. Valid: {HARNESS_TOPICS}")
        return self._registry.register(topic, handler, priority, handler_id)

    def unregister(self, topic: str, handler_id: str) -> bool:
        return self._registry.unregister(topic, handler_id)

    def fire(self, topic: str, event_data: dict[str, Any]) -> ChainResult:
        """触发指定话题的钩子链。"""
        return HookChain(self._registry).execute(topic, event_data)

    def get_chain(self, topic: str) -> list[dict[str, Any]]:
        return [
            {"handler_id": e.handler_id, "priority": e.priority}
            for e in self._registry.get_chain(topic)
        ]

    def is_registered(self, topic: str) -> bool:
        return len(self._registry.get_chain(topic)) > 0

    def clear(self) -> None:
        self._registry.clear()

    @staticmethod
    def _valid_topics() -> set[str]:
        return set(HARNESS_TOPICS)
