"""
PCI DSS 金融合规模块

Payment Card Industry Data Security Standard (PCI DSS) v4.0 合规支持。
保护支付卡数据和金融交易安全。

关键要求:
- Build and Maintain Secure Network
- Protect Cardholder Data
- Maintain Vulnerability Management Program
- Implement Strong Access Control Measures
- Regularly Monitor and Test Networks
- Maintain Information Security Policy
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PCIRequirement(Enum):
    """PCI DSS 要求（12大核心要求）"""

    R1 = "r1"  # Install and maintain network security controls
    R2 = "r2"  # Apply secure configurations to all system components
    R3 = "r3"  # Protect stored account data
    R4 = "r4"  # Protect cardholder data with strong cryptography during transmission
    R5 = "r5"  # Protect all systems and networks from malicious software
    R6 = "r6"  # Develop and maintain secure systems and software
    R7 = "r7"  # Restrict access to system components and cardholder data by business need to know
    R8 = "r8"  # Identify users and authenticate access to system components
    R9 = "r9"  # Restrict physical access to cardholder data
    R10 = "r10"  # Log and monitor all access to system components and cardholder data
    R11 = "r11"  # Test security of systems and networks regularly
    R12 = "r12"  # Support information security with organizational policies and programs


class PCISensitivityLevel(Enum):
    """卡数据敏感度"""

    PAN = "pan"  # Primary Account Number
    CARDHOLDER_NAME = "name"  # 持卡人姓名
    EXPIRATION_DATE = "expiry"  # 过期日期
    SERVICE_CODE = "service_code"  # 服务码
    SENSITIVE_AUTH = "sensitive_auth"  # 敏感认证数据 (CVV/CVC/磁条/芯片)


class PCIComplianceStatus(Enum):
    """PCI 合规状态"""

    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    COMPENSATING_CONTROL = "compensating_control"
    NOT_APPLICABLE = "not_applicable"


class SAQType(Enum):
    """自评问卷类型"""

    SAQ_A = "saq_a"  # 完全外包，无电子存储
    SAQ_A_EP = "saq_a_ep"  # 部分外包的电子商务
    SAQ_B = "saq_b"  # 仅印表机终端
    SAQ_B_IP = "saq_b_ip"  # 仅独立IP终端
    SAQ_C = "saq_c"  # 连接到互联网的支付应用
    SAQ_C_VT = "saq_c_vt"  # 仅虚拟终端
    SAQ_D = "saq_d"  # 所有其他商户 + 服务提供商


@dataclass
class CardholderDataEnvironment:
    """持卡数据环境 (CDE)"""

    cde_id: str
    description: str
    scoped_systems: list[str]
    data_flows: list[str]
    saq_type: SAQType
    last_assessment: datetime | None = None
    compliance_status: PCIComplianceStatus = PCIComplianceStatus.NOT_APPLICABLE
    compensating_controls: list[str] = field(default_factory=list)


@dataclass
class PCIControlTest:
    """PCI 控制测试"""

    test_id: str
    requirement: PCIRequirement
    description: str
    test_procedure: str
    result: PCIComplianceStatus
    evidence: list[str] = field(default_factory=list)
    tested_at: datetime | None = None
    tested_by: str | None = None
    findings: list[str] = field(default_factory=list)
    remediation_plan: str | None = None


@dataclass
class MerchantLevel:
    """商户等级"""

    level: int
    annual_transactions: str
    assessment_required: str
    saq_allowed: bool
    external_scan_required: bool
    onsite_audit_required: bool


class PCIComplianceEngine:
    """
    PCI DSS 合规引擎

    管理支付卡数据安全合规检查和控制。
    """

    # PCI DSS 版本
    PCI_VERSION = "4.0"

    # 商户等级定义
    MERCHANT_LEVELS = {
        1: MerchantLevel(1, ">6M transactions/year", "Annual ROC by QSA", False, True, True),
        2: MerchantLevel(2, "1M-6M transactions/year", "Annual SAQ + ASV scan", True, True, False),
        3: MerchantLevel(
            3, "20K-1M e-commerce transactions/year", "Annual SAQ + ASV scan", True, True, False
        ),
        4: MerchantLevel(
            4,
            "<20K e-commerce transactions/year",
            "Annual SAQ (if required by acquirer)",
            True,
            False,
            False,
        ),
    }

    def __init__(self):
        self._cdes: dict[str, CardholderDataEnvironment] = {}
        self._tests: dict[str, PCIControlTest] = {}
        self._requirement_status: dict[str, PCIComplianceStatus] = {}

        self._initialize_requirements()

    def _initialize_requirements(self) -> None:
        """初始化 PCI DSS 要求"""
        self._requirement_map = {
            PCIRequirement.R1: "Install and Maintain Network Security Controls",
            PCIRequirement.R2: "Apply Secure Configurations to All System Components",
            PCIRequirement.R3: "Protect Stored Account Data",
            PCIRequirement.R4: "Protect Cardholder Data with Strong Cryptography During Transmission",
            PCIRequirement.R5: "Protect All Systems and Networks from Malicious Software",
            PCIRequirement.R6: "Develop and Maintain Secure Systems and Software",
            PCIRequirement.R7: "Restrict Access to System Components and Cardholder Data",
            PCIRequirement.R8: "Identify Users and Authenticate Access to System Components",
            PCIRequirement.R9: "Restrict Physical Access to Cardholder Data",
            PCIRequirement.R10: "Log and Monitor All Access to System Components and Cardholder Data",
            PCIRequirement.R11: "Test Security of Systems and Networks Regularly",
            PCIRequirement.R12: "Support Information Security with Organizational Policies and Programs",
        }

        for req in PCIRequirement:
            self._requirement_status[req.value] = PCIComplianceStatus.NOT_APPLICABLE

    def register_cde(self, cde: CardholderDataEnvironment) -> str:
        """注册持卡数据环境"""
        self._cdes[cde.cde_id] = cde
        return cde.cde_id

    def scope_environment(
        self,
        systems: list[str],
        data_flows: list[str],
        stores_card_data: bool,
        processes_payments: bool,
    ) -> CardholderDataEnvironment:
        """
        确定 CDE 范围和 SAQ 类型

        Args:
            systems: 系统列表
            data_flows: 数据流列表
            stores_card_data: 是否存储卡数据
            processes_payments: 是否处理支付

        Returns:
            CDE 定义
        """
        # 确定 SAQ 类型
        if not stores_card_data and not processes_payments:
            saq_type = SAQType.SAQ_A
        elif stores_card_data:
            saq_type = SAQType.SAQ_D  # 最严格要求
        elif processes_payments:
            saq_type = SAQType.SAQ_C
        else:
            saq_type = SAQType.SAQ_D

        cde = CardholderDataEnvironment(
            cde_id=f"cde-{int(datetime.now().timestamp())}",
            description="Auto-scoped CDE",
            scoped_systems=systems,
            data_flows=data_flows,
            saq_type=saq_type,
        )

        self._cdes[cde.cde_id] = cde
        return cde

    def mask_pan(self, pan: str) -> dict[str, Any]:
        """
        PAN 掩码处理 (PCI DSS Requirement 3.3)

        显示规则: 最多前6位和后4位
        """
        if len(pan) < 10:
            return {"masked": True, "display": "****", "error": "Invalid PAN length"}

        first_six = pan[:6]
        last_four = pan[-4:]
        masked = f"{first_six}******{last_four}"

        return {
            "masked": True,
            "display": masked,
            "first_six": first_six,
            "last_four": last_four,
            "compliance": "Meets PCI DSS Requirement 3.3 for PAN masking",
        }

    def validate_encryption_strength(self, algorithm: str, key_length: int) -> dict[str, Any]:
        """
        验证加密强度是否符合 PCI DSS

        Args:
            algorithm: 加密算法
            key_length: 密钥长度（位）

        Returns:
            验证结果
        """
        pci_minimum = {
            "AES": 128,
            "RSA": 2048,
            "ECC": 256,  # 等效RSA 3072+
            "TDES": 112,  # 有效密钥长度
        }

        min_length = pci_minimum.get(algorithm.upper())
        if min_length is None:
            return {
                "compliant": False,
                "reason": f"Algorithm {algorithm} not recognized for PCI DSS",
                "recommendation": "Use AES-128+, RSA-2048+, or ECC-256+",
            }

        is_compliant = key_length >= min_length

        return {
            "compliant": is_compliant,
            "algorithm": algorithm.upper(),
            "key_length": key_length,
            "minimum_required": min_length,
            "status": "Meets PCI DSS cryptographic requirements"
            if is_compliant
            else f"Below minimum {min_length}-bit requirement",
        }

    def test_requirement(
        self,
        requirement: PCIRequirement,
        test_description: str,
        test_procedure: str,
        evidence: list[str],
    ) -> PCIControlTest:
        """
        执行 PCI 要求测试

        Args:
            requirement: PCI 要求
            test_description: 测试描述
            test_procedure: 测试步骤
            evidence: 证据列表

        Returns:
            测试结果
        """
        # 检查是否有证据
        has_evidence = len(evidence) > 0

        # 检查是否有补偿控制
        compensating = self._check_compensating_controls(requirement)

        if has_evidence:
            status = PCIComplianceStatus.COMPLIANT
        elif compensating:
            status = PCIComplianceStatus.COMPENSATING_CONTROL
        else:
            status = PCIComplianceStatus.NON_COMPLIANT

        test = PCIControlTest(
            test_id=f"pci-test-{int(datetime.now().timestamp())}",
            requirement=requirement,
            description=test_description,
            test_procedure=test_procedure,
            result=status,
            evidence=evidence,
            tested_at=datetime.now(),
            findings=[] if status == PCIComplianceStatus.COMPLIANT else ["Insufficient evidence"],
            remediation_plan=None
            if status == PCIComplianceStatus.COMPLIANT
            else "Collect required evidence",
        )

        self._tests[test.test_id] = test
        self._requirement_status[requirement.value] = status

        return test

    def _check_compensating_controls(self, requirement: PCIRequirement) -> bool:
        """检查是否有补偿控制"""
        return any(requirement.value in cde.compensating_controls for cde in self._cdes.values())

    def get_roc_summary(self) -> dict[str, Any]:
        """
        生成 ROC (Report on Compliance) 摘要

        Returns:
            ROC 摘要
        """
        total = len(self._requirement_status)
        compliant = sum(
            1 for s in self._requirement_status.values() if s == PCIComplianceStatus.COMPLIANT
        )
        compensating = sum(
            1
            for s in self._requirement_status.values()
            if s == PCIComplianceStatus.COMPENSATING_CONTROL
        )
        non_compliant = sum(
            1 for s in self._requirement_status.values() if s == PCIComplianceStatus.NON_COMPLIANT
        )

        compliance_rate = (compliant + compensating) / total * 100 if total > 0 else 0.0

        return {
            "generated_at": datetime.now().isoformat(),
            "pci_version": self.PCI_VERSION,
            "assessment_type": "Self-Assessment",
            "requirements_tested": total,
            "compliant": compliant,
            "compensating_controls": compensating,
            "non_compliant": non_compliant,
            "compliance_rate": round(compliance_rate, 1),
            "overall_status": "Compliant" if compliance_rate >= 100 else "Non-Compliant",
            "recommendations": self._generate_recommendations(),
        }

    def _generate_recommendations(self) -> list[str]:
        """生成 PCI DSS 建议"""
        recommendations = []

        for req_value, status in self._requirement_status.items():
            if status == PCIComplianceStatus.NON_COMPLIANT:
                req = PCIRequirement(req_value)
                recommendations.append(
                    f"Address non-compliance for Requirement {req.value.upper()}: {self._requirement_map.get(req, '')}"
                )

        return (
            recommendations
            if recommendations
            else ["All requirements are met or have compensating controls"]
        )

    def generate_saq(self, cde_id: str) -> dict[str, Any]:
        """
        生成 SAQ (自评问卷)

        Args:
            cde_id: CDE ID

        Returns:
            SAQ 文档
        """
        cde = self._cdes.get(cde_id)
        if not cde:
            raise ValueError(f"CDE not found: {cde_id}")

        # 根据 SAQ 类型获取适用的问题
        applicable_requirements = self._get_applicable_requirements(cde.saq_type)

        questions = []
        for req in applicable_requirements:
            questions.append(
                {
                    "requirement": req.value,
                    "description": self._requirement_map[req],
                    "status": self._requirement_status[req.value].value,
                }
            )

        return {
            "saq_type": cde.saq_type.value,
            "cde_id": cde_id,
            "generated_at": datetime.now().isoformat(),
            "applicable_requirements": len(applicable_requirements),
            "questions": questions,
        }

    def _get_applicable_requirements(self, saq_type: SAQType) -> list[PCIRequirement]:
        """根据 SAQ 类型获取适用的要求"""
        if saq_type == SAQType.SAQ_A:
            return [PCIRequirement.R1, PCIRequirement.R3, PCIRequirement.R4, PCIRequirement.R8]
        elif saq_type == SAQType.SAQ_D:
            return list(PCIRequirement)  # 所有要求
        else:
            return list(PCIRequirement)  # 默认全部

    def get_merchant_level_info(self, annual_tx_count: int) -> dict[str, Any]:
        """
        根据年交易量确定商户等级

        Args:
            annual_tx_count: 年交易笔数

        Returns:
            商户等级信息
        """
        if annual_tx_count > 6000000:
            level_info = self.MERCHANT_LEVELS[1]
        elif annual_tx_count > 1000000:
            level_info = self.MERCHANT_LEVELS[2]
        elif annual_tx_count > 20000:
            level_info = self.MERCHANT_LEVELS[3]
        else:
            level_info = self.MERCHANT_LEVELS[4]

        return {
            "merchant_level": level_info.level,
            "annual_transaction_range": level_info.annual_transactions,
            "assessment_required": level_info.assessment_required,
            "external_scan_required": level_info.external_scan_required,
            "onsite_audit_required": level_info.onsite_audit_required,
        }

    def validate_segment_network(
        self, cde_ips: list[str], non_cde_ips: list[str]
    ) -> dict[str, Any]:
        """
        验证 CDE 和非 CDE 之间的网络分段

        PCI DSS 要求1: 网络安全控制
        """
        # 检查是否有重叠IP（表示分段不足）
        cde_set = set(cde_ips)
        non_cde_set = set(non_cde_ips)
        overlap = cde_set & non_cde_set

        is_segmented = len(overlap) == 0

        return {
            "segmented": is_segmented,
            "cde_count": len(cde_ips),
            "non_cde_count": len(non_cde_ips),
            "overlapping_ips": list(overlap),
            "compliant": is_segmented,
            "recommendation": None if is_segmented else "Isolate CDE systems from non-CDE systems",
        }


def create_pci_engine() -> PCIComplianceEngine:
    """创建 PCI DSS 合规引擎"""
    return PCIComplianceEngine()


__all__ = [
    "PCIComplianceEngine",
    "CardholderDataEnvironment",
    "PCIControlTest",
    "PCIRequirement",
    "PCIComplianceStatus",
    "SAQType",
    "create_pci_engine",
]
