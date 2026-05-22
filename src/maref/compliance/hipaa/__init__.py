"""
HIPAA 医疗合规模块

Health Insurance Portability and Accountability Act (HIPAA) 合规支持。
实现 PHI (Protected Health Information) 数据保护和安全控制。

关键规则:
- HIPAA Privacy Rule: PHI 使用和披露
- HIPAA Security Rule: ePHI 技术安全保护
- HITECH Act: 违规通知和强化执行
- Breach Notification Rule: 数据泄露通知
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PHICategory(Enum):
    """PHI 数据类别"""
    DEMOGRAPHIC = "demographic"
    MEDICAL_RECORD = "medical_record"
    PAYMENT = "payment"
    INSURANCE = "insurance"
    GENETIC = "genetic"
    BIOMETRIC = "biometric"
    CLINICAL_TRIAL = "clinical_trial"
    MENTAL_HEALTH = "mental_health"
    SUBSTANCE_ABUSE = "substance_abuse"
    OTHER = "other"


class HIPAAComplianceStatus(Enum):
    """HIPAA 合规状态"""
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PARTIAL = "partial"
    EXEMPT = "exempt"


class SecurityRuleCategory(Enum):
    """HIPAA Security Rule 分类"""
    ADMINISTRATIVE = "administrative"
    PHYSICAL = "physical"
    TECHNICAL = "technical"


class BreachRiskLevel(Enum):
    """泄露风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class PHIDataElement:
    """PHI 数据元素"""

    element_id: str
    name: str
    category: PHICategory
    is_direct_identifier: bool
    encryption_required: bool = True
    access_controls: list[str] = field(default_factory=list)
    retention_period_days: int = 2190  # 默认6年
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BusinessAssociateAgreement:
    """业务伙伴协议 (BAA)"""

    baa_id: str
    covered_entity: str
    business_associate: str
    signed_at: datetime
    expires_at: datetime
    phi_categories: list[PHICategory] = field(default_factory=list)
    permitted_uses: list[str] = field(default_factory=list)
    is_active: bool = True

    def is_valid(self) -> bool:
        return self.is_active and datetime.now() < self.expires_at


@dataclass
class BreachAssessment:
    """数据泄露评估"""

    assessment_id: str
    incident_date: datetime
    description: str
    affected_individuals: int
    affected_phi_categories: list[PHICategory]
    risk_level: BreachRiskLevel
    notification_required: bool = True
    notification_deadline: datetime | None = None
    hhs_notification_required: bool = False
    media_notification_required: bool = False


