"""
Governance ↔ Recursive 桥接模块

提供 FormalWall 模式，实现 governance 层与 recursive 层的双向通信：
- recursive 模块通过桥接层查询 governance 状态
- governance 通过回调接收 recursive 事件

解决审计问题 P11：13 个 recursive 文件仅 1 个导入 governance，无双向反馈。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState, StateTransition

logger = logging.getLogger(__name__)


class RecursiveEventType(Enum):
    """Recursive 层事件类型"""

    AGENT_REGISTERED = "agent_registered"
    AGENT_EVOLVED = "agent_evolved"
    SAFETY_VIOLATION = "safety_violation"
    AUDIT_ANOMALY = "audit_anomaly"
    CIRCUIT_TRIPPED = "circuit_tripped"
    TRUST_CHANGED = "trust_changed"
    PHASE_TRANSITION = "phase_transition"


@dataclass
class RecursiveEvent:
    """Recursive 层发出的事件"""

    event_type: RecursiveEventType
    source_agent: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: __import__("time").time())


@dataclass
class GovernanceQuery:
    """向 governance 层查询的状态信息"""

    current_state: GovernanceState
    current_entropy: int
    transition_count: int
    is_terminal: bool
    valid_next_states: list[GovernanceState]


class GovernanceBridge:
    """
    Governance 与 Recursive 层之间的桥接器。

    提供 FormalWall 安全边界：
    - 所有跨层通信必须经过此桥接器
    - 事件转换和验证在此进行
    - 支持双向回调注册

    Usage:
        bridge = GovernanceBridge(state_machine)
        bridge.register_recursive_hook(on_recursive_event)
        bridge.notify_governance(event)
        query = bridge.query_governance_state()
    """

    def __init__(self, state_machine: GovernanceStateMachine) -> None:
        self._sm = state_machine
        self._recursive_hooks: list[Callable[[StateTransition], None]] = []
        self._governance_hooks: list[Callable[[RecursiveEvent], bool]] = []
        self._event_history: list[RecursiveEvent] = []
        self._enabled: bool = True

    # --- 状态查询 ---

    def query_governance_state(self) -> GovernanceQuery:
        """查询当前治理状态（供 recursive 层调用）。"""
        return GovernanceQuery(
            current_state=self._sm.current_state,
            current_entropy=self._sm.current_entropy,
            transition_count=self._sm.transition_count,
            is_terminal=self._sm.is_terminal(),
            valid_next_states=self._sm.valid_next_states,
        )

    def is_transition_allowed(self, target: GovernanceState) -> bool:
        """检查状态转换是否被允许。"""
        return self._sm.can_transition(target)

    # --- Recursive → Governance ---

    def notify_governance(self, event: RecursiveEvent) -> bool:
        """
        将 recursive 事件通知 governance 层。

        根据事件类型自动触发相应的状态转换：
        - SAFETY_VIOLATION → 尝试 force_stabilize
        - CIRCUIT_TRIPPED → 尝试 force_halt
        - AUDIT_ANOMALY → 记录但不强制转换

        Returns:
            True 如果事件被成功处理
        """
        if not self._enabled:
            return False

        self._event_history.append(event)

        # 触发 governance 动作
        handled = False
        if event.event_type == RecursiveEventType.SAFETY_VIOLATION:
            handled = self._sm.force_stabilize(reason=f"safety_violation:{event.source_agent}")
        elif event.event_type == RecursiveEventType.CIRCUIT_TRIPPED:
            handled = self._sm.force_halt(reason=f"circuit_tripped:{event.source_agent}")
        elif event.event_type == RecursiveEventType.AUDIT_ANOMALY:
            # 记录异常但不强制状态转换
            handled = True

        # 通知 governance 层钩子
        for hook in self._governance_hooks:
            try:
                hook(event)
            except Exception:
                logger.exception("Governance hook %s failed, isolating", getattr(hook, '__name__', str(hook)))

        return handled

    # --- Governance → Recursive ---

    def register_recursive_hook(self, hook: Callable[[StateTransition], None]) -> None:
        """
        注册 recursive 层回调，在 governance 状态转换时触发。

        这是 governance 向 recursive 层发送通知的主要机制。
        """
        self._recursive_hooks.append(hook)
        self._sm.add_callback(hook)

    def remove_recursive_hook(self, hook: Callable[[StateTransition], None]) -> None:
        """移除 recursive 层回调。"""
        if hook in self._recursive_hooks:
            self._recursive_hooks.remove(hook)
            self._sm.remove_callback(hook)

    def register_governance_hook(self, hook: Callable[[RecursiveEvent], bool]) -> None:
        """注册 governance 层事件处理器。"""
        self._governance_hooks.append(hook)

    # --- 控制 ---

    def enable(self) -> None:
        """启用桥接通信。"""
        self._enabled = True

    def disable(self) -> None:
        """禁用桥接通信（紧急情况下使用）。"""
        self._enabled = False

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def event_count(self) -> int:
        return len(self._event_history)

    def get_recent_events(
        self, event_type: RecursiveEventType | None = None, limit: int = 10
    ) -> list[RecursiveEvent]:
        """获取最近的事件记录。"""
        events = self._event_history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[-limit:]
