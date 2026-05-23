"""
安全编排与自动化响应 (SOAR)

提供基础的安全编排、自动化和响应能力。
支持事件响应剧本、自动化动作和调度管理。

核心概念:
1. Playbooks - 可配置的响应剧本
2. Actions - 原子化的安全操作
3. Triggers - 事件触发条件
4. Workflows - 组合多个动作的自动化流程
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ActionStatus(Enum):
    """动作状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"


class TriggerCondition(Enum):
    """触发条件"""
    THREAT_ALERT = "threat_alert"
    COMPLIANCE_VIOLATION = "compliance_violation"
    VULNERABILITY_FOUND = "vulnerability_found"
    IOC_MATCH = "ioc_match"
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    ANOMALY_DETECTED = "anomaly_detected"


class NotificationChannel(Enum):
    """通知渠道"""
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    LOG = "log"


@dataclass
class SecurityAction:
    """安全操作"""

    action_id: str
    name: str
    description: str
    action_type: str  # "block_ip", "quarantine_file", "notify", "patch", "isolate_agent"
    executor: Callable | None = None  # 执行函数
    parameters: dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = False
    rollback_action_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "name": self.name,
            "description": self.description,
            "type": self.action_type,
            "parameters": self.parameters,
            "requires_approval": self.requires_approval,
            "rollback": self.rollback_action_id,
        }


@dataclass
class SecurityEvent:
    """安全事件"""

    event_id: str
    event_type: str
    severity: str  # critical, high, medium, low
    title: str
    description: str
    source: str
    detected_at: datetime
    affected_assets: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    is_resolved: bool = False
    resolved_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "type": self.event_type,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "source": self.source,
            "detected_at": self.detected_at.isoformat(),
            "affected_assets": self.affected_assets,
            "is_resolved": self.is_resolved,
        }


@dataclass
class PlaybookStep:
    """剧本步骤"""

    step_id: str
    action_id: str
    order: int
    condition: str | None = None  # 条件表达式
    on_failure: str = "stop"  # "stop", "continue", "rollback"
    timeout_seconds: int = 300
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action_id": self.action_id,
            "order": self.order,
            "condition": self.condition,
            "on_failure": self.on_failure,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class Playbook:
    """响应剧本"""

    playbook_id: str
    name: str
    description: str
    trigger: TriggerCondition
    steps: list[PlaybookStep] = field(default_factory=list)
    enabled: bool = True
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "playbook_id": self.playbook_id,
            "name": self.name,
            "description": self.description,
            "trigger": self.trigger.value,
            "steps": [s.to_dict() for s in self.steps],
            "enabled": self.enabled,
            "tags": self.tags,
        }


@dataclass
class ExecutionRecord:
    """执行记录"""

    record_id: str
    playbook_id: str
    triggered_by: str
    started_at: datetime
    completed_at: datetime | None = None
    status: str = "running"  # running, completed, failed
    step_results: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "playbook_id": self.playbook_id,
            "triggered_by": self.triggered_by,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status,
            "step_count": len(self.step_results),
            "notes": self.notes,
        }


