from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from maref.compliance.hipaa._models import (
    BreachAssessment,
    BreachRiskLevel,
    BusinessAssociateAgreement,
    PHICategory,
    PHIDataElement,
)


class HIPAAComplianceEngine:

    HIPAA_IDENTIFIERS = [
        "name", "address", "dates", "telephone", "fax",
        "email", "ssn", "medical_record_number", "health_plan_number",
        "account_number", "certificate_number", "vehicle_identifier",
        "device_identifier", "url", "ip_address", "biometric_identifier",
        "full_face_photo", "any_other_unique_identifier",
    ]

    def __init__(self):
        self._phi_elements: dict[str, PHIDataElement] = {}
        self._baas: dict[str, BusinessAssociateAgreement] = {}
        self._breaches: list[BreachAssessment] = []
        self._initialize_default_elements()

    def _initialize_default_elements(self) -> None:
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
        self._phi_elements[element.element_id] = element
        return element.element_id

    def classify_data(self, data_categories: list[str]) -> list[PHIDataElement]:
        phi_matches: list[PHIDataElement] = []

        for category in data_categories:
            for element in self._phi_elements.values():
                if element.name.lower() in category.lower() or category.lower() in element.name.lower() or element.category.value in category.lower():
                    phi_matches.append(element)

        return phi_matches

    def check_identifier_presence(self, data_fields: list[str]) -> dict[str, Any]:
        found_identifiers: list[str] = []

        for data_field in data_fields:
            for identifier in self.HIPAA_IDENTIFIERS:
                if identifier in data_field.lower():
                    found_identifiers.append(f"{data_field} -> {identifier}")

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
        element = self._phi_elements.get(phi_element_id)
        if not element:
            return {
                "allowed": False,
                "reason": "PHI element not recognized",
            }

        allowed_purposes = ["treatment", "payment", "healthcare_operations"]

        if purpose not in allowed_purposes:
            if "consent_required" in element.access_controls:
                return {
                    "allowed": False,
                    "reason": f"Purpose '{purpose}' requires patient authorization",
                    "required": "Patient consent or authorization",
                }

        if action == "delete" and purpose not in ("healthcare_operations", "legal_requirement"):
            return {
                "allowed": False,
                "reason": "PHI deletion not permitted for this purpose",
            }

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
        self._baas[baa.baa_id] = baa
        return baa.baa_id

    def verify_baa(self, business_associate: str) -> dict[str, Any]:
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
        now = datetime.now()

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

        notification_deadline = now + timedelta(days=60) if notification_required else None

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

        self._breaches.append(assessment)
        return assessment

    def generate_hipaa_compliance_report(self) -> dict[str, Any]:
        now = datetime.now()

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
    return HIPAAComplianceEngine()
