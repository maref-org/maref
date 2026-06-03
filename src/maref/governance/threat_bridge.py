"""
威胁情报 → 治理层桥接模块

订阅威胁情报事件，将高威胁自动转换为治理层状态转换。

解决审计问题 P13：ThreatIntelligenceEngine 发现威胁但不触发 governance 状态转换。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from maref.governance.state_machine import GovernanceStateMachine
from maref.monitoring.threat_intelligence import (
    ThreatAlert,
    ThreatSeverity,
)


@dataclass
class ThreatGovernanceMapping:
    """威胁等级到治理动作的映射配置"""

    critical_action: str = "force_halt"
    high_action: str = "force_stabilize"
    medium_action: str = "log_only"
    low_action: str = "log_only"
    auto_resolve_low: bool = True


class ThreatGovernanceBridge:
    """
    威胁情报与治理状态的桥接器。

    当威胁情报引擎检测到高严重度威胁时，自动触发治理层响应：
    - CRITICAL → force_halt（紧急停机）
    - HIGH → force_stabilize（强制稳定）
    - MEDIUM/LOW → 记录日志，不触发状态转换

    Usage:
        bridge = ThreatGovernanceBridge(state_machine)
        bridge.on_threat_alert(alert)
    """

    def __init__(
        self,
        state_machine: GovernanceStateMachine,
        mapping: ThreatGovernanceMapping | None = None,
    ) -> None:
        self._sm = state_machine
        self._mapping = mapping or ThreatGovernanceMapping()
        self._alert_history: list[ThreatAlert] = []
        self._action_log: list[dict[str, Any]] = []
        self._handlers: list[Callable[[ThreatAlert, str], None]] = []

    def on_threat_alert(self, alert: ThreatAlert) -> dict[str, Any]:
        """
        处理威胁告警，根据严重度触发相应治理动作。

        Returns:
            动作执行结果，包含 triggered（是否触发转换）和 action（执行的动作）
        """
        self._alert_history.append(alert)

        severity = alert.severity
        action: str = ""
        triggered: bool = False
        reason: str = f"threat:{alert.alert_type}:{alert.alert_id}"

        if severity == ThreatSeverity.CRITICAL:
            action = self._mapping.critical_action
            triggered = self._sm.force_halt(reason=reason)
        elif severity == ThreatSeverity.HIGH:
            action = self._mapping.high_action
            triggered = self._sm.force_stabilize(reason=reason)
        elif severity == ThreatSeverity.MEDIUM:
            action = self._mapping.medium_action
            triggered = False
        elif severity == ThreatSeverity.LOW:
            action = self._mapping.low_action
            triggered = False
            if self._mapping.auto_resolve_low:
                alert.is_active = False
                alert.resolved_at = __import__("datetime").datetime.now()
        else:
            action = "none"

        result = {
            "alert_id": alert.alert_id,
            "severity": severity.value,
            "action": action,
            "triggered": triggered,
            "current_state": self._sm.current_state.name,
            "reason": reason,
        }
        self._action_log.append(result)

        # 通知外部处理器
        for handler in self._handlers:
            try:
                handler(alert, action)
            except Exception:
                pass

        return result

    def register_handler(self, handler: Callable[[ThreatAlert, str], None]) -> None:
        """注册威胁处理回调。"""
        self._handlers.append(handler)

    def get_alert_statistics(self) -> dict[str, Any]:
        """获取威胁告警统计信息。"""
        if not self._alert_history:
            return {"total": 0, "by_severity": {}, "actions_taken": 0}

        by_severity: dict[str, int] = {}
        for alert in self._alert_history:
            sev = alert.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

        actions_taken = sum(1 for log in self._action_log if log.get("triggered"))

        return {
            "total": len(self._alert_history),
            "by_severity": by_severity,
            "actions_taken": actions_taken,
            "current_state": self._sm.current_state.name,
        }

    def get_recent_alerts(self, limit: int = 10) -> list[ThreatAlert]:
        """获取最近的威胁告警。"""
        return self._alert_history[-limit:]
