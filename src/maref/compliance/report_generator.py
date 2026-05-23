"""
合规报告生成器

支持多种监管格式的自动化合规报告生成。
覆盖: EU AI Act, GDPR, CCPA, China CSL, Russia 149-FZ, India PDPB

报告类型:
1. 合规状态报告 - 各法域当前合规状态
2. 审计就绪报告 - SOC 2 / ISO 27001 准备
3. 监管报送报告 - 面向监管机构
4. 风险评估报告 - 合规风险矩阵
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from maref.compliance import ComplianceRegistry, Jurisdiction


class ReportFormat(Enum):
    """报告格式"""
    JSON = "json"
    MARKDOWN = "markdown"
    HTML = "html"
    PDF_READY = "pdf_ready"  # JSON schema for PDF generation


class ReportType(Enum):
    """报告类型"""
    COMPLIANCE_STATUS = "compliance_status"
    AUDIT_READINESS = "audit_readiness"
    REGULATORY_SUBMISSION = "regulatory_submission"
    RISK_ASSESSMENT = "risk_assessment"
    EXECUTIVE_SUMMARY = "executive_summary"


@dataclass
class ReportSection:
    """报告章节"""

    title: str
    content: str
    subsections: list[ReportSection] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_markdown(self, level: int = 2) -> str:
        """转换为Markdown"""
        prefix = "#" * level
        lines = [f"{prefix} {self.title}", "", self.content, ""]
        for sub in self.subsections:
            lines.append(sub.to_markdown(level + 1))
        return "\n".join(lines)


@dataclass
class ComplianceReport:
    """合规报告"""

    report_id: str
    report_type: ReportType
    title: str
    generated_at: datetime
    jurisdiction: Jurisdiction | None
    sections: list[ReportSection] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    classifications: list[str] = field(default_factory=list)  # confidentiality level
    version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "type": self.report_type.value,
            "title": self.title,
            "generated_at": self.generated_at.isoformat(),
            "jurisdiction": self.jurisdiction.value if self.jurisdiction else None,
            "sections": [
                {
                    "title": s.title,
                    "content": s.content,
                    "subsections": len(s.subsections),
                }
                for s in self.sections
            ],
            "metrics": self.metrics,
            "recommendations": self.recommendations,
            "classifications": self.classifications,
            "version": self.version,
        }

    def to_markdown(self) -> str:
        """转换为Markdown格式"""
        lines = [
            f"# {self.title}",
            "",
            f"**Report ID**: {self.report_id}",
            f"**Type**: {self.report_type.value}",
            f"**Generated**: {self.generated_at.isoformat()}",
            f"**Jurisdiction**: {self.jurisdiction.value if self.jurisdiction else 'Multi-Jurisdiction'}",
            f"**Version**: {self.version}",
            "",
            "---",
            "",
        ]

        for section in self.sections:
            lines.append(section.to_markdown(2))

        if self.recommendations:
            lines.append("## Recommendations")
            lines.append("")
            for i, rec in enumerate(self.recommendations, 1):
                lines.append(f"{i}. **{rec.get('action', '')}** - {rec.get('details', '')}")
            lines.append("")

        return "\n".join(lines)


class ReportGenerator:
    """
    合规报告生成器

    自动从合规注册表收集数据并生成多格式合规报告。
    """

    def __init__(self, registry: ComplianceRegistry):
        self.registry = registry
        self._report_history: list[ComplianceReport] = []

    def generate_compliance_status_report(
        self,
        jurisdiction: Jurisdiction | None = None,
    ) -> ComplianceReport:
        """
        生成合规状态报告

        Args:
            jurisdiction: 目标司法管辖区，None表示所有

        Returns:
            ComplianceReport: 合规报告
        """
        jurisdictions = [jurisdiction] if jurisdiction else [
            j for j in Jurisdiction if j not in (Jurisdiction.GLOBAL, Jurisdiction.CROSS_BORDER)
        ]

        report = ComplianceReport(
            report_id=f"csr-{int(time.time())}",
            report_type=ReportType.COMPLIANCE_STATUS,
            title=f"Compliance Status Report - {jurisdiction.value if jurisdiction else 'All Jurisdictions'}",
            generated_at=datetime.now(),
            jurisdiction=jurisdiction,
        )

        metrics = {
            "total_jurisdictions": len(jurisdictions),
            "jurisdiction_details": {},
            "overall_compliance_rate": 0.0,
        }

        total_rate = 0.0
        for jur in jurisdictions:
            status = self.registry.get_jurisdiction_compliance_status(jur)
            rate = status.get("compliance_rate", 0.0)
            total_rate += rate

            metrics["jurisdiction_details"][jur.value] = {
                "status": status,
                "compliance_rate": rate,
            }

            # 添加报告章节
            section = ReportSection(
                title=f"{jur.value.upper()} Jurisdiction",
                content=f"Compliance Rate: {rate:.1f}%\n"
                        f"Active Regulations: {status.get('active_regulations', 0)}\n"
                        f"Checked Requirements: {status.get('checked_requirements', 0)}",
                metadata={"jurisdiction": jur.value},
            )
            report.sections.append(section)

        if jurisdictions:
            metrics["overall_compliance_rate"] = round(total_rate / len(jurisdictions), 2)

        report.metrics = metrics

        # 推荐建议
        for rec in self.registry.generate_compliance_report(jurisdictions).get("recommendations", []):
            report.recommendations.append(rec)

        report.classifications = ["INTERNAL", "COMPLIANCE_OFFICER"]
        self._report_history.append(report)

        return report

    def generate_audit_readiness_report(self) -> ComplianceReport:
        """
        生成审计就绪报告

        评估对 SOC 2 Type II 和 ISO 27001 审计的准备情况。
        """
        report = ComplianceReport(
            report_id=f"aar-{int(time.time())}",
            report_type=ReportType.AUDIT_READINESS,
            title="Audit Readiness Assessment Report",
            generated_at=datetime.now(),
            jurisdiction=None,
        )

        # SOC 2 Trust Services Criteria
        soc2_criteria = [
            ("Security", "Information and systems are protected against unauthorized access"),
            ("Availability", "Information and systems are available for operation and use"),
            ("Processing Integrity", "System processing is complete, valid, accurate, and authorized"),
            ("Confidentiality", "Information designated as confidential is protected"),
            ("Privacy", "Personal information is collected, used, retained, and disclosed appropriately"),
        ]

        # ISO 27001 Controls 参考
        iso27001_controls = [
            ("A.5 Information Security Policies", "Management direction for information security"),
            ("A.6 Organization of Information Security", "Internal organization and mobile devices"),
            ("A.8 Asset Management", "Identification and classification of information assets"),
            ("A.9 Access Control", "Business requirements, user management, and responsibilities"),
            ("A.12 Operations Security", "Protection from malware, backup, logging, and monitoring"),
            ("A.14 System Acquisition & Development", "Security requirements in development lifecycle"),
            ("A.16 Incident Management", "Management of information security incidents"),
            ("A.18 Compliance", "Compliance with legal and contractual requirements"),
        ]

        # SOC 2 section
        soc2_section = ReportSection(
            title="SOC 2 Type II Readiness",
            content="Assessment of Trust Services Criteria alignment",
            subsections=[
                ReportSection(
                    title=f"TSC: {criterion}",
                    content=f"{description}\n\nStatus: Partially Implemented\nEvidence: Review required",
                )
                for criterion, description in soc2_criteria
            ]
        )
        report.sections.append(soc2_section)

        # ISO 27001 section
        iso_section = ReportSection(
            title="ISO 27001 Control Assessment",
            content="Assessment of Annex A controls readiness",
            subsections=[
                ReportSection(
                    title=f"Control: {control}",
                    content=f"{description}\n\nImplementation Status: In Progress\nGap Analysis: Pending",
                )
                for control, description in iso27001_controls
            ]
        )
        report.sections.append(iso_section)

        report.metrics = {
            "soc2_criteria_assessed": len(soc2_criteria),
            "iso27001_controls_assessed": len(iso27001_controls),
            "readiness_level": "partial",
        }

        report.recommendations = [
            {"action": "Complete TSC evidence collection", "details": "Gather evidence for all 5 Trust Services Criteria"},
            {"action": "ISO 27001 gap analysis", "details": "Perform gap analysis against all Annex A controls"},
            {"action": "Third-party assessment", "details": "Schedule external auditor review"},
        ]

        report.classifications = ["CONFIDENTIAL", "COMPLIANCE_OFFICER", "CISO"]
        self._report_history.append(report)

        return report

    def generate_regulatory_submission(
        self,
        regulation_id: str,
        submission_data: dict[str, Any] | None = None,
    ) -> ComplianceReport:
        """
        生成监管报送报告

        Args:
            regulation_id: 法规ID
            submission_data: 提交数据

        Returns:
            ComplianceReport: 监管报告
        """
        regulation = self.registry.regulations.get(regulation_id)
        if not regulation:
            raise ValueError(f"Regulation not found: {regulation_id}")

        report = ComplianceReport(
            report_id=f"rsb-{int(time.time())}",
            report_type=ReportType.REGULATORY_SUBMISSION,
            title=f"Regulatory Submission - {regulation.name}",
            generated_at=datetime.now(),
            jurisdiction=regulation.jurisdiction,
        )

        section = ReportSection(
            title="Submission Details",
            content=f"**Regulation**: {regulation.name}\n"
                    f"**Jurisdiction**: {regulation.jurisdiction.value}\n"
                    f"**Type**: {regulation.regulation_type.value}\n"
                    f"**Description**: {regulation.description}",
        )
        report.sections.append(section)

        # 需求达标状态
        requirements_section = ReportSection(
            title="Requirement Compliance Status",
            content="Compliance status for each requirement:",
            subsections=[
                ReportSection(
                    title=f"Requirement: {req}",
                    content="Status: Under Review",
                )
                for req in regulation.requirements
            ]
        )
        report.sections.append(requirements_section)

        if submission_data:
            report.sections.append(ReportSection(
                title="Submitted Data",
                content=json.dumps(submission_data, indent=2),
            ))

        report.metrics = {
            "regulation_id": regulation_id,
            "total_requirements": len(regulation.requirements),
            "penalty": regulation.penalty,
        }

        report.classifications = ["REGULATORY", "CONFIDENTIAL"]
        self._report_history.append(report)

        return report

    def generate_risk_assessment_report(
        self,
        assessment_data: dict[str, Any] | None = None,
    ) -> ComplianceReport:
        """
        生成风险评估报告

        Args:
            assessment_data: 评估数据

        Returns:
            ComplianceReport: 风险评估报告
        """
        report = ComplianceReport(
            report_id=f"rar-{int(time.time())}",
            report_type=ReportType.RISK_ASSESSMENT,
            title="Compliance Risk Assessment Report",
            generated_at=datetime.now(),
            jurisdiction=None,
        )

        # 风险矩阵
        risk_categories = [
            ("Data Protection", "Risk of non-compliance with data protection regulations", "HIGH"),
            ("Cross-Border Data Transfer", "Risk related to international data flows", "MEDIUM"),
            ("AI System Classification", "Risk of misclassifying AI system risk levels", "HIGH"),
            ("Record Keeping", "Risk of inadequate audit trail maintenance", "LOW"),
            ("Breach Notification", "Risk of delayed incident notification", "MEDIUM"),
            ("Third-Party Risk", "Risk from vendor and supplier compliance", "MEDIUM"),
        ]

        for category, description, level in risk_categories:
            report.sections.append(ReportSection(
                title=f"Risk: {category}",
                content=f"**Risk Level**: {level}\n**Description**: {description}\n"
                        f"**Mitigation**: Review and implement controls",
            ))

        # 风险矩阵统计
        risk_counts = {"HIGH": 2, "MEDIUM": 3, "LOW": 1}

        report.metrics = {
            "total_risks_identified": len(risk_categories),
            "risk_distribution": risk_counts,
            "assessment_date": datetime.now().isoformat(),
        }

        report.recommendations = [
            {"action": "Address HIGH priority risks", "details": "Focus on Data Protection and AI Classification risks within 30 days"},
            {"action": "Review MEDIUM priority risks", "details": "Address cross-border data transfer and breach notification procedures within 90 days"},
        ]

        report.classifications = ["CONFIDENTIAL", "RISK_MANAGEMENT", "CISO"]
        self._report_history.append(report)

        return report

    def generate_executive_summary(self) -> ComplianceReport:
        """生成高管摘要"""
        report = ComplianceReport(
            report_id=f"exs-{int(time.time())}",
            report_type=ReportType.EXECUTIVE_SUMMARY,
            title="Executive Compliance Summary",
            generated_at=datetime.now(),
            jurisdiction=None,
        )

        # 汇总所有法域状态
        jurisdictions = [j for j in Jurisdiction if j not in (Jurisdiction.GLOBAL, Jurisdiction.CROSS_BORDER)]

        summary_data = []
        total_rate = 0.0
        for jur in jurisdictions:
            status = self.registry.get_jurisdiction_compliance_status(jur)
            rate = status.get("compliance_rate", 0.0)
            total_rate += rate
            summary_data.append(f"- **{jur.value.upper()}**: {rate:.1f}% compliant")

        overall = total_rate / len(jurisdictions) if jurisdictions else 0.0

        report.sections.append(ReportSection(
            title="Overall Compliance Status",
            content=f"Overall Compliance Rate: **{overall:.1f}%**\n\n"
                    + "\n".join(summary_data),
        ))

        report.sections.append(ReportSection(
            title="Key Metrics",
            content=f"- Jurisdictions Covered: {len(jurisdictions)}\n"
                    f"- Active Regulations: {sum(self.registry.get_jurisdiction_compliance_status(j).get('active_regulations', 0) for j in jurisdictions)}\n"
                    f"- Reports Generated: {len(self._report_history)}",
        ))

        report.sections.append(ReportSection(
            title="Top Actions Required",
            content="1. Complete evidence collection for GDPR Article 5 requirements\n"
                    "2. Update China CSL data localization procedures\n"
                    "3. Schedule HIPAA readiness assessment",
        ))

        report.metrics = {"overall_compliance_rate": round(overall, 2)}
        report.classifications = ["EXECUTIVE", "CONFIDENTIAL"]
        self._report_history.append(report)

        return report

    def export_report(
        self,
        report: ComplianceReport,
        format: ReportFormat = ReportFormat.MARKDOWN,
    ) -> str:
        """
        导出报告为指定格式

        Args:
            report: 合规报告
            format: 输出格式

        Returns:
            格式化后的报告字符串
        """
        if format == ReportFormat.MARKDOWN:
            return report.to_markdown()
        elif format == ReportFormat.JSON:
            return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
        elif format == ReportFormat.HTML:
            return self._to_html(report)
        else:
            return json.dumps(report.to_dict(), indent=2)

    def _to_html(self, report: ComplianceReport) -> str:
        """转换为HTML格式"""
        md_content = report.to_markdown()
        # 简化的Markdown转HTML
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{report.title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 2em; }}
        h1 {{ color: #1a1a1a; }}
        h2 {{ color: #333; border-bottom: 1px solid #ccc; }}
    </style>
</head>
<body>
    <pre>{md_content}</pre>
    <footer>Generated by MAREF Compliance Engine v{report.version}</footer>
</body>
</html>"""
        return html

    def get_report_history(self) -> list[dict[str, Any]]:
        """获取报告历史"""
        return [
            {
                "report_id": r.report_id,
                "type": r.report_type.value,
                "generated_at": r.generated_at.isoformat(),
                "jurisdiction": r.jurisdiction.value if r.jurisdiction else "multi",
            }
            for r in self._report_history
        ]

    def batch_generate_all_reports(self) -> list[ComplianceReport]:
        """批量生成所有类型的报告"""
        reports: list[ComplianceReport] = []

        try:
            reports.append(self.generate_compliance_status_report())
        except Exception:
            pass

        try:
            reports.append(self.generate_audit_readiness_report())
        except Exception:
            pass

        try:
            reports.append(self.generate_risk_assessment_report())
        except Exception:
            pass

        try:
            reports.append(self.generate_executive_summary())
        except Exception:
            pass

        return reports


def create_report_generator(registry: ComplianceRegistry) -> ReportGenerator:
    """创建报告生成器"""
    return ReportGenerator(registry)


__all__ = [
    "ReportGenerator",
    "ComplianceReport",
    "ReportSection",
    "ReportFormat",
    "ReportType",
    "create_report_generator",
]
