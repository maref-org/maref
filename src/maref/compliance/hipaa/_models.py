from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PHICategory(Enum):
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
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PARTIAL = "partial"
    EXEMPT = "exempt"


class SecurityRuleCategory(Enum):
    ADMINISTRATIVE = "administrative"
    PHYSICAL = "physical"
    TECHNICAL = "technical"


class BreachRiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class PHIDataElement:
    element_id: str
    name: str
    category: PHICategory
    is_direct_identifier: bool
    encryption_required: bool = True
    access_controls: list[str] = field(default_factory=list)
    retention_period_days: int = 2190
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BusinessAssociateAgreement:
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
