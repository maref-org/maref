"""Phase 3.5 — regulatory compliance rule library.

Real rule books mapped onto :class:`JurisdictionPolicyRouter`:

1. **GDPR** (Regulation (EU) 2016/679) — cross-border transfers need an
   adequacy decision or SCCs (Art. 44-49); automated decision-making with
   high impact requires human review (Art. 22); personal-data processing
   needs a legal basis (Art. 6).
2. **China CSL** (Cybersecurity Law 2016 / DSL 2021 / Generative-AI interim
   measures 2023) — cross-border data flows need a CAC security
   assessment; generative-AI services need registration; important data
   stays local; security logs retained ≥ 6 months.
3. **Five Eyes** (CISA/Five-Eyes Agentic AI Security Guidance) — agents
   need verifiable identity credentials; delegation depth/capability
   bounded; prompt-injection blocked; high-risk actions need human
   approval; audit logging mandatory.

Every rule carries a ``regulation_ref`` (legal article) so decisions are
auditable back to the underlying law.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from maref.federation.jurisdiction_router import (
    JurisdictionConfig,
    JurisdictionPolicyRouter,
)
from maref.federation.policy import PolicyDecision

# Jurisdiction identifiers used by the router.
JURISDICTION_GDPR = "gdpr"
JURISDICTION_CHINA_CSL = "china_csl"
JURISDICTION_FIVE_EYES = "five_eyes"


@dataclass(frozen=True)
class RegulatoryRule:
    """A single rule taken from a real regulation.

    Attributes:
        rule_id: Unique rule identifier (e.g. ``gdpr-art44-transfer``).
        action: The governed action (matched against the request action).
        decision: The policy decision.
        conditions: Match conditions against the request context.
        priority: Higher wins when several rules match.
        regulation_ref: Legal article reference for auditability.
        description: Human-readable description.
    """

    rule_id: str
    action: str
    decision: PolicyDecision
    conditions: dict[str, Any]
    priority: int = 0
    regulation_ref: str = ""
    description: str = ""


@dataclass(frozen=True)
class JurisdictionSpec:
    """Registration metadata for a regulatory jurisdiction."""

    name: str
    description: str
    regulation_ref: str
    weight: int = 1


# ── GDPR (EU 2016/679) ───────────────────────────────────────────────────

GDPR_SPEC = JurisdictionSpec(
    name=JURISDICTION_GDPR,
    description="EU General Data Protection Regulation 2016/679",
    regulation_ref="Regulation (EU) 2016/679",
    weight=2,
)

GDPR_RULES: list[RegulatoryRule] = [
    RegulatoryRule(
        rule_id="gdpr-art44-transfer-deny",
        action="cross_border_transfer",
        decision=PolicyDecision.DENY,
        conditions={},
        priority=0,
        regulation_ref="Art. 44-49",
        description="Transfer of personal data outside the EU requires an "
        "adequacy decision or appropriate safeguards (SCCs/BTIs).",
    ),
    RegulatoryRule(
        rule_id="gdpr-art44-transfer-allow",
        action="cross_border_transfer",
        decision=PolicyDecision.ALLOW,
        conditions={"transfer_basis": ["adequacy", "scc"]},
        priority=10,
        regulation_ref="Art. 45-46",
        description="Adequacy decision or SCCs in place — transfer allowed.",
    ),
    RegulatoryRule(
        rule_id="gdpr-art22-auto-decision-deny",
        action="automated_decision_making",
        decision=PolicyDecision.DENY,
        conditions={},
        priority=0,
        regulation_ref="Art. 22",
        description="Solely automated decisions with legal/significant "
        "effects require safeguards.",
    ),
    RegulatoryRule(
        rule_id="gdpr-art22-auto-decision-defer",
        action="automated_decision_making",
        decision=PolicyDecision.DEFER,
        conditions={"high_impact": True},
        priority=20,
        regulation_ref="Art. 22(3)",
        description="High-impact automated decision — human review required.",
    ),
    RegulatoryRule(
        rule_id="gdpr-art22-auto-decision-allow",
        action="automated_decision_making",
        decision=PolicyDecision.ALLOW,
        conditions={"high_impact": False},
        priority=10,
        regulation_ref="Art. 22",
        description="Non-high-impact automated decision — permitted.",
    ),
    RegulatoryRule(
        rule_id="gdpr-art6-processing-deny",
        action="personal_data_processing",
        decision=PolicyDecision.DENY,
        conditions={},
        priority=0,
        regulation_ref="Art. 6",
        description="Processing personal data requires a lawful basis.",
    ),
    RegulatoryRule(
        rule_id="gdpr-art6-processing-allow",
        action="personal_data_processing",
        decision=PolicyDecision.ALLOW,
        conditions={"legal_basis": ["consent", "contract", "legitimate_interest"]},
        priority=10,
        regulation_ref="Art. 6(1)",
        description="Lawful basis present — processing allowed.",
    ),
]


# ── China CSL / DSL / Gen-AI measures ────────────────────────────────────

CHINA_SPEC = JurisdictionSpec(
    name=JURISDICTION_CHINA_CSL,
    description="China Cybersecurity Law / Data Security Law / Gen-AI measures",
    regulation_ref="Cybersecurity Law 2016 · DSL 2021 · Gen-AI Measures 2023",
    weight=2,
)

CHINA_CSL_RULES: list[RegulatoryRule] = [
    RegulatoryRule(
        rule_id="csl-art37-transfer-deny",
        action="cross_border_transfer",
        decision=PolicyDecision.DENY,
        conditions={},
        priority=0,
        regulation_ref="Cybersec. Law Art. 37 · DSL Art. 36",
        description="Cross-border transfer of personal/important data "
        "requires a CAC security assessment.",
    ),
    RegulatoryRule(
        rule_id="csl-art37-transfer-allow",
        action="cross_border_transfer",
        decision=PolicyDecision.ALLOW,
        conditions={"cnis_assessment": "approved"},
        priority=10,
        regulation_ref="Cybersec. Law Art. 37",
        description="Security assessment approved by the CAC — transfer allowed.",
    ),
    RegulatoryRule(
        rule_id="csl-genai-registration-deny",
        action="ai_content_generation",
        decision=PolicyDecision.DENY,
        conditions={},
        priority=0,
        regulation_ref="Gen-AI Measures Art. 16-19",
        description="Generative-AI services must be filed/registered with "
        "the authorities.",
    ),
    RegulatoryRule(
        rule_id="csl-genai-registration-allow",
        action="ai_content_generation",
        decision=PolicyDecision.ALLOW,
        conditions={"registration": "filed"},
        priority=10,
        regulation_ref="Gen-AI Measures Art. 19",
        description="Service registration filed — generation allowed.",
    ),
    RegulatoryRule(
        rule_id="dsl-localization-defer",
        action="data_localization",
        decision=PolicyDecision.DEFER,
        conditions={"data_category": "important"},
        priority=10,
        regulation_ref="DSL Art. 38",
        description="Important data must be stored domestically — human review.",
    ),
    RegulatoryRule(
        rule_id="dsl-localization-allow",
        action="data_localization",
        decision=PolicyDecision.ALLOW,
        conditions={"data_category": ["general", "personal"]},
        priority=5,
        regulation_ref="DSL Art. 38",
        description="General/personal data — no localization obligation.",
    ),
    RegulatoryRule(
        rule_id="csl-art21-logging-deny",
        action="audit_log_retention",
        decision=PolicyDecision.DENY,
        conditions={"logging": "disabled"},
        priority=10,
        regulation_ref="Cybersec. Law Art. 21",
        description="Network operators must keep security logs ≥ 6 months.",
    ),
]


# ── Five Eyes Agentic AI Security Guidance ───────────────────────────────

FIVE_EYES_SPEC = JurisdictionSpec(
    name=JURISDICTION_FIVE_EYES,
    description="CISA/Five-Eyes Agentic AI Security Guidance",
    regulation_ref="CISA/Five-Eyes Agentic AI Security Guidance (2025)",
    weight=1,
)

FIVE_EYES_RULES: list[RegulatoryRule] = [
    RegulatoryRule(
        rule_id="fiveeyes-ai1-identity-deny",
        action="agent_register",
        decision=PolicyDecision.DENY,
        conditions={},
        priority=0,
        regulation_ref="Guidance AI-1",
        description="Agents must have verifiable identity credentials.",
    ),
    RegulatoryRule(
        rule_id="fiveeyes-ai1-identity-allow",
        action="agent_register",
        decision=PolicyDecision.ALLOW,
        conditions={"identity_credential": "verified"},
        priority=10,
        regulation_ref="Guidance AI-1",
        description="Identity credential verified — registration allowed.",
    ),
    RegulatoryRule(
        rule_id="fiveeyes-te2-delegation-deny",
        action="delegation",
        decision=PolicyDecision.DENY,
        conditions={},
        priority=0,
        regulation_ref="Guidance TE-2",
        description="Delegated capabilities must not exceed the delegator's.",
    ),
    RegulatoryRule(
        rule_id="fiveeyes-te2-delegation-allow",
        action="delegation",
        decision=PolicyDecision.ALLOW,
        conditions={"chain_depth": [1, 2, 3, 4, 5], "within_capability": True},
        priority=10,
        regulation_ref="Guidance TE-1/TE-2",
        description="Chain depth ≤ 5 and capability preserved — delegation allowed.",
    ),
    RegulatoryRule(
        rule_id="fiveeyes-cap2-injection-deny",
        action="agent_message",
        decision=PolicyDecision.DENY,
        conditions={"injection_risk": "high"},
        priority=10,
        regulation_ref="Guidance CAP-2",
        description="Prompt injection detected — message blocked.",
    ),
    RegulatoryRule(
        rule_id="fiveeyes-cap2-injection-allow",
        action="agent_message",
        decision=PolicyDecision.ALLOW,
        conditions={"injection_risk": ["low", "none"]},
        priority=5,
        regulation_ref="Guidance CAP-2",
        description="Message security scan passed.",
    ),
    RegulatoryRule(
        rule_id="fiveeyes-ho1-high-risk-deny",
        action="high_risk_action",
        decision=PolicyDecision.DENY,
        conditions={},
        priority=0,
        regulation_ref="Guidance HO-1",
        description="High-risk actions require human approval.",
    ),
    RegulatoryRule(
        rule_id="fiveeyes-ho1-high-risk-defer",
        action="high_risk_action",
        decision=PolicyDecision.DEFER,
        conditions={"human_approval": "required"},
        priority=10,
        regulation_ref="Guidance HO-1",
        description="Human approval pending — action deferred to HITL.",
    ),
    RegulatoryRule(
        rule_id="fiveeyes-ho1-high-risk-allow",
        action="high_risk_action",
        decision=PolicyDecision.ALLOW,
        conditions={"human_approval": "granted"},
        priority=20,
        regulation_ref="Guidance HO-1",
        description="Human approval granted — action allowed.",
    ),
    RegulatoryRule(
        rule_id="fiveeyes-al1-logging-deny",
        action="audit_logging",
        decision=PolicyDecision.DENY,
        conditions={"audit_enabled": False},
        priority=10,
        regulation_ref="Guidance AL-1",
        description="Immutable audit trail is mandatory.",
    ),
]


# ── Installation ─────────────────────────────────────────────────────────

JURISDICTION_SPECS: list[JurisdictionSpec] = [GDPR_SPEC, CHINA_SPEC, FIVE_EYES_SPEC]

_RULES_BY_JURISDICTION: dict[str, list[RegulatoryRule]] = {
    JURISDICTION_GDPR: GDPR_RULES,
    JURISDICTION_CHINA_CSL: CHINA_CSL_RULES,
    JURISDICTION_FIVE_EYES: FIVE_EYES_RULES,
}


def install_regulatory_rules(router: JurisdictionPolicyRouter) -> list[str]:
    """Install the GDPR / China CSL / Five-Eyes rule books into a router.

    Registers the three jurisdictions (with regulatory metadata) and adds
    every rule to the matching jurisdiction's policy engine.

    Args:
        router: The router to populate.

    Returns:
        The list of installed rule ids.
    """
    installed: list[str] = []
    for spec in JURISDICTION_SPECS:
        router.register_jurisdiction(
            JurisdictionConfig(
                name=spec.name,
                description=spec.description,
                weight=spec.weight,
                metadata={"regulation_ref": spec.regulation_ref},
            )
        )
        for rule in _RULES_BY_JURISDICTION[spec.name]:
            router.add_jurisdiction_rule(
                jurisdiction=spec.name,
                rule_id=rule.rule_id,
                action=rule.action,
                decision=rule.decision,
                priority=rule.priority,
                conditions=dict(rule.conditions),
                description=f"[{rule.regulation_ref}] {rule.description}",
            )
            installed.append(rule.rule_id)
    return installed


def create_regulatory_router(
    conflict_strategy: Any = None,
) -> JurisdictionPolicyRouter:
    """Build a router pre-loaded with the real regulatory rule books.

    Args:
        conflict_strategy: Optional cross-jurisdiction conflict strategy
            (defaults to the router's MOST_RESTRICTIVE).

    Returns:
        A configured :class:`JurisdictionPolicyRouter`.
    """
    from maref.federation.jurisdiction_router import JurisdictionConflictStrategy

    router = JurisdictionPolicyRouter(
        conflict_strategy=conflict_strategy
        or JurisdictionConflictStrategy.MOST_RESTRICTIVE
    )
    install_regulatory_rules(router)
    return router


__all__ = [
    "JURISDICTION_GDPR",
    "JURISDICTION_CHINA_CSL",
    "JURISDICTION_FIVE_EYES",
    "RegulatoryRule",
    "JurisdictionSpec",
    "GDPR_SPEC",
    "GDPR_RULES",
    "CHINA_SPEC",
    "CHINA_CSL_RULES",
    "FIVE_EYES_SPEC",
    "FIVE_EYES_RULES",
    "JURISDICTION_SPECS",
    "install_regulatory_rules",
    "create_regulatory_router",
]
