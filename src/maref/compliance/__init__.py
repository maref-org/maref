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

# Deferred imports to break circular dependency.
# compliance_monitor and report_generator import from compliance.registry
# directly, so there is no cycle at module-load time.  We re-export their
# public names lazily via __getattr__ so that ``from maref.compliance import
# ComplianceMonitor`` still works without triggering an import loop.


def __getattr__(name: str) -> Any:
    if name in (
        "OWASPAgenticTop10",
        "OWASPCoverageMatrix",
        "OWASPControl",
        "verify_owasp_coverage",
    ):
        from maref.compliance.owasp_agentic_top10 import (  # noqa: F401
            OWASPAgenticTop10,
            OWASPControl,
            OWASPCoverageMatrix,
            verify_owasp_coverage,
        )

        return locals()[name]
    if name in ("CACBlockchainTraceability",):
        from maref.compliance.cac.blockchain_traceability import (  # noqa: F401
            CACBlockchainTraceability,
        )

        return locals()[name]
    if name in (
        "FrameworkMapping",
        "MAPS",
        "CATEGORIES",
        "coverage_report",
        "gaps",
        "verify_module_paths",
        "verify_report",
        "render_markdown",
    ):
        from maref.compliance.cac.framework_3_0 import (  # noqa: F401
            CATEGORIES,
            MAPS,
            FrameworkMapping,
            coverage_report,
            gaps,
            render_markdown,
            verify_module_paths,
            verify_report,
        )

        return locals()[name]
    if name in (
        "CACRiskGrade",
        "RiskDimension",
        "GradedRisk",
        "grade_action",
        "GRADE_FLOW",
        "exceeds",
    ):
        from maref.compliance.cac.risk_grading import (  # noqa: F401
            GRADE_FLOW,
            CACRiskGrade,
            GradedRisk,
            RiskDimension,
            exceeds,
            grade_action,
        )

        return locals()[name]
    if name in (
        "ReportGenerator",
        "ComplianceReport",
        "ReportSection",
        "ReportFormat",
        "ReportType",
        "create_report_generator",
    ):
        from maref.compliance.report_generator import (  # noqa: F401
            ComplianceReport,
            ReportFormat,
            ReportGenerator,
            ReportSection,
            ReportType,
            create_report_generator,
        )

        return locals()[name]
    if name in (
        "ComplianceMonitor",
        "ComplianceSnapshot",
        "ComplianceAlert",
        "AlertSeverity",
        "MonitorState",
        "MonitoringRule",
        "create_compliance_monitor",
    ):
        from maref.compliance.compliance_monitor import (  # noqa: F401
            AlertSeverity,
            ComplianceAlert,
            ComplianceMonitor,
            ComplianceSnapshot,
            MonitoringRule,
            MonitorState,
            create_compliance_monitor,
        )

        return locals()[name]
    if name in (
        "EUAIComplianceEngineV2",
        "EUAIComplianceSummary",
        "RiskClassifier",
        "RiskLevel",
        "AnnexIIICategory",
        "RiskManagementSystem",
        "TechnicalDocumentation",
        "TransparencyManager",
        "HumanOversightBridge",
        "ConformityAssessmentManager",
        "GPAIComplianceManager",
    ):
        from maref.compliance.eu_ai_act_v2 import (  # noqa: F401
            AnnexIIICategory,
            ConformityAssessmentManager,
            EUAIComplianceEngineV2,
            EUAIComplianceSummary,
            GPAIComplianceManager,
            HumanOversightBridge,
            RiskClassifier,
            RiskLevel,
            RiskManagementSystem,
            TechnicalDocumentation,
            TransparencyManager,
        )

        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    # CAC 网信办区块链可追溯
    "CACBlockchainTraceability",
    # 人工智能安全治理框架3.0（附件2 智能体风险管理）
    "FrameworkMapping",
    "MAPS",
    "CATEGORIES",
    "coverage_report",
    "gaps",
    "verify_module_paths",
    "verify_report",
    "render_markdown",
    # 框架3.0 风险分级（附件1 五级 + 附件2 四维度）
    "CACRiskGrade",
    "RiskDimension",
    "GradedRisk",
    "grade_action",
    "GRADE_FLOW",
    "exceeds",
    # OWASP Agentic Top 10 coverage
    "OWASPAgenticTop10",
    "OWASPCoverageMatrix",
    "OWASPControl",
    "verify_owasp_coverage",
    # V2 EU AI Act engine
    "EUAIComplianceEngineV2",
    "EUAIComplianceSummary",
    "RiskClassifier",
    "RiskLevel",
    "AnnexIIICategory",
    "RiskManagementSystem",
    "TechnicalDocumentation",
    "TransparencyManager",
    "HumanOversightBridge",
    "ConformityAssessmentManager",
    "GPAIComplianceManager",
]
