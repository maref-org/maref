from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class PCIRequirement(Enum):
    R1 = "r1"
    R2 = "r2"
    R3 = "r3"
    R4 = "r4"
    R5 = "r5"
    R6 = "r6"
    R7 = "r7"
    R8 = "r8"
    R9 = "r9"
    R10 = "r10"
    R11 = "r11"
    R12 = "r12"


class PCISensitivityLevel(Enum):
    PAN = "pan"
    CARDHOLDER_NAME = "name"
    EXPIRATION_DATE = "expiry"
    SERVICE_CODE = "service_code"
    SENSITIVE_AUTH = "sensitive_auth"


class PCIComplianceStatus(Enum):
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    COMPENSATING_CONTROL = "compensating_control"
    NOT_APPLICABLE = "not_applicable"


class SAQType(Enum):
    SAQ_A = "saq_a"
    SAQ_A_EP = "saq_a_ep"
    SAQ_B = "saq_b"
    SAQ_B_IP = "saq_b_ip"
    SAQ_C = "saq_c"
    SAQ_C_VT = "saq_c_vt"
    SAQ_D = "saq_d"


@dataclass
class CardholderDataEnvironment:
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
    level: int
    annual_transactions: str
    assessment_required: str
    saq_allowed: bool
    external_scan_required: bool
    onsite_audit_required: bool