class SecurityOrchestrator:
    """
    安全编排器 (SOAR)

    管理安全事件响应、剧本执行和自动化的核心组件。
    """

    def __init__(self):
        self._actions: dict[str, SecurityAction] = {}
        self._playbooks: dict[str, Playbook] = {}
        self._events: dict[str, SecurityEvent] = {}
        self._execution_history: list[ExecutionRecord] = []
        self._notification_handlers: dict[NotificationChannel, list[Callable]] = {}
        self._event_counter: int = 0

        self._initialize_builtin_actions()
        self._initialize_builtin_playbooks()

    def _initialize_builtin_actions(self) -> None:
        """初始化内置安全操作"""
        builtin = [
            SecurityAction(
                action_id="action-block-ip",
                name="Block IP Address",
                description="Block a suspicious IP at firewall level",
                action_type="block_ip",
                parameters={"ip": "", "duration_hours": 24},
                rollback_action_id="action-unblock-ip",
            ),
            SecurityAction(
                action_id="action-unblock-ip",
                name="Unblock IP Address",
                description="Remove IP from firewall block list",
                action_type="unblock_ip",
                parameters={"ip": ""},
            ),
            SecurityAction(
                action_id="action-quarantine-agent",
                name="Quarantine Agent",
                description="Isolate a suspicious agent from the network",
                action_type="isolate_agent",
                parameters={"agent_id": "", "isolation_level": "full"},
                requires_approval=True,
            ),
            SecurityAction(
                action_id="action-notify-team",
                name="Notify Security Team",
                description="Send notification to security team",
                action_type="notify",
                parameters={"channel": "slack", "message": "", "priority": "high"},
            ),
            SecurityAction(
                action_id="action-create-ticket",
                name="Create Incident Ticket",
                description="Create an incident response ticket",
                action_type="create_ticket",
                parameters={"title": "", "severity": "medium", "assignee": "security-team"},
            ),
            SecurityAction(
                action_id="action-scan-vulnerabilities",
                name="Scan for Vulnerabilities",
                description="Trigger vulnerability scan for affected components",
                action_type="scan",
                parameters={"components": [], "scan_type": "full"},
            ),
            SecurityAction(
                action_id="action-revoke-access",
                name="Revoke Access",
                description="Revoke access for a compromised agent",
                action_type="revoke_access",
                parameters={"agent_id": "", "revoke_reason": "security_incident"},
                requires_approval=True,
            ),
        ]

        for action in builtin:
            self.register_action(action)

    def _initialize_builtin_playbooks(self) -> None:
        """初始化内置响应剧本"""

        # 威胁检测剧本
        threat_playbook = Playbook(
            playbook_id="playbook-threat-response",
            name="Threat Detection Response",
            description="Automated response to threat alerts",
            trigger=TriggerCondition.THREAT_ALERT,
            tags=["threat", "automated"],
        )
        threat_playbook.steps = [
            PlaybookStep("step-1", "action-notify-team", order=1, timeout_seconds=60),
            PlaybookStep("step-2", "action-create-ticket", order=2, timeout_seconds=30),
            PlaybookStep("step-3", "action-block-ip", order=3, on_failure="continue", timeout_seconds=120),
            PlaybookStep("step-4", "action-scan-vulnerabilities", order=4, timeout_seconds=600),
        ]
        self.register_playbook(threat_playbook)

        # 合规违规剧本
        compliance_playbook = Playbook(
            playbook_id="playbook-compliance-response",
            name="Compliance Violation Response",
            description="Response to compliance violations",
            trigger=TriggerCondition.COMPLIANCE_VIOLATION,
            tags=["compliance", "manual"],
        )
        compliance_playbook.steps = [
            PlaybookStep("step-1", "action-create-ticket", order=1),
            PlaybookStep("step-2", "action-notify-team", order=2),
        ]
        self.register_playbook(compliance_playbook)

        # Agent隔离剧本
        isolation_playbook = Playbook(
            playbook_id="playbook-agent-isolation",
            name="Agent Isolation Response",
            description="Isolate compromised agent",
            trigger=TriggerCondition.ANOMALY_DETECTED,
            tags=["isolation", "approval_required"],
        )
        isolation_playbook.steps = [
            PlaybookStep("step-1", "action-notify-team", order=1),
            PlaybookStep("step-2", "action-quarantine-agent", order=2, timeout_seconds=120),
            PlaybookStep("step-3", "action-revoke-access", order=3),
            PlaybookStep("step-4", "action-create-ticket", order=4),
        ]
        self.register_playbook(isolation_playbook)

    def register_action(self, action: SecurityAction) -> str:
        """注册安全操作"""
        self._actions[action.action_id] = action
        return action.action_id

    def register_playbook(self, playbook: Playbook) -> str:
        """注册响应剧本"""
        self._playbooks[playbook.playbook_id] = playbook
        return playbook.playbook_id

    def create_event(
        self,
        event_type: str,
        severity: str,
        title: str,
        description: str,
        source: str = "system",
        affected_assets: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SecurityEvent:
        """创建安全事件"""
        event = SecurityEvent(
            event_id=f"event-{int(time.time())}-{self._event_counter}",
            event_type=event_type,
            severity=severity,
            title=title,
            description=description,
            source=source,
            detected_at=datetime.now(),
            affected_assets=affected_assets or [],
            metadata=metadata or {},
        )
        self._event_counter += 1
        self._events[event.event_id] = event
        return event

    def trigger_playbook(
        self,
        playbook_id: str,
        event_id: str,
        parameters: dict[str, Any] | None = None
    ) -> ExecutionRecord | None:
        """
        触发响应剧本

        Args:
            playbook_id: 剧本ID
            event_id: 触发事件ID
            parameters: 剧本参数

        Returns:
            执行记录，如果剧本不存在则返回None
        """
        playbook = self._playbooks.get(playbook_id)
        if not playbook or not playbook.enabled:
            return None

        event = self._events.get(event_id)
        if not event:
            return None

        record = ExecutionRecord(
            record_id=f"exec-{int(time.time())}",
            playbook_id=playbook_id,
            triggered_by=event_id,
            started_at=datetime.now(),
        )

        # 按步骤顺序执行
        steps_sorted = sorted(playbook.steps, key=lambda s: s.order)

        for step in steps_sorted:
            action = self._actions.get(step.action_id)
            if not action:
                record.notes.append(f"Action not found: {step.action_id}")
                record.step_results.append({
                    "step_id": step.step_id,
                    "status": ActionStatus.SKIPPED.value,
                    "reason": "Action not found",
                })
                continue

            # 检查是否需要审批
            if action.requires_approval:
                record.notes.append(f"Action {action.action_id} requires manual approval")
                record.step_results.append({
                    "step_id": step.step_id,
                    "action_id": action.action_id,
                    "status": ActionStatus.PENDING.value,
                    "reason": "Approval required",
                })
                continue

            # 执行动作（模拟）
            try:
                record.step_results.append({
                    "step_id": step.step_id,
                    "action_id": action.action_id,
                    "status": ActionStatus.COMPLETED.value,
                    "action_type": action.action_type,
                })
                record.notes.append(f"Executed {action.name}")
            except Exception as e:
                record.step_results.append({
                    "step_id": step.step_id,
                    "action_id": action.action_id,
                    "status": ActionStatus.FAILED.value,
                    "error": str(e),
                })

                if step.on_failure == "stop":
                    record.status = "failed"
                    record.completed_at = datetime.now()
                    self._execution_history.append(record)
                    return record
                elif step.on_failure == "continue":
                    record.notes.append(f"Continuing despite failure in {action.action_id}")

        record.status = "completed"
        record.completed_at = datetime.now()
        self._execution_history.append(record)

        # 标记事件已处理
        event.is_resolved = True
        event.resolved_at = datetime.now()

        return record

    def auto_respond(self, event_id: str) -> list[ExecutionRecord]:
        """
        自动响应 - 根据事件类型匹配并执行合适的剧本

        Args:
            event_id: 事件ID

        Returns:
            执行记录列表
        """
        event = self._events.get(event_id)
        if not event:
            return []

        records: list[ExecutionRecord] = []

        # 事件类型到触发条件的映射
        type_to_trigger = {
            "threat_detected": TriggerCondition.THREAT_ALERT,
            "compliance_violation": TriggerCondition.COMPLIANCE_VIOLATION,
            "vulnerability_found": TriggerCondition.VULNERABILITY_FOUND,
            "ioc_match": TriggerCondition.IOC_MATCH,
            "anomaly_detected": TriggerCondition.ANOMALY_DETECTED,
        }

        target_trigger = type_to_trigger.get(event.event_type)
        if not target_trigger:
            return records

        # 查找匹配的剧本
        for playbook in self._playbooks.values():
            if playbook.trigger == target_trigger and playbook.enabled:
                # 为剧本传递事件参数
                parameters = {
                    "event_type": event.event_type,
                    "severity": event.severity,
                    "affected_assets": event.affected_assets,
                }

                record = self.trigger_playbook(playbook.playbook_id, event_id, parameters)
                if record:
                    records.append(record)

        return records

    def get_playbook(self, playbook_id: str) -> Playbook | None:
        """获取剧本"""
        return self._playbooks.get(playbook_id)

    def get_action(self, action_id: str) -> SecurityAction | None:
        """获取操作"""
        return self._actions.get(action_id)

    def get_event(self, event_id: str) -> SecurityEvent | None:
        """获取事件"""
        return self._events.get(event_id)

    def get_open_events(self, min_severity: str | None = None) -> list[SecurityEvent]:
        """获取未解决的事件"""
        events = [e for e in self._events.values() if not e.is_resolved]

        if min_severity:
            severity_levels = {"critical": 4, "high": 3, "medium": 2, "low": 1}
            min_level = severity_levels.get(min_severity, 0)
            events = [e for e in events if severity_levels.get(e.severity, 0) >= min_level]

        return sorted(events, key=lambda e: e.detected_at, reverse=True)

    def get_execution_history(self, limit: int = 50) -> list[ExecutionRecord]:
        """获取执行历史"""
        return sorted(
            self._execution_history,
            key=lambda r: r.started_at,
            reverse=True
        )[:limit]

    def get_statistics(self) -> dict[str, Any]:
        """获取SOAR统计"""
        total_executions = len(self._execution_history)
        completed = sum(1 for r in self._execution_history if r.status == "completed")
        failed = sum(1 for r in self._execution_history if r.status == "failed")

        open_events = len(self.get_open_events())

        most_executed_playbook = ""
        if self._execution_history:
            from collections import Counter
            counter = Counter(r.playbook_id for r in self._execution_history)
            most_executed_playbook = counter.most_common(1)[0][0]

        return {
            "generated_at": datetime.now().isoformat(),
            "total_actions": len(self._actions),
            "total_playbooks": len(self._playbooks),
            "total_events": len(self._events),
            "open_events": open_events,
            "total_executions": total_executions,
            "completed_executions": completed,
            "failed_executions": failed,
            "success_rate": round(completed / total_executions * 100, 1) if total_executions > 0 else 0.0,
            "most_executed_playbook": most_executed_playbook,
        }

    def export_playbooks(self) -> list[dict[str, Any]]:
        """导出所有剧本"""
        return [p.to_dict() for p in self._playbooks.values()]

    def register_notification_handler(
        self,
        channel: NotificationChannel,
        handler: Callable[[str, str, str], None]
    ) -> None:
        """注册通知处理器"""
        if channel not in self._notification_handlers:
            self._notification_handlers[channel] = []
        self._notification_handlers[channel].append(handler)

    def send_notification(
        self,
        channel: NotificationChannel,
        title: str,
        message: str,
        severity: str = "info"
    ) -> bool:
        """发送通知"""
        handlers = self._notification_handlers.get(channel, [])
        if not handlers:
            return False

        for handler in handlers:
            try:
                handler(title, message, severity)
            except Exception:
                continue

        return True


def create_security_orchestrator() -> SecurityOrchestrator:
    """创建安全编排器"""
    return SecurityOrchestrator()


__all__ = [
    "SecurityOrchestrator",
    "SecurityAction",
    "SecurityEvent",
    "Playbook",
    "PlaybookStep",
    "ExecutionRecord",
    "ActionStatus",
    "TriggerCondition",
    "NotificationChannel",
    "create_security_orchestrator",
]
