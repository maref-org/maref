"""
合规管理系统

提供多法域合规框架，支持EU、US、China、Russia、India五大法域。

所有核心类从 registry 模块重新导出，解决循环导入问题。
"""

from __future__ import annotations

from typing import Any

from maref.compliance.registry import (
    ComplianceCheckResult,
    ComplianceEngine,
    ComplianceRegistry,
    ComplianceRequirement,
    ComplianceStatus,
    Jurisdiction,
    Regulation,
    RegulationType,
    create_compliance_system,
)

from maref.compliance.report_generator import (
    ComplianceReport,
    ReportFormat,
    ReportGenerator,
    ReportSection,
    ReportType,
    create_report_generator,
)

from maref.compliance.compliance_monitor import (
    AlertSeverity,
    ComplianceAlert,
    ComplianceMonitor,
    ComplianceSnapshot,
    MonitoringRule,
    MonitorState,
    create_compliance_monitor,
)


__all__ = [
    "ComplianceStatus",
    "RegulationType",
    "Jurisdiction",
    "Regulation",
    "ComplianceRequirement",
    "ComplianceCheckResult",
    "ComplianceRegistry",
    "ComplianceEngine",
    "create_compliance_system",
    "ReportGenerator",
    "ComplianceReport",
    "ReportSection",
    "ReportFormat",
    "ReportType",
    "create_report_generator",
    "ComplianceMonitor",
    "ComplianceSnapshot",
    "ComplianceAlert",
    "AlertSeverity",
    "MonitorState",
    "MonitoringRule",
    "create_compliance_monitor",
]
