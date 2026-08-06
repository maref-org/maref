"""
合规状态监控器

实时监控合规状态变化，提供预警通知和补救建议。
支持动态合规评估和自动检测调度。

核心功能:
1. 持续合规状态监控
2. 基于优先级的自动检测调度
3. 合规预警和通知
4. 补救措施建议引擎
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from maref.compliance import ComplianceRegistry, ComplianceStatus, Jurisdiction


class MonitorState(Enum):
    """监控状态"""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


class AlertSeverity(Enum):
    """告警严重程度"""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ComplianceSnapshot:
    """合规快照"""

    snapshot_id: str
    timestamp: datetime
    jurisdiction: Jurisdiction | None
    overall_status: dict[str, Any]
    requirement_status: dict[str, ComplianceStatus]
    changes_since_last: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp.isoformat(),
            "jurisdiction": self.jurisdiction.value if self.jurisdiction else None,
            "overall_status": self.overall_status,
            "requirement_count": len(self.requirement_status),
            "changes_count": len(self.changes_since_last),
        }


@dataclass
class ComplianceAlert:
    """合规告警"""

    alert_id: str
    jurisdiction: Jurisdiction
    severity: AlertSeverity
    title: str
    description: str
    detected_at: datetime
    affected_requirements: list[str] = field(default_factory=list)
    recommended_remediation: list[str] = field(default_factory=list)
    is_active: bool = True
    resolved_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "jurisdiction": self.jurisdiction.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "detected_at": self.detected_at.isoformat(),
            "affected_requirements": self.affected_requirements,
            "recommended_remediation": self.recommended_remediation,
            "is_active": self.is_active,
        }


class MonitoringRule:
    """监控规则"""

    def __init__(
        self,
        rule_id: str,
        name: str,
        description: str,
        check_interval_hours: int = 24,
        threshold: float = 80.0,
        auto_remediate: bool = False,
    ):
        self.rule_id = rule_id
        self.name = name
        self.description = description
        self.check_interval_hours = check_interval_hours
        self.threshold = threshold
        self.auto_remediate = auto_remediate
        self.last_checked: datetime | None = None
        self.is_active = True

    def is_due(self) -> bool:
        """检查是否到期"""
        if not self.last_checked:
            return True
        return (datetime.now() - self.last_checked) > timedelta(hours=self.check_interval_hours)

    def mark_checked(self) -> None:
        """标记已检查"""
        self.last_checked = datetime.now()


class ComplianceMonitor:
    """
    合规状态监控器

    持续监控合规状态、生成快照、发出告警并提供补救建议。
    """

    def __init__(self, registry: ComplianceRegistry):
        self.registry = registry
        self.state = MonitorState.IDLE
        self._snapshots: dict[Jurisdiction, list[ComplianceSnapshot]] = defaultdict(list)
        self._alerts: dict[str, ComplianceAlert] = {}
        self._rules: dict[str, MonitoringRule] = {}
        self._alert_callbacks: list[Callable[[ComplianceAlert], None]] = []

        self._initialize_default_rules()

    def _initialize_default_rules(self) -> None:
        """初始化默认监控规则"""
        default_rules = [
            MonitoringRule(
                rule_id="rule-data-protection",
                name="Data Protection Compliance",
                description="Monitor data protection regulation compliance across jurisdictions",
                check_interval_hours=24,
                threshold=85.0,
            ),
            MonitoringRule(
                rule_id="rule-cross-border-transfer",
                name="Cross-Border Data Transfer",
                description="Monitor cross-border data transfer compliance",
                check_interval_hours=24,
                threshold=90.0,
                auto_remediate=True,
            ),
            MonitoringRule(
                rule_id="rule-critical-priority",
                name="Critical Priority Requirements",
                description="Monitor priority 1 compliance requirements hourly",
                check_interval_hours=1,
                threshold=95.0,
            ),
            MonitoringRule(
                rule_id="rule-breach-notification",
                name="Breach Notification Timeliness",
                description="Verify breach notification windows are met",
                check_interval_hours=12,
                threshold=100.0,
                auto_remediate=True,
            ),
        ]

        for rule in default_rules:
            self.add_rule(rule)

    def add_rule(self, rule: MonitoringRule) -> str:
        """添加监控规则"""
        self._rules[rule.rule_id] = rule
        return rule.rule_id

    def remove_rule(self, rule_id: str) -> bool:
        """移除监控规则"""
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False

    def take_snapshot(self, jurisdiction: Jurisdiction | None = None) -> ComplianceSnapshot:
        """
        生成合规快照

        Args:
            jurisdiction: 目标法域，None表示全部

        Returns:
            ComplianceSnapshot: 合规快照
        """
        # 获取之前的最新快照以计算变化
        previous_snapshot = None
        if jurisdiction:
            existing = self._snapshots.get(jurisdiction, [])
            if existing:
                previous_snapshot = existing[-1]

        overall = (
            self.registry.get_jurisdiction_compliance_status(jurisdiction)
            if jurisdiction
            else self.registry.generate_compliance_report()
        )

        # 收集需求状态
        requirement_status: dict[str, ComplianceStatus] = {}
        for req_id, result in self.registry.check_results.items():
            requirement_status[req_id] = result.status

        # 计算变化
        changes = []
        if previous_snapshot and previous_snapshot.overall_status:
            prev_rate = previous_snapshot.overall_status.get("compliance_rate", 0.0)
            current_rate = overall.get("compliance_rate", 0.0)

            if abs(current_rate - prev_rate) > 0.1:
                changes.append(
                    {
                        "field": "compliance_rate",
                        "previous": prev_rate,
                        "current": current_rate,
                        "change": round(current_rate - prev_rate, 2),
                    }
                )

            # 检测需求状态变化
            for req_id, status in requirement_status.items():
                prev_status = previous_snapshot.requirement_status.get(req_id)
                if prev_status and prev_status != status:
                    changes.append(
                        {
                            "field": f"requirement:{req_id}",
                            "previous": prev_status.value,
                            "current": status.value,
                        }
                    )

        snapshot = ComplianceSnapshot(
            snapshot_id=f"snap-{int(time.time())}",
            timestamp=datetime.now(),
            jurisdiction=jurisdiction,
            overall_status=overall,
            requirement_status=requirement_status,
            changes_since_last=changes,
        )

        if jurisdiction:
            self._snapshots[jurisdiction].append(snapshot)

        return snapshot

    def check_all_rules(self) -> list[ComplianceAlert]:
        """
        检查所有监控规则

        Returns:
            本次检查产生的新告警列表
        """
        new_alerts: list[ComplianceAlert] = []

        for rule in self._rules.values():
            if not rule.is_active or not rule.is_due():
                continue

            rule.mark_checked()

            for jurisdiction in Jurisdiction:
                if jurisdiction in (Jurisdiction.GLOBAL, Jurisdiction.CROSS_BORDER):
                    continue

                status = self.registry.get_jurisdiction_compliance_status(jurisdiction)
                rate = status.get("compliance_rate", 0.0)

                if rate < rule.threshold:
                    alert = self._create_alert(
                        jurisdiction=jurisdiction,
                        severity=AlertSeverity.WARNING if rate > 50 else AlertSeverity.CRITICAL,
                        title=f"Compliance below threshold: {rule.name}",
                        description=f"{jurisdiction.value.upper()} compliance rate: {rate:.1f}% (threshold: {rule.threshold}%)",
                        rule=rule,
                    )

                    new_alerts.append(alert)
                    self._alerts[alert.alert_id] = alert

                    # 通知回调
                    for callback in self._alert_callbacks:
                        try:
                            callback(alert)
                        except Exception:
                            pass

        return new_alerts

    def _create_alert(
        self,
        jurisdiction: Jurisdiction,
        severity: AlertSeverity,
        title: str,
        description: str,
        rule: MonitoringRule,
    ) -> ComplianceAlert:
        """创建合规告警"""
        # 生成补救建议
        remediation = self._generate_remediation(jurisdiction, rule)

        return ComplianceAlert(
            alert_id=f"alert-comp-{int(time.time())}",
            jurisdiction=jurisdiction,
            severity=severity,
            title=title,
            description=description,
            detected_at=datetime.now(),
            recommended_remediation=remediation,
        )

    def _generate_remediation(self, jurisdiction: Jurisdiction, rule: MonitoringRule) -> list[str]:
        """根据法规和规则生成补救建议"""
        remediation: list[str] = []

        rules = self.registry.jurisdiction_rules.get(jurisdiction, {})

        if "breach_notification" in rule.rule_id:
            hours = rules.get("breach_notification_hours", 72)
            remediation.append(f"Ensure breach notification within {hours} hours")
            remediation.append("Set up automated breach detection and notification workflow")
        elif "data_protection" in rule.rule_id.lower():
            remediation.append("Review data processing activities")
            remediation.append("Update data protection impact assessment (DPIA)")
            remediation.append("Verify consent management implementation")
        elif "cross_border" in rule.rule_id.lower():
            remediation.append("Review cross-border data transfer mechanisms")
            remediation.append("Implement appropriate safeguards (SCCs, BCRs)")
            remediation.append("Conduct transfer impact assessment")
        else:
            remediation.append("Review compliance requirements for affected jurisdiction")
            remediation.append("Schedule compliance gap analysis")

        if rule.auto_remediate:
            remediation.append("[AUTO] Automated remediation scheduled")

        return remediation

    def resolve_alert(self, alert_id: str) -> bool:
        """解决告警"""
        alert = self._alerts.get(alert_id)
        if alert and alert.is_active:
            alert.is_active = False
            alert.resolved_at = datetime.now()
            return True
        return False

    def get_active_alerts(
        self,
        min_severity: AlertSeverity | None = None,
        jurisdiction: Jurisdiction | None = None,
    ) -> list[ComplianceAlert]:
        """获取活跃告警"""
        active = [a for a in self._alerts.values() if a.is_active]

        if min_severity:
            severity_order = {
                AlertSeverity.CRITICAL: 3,
                AlertSeverity.WARNING: 2,
                AlertSeverity.INFO: 1,
            }
            min_level = severity_order.get(min_severity, 0)
            active = [a for a in active if severity_order.get(a.severity, 0) >= min_level]

        if jurisdiction:
            active = [a for a in active if a.jurisdiction == jurisdiction]

        return sorted(active, key=lambda a: a.detected_at, reverse=True)

    def get_compliance_trend(
        self,
        jurisdiction: Jurisdiction,
        max_snapshots: int = 10,
    ) -> list[dict[str, Any]]:
        """
        获取合规趋势数据

        Args:
            jurisdiction: 目标法域
            max_snapshots: 最多返回的快照数

        Returns:
            趋势数据列表
        """
        snapshots = self._snapshots.get(jurisdiction, [])
        recent = snapshots[-max_snapshots:] if len(snapshots) > max_snapshots else snapshots

        return [
            {
                "timestamp": s.timestamp.isoformat(),
                "compliance_rate": s.overall_status.get("compliance_rate", 0.0),
                "changes": len(s.changes_since_last),
            }
            for s in recent
        ]

    def get_monitor_status(self) -> dict[str, Any]:
        """获取监控器状态"""
        return {
            "state": self.state.value,
            "rules_count": len(self._rules),
            "rules_due": sum(1 for r in self._rules.values() if r.is_due()),
            "active_alerts": len(self.get_active_alerts()),
            "total_snapshots": sum(len(s) for s in self._snapshots.values()),
            "last_checked": datetime.now().isoformat(),
        }

    def register_alert_callback(self, callback: Callable[[ComplianceAlert], None]) -> None:
        """注册告警回调"""
        self._alert_callbacks.append(callback)

    def run_check_cycle(self) -> dict[str, Any]:
        """
        执行一次完整的检查周期

        Returns:
            检查结果摘要
        """
        self.state = MonitorState.RUNNING

        try:
            # 对所有法域生成快照
            for jurisdiction in Jurisdiction:
                if jurisdiction in (Jurisdiction.GLOBAL, Jurisdiction.CROSS_BORDER):
                    continue
                self.take_snapshot(jurisdiction)

            # 检查所有规则
            new_alerts = self.check_all_rules()

            self.state = MonitorState.IDLE

            return {
                "cycle_completed": True,
                "timestamp": datetime.now().isoformat(),
                "jurisdictions_checked": len(self._snapshots),
                "new_alerts": len(new_alerts),
                "total_active_alerts": len(self.get_active_alerts()),
                "state": self.state.value,
            }
        except Exception as e:
            self.state = MonitorState.ERROR
            return {
                "cycle_completed": False,
                "error": str(e),
                "state": self.state.value,
            }


def create_compliance_monitor(registry: ComplianceRegistry) -> ComplianceMonitor:
    """创建合规状态监控器"""
    return ComplianceMonitor(registry)


__all__ = [
    "ComplianceMonitor",
    "ComplianceSnapshot",
    "ComplianceAlert",
    "AlertSeverity",
    "MonitorState",
    "MonitoringRule",
    "create_compliance_monitor",
]
