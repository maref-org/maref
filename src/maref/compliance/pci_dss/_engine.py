from __future__ import annotations

from datetime import datetime
from typing import Any

from maref.compliance.pci_dss._models import (
    CardholderDataEnvironment,
    MerchantLevel,
    PCIComplianceStatus,
    PCIControlTest,
    PCIRequirement,
    SAQType,
)


class PCIComplianceEngine:
    PCI_VERSION = "4.0"

    MERCHANT_LEVELS = {
        1: MerchantLevel(1, ">6M transactions/year", "Annual ROC by QSA", False, True, True),
        2: MerchantLevel(2, "1M-6M transactions/year", "Annual SAQ + ASV scan", True, True, False),
        3: MerchantLevel(3, "20K-1M e-commerce transactions/year", "Annual SAQ + ASV scan", True, True, False),
        4: MerchantLevel(4, "<20K e-commerce transactions/year", "Annual SAQ (if required by acquirer)", True, False, False),
    }

    def __init__(self):
        self._cdes: dict[str, CardholderDataEnvironment] = {}
        self._tests: dict[str, PCIControlTest] = {}
        self._requirement_status: dict[str, PCIComplianceStatus] = {}
        self._initialize_requirements()

    def _initialize_requirements(self) -> None:
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
        self._cdes[cde.cde_id] = cde
        return cde.cde_id

    def scope_environment(
        self,
        systems: list[str],
        data_flows: list[str],
        stores_card_data: bool,
        processes_payments: bool,
    ) -> CardholderDataEnvironment:
        if not stores_card_data and not processes_payments:
            saq_type = SAQType.SAQ_A
        elif stores_card_data:
            saq_type = SAQType.SAQ_D
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
        pci_minimum = {
            "AES": 128,
            "RSA": 2048,
            "ECC": 256,
            "TDES": 112,
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
            "status": "Meets PCI DSS cryptographic requirements" if is_compliant else f"Below minimum {min_length}-bit requirement",
        }

    def test_requirement(
        self,
        requirement: PCIRequirement,
        test_description: str,
        test_procedure: str,
        evidence: list[str],
    ) -> PCIControlTest:
        has_evidence = len(evidence) > 0
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
            remediation_plan=None if status == PCIComplianceStatus.COMPLIANT else "Collect required evidence",
        )

        self._tests[test.test_id] = test
        self._requirement_status[requirement.value] = status
        return test

    def _check_compensating_controls(self, requirement: PCIRequirement) -> bool:
        return any(requirement.value in cde.compensating_controls for cde in self._cdes.values())

    def get_roc_summary(self) -> dict[str, Any]:
        total = len(self._requirement_status)
        compliant = sum(1 for s in self._requirement_status.values() if s == PCIComplianceStatus.COMPLIANT)
        compensating = sum(1 for s in self._requirement_status.values() if s == PCIComplianceStatus.COMPENSATING_CONTROL)
        non_compliant = sum(1 for s in self._requirement_status.values() if s == PCIComplianceStatus.NON_COMPLIANT)

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
        recommendations = []

        for req_value, status in self._requirement_status.items():
            if status == PCIComplianceStatus.NON_COMPLIANT:
                req = PCIRequirement(req_value)
                recommendations.append(f"Address non-compliance for Requirement {req.value.upper()}: {self._requirement_map.get(req, '')}")

        return recommendations if recommendations else ["All requirements are met or have compensating controls"]

    def generate_saq(self, cde_id: str) -> dict[str, Any]:
        cde = self._cdes.get(cde_id)
        if not cde:
            raise ValueError(f"CDE not found: {cde_id}")

        applicable_requirements = self._get_applicable_requirements(cde.saq_type)

        questions = []
        for req in applicable_requirements:
            questions.append({
                "requirement": req.value,
                "description": self._requirement_map[req],
                "status": self._requirement_status[req.value].value,
            })

        return {
            "saq_type": cde.saq_type.value,
            "cde_id": cde_id,
            "generated_at": datetime.now().isoformat(),
            "applicable_requirements": len(applicable_requirements),
            "questions": questions,
        }

    def _get_applicable_requirements(self, saq_type: SAQType) -> list[PCIRequirement]:
        if saq_type == SAQType.SAQ_A:
            return [PCIRequirement.R1, PCIRequirement.R3, PCIRequirement.R4, PCIRequirement.R8]
        elif saq_type == SAQType.SAQ_D:
            return list(PCIRequirement)
        else:
            return list(PCIRequirement)

    def get_merchant_level_info(self, annual_tx_count: int) -> dict[str, Any]:
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

    def validate_segment_network(self, cde_ips: list[str], non_cde_ips: list[str]) -> dict[str, Any]:
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
    return PCIComplianceEngine()
