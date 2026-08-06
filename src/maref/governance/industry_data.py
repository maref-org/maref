"""
MAREF Industry Classification Data

ISIC Rev.4 based industry taxonomy with automation substitution
rate estimates for agent deployment impact assessment.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IndustrySector:
    code: str
    name: str
    description: str
    substitution_rate: float
    risk_factors: list[str] = field(default_factory=list)


# ISIC-based sector taxonomy with estimated substitution rates
# Rates represent approximate percentage of tasks automatable
# by current-generation agent systems. Source: expert estimates
# based on OECD AI task exposure indices (2024-2026).
_INDUSTRY_DATA: dict[str, IndustrySector] = {
    "A": IndustrySector(
        code="A",
        name="Agriculture, Forestry and Fishing",
        description="Crop production, animal farming, forestry, fishing",
        substitution_rate=0.35,
        risk_factors=["rural_employment", "seasonal_labor"],
    ),
    "B": IndustrySector(
        code="B",
        name="Mining and Quarrying",
        description="Extraction of minerals, oil, gas, stone",
        substitution_rate=0.30,
        risk_factors=["occupational_safety", "remote_operations"],
    ),
    "C": IndustrySector(
        code="C",
        name="Manufacturing",
        description="Food, textiles, chemicals, machinery, electronics, vehicles",
        substitution_rate=0.55,
        risk_factors=["mass_layoffs", "supply_chain", "skilled_trade"],
    ),
    "D": IndustrySector(
        code="D",
        name="Electricity, Gas, Steam and Air Conditioning",
        description="Energy generation, transmission, distribution",
        substitution_rate=0.25,
        risk_factors=["critical_infrastructure", "grid_stability"],
    ),
    "E": IndustrySector(
        code="E",
        name="Water Supply, Sewerage, Waste Management",
        description="Water collection, treatment, remediation services",
        substitution_rate=0.30,
        risk_factors=["public_health", "environmental_safety"],
    ),
    "F": IndustrySector(
        code="F",
        name="Construction",
        description="Building construction, civil engineering, demolition",
        substitution_rate=0.20,
        risk_factors=["workplace_safety", "skilled_labor"],
    ),
    "G": IndustrySector(
        code="G",
        name="Wholesale and Retail Trade",
        description="Wholesale, retail, e-commerce, vehicle trade",
        substitution_rate=0.45,
        risk_factors=["retail_employment", "small_business"],
    ),
    "H": IndustrySector(
        code="H",
        name="Transportation and Storage",
        description="Freight, passenger transport, warehousing, postal services",
        substitution_rate=0.50,
        risk_factors=["trucking_employment", "logistics_disruption"],
    ),
    "I": IndustrySector(
        code="I",
        name="Accommodation and Food Service",
        description="Hotels, restaurants, catering, short-term accommodation",
        substitution_rate=0.40,
        risk_factors=["hospitality_employment", "service_quality"],
    ),
    "J": IndustrySector(
        code="J",
        name="Information and Communication",
        description="Publishing, software, telecommunications, IT services",
        substitution_rate=0.40,
        risk_factors=["tech_employment", "data_privacy"],
    ),
    "K": IndustrySector(
        code="K",
        name="Financial and Insurance Activities",
        description="Banking, insurance, asset management, pension funds",
        substitution_rate=0.35,
        risk_factors=["systemic_risk", "consumer_protection", "regulatory"],
    ),
    "L": IndustrySector(
        code="L",
        name="Real Estate Activities",
        description="Property management, real estate agencies, valuation",
        substitution_rate=0.30,
        risk_factors=["housing_market", "tenant_rights"],
    ),
    "M": IndustrySector(
        code="M",
        name="Professional, Scientific and Technical Activities",
        description="Legal, accounting, consulting, R&D, advertising",
        substitution_rate=0.25,
        risk_factors=["professional_services", "liability"],
    ),
    "N": IndustrySector(
        code="N",
        name="Administrative and Support Service",
        description="Office administration, call centers, security, travel agency",
        substitution_rate=0.55,
        risk_factors=["admin_employment", "service_quality"],
    ),
    "O": IndustrySector(
        code="O",
        name="Public Administration and Defence",
        description="Government, defense, public services, social security",
        substitution_rate=0.20,
        risk_factors=["national_security", "public_trust", "democratic_process"],
    ),
    "P": IndustrySector(
        code="P",
        name="Education",
        description="Primary, secondary, higher education, adult education",
        substitution_rate=0.20,
        risk_factors=["educational_quality", "teacher_employment", "student_welfare"],
    ),
    "Q": IndustrySector(
        code="Q",
        name="Human Health and Social Work",
        description="Hospitals, medical practice, residential care, social work",
        substitution_rate=0.15,
        risk_factors=["patient_safety", "medical_liability", "healthcare_access"],
    ),
    "R": IndustrySector(
        code="R",
        name="Arts, Entertainment and Recreation",
        description="Creative arts, libraries, museums, gambling, sports",
        substitution_rate=0.20,
        risk_factors=["creative_employment", "cultural_heritage"],
    ),
    "S": IndustrySector(
        code="S",
        name="Other Service Activities",
        description="Repair services, personal care, religious organizations",
        substitution_rate=0.25,
        risk_factors=["personal_services", "community_impact"],
    ),
}


def get_industry(code: str) -> IndustrySector | None:
    return _INDUSTRY_DATA.get(code.upper())


def list_industries() -> list[IndustrySector]:
    return list(_INDUSTRY_DATA.values())


def get_high_risk_industries(threshold: float = 0.40) -> list[IndustrySector]:
    return [s for s in _INDUSTRY_DATA.values() if s.substitution_rate >= threshold]
