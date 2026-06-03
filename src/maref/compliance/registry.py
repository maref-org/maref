"""
合规注册表核心模块

提供多法域合规框架的基础数据结构和引擎。
支持EU、US、China、Russia、India五大法域。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ComplianceStatus(Enum):
    """合规状态"""

    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PARTIAL = "partial"
    EXEMPT = "exempt"
    NOT_APPLICABLE = "not_applicable"
    PENDING_REVIEW = "pending_review"


class RegulationType(Enum):
    """法规类型"""

    DATA_PROTECTION = "data_protection"
    CYBERSECURITY = "cybersecurity"
    AI_GOVERNANCE = "ai_governance"
    FINANCIAL = "financial"
    HEALTHCARE = "healthcare"
    PRIVACY = "privacy"
    CROSS_BORDER = "cross_border"
    INDUSTRY_SPECIFIC = "industry_specific"


class Jurisdiction(Enum):
    """法域"""

    EU = "eu"
    US = "us"
    CHINA = "china"
    RUSSIA = "russia"
    INDIA = "india"
    GLOBAL = "global"
    CROSS_BORDER = "cross_border"


@dataclass
class Regulation:
    """法规定义"""

    regulation_id: str
    name: str
    jurisdiction: Jurisdiction
    regulation_type: RegulationType
    description: str
    effective_date: datetime | None = None
    requirements: list[str] = field(default_factory=list)
    penalty: str = ""
    reference_url: str = ""


@dataclass
class ComplianceRequirement:
    """合规需求"""

    requirement_id: str
    regulation_id: str
    name: str
    description: str
    jurisdiction: Jurisdiction
    priority: int = 1
    status: ComplianceStatus = ComplianceStatus.PENDING_REVIEW
    checked_at: datetime | None = None
    evidence: list[str] = field(default_factory=list)
    assigned_to: str = ""


@dataclass
class ComplianceCheckResult:
    """合规检查结果"""

    result_id: str
    requirement_id: str
    status: ComplianceStatus
    checked_at: datetime
    checked_by: str
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    score: float = 0.0


class ComplianceRegistry:
    """
    合规注册表

    管理法规、需求、检查结果和法域规则。
    """

    def __init__(self):
        self.regulations: dict[str, Regulation] = {}
        self.requirements: dict[str, ComplianceRequirement] = {}
        self.check_results: dict[str, ComplianceCheckResult] = {}
        self.jurisdiction_rules: dict[Jurisdiction, dict[str, Any]] = {}
        self._initialize_default_regulations()
        self._initialize_default_rules()

    def _initialize_default_regulations(self) -> None:
        """初始化默认法规"""
        default_regulations = [
            Regulation(
                regulation_id="gdpr",
                name="General Data Protection Regulation",
                jurisdiction=Jurisdiction.EU,
                regulation_type=RegulationType.DATA_PROTECTION,
                description="EU regulation on data protection and privacy",
                requirements=[
                    "lawful_basis",
                    "data_minimization",
                    "purpose_limitation",
                    "accuracy",
                    "storage_limitation",
                    "integrity_confidentiality",
                    "accountability",
                ],
                penalty="Up to 4% of global annual turnover or €20M",
            ),
            Regulation(
                regulation_id="ccpa",
                name="California Consumer Privacy Act",
                jurisdiction=Jurisdiction.US,
                regulation_type=RegulationType.PRIVACY,
                description="California state statute intended to enhance privacy rights",
                requirements=[
                    "consumer_rights",
                    "disclosure",
                    "opt_out",
                    "non_discrimination",
                ],
                penalty="Up to $7,500 per intentional violation",
            ),
            Regulation(
                regulation_id="csl",
                name="China Cybersecurity Law",
                jurisdiction=Jurisdiction.CHINA,
                regulation_type=RegulationType.CYBERSECURITY,
                description="Chinese law on cybersecurity and data localization",
                requirements=[
                    "data_localization",
                    "security_assessment",
                    "cross_border_transfer_review",
                    "personal_information_protection",
                ],
                penalty="Up to 1M RMB and business suspension",
            ),
            Regulation(
                regulation_id="149-fz",
                name="Russia Federal Law 149-FZ",
                jurisdiction=Jurisdiction.RUSSIA,
                regulation_type=RegulationType.DATA_PROTECTION,
                description="Russian law on information, information technologies and data protection",
                requirements=[
                    "data_localization",
                    "operator_obligations",
                    "consent_requirements",
                ],
                penalty="Up to 500K RUB for first violation",
            ),
            Regulation(
                regulation_id="pdpb",
                name="India Personal Data Protection Bill",
                jurisdiction=Jurisdiction.INDIA,
                regulation_type=RegulationType.DATA_PROTECTION,
                description="Indian comprehensive data protection legislation",
                requirements=[
                    "data_fiduciary_obligations",
                    "data_principal_rights",
                    "cross_border_transfer",
                    "consent_framework",
                ],
                penalty="Up to 150 crore INR for serious violations",
            ),
            Regulation(
                regulation_id="eu-ai-act",
                name="EU AI Act",
                jurisdiction=Jurisdiction.EU,
                regulation_type=RegulationType.AI_GOVERNANCE,
                description="EU regulation on artificial intelligence systems",
                requirements=[
                    "risk_classification",
                    "high_risk_requirements",
                    "transparency_obligations",
                    "human_oversight",
                    "conformity_assessment",
                ],
                penalty="Up to 6% of global annual turnover",
            ),
        ]

        for reg in default_regulations:
            self.regulations[reg.regulation_id] = reg

    def _initialize_default_rules(self) -> None:
        """初始化默认法域规则"""
        self.jurisdiction_rules = {
            Jurisdiction.EU: {
                "breach_notification_hours": 72,
                "dpo_required": True,
                "data_transfer_mechanism": "SCC",
            },
            Jurisdiction.US: {
                "breach_notification_hours": 72,
                "sectoral_approach": True,
                "state_variations": ["CCPA", "CPRA", "VCDPA"],
            },
            Jurisdiction.CHINA: {
                "breach_notification_hours": 24,
                "data_localization_required": True,
                "security_review_required": True,
            },
            Jurisdiction.RUSSIA: {
                "breach_notification_hours": 24,
                "data_localization_required": True,
                "roscomnadzor_notification": True,
            },
            Jurisdiction.INDIA: {
                "breach_notification_hours": 72,
                "data_localization_preferred": True,
                "dpu_required": True,
            },
        }

    def register_requirement(self, requirement: ComplianceRequirement) -> str:
        """注册合规需求"""
        self.requirements[requirement.requirement_id] = requirement
        return requirement.requirement_id

    def record_check_result(self, result: ComplianceCheckResult) -> str:
        """记录检查结果"""
        self.check_results[result.result_id] = result
        # 更新对应需求的状态
        if result.requirement_id in self.requirements:
            self.requirements[result.requirement_id].status = result.status
            self.requirements[result.requirement_id].checked_at = result.checked_at
        return result.result_id

    def get_jurisdiction_compliance_status(
        self,
        jurisdiction: Jurisdiction | None = None,
    ) -> dict[str, Any]:
        """
        获取法域合规状态

        Args:
            jurisdiction: 目标法域，None 返回全局状态

        Returns:
            合规状态字典
        """
        if jurisdiction:
            reqs = [r for r in self.requirements.values() if r.jurisdiction == jurisdiction]
            regs = [r for r in self.regulations.values() if r.jurisdiction == jurisdiction]
        else:
            reqs = list(self.requirements.values())
            regs = list(self.regulations.values())

        if not reqs:
            # 没有需求记录时，基于法规返回基础状态
            return {
                "jurisdiction": jurisdiction.value if jurisdiction else "global",
                "compliance_rate": 0.0,
                "active_regulations": len(regs),
                "checked_requirements": 0,
                "status": ComplianceStatus.PENDING_REVIEW.value,
            }

        compliant_count = sum(1 for r in reqs if r.status == ComplianceStatus.COMPLIANT)
        total = len(reqs)
        rate = (compliant_count / total * 100) if total > 0 else 0.0

        return {
            "jurisdiction": jurisdiction.value if jurisdiction else "global",
            "compliance_rate": round(rate, 2),
            "active_regulations": len(regs),
            "checked_requirements": total,
            "compliant_count": compliant_count,
            "non_compliant_count": sum(
                1 for r in reqs if r.status == ComplianceStatus.NON_COMPLIANT
            ),
            "status": (
                ComplianceStatus.COMPLIANT.value
                if rate >= 95
                else ComplianceStatus.PARTIAL.value
                if rate >= 50
                else ComplianceStatus.NON_COMPLIANT.value
            ),
        }

    def generate_compliance_report(
        self,
        jurisdictions: list[Jurisdiction] | None = None,
    ) -> dict[str, Any]:
        """
        生成合规报告

        Args:
            jurisdictions: 目标法域列表，None 表示全部

        Returns:
            合规报告数据
        """
        if jurisdictions is None:
            jurisdictions = [
                j for j in Jurisdiction if j not in (Jurisdiction.GLOBAL, Jurisdiction.CROSS_BORDER)
            ]

        jurisdiction_reports = {}
        total_rate = 0.0

        for jur in jurisdictions:
            status = self.get_jurisdiction_compliance_status(jur)
            jurisdiction_reports[jur.value] = status
            total_rate += status.get("compliance_rate", 0.0)

        overall_rate = round(total_rate / len(jurisdictions), 2) if jurisdictions else 0.0

        # 生成推荐建议
        recommendations: list[dict[str, Any]] = []
        for jur in jurisdictions:
            status = jurisdiction_reports.get(jur.value, {})
            rate = status.get("compliance_rate", 0.0)
            if rate < 50:
                recommendations.append(
                    {
                        "action": f"Urgent compliance improvement needed in {jur.value.upper()}",
                        "details": f"Current rate: {rate:.1f}%. Immediate action required.",
                        "priority": "critical",
                        "jurisdiction": jur.value,
                    }
                )
            elif rate < 95:
                recommendations.append(
                    {
                        "action": f"Continue compliance enhancement in {jur.value.upper()}",
                        "details": f"Current rate: {rate:.1f}%. Address remaining gaps.",
                        "priority": "medium",
                        "jurisdiction": jur.value,
                    }
                )

        return {
            "overall_compliance_rate": overall_rate,
            "jurisdiction_count": len(jurisdictions),
            "jurisdictions": jurisdiction_reports,
            "recommendations": recommendations,
            "generated_at": datetime.now().isoformat(),
            "total_regulations": len(self.regulations),
            "total_requirements": len(self.requirements),
        }


class ComplianceEngine:
    """
    合规引擎

    提供高级合规评估和检查功能。
    """

    def __init__(self, registry: ComplianceRegistry):
        self.registry = registry

    def evaluate_compliance(
        self,
        requirement_id: str,
        evidence: list[str],
        evaluator: str = "system",
    ) -> ComplianceCheckResult:
        """
        评估单个需求的合规性

        Args:
            requirement_id: 需求ID
            evidence: 证据列表
            evaluator: 评估者标识

        Returns:
            检查结果
        """
        requirement = self.registry.requirements.get(requirement_id)
        if not requirement:
            return ComplianceCheckResult(
                result_id=f"res-{requirement_id}-{int(datetime.now().timestamp())}",
                requirement_id=requirement_id,
                status=ComplianceStatus.NOT_APPLICABLE,
                checked_at=datetime.now(),
                checked_by=evaluator,
                findings=["Requirement not found in registry"],
            )

        # 简化评估逻辑：有证据则视为合规
        status = ComplianceStatus.COMPLIANT if evidence else ComplianceStatus.NON_COMPLIANT
        score = 100.0 if evidence else 0.0

        result = ComplianceCheckResult(
            result_id=f"res-{requirement_id}-{int(datetime.now().timestamp())}",
            requirement_id=requirement_id,
            status=status,
            checked_at=datetime.now(),
            checked_by=evaluator,
            findings=[
                f"Evidence provided: {len(evidence)} items" if evidence else "No evidence provided"
            ],
            recommendations=[
                "Ensure all required evidence is documented",
                "Schedule periodic review",
            ]
            if status != ComplianceStatus.COMPLIANT
            else [],
            score=score,
        )

        self.registry.record_check_result(result)
        return result

    def batch_evaluate(
        self,
        jurisdiction: Jurisdiction | None = None,
        evaluator: str = "system",
    ) -> list[ComplianceCheckResult]:
        """
        批量评估法域内所有需求

        Args:
            jurisdiction: 目标法域
            evaluator: 评估者标识

        Returns:
            检查结果列表
        """
        requirements = [
            r
            for r in self.registry.requirements.values()
            if jurisdiction is None or r.jurisdiction == jurisdiction
        ]

        results: list[ComplianceCheckResult] = []
        for req in requirements:
            result = self.evaluate_compliance(
                req.requirement_id,
                req.evidence,
                evaluator,
            )
            results.append(result)

        return results


def create_compliance_system() -> tuple[ComplianceRegistry, ComplianceEngine]:
    """
    创建完整的合规系统

    Returns:
        (registry, engine) 元组
    """
    registry = ComplianceRegistry()
    engine = ComplianceEngine(registry)
    return registry, engine


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
]
