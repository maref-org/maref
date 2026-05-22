"""
合规管理系统

提供多法域合规框架，支持EU、US、China、Russia、India五大法域。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from maref.compliance.compliance_monitor import (
    AlertSeverity,
    ComplianceAlert,
    ComplianceMonitor,
    ComplianceSnapshot,
    MonitoringRule,
    MonitorState,
    create_compliance_monitor,
)
from maref.compliance.report_generator import (
    ComplianceReport,
    ReportFormat,
    ReportGenerator,
    ReportSection,
    ReportType,
    create_report_generator,
)
from maref.governance.audit import AuditLogger


class ComplianceStatus(Enum):
    """合规状态"""
    COMPLIANT = "compliant"          # 完全合规
    PARTIAL_COMPLIANT = "partial"    # 部分合规
    NON_COMPLIANT = "non_compliant"  # 不合规
    UNKNOWN = "unknown"              # 状态未知
    EXEMPT = "exempt"                # 豁免


class RegulationType(Enum):
    """法规类型"""
    DATA_PROTECTION = "data_protection"       # 数据保护 (GDPR, CCPA等)
    AI_GOVERNANCE = "ai_governance"           # AI治理 (EU AI Act等)
    CYBERSECURITY = "cybersecurity"           # 网络安全
    INDUSTRY_SPECIFIC = "industry_specific"   # 行业特定
    EXPORT_CONTROL = "export_control"         # 出口控制


class Jurisdiction(Enum):
    """司法管辖区"""
    EU = "eu"              # 欧洲联盟
    US = "us"              # 美国
    CN = "cn"              # 中国
    RU = "ru"              # 俄罗斯
    IN = "in"              # 印度
    GLOBAL = "global"      # 全球通用
    CROSS_BORDER = "cross_border"  # 跨境


@dataclass
class Regulation:
    """法规定义"""

    id: str                      # 法规ID，如 "gdpr-art5"
    name: str                    # 法规名称，如 "GDPR Article 5: Data Minimization"
    jurisdiction: Jurisdiction   # 适用司法管辖区
    regulation_type: RegulationType  # 法规类型
    description: str             # 法规描述
    requirements: list[str]      # 具体要求列表
    penalty: str | None = None  # 违规处罚说明
    effective_date: datetime | None = None  # 生效日期
    sunset_date: datetime | None = None     # 过期日期

    def is_active(self) -> bool:
        """检查法规是否活跃（在有效期内）"""
        current = datetime.now()

        if self.effective_date and current < self.effective_date:
            return False

        return not (self.sunset_date and current > self.sunset_date)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "jurisdiction": self.jurisdiction.value,
            "type": self.regulation_type.value,
            "description": self.description,
            "requirements": self.requirements,
            "penalty": self.penalty,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "sunset_date": self.sunset_date.isoformat() if self.sunset_date else None,
            "is_active": self.is_active()
        }


@dataclass
class ComplianceRequirement:
    """合规要求"""

    regulation_id: str        # 对应的法规ID
    requirement_text: str     # 要求文本
    implementation_guide: str  # 实施指南
    priority: int = 1        # 优先级 (1-5, 1最高)
    automated: bool = False  # 是否可自动化检查

    def to_dict(self) -> dict[str, Any]:
        return {
            "regulation_id": self.regulation_id,
            "requirement_text": self.requirement_text,
            "implementation_guide": self.implementation_guide,
            "priority": self.priority,
            "automated": self.automated
        }


@dataclass
class ComplianceCheckResult:
    """合规检查结果"""

    requirement_id: str          # 要求ID
    status: ComplianceStatus    # 检查状态
    evidence: list[str]         # 合规证据列表
    violations: list[str]       # 违规描述列表
    checked_at: datetime        # 检查时间
    next_check_due: datetime | None = None  # 下次检查时间

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "status": self.status.value,
            "evidence": self.evidence,
            "violations": self.violations,
            "checked_at": self.checked_at.isoformat(),
            "next_check_due": self.next_check_due.isoformat() if self.next_check_due else None
        }


class ComplianceRegistry:
    """合规注册表 - 多法规管理核心"""

    def __init__(self, audit_logger: AuditLogger | None = None):
        self.audit_logger = audit_logger or AuditLogger()
        self.regulations: dict[str, Regulation] = {}
        self.requirements: dict[str, ComplianceRequirement] = {}
        self.check_results: dict[str, ComplianceCheckResult] = {}  # key: requirement_id
        self.jurisdiction_rules: dict[Jurisdiction, dict[str, Any]] = {}

        # 初始化内置法规
        self._initialize_builtin_regulations()
        self._initialize_jurisdiction_rules()

    def _initialize_builtin_regulations(self) -> None:
        """初始化内置法规"""
        # GDPR示例法规
        gdpr_articles = [
            Regulation(
                id="gdpr-art5",
                name="GDPR Article 5: Principles relating to processing of personal data",
                jurisdiction=Jurisdiction.EU,
                regulation_type=RegulationType.DATA_PROTECTION,
                description="Data minimization, purpose limitation, accuracy, storage limitation, integrity and confidentiality",
                requirements=[
                    "Lawfulness, fairness and transparency",
                    "Purpose limitation",
                    "Data minimization",
                    "Accuracy",
                    "Storage limitation",
                    "Integrity and confidentiality",
                    "Accountability"
                ],
                effective_date=datetime(2018, 5, 25),
                penalty="Up to €20 million or 4% of global annual turnover"
            ),
            Regulation(
                id="gdpr-art15",
                name="GDPR Article 15: Right of access by the data subject",
                jurisdiction=Jurisdiction.EU,
                regulation_type=RegulationType.DATA_PROTECTION,
                description="Data subjects have the right to obtain confirmation as to whether personal data concerning them is being processed",
                requirements=[
                    "Provide access to personal data",
                    "Provide information on processing purposes",
                    "Provide information on data categories",
                    "Provide information on data recipients",
                    "Provide information on data retention periods"
                ],
                effective_date=datetime(2018, 5, 25)
            )
        ]

        # EU AI Act示例
        ai_act_articles = [
            Regulation(
                id="eu-ai-act-art6",
                name="EU AI Act Article 6: High-risk AI systems",
                jurisdiction=Jurisdiction.EU,
                regulation_type=RegulationType.AI_GOVERNANCE,
                description="Requirements for high-risk AI systems including risk management, data governance, transparency, human oversight",
                requirements=[
                    "Risk management system",
                    "Data and data governance",
                    "Technical documentation",
                    "Record-keeping",
                    "Transparency and information provision",
                    "Human oversight",
                    "Accuracy, robustness and cybersecurity"
                ],
                effective_date=datetime(2026, 1, 1),  # 预期生效日期
                penalty="Up to €30 million or 6% of global annual turnover"
            )
        ]

        # 中国网络安全法示例
        csl_articles = [
            Regulation(
                id="csl-art37",
                name="China Cybersecurity Law Article 37: Cross-border data transfer",
                jurisdiction=Jurisdiction.CN,
                regulation_type=RegulationType.CYBERSECURITY,
                description="Critical information infrastructure operators must store personal information and important data collected in China within China",
                requirements=[
                    "Data localization for critical information infrastructure",
                    "Security assessment for cross-border data transfer",
                    "Consent from data subjects",
                    "Notification to authorities"
                ],
                penalty="Confiscation of illegal gains, fines up to 1M RMB"
            )
        ]

        # 注册所有法规
        for regulation in gdpr_articles + ai_act_articles + csl_articles:
            self.register_regulation(regulation)

    def _initialize_jurisdiction_rules(self) -> None:
        """初始化司法管辖区规则"""
        self.jurisdiction_rules = {
            Jurisdiction.EU: {
                "data_transfers_allowed_to": ["EEA", "Adequacy decisions countries"],
                "requires_dpo": True,  # Data Protection Officer
                "default_retention_period": "6 years",
                "breach_notification_hours": 72,
                "requires_dpia": True  # Data Protection Impact Assessment
            },
            Jurisdiction.US: {
                "data_transfers_allowed_to": ["US", "Privacy Shield participants"],
                "requires_dpo": False,
                "default_retention_period": "7 years",  # 财务记录保留
                "breach_notification_days": 30,
                "state_specific_rules": ["CCPA", "CPRA", "VCDPA", "CPA"]
            },
            Jurisdiction.CN: {
                "data_transfers_allowed_to": ["China"],
                "requires_dpo": False,
                "default_retention_period": "永久保存",
                "breach_notification_hours": 24,
                "requires_safety_assessment": True,
                "data_categories": ["important data", "personal information"]
            },
            Jurisdiction.RU: {
                "data_transfers_allowed_to": ["Russia"],
                "requires_dpo": False,
                "default_retention_period": "5 years",
                "breach_notification_hours": 24,
                "requires_localization": True
            },
            Jurisdiction.IN: {
                "data_transfers_allowed_to": ["India"],
                "requires_dpo": True,
                "default_retention_period": "5 years",
                "breach_notification_hours": 72,
                "requires_consent_manager": True
            }
        }

    def register_regulation(self, regulation: Regulation) -> None:
        """注册法规"""
        self.regulations[regulation.id] = regulation

        # 审计日志
        self.audit_logger.log(
            event_type="compliance_regulation_registered",
            actor="ComplianceRegistry",
            action="register_regulation",
            details=f"Registered regulation: {regulation.name}",
            metadata={
                "regulation_id": regulation.id,
                "jurisdiction": regulation.jurisdiction.value,
                "type": regulation.regulation_type.value
            }
        )

    def add_requirement(self, requirement: ComplianceRequirement) -> None:
        """添加合规要求"""
        self.requirements[requirement.regulation_id] = requirement

        self.audit_logger.log(
            event_type="compliance_requirement_added",
            actor="ComplianceRegistry",
            action="add_requirement",
            details=f"Added requirement for {requirement.regulation_id}",
            metadata={
                "regulation_id": requirement.regulation_id,
                "priority": requirement.priority,
                "automated": requirement.automated
            }
        )

    def check_compliance(self, requirement_id: str, evidence: list[str] = None) -> ComplianceCheckResult:
        """检查特定要求的合规性"""
        requirement = self.requirements.get(requirement_id)
        if not requirement:
            raise ValueError(f"Requirement not found: {requirement_id}")

        regulation = self.regulations.get(requirement.regulation_id)
        if not regulation:
            raise ValueError(f"Regulation not found: {requirement.regulation_id}")

        checked_at = datetime.now()
        evidence = evidence or []

        # 简化的合规检查逻辑
        # 在实际实现中，这里会调用具体的检查器
        if evidence and len(evidence) > 0:
            status = ComplianceStatus.COMPLIANT
            violations = []
        else:
            status = ComplianceStatus.NON_COMPLIANT
            violations = ["No evidence provided for compliance verification"]

        # 计算下次检查时间（基于优先级）
        if requirement.priority == 1:
            next_check = checked_at + timedelta(days=7)   # 高优先级：每周检查
        elif requirement.priority == 2:
            next_check = checked_at + timedelta(days=30)  # 中优先级：每月检查
        else:
            next_check = checked_at + timedelta(days=90)  # 低优先级：每季度检查

        result = ComplianceCheckResult(
            requirement_id=requirement_id,
            status=status,
            evidence=evidence,
            violations=violations,
            checked_at=checked_at,
            next_check_due=next_check
        )

        self.check_results[requirement_id] = result

        # 审计日志
        self.audit_logger.log(
            event_type="compliance_check_completed",
            actor="ComplianceRegistry",
            action="check_compliance",
            details=f"Compliance check for {requirement_id}: {status.value}",
            metadata={
                "requirement_id": requirement_id,
                "status": status.value,
                "evidence_count": len(evidence),
                "violation_count": len(violations)
            }
        )

        return result

    def get_jurisdiction_compliance_status(self, jurisdiction: Jurisdiction) -> dict[str, Any]:
        """获取特定司法管辖区的合规状态"""
        jurisdiction_regulations = [
            reg for reg in self.regulations.values()
            if reg.jurisdiction == jurisdiction and reg.is_active()
        ]

        jurisdiction_requirements = [
            req for req in self.requirements.values()
            if req.regulation_id in [reg.id for reg in jurisdiction_regulations]
        ]

        # 获取最新的检查结果
        check_results = []
        for req in jurisdiction_requirements:
            result = self.check_results.get(req.regulation_id)
            if result:
                check_results.append(result)

        # 统计合规状态
        status_counts = {
            ComplianceStatus.COMPLIANT.value: 0,
            ComplianceStatus.PARTIAL_COMPLIANT.value: 0,
            ComplianceStatus.NON_COMPLIANT.value: 0,
            ComplianceStatus.UNKNOWN.value: 0,
            ComplianceStatus.EXEMPT.value: 0
        }

        for result in check_results:
            status_counts[result.status.value] += 1

        total_checks = len(check_results)
        if total_checks > 0:
            compliance_rate = (status_counts[ComplianceStatus.COMPLIANT.value] +
                              status_counts[ComplianceStatus.EXEMPT.value]) / total_checks * 100
        else:
            compliance_rate = 0.0

        return {
            "jurisdiction": jurisdiction.value,
            "active_regulations": len(jurisdiction_regulations),
            "requirements_count": len(jurisdiction_requirements),
            "checked_requirements": len(check_results),
            "compliance_rate": round(compliance_rate, 2),
            "status_counts": status_counts,
            "jurisdiction_rules": self.jurisdiction_rules.get(jurisdiction, {}),
            "next_check_due": self._get_next_check_due(check_results)
        }

    def _get_next_check_due(self, check_results: list[ComplianceCheckResult]) -> str | None:
        """获取下次检查到期时间"""
        if not check_results:
            return None

        # 找到最早的到期时间
        due_dates = [r.next_check_due for r in check_results if r.next_check_due]
        if not due_dates:
            return None

        earliest = min(due_dates)
        return earliest.isoformat()

    def generate_compliance_report(
        self,
        jurisdictions: list[Jurisdiction] | None = None
    ) -> dict[str, Any]:
        """生成合规报告"""
        if not jurisdictions:
            jurisdictions = [j for j in Jurisdiction if j != Jurisdiction.GLOBAL and j != Jurisdiction.CROSS_BORDER]

        report_data = {
            "generated_at": datetime.now().isoformat(),
            "jurisdictions": {},
            "summary": {},
            "recommendations": []
        }

        total_active_regulations = 0
        total_compliance_rate = 0.0
        jurisdiction_count = 0

        for jurisdiction in jurisdictions:
            jurisdiction_status = self.get_jurisdiction_compliance_status(jurisdiction)
            report_data["jurisdictions"][jurisdiction.value] = jurisdiction_status

            # 累加统计数据
            total_active_regulations += jurisdiction_status["active_regulations"]
            total_compliance_rate += jurisdiction_status.get("compliance_rate", 0.0)
            jurisdiction_count += 1

            # 生成建议
            if jurisdiction_status["compliance_rate"] < 80.0:
                report_data["recommendations"].append({
                    "jurisdiction": jurisdiction.value,
                    "priority": "high",
                    "action": f"Improve compliance rate for {jurisdiction.value} jurisdiction",
                    "details": f"Current compliance rate: {jurisdiction_status['compliance_rate']}%"
                })

        # 计算总体统计
        if jurisdiction_count > 0:
            avg_compliance_rate = total_compliance_rate / jurisdiction_count
        else:
            avg_compliance_rate = 0.0

        report_data["summary"] = {
            "total_jurisdictions": jurisdiction_count,
            "total_active_regulations": total_active_regulations,
            "average_compliance_rate": round(avg_compliance_rate, 2),
            "generation_time": datetime.now().isoformat()
        }

        return report_data

    def get_regulations_by_type(self, regulation_type: RegulationType) -> list[Regulation]:
        """按类型获取法规"""
        return [
            reg for reg in self.regulations.values()
            if reg.regulation_type == regulation_type and reg.is_active()
        ]

    def get_upcoming_checks(self, days_ahead: int = 30) -> list[ComplianceCheckResult]:
        """获取即将到期的检查"""
        upcoming = []
        today = datetime.now()

        for result in self.check_results.values():
            if result.next_check_due:
                days_until = (result.next_check_due - today).days
                if 0 <= days_until <= days_ahead:
                    upcoming.append(result)

        # 按到期时间排序
        upcoming.sort(key=lambda x: x.next_check_due or datetime.max)
        return upcoming

    def export_registry(self, filepath: str) -> None:
        """导出注册表数据"""
        export_data = {
            "exported_at": datetime.now().isoformat(),
            "regulations": [reg.to_dict() for reg in self.regulations.values()],
            "requirements": [req.to_dict() for req in self.requirements.values()],
            "check_results": [res.to_dict() for res in self.check_results.values()],
            "jurisdiction_rules": {
                jur.value: rules for jur, rules in self.jurisdiction_rules.items()
            }
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        self.audit_logger.log(
            event_type="compliance_registry_exported",
            actor="ComplianceRegistry",
            action="export_registry",
            details=f"Exported registry to {filepath}",
            metadata={"filepath": filepath, "record_count": len(export_data["regulations"])}
        )

    def load_registry(self, filepath: str) -> None:
        """加载注册表数据"""
        try:
            with open(filepath, encoding='utf-8') as f:
                import_data = json.load(f)

            # 清空当前数据
            self.regulations.clear()
            self.requirements.clear()
            self.check_results.clear()

            # 加载法规
            for reg_data in import_data.get("regulations", []):
                regulation = Regulation(
                    id=reg_data["id"],
                    name=reg_data["name"],
                    jurisdiction=Jurisdiction(reg_data["jurisdiction"]),
                    regulation_type=RegulationType(reg_data["type"]),
                    description=reg_data["description"],
                    requirements=reg_data["requirements"],
                    penalty=reg_data.get("penalty"),
                    effective_date=datetime.fromisoformat(reg_data["effective_date"]) if reg_data.get("effective_date") else None,
                    sunset_date=datetime.fromisoformat(reg_data["sunset_date"]) if reg_data.get("sunset_date") else None
                )
                self.regulations[regulation.id] = regulation

            # 加载要求
            for req_data in import_data.get("requirements", []):
                requirement = ComplianceRequirement(
                    regulation_id=req_data["regulation_id"],
                    requirement_text=req_data["requirement_text"],
                    implementation_guide=req_data["implementation_guide"],
                    priority=req_data.get("priority", 1),
                    automated=req_data.get("automated", False)
                )
                self.requirements[requirement.regulation_id] = requirement

            # 加载检查结果
            for res_data in import_data.get("check_results", []):
                result = ComplianceCheckResult(
                    requirement_id=res_data["requirement_id"],
                    status=ComplianceStatus(res_data["status"]),
                    evidence=res_data["evidence"],
                    violations=res_data["violations"],
                    checked_at=datetime.fromisoformat(res_data["checked_at"]),
                    next_check_due=datetime.fromisoformat(res_data["next_check_due"]) if res_data.get("next_check_due") else None
                )
                self.check_results[result.requirement_id] = result

            self.audit_logger.log(
                event_type="compliance_registry_loaded",
                actor="ComplianceRegistry",
                action="load_registry",
                details=f"Loaded registry from {filepath}",
                metadata={"filepath": filepath, "record_count": len(import_data.get("regulations", []))}
            )

        except Exception as e:
            self.audit_logger.log(
                event_type="compliance_registry_load_failed",
                actor="ComplianceRegistry",
                action="load_registry",
                details=f"Failed to load registry from {filepath}: {str(e)}",
                metadata={"filepath": filepath, "error": str(e)},
                level="ERROR"
            )
            raise


class ComplianceEngine:
    """合规引擎 - 提供高级合规操作"""

    def __init__(self, registry: ComplianceRegistry):
        self.registry = registry
        self.compliance_cache: dict[str, dict[str, Any]] = {}

    def assess_system_compliance(
        self,
        system_info: dict[str, Any],
        target_jurisdictions: list[Jurisdiction]
    ) -> dict[str, Any]:
        """评估系统整体合规性"""
        assessment = {
            "assessment_id": f"comp-assessment-{int(time.time())}",
            "assessed_at": datetime.now().isoformat(),
            "system_info": system_info,
            "jurisdiction_assessments": {},
            "overall_compliance_score": 0.0,
            "risk_level": "unknown",
            "recommended_actions": []
        }

        total_score = 0.0
        jurisdiction_count = len(target_jurisdictions)

        for jurisdiction in target_jurisdictions:
            jurisdiction_status = self.registry.get_jurisdiction_compliance_status(jurisdiction)
            compliance_rate = jurisdiction_status.get("compliance_rate", 0.0)

            # 风险评估
            if compliance_rate >= 90:
                risk_level = "low"
            elif compliance_rate >= 70:
                risk_level = "medium"
            else:
                risk_level = "high"

            jurisdiction_assessment = {
                **jurisdiction_status,
                "risk_level": risk_level,
                "assessment_complete": compliance_rate > 0
            }

            assessment["jurisdiction_assessments"][jurisdiction.value] = jurisdiction_assessment
            total_score += compliance_rate

            # 为高风险管辖区添加建议
            if risk_level == "high":
                assessment["recommended_actions"].append({
                    "priority": "high",
                    "jurisdiction": jurisdiction.value,
                    "action": f"Review and improve compliance for {jurisdiction.value} jurisdiction",
                    "details": f"Current compliance rate: {compliance_rate}%"
                })

        # 计算总体分数
        overall_score = total_score / jurisdiction_count if jurisdiction_count > 0 else 0.0

        assessment["overall_compliance_score"] = round(overall_score, 2)

        # 总体风险等级
        if overall_score >= 90:
            assessment["risk_level"] = "low"
        elif overall_score >= 70:
            assessment["risk_level"] = "medium"
        else:
            assessment["risk_level"] = "high"

        # 缓存评估结果
        cache_key = f"{system_info.get('system_id', 'unknown')}-{int(time.time())}"
        self.compliance_cache[cache_key] = assessment

        return assessment

    def validate_data_processing(
        self,
        processing_purpose: str,
        data_categories: list[str],
        data_subjects_location: Jurisdiction,
        processor_location: Jurisdiction
    ) -> dict[str, Any]:
        """验证数据处理活动的合规性"""
        validation_id = f"dp-validation-{int(time.time())}"

        # 检查数据转移合规性
        data_transfer_compliance = self._check_data_transfer_compliance(
            sender_jurisdiction=data_subjects_location,
            receiver_jurisdiction=processor_location
        )

        # 检查目的限制
        purpose_valid = self._validate_processing_purpose(processing_purpose)

        # 数据最小化检查
        data_minimization = self._check_data_minimization(data_categories, processing_purpose)

        # 生成验证结果
        validation_result = {
            "validation_id": validation_id,
            "validated_at": datetime.now().isoformat(),
            "processing_purpose": processing_purpose,
            "data_categories": data_categories,
            "data_subjects_location": data_subjects_location.value,
            "processor_location": processor_location.value,
            "data_transfer_compliance": data_transfer_compliance,
            "purpose_valid": purpose_valid,
            "data_minimization": data_minimization,
            "overall_validation": {
                "valid": data_transfer_compliance["allowed"] and purpose_valid and data_minimization["valid"],
                "issues": [
                    issue for issue in [
                        *data_transfer_compliance.get("issues", []),
                        *data_minimization.get("issues", [])
                    ] if issue
                ]
            }
        }

        return validation_result

    def _check_data_transfer_compliance(
        self,
        sender_jurisdiction: Jurisdiction,
        receiver_jurisdiction: Jurisdiction
    ) -> dict[str, Any]:
        """检查数据转移合规性"""
        sender_rules = self.registry.jurisdiction_rules.get(sender_jurisdiction, {})
        allowed_destinations = sender_rules.get("data_transfers_allowed_to", [])

        is_same_jurisdiction = sender_jurisdiction == receiver_jurisdiction

        if is_same_jurisdiction:
            return {
                "allowed": True,
                "reason": "Data transfer within same jurisdiction",
                "restrictions": [],
                "issues": []
            }

        # 检查是否在允许的目的地列表中
        receiver_name = receiver_jurisdiction.value.upper()
        if receiver_name in [dest.upper() for dest in allowed_destinations]:
            return {
                "allowed": True,
                "reason": f"Data transfer to {receiver_name} is allowed",
                "restrictions": [],
                "issues": []
            }

        # 需要额外措施
        required_measures = []
        issues = []

        if sender_jurisdiction == Jurisdiction.EU and receiver_jurisdiction == Jurisdiction.US:
            required_measures.append("Implement EU-US Data Privacy Framework safeguards")
            required_measures.append("Conduct transfer impact assessment")

        elif sender_jurisdiction == Jurisdiction.CN:
            required_measures.append("Conduct security assessment")
            required_measures.append("Obtain approval from Chinese authorities")
            issues.append("Cross-border data transfer from China requires special approval")

        elif sender_jurisdiction == Jurisdiction.RU:
            issues.append("Data transfer out of Russia is generally prohibited")

        return {
            "allowed": len(issues) == 0,
            "reason": "Data transfer requires additional measures",
            "required_measures": required_measures,
            "issues": issues,
            "sender_jurisdiction": sender_jurisdiction.value,
            "receiver_jurisdiction": receiver_jurisdiction.value
        }

    def _validate_processing_purpose(self, purpose: str) -> bool:
        """验证处理目的的合法性"""
        valid_purposes = [
            "consent", "contract", "legal_obligation", "vital_interests",
            "public_task", "legitimate_interests", "research", "archiving"
        ]

        # 简化的检查：目的描述中是否包含合法目的关键词
        purpose_lower = purpose.lower()
        return any(valid in purpose_lower for valid in valid_purposes)

    def _check_data_minimization(
        self,
        data_categories: list[str],
        processing_purpose: str
    ) -> dict[str, Any]:
        """检查数据最小化原则"""
        sensitive_categories = [
            "biometric", "genetic", "health", "racial", "political",
            "religious", "sexual", "criminal", "financial", "location"
        ]

        used_categories = set(data_categories)
        sensitive_used = [cat for cat in used_categories if cat in sensitive_categories]

        issues = []
        if sensitive_used:
            issues.append(f"Sensitive data categories used: {', '.join(sensitive_used)}")

        # 检查是否符合目的
        purpose_specific_categories = {
            "research": ["demographic", "behavioral", "preferences"],
            "marketing": ["contact", "preferences", "behavioral"],
            "analytics": ["usage", "performance", "behavioral"],
            "security": ["login", "access", "audit"]
        }

        appropriate_categories = []
        for purpose_key, categories in purpose_specific_categories.items():
            if purpose_key in processing_purpose.lower():
                appropriate_categories.extend(categories)

        # 检查是否有不适当的数据类别
        inappropriate = used_categories - set(appropriate_categories)
        if inappropriate and inappropriate != used_categories:
            issues.append(f"Potential data minimization issue: {', '.join(inappropriate)} may not be necessary for purpose '{processing_purpose}'")

        return {
            "valid": len(issues) == 0,
            "sensitive_categories_used": sensitive_used,
            "appropriate_categories": list(set(appropriate_categories)),
            "issues": issues
        }

    def generate_compliance_certificate(
        self,
        entity_name: str,
        jurisdictions: list[Jurisdiction],
        assessment_id: str
    ) -> dict[str, Any]:
        """生成合规证书"""
        assessment = self.compliance_cache.get(assessment_id)
        if not assessment:
            assessment = self.assess_system_compliance(
                {"entity_name": entity_name},
                jurisdictions
            )

        overall_score = assessment.get("overall_compliance_score", 0.0)

        if overall_score >= 90:
            compliance_level = "Excellent"
            certificate_class = "A"
        elif overall_score >= 75:
            compliance_level = "Good"
            certificate_class = "B"
        elif overall_score >= 60:
            compliance_level = "Adequate"
            certificate_class = "C"
        else:
            compliance_level = "Needs Improvement"
            certificate_class = "D"

        certificate = {
            "certificate_id": f"compliance-cert-{int(time.time())}",
            "issued_at": datetime.now().isoformat(),
            "valid_until": (datetime.now() + timedelta(days=365)).isoformat(),
            "entity_name": entity_name,
            "compliance_level": compliance_level,
            "certificate_class": certificate_class,
            "overall_score": overall_score,
            "jurisdictions_covered": [jur.value for jur in jurisdictions],
            "assessment_summary": {
                "total_jurisdictions": len(jurisdictions),
                "average_compliance_rate": overall_score,
                "risk_level": assessment.get("risk_level", "unknown")
            },
            "issuing_authority": "MAREF Compliance Engine",
            "certificate_notes": "This certificate is based on automated assessment and should be verified by legal professionals."
        }

        return certificate


def create_compliance_system() -> tuple[ComplianceRegistry, ComplianceEngine]:
    """创建合规系统"""
    audit_logger = AuditLogger()
    registry = ComplianceRegistry(audit_logger)
    engine = ComplianceEngine(registry)

    return registry, engine


# 导出主要类
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