class HIPAAComplianceEngine:
    """
    HIPAA 合规引擎

    管理医疗保健数据的合规检查和安全控制。
    """

    # HIPAA 标识符列表（18类）
    HIPAA_IDENTIFIERS = [
        "name", "address", "dates", "telephone", "fax",
        "email", "ssn", "medical_record_number", "health_plan_number",
        "account_number", "certificate_number", "vehicle_identifier",
        "device_identifier", "url", "ip_address", "biometric_identifier",
        "full_face_photo", "any_other_unique_identifier"
    ]

    def __init__(self):
        self._phi_elements: dict[str, PHIDataElement] = {}
        self._baas: dict[str, BusinessAssociateAgreement] = {}
        self._breaches: dict[str, BreachAssessment] = []
        self._initialize_default_elements()

    def _initialize_default_elements(self) -> None:
        """初始化默认 PHI 数据元素"""
        defaults = [
            PHIDataElement("phi-name", "Patient Name", PHICategory.DEMOGRAPHIC, True, access_controls=["role_based", "audit_log"]),
            PHIDataElement("phi-ssn", "Social Security Number", PHICategory.DEMOGRAPHIC, True, access_controls=["role_based", "encryption", "masking"]),
            PHIDataElement("phi-dob", "Date of Birth", PHICategory.DEMOGRAPHIC, False, access_controls=["role_based"]),
            PHIDataElement("phi-mrn", "Medical Record Number", PHICategory.MEDICAL_RECORD, True, access_controls=["role_based", "audit_log"]),
            PHIDataElement("phi-diag", "Diagnosis Information", PHICategory.MEDICAL_RECORD, True, access_controls=["role_based", "encryption"]),
            PHIDataElement("phi-med", "Medication List", PHICategory.MEDICAL_RECORD, False, access_controls=["role_based"]),
            PHIDataElement("phi-insurance", "Insurance ID", PHICategory.INSURANCE, True, access_controls=["role_based", "encryption"]),
            PHIDataElement("phi-payment", "Payment Information", PHICategory.PAYMENT, True, access_controls=["role_based", "encryption", "audit_log"]),
            PHIDataElement("phi-genetic", "Genetic Information", PHICategory.GENETIC, True, access_controls=["role_based", "encryption", "consent_required"]),
            PHIDataElement("phi-mental", "Mental Health Records", PHICategory.MENTAL_HEALTH, True, access_controls=["role_based", "encryption", "consent_required", "special_protection"]),
        ]

        for element in defaults:
            self.register_phi_element(element)

    def register_phi_element(self, element: PHIDataElement) -> str:
        """注册 PHI 数据元素"""
        self._phi_elements[element.element_id] = element
        return element.element_id

    def classify_data(self, data_categories: list[str]) -> list[PHIDataElement]:
        """
        分类数据是否为 PHI

        Args:
            data_categories: 数据类别列表

        Returns:
            PHI数据元素列表
        """
        phi_matches: list[PHIDataElement] = []

        for category in data_categories:
            for element in self._phi_elements.values():
                if element.name.lower() in category.lower() or category.lower() in element.name.lower() or element.category.value in category.lower():
                    phi_matches.append(element)

        return phi_matches

    def check_identifier_presence(self, data_fields: list[str]) -> dict[str, Any]:
        """
        检查数据字段中是否包含 HIPAA 标识符

        Args:
            data_fields: 数据字段名列表

        Returns:
            检查结果
        """
        found_identifiers: list[str] = []

        for field in data_fields:
            for identifier in self.HIPAA_IDENTIFIERS:
                if identifier in field.lower():
                    found_identifiers.append(f"{field} -> {identifier}")

        return {
            "contains_phi": len(found_identifiers) > 0,
            "identifiers_found": found_identifiers,
            "deidentification_required": len(found_identifiers) > 0,
            "safe_harbor_applicable": bool(found_identifiers),
        }

    def verify_access_control(
        self,
        user_role: str,
        phi_element_id: str,
        action: str,
        purpose: str,
    ) -> dict[str, Any]:
        """
        验证 PHI 访问是否符合 HIPAA 最小必要原则

        Args:
            user_role: 用户角色
            phi_element_id: PHI元素ID
            action: 操作 (read, write, delete)
            purpose: 访问目的 (treatment, payment, operations)

        Returns:
            访问控制验证结果
        """
        element = self._phi_elements.get(phi_element_id)
        if not element:
            return {
                "allowed": False,
                "reason": "PHI element not recognized",
            }

        # TPO 例外 (Treatment, Payment, Operations)
        allowed_purposes = ["treatment", "payment", "healthcare_operations"]

        if purpose not in allowed_purposes:
            # 需要授权
            if "consent_required" in element.access_controls:
                return {
                    "allowed": False,
                    "reason": f"Purpose '{purpose}' requires patient authorization",
                    "required": "Patient consent or authorization",
                }

        # 最小必要原则
        if action == "delete" and purpose not in ("healthcare_operations", "legal_requirement"):
            return {
                "allowed": False,
                "reason": "PHI deletion not permitted for this purpose",
            }

        # 角色检查
        if "special_protection" in element.access_controls:
            allowed_roles = ["physician", "psychiatrist", "compliance_officer"]
            if user_role not in allowed_roles:
                return {
                    "allowed": False,
                    "reason": f"Special protection applies. Role '{user_role}' not authorized.",
                }

        return {
            "allowed": True,
            "element_id": phi_element_id,
            "user_role": user_role,
            "action": action,
            "purpose": purpose,
            "minimum_necessary": True if purpose in allowed_purposes else "review_required",
        }

    def register_baa(self, baa: BusinessAssociateAgreement) -> str:
        """注册业务伙伴协议"""
        self._baas[baa.baa_id] = baa
        return baa.baa_id

    def verify_baa(self, business_associate: str) -> dict[str, Any]:
        """
        验证 BAA 是否存在且有效

        Args:
            business_associate: 业务伙伴名称

        Returns:
            BAA 验证结果
        """
        matching_baas = [
            b for b in self._baas.values()
            if b.business_associate == business_associate
        ]

        if not matching_baas:
            return {
                "valid": False,
                "reason": f"No BAA found for {business_associate}",
                "action_required": "Execute BAA before sharing PHI",
            }

        valid_baas = [b for b in matching_baas if b.is_valid()]

        if valid_baas:
            baa = valid_baas[0]
            return {
                "valid": True,
                "baa_id": baa.baa_id,
                "expires_at": baa.expires_at.isoformat(),
                "phi_categories": [c.value for c in baa.phi_categories],
            }

        return {
            "valid": False,
            "reason": "BAA found but expired or inactive",
            "action_required": "Renew BAA before sharing PHI",
        }

    def assess_breach(
        self,
        incident_description: str,
        affected_individuals: int,
        affected_phi_categories: list[PHICategory],
    ) -> BreachAssessment:
        """
        评估数据泄露

        Args:
            incident_description: 事件描述
            affected_individuals: 受影响的个人数量
            affected_phi_categories: 受影响的PHI类别

        Returns:
            泄露评估结果
        """
        now = datetime.now()

        # 风险评估
        risk_level = BreachRiskLevel.LOW
        notification_required = False
        hhs_required = False
        media_required = False

        sensitive_categories = {PHICategory.GENETIC, PHICategory.MENTAL_HEALTH, PHICategory.SUBSTANCE_ABUSE}
        has_sensitive = bool(set(affected_phi_categories) & sensitive_categories)

        if affected_individuals >= 500:
            risk_level = BreachRiskLevel.HIGH
            notification_required = True
            hhs_required = True
            media_required = True
        elif affected_individuals >= 50:
            risk_level = BreachRiskLevel.MEDIUM
            notification_required = True
            hhs_required = True
        elif has_sensitive:
            risk_level = BreachRiskLevel.MEDIUM
            notification_required = True

        # 通知截止日期（60天内）
        notification_deadline = now + __import__('datetime').timedelta(days=60) if notification_required else None

        assessment = BreachAssessment(
            assessment_id=f"breach-{int(now.timestamp())}",
            incident_date=now,
            description=incident_description,
            affected_individuals=affected_individuals,
            affected_phi_categories=affected_phi_categories,
            risk_level=risk_level,
            notification_required=notification_required,
            notification_deadline=notification_deadline,
            hhs_notification_required=hhs_required,
            media_notification_required=media_required,
        )

        self._breaches.append(assessment)  # type: ignore
        return assessment

    def generate_hipaa_compliance_report(self) -> dict[str, Any]:
        """生成 HIPAA 合规报告"""
        now = datetime.now()

        # 统计
        total_elements = len(self._phi_elements)
        encrypted_elements = sum(1 for e in self._phi_elements.values() if e.encryption_required)
        active_baas = sum(1 for b in self._baas.values() if b.is_valid())
        total_breaches = len(self._breaches)

        return {
            "generated_at": now.isoformat(),
            "framework": "HIPAA + HITECH",
            "elements_registered": total_elements,
            "encryption_coverage": round(encrypted_elements / total_elements * 100, 1) if total_elements > 0 else 0.0,
            "active_baas": active_baas,
            "breach_incidents": total_breaches,
            "security_rule_categories": {
                "administrative": {
                    "policies_and_procedures": "Review required",
                    "risk_assessment": "Periodic assessment needed",
                    "training": "Annual training required",
                },
                "physical": {
                    "facility_access": "Restricted access controls",
                    "workstation_security": "Screen locks and session timeouts",
                    "device_controls": "Media disposal and reuse policies",
                },
                "technical": {
                    "access_control": "Unique user IDs, emergency access",
                    "audit_controls": "Hardware/software/procedural mechanisms",
                    "integrity_controls": "ePHI alteration/destruction verification",
                    "transmission_security": "Encryption in transit",
                },
            },
            "priorities": [
                "Verify encryption of all ePHI at rest and in transit",
                "Review and update all Business Associate Agreements",
                "Conduct periodic risk assessments",
                "Implement breach notification procedures",
                "Ensure audit controls are operational",
            ],
        }

    def get_security_rule_checklist(self) -> list[dict[str, Any]]:
        """获取 HIPAA Security Rule 检查清单"""
        return [
            {"id": "sra-1", "category": "administrative", "control": "Risk Analysis", "required": True},
            {"id": "sra-2", "category": "administrative", "control": "Risk Management", "required": True},
            {"id": "sra-3", "category": "administrative", "control": "Sanction Policy", "required": True},
            {"id": "sra-4", "category": "administrative", "control": "Information System Activity Review", "required": True},
            {"id": "srp-1", "category": "physical", "control": "Facility Access Controls", "required": True},
            {"id": "srp-2", "category": "physical", "control": "Workstation Use", "required": True},
            {"id": "srp-3", "category": "physical", "control": "Device and Media Controls", "required": True},
            {"id": "srt-1", "category": "technical", "control": "Access Control", "required": True},
            {"id": "srt-2", "category": "technical", "control": "Audit Controls", "required": True},
            {"id": "srt-3", "category": "technical", "control": "Integrity", "required": True},
            {"id": "srt-4", "category": "technical", "control": "Person or Entity Authentication", "required": True},
            {"id": "srt-5", "category": "technical", "control": "Transmission Security", "required": True},
        ]


def create_hipaa_engine() -> HIPAAComplianceEngine:
    """创建 HIPAA 合规引擎"""
    return HIPAAComplianceEngine()


__all__ = [
    "HIPAAComplianceEngine",
    "PHIDataElement",
    "PHICategory",
    "HIPAAComplianceStatus",
    "BusinessAssociateAgreement",
    "BreachAssessment",
    "BreachRiskLevel",
    "create_hipaa_engine",
]
