"""Cross-jurisdiction regulatory scenario set (P2-C).

These scenarios exercise the policy mapper, governance pipeline, evidence
mapping, and Annex IV handoff together.  They are intentionally data-driven
so regulators/operators can add cases without rewriting test logic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maref.compliance.eu_ai_act_v2.technical_docs import TechnicalDocumentation
from maref.compliance.jurisdiction_profile import EnforcementLevel
from maref.compliance.regulatory_policy_mapper import RegulatoryPolicyMapper
from maref.governance.core_pipeline import GovernanceRequest, Verdict
from maref.governance.governed_pipeline import GovernedPipeline
from maref.governance.org_policy import OrganizationPolicy
from maref.governance.regulatory_evidence import RegulatoryEvidenceMapper

POLICY = """
version: 1
epoch: "2026-10-19"
default_decision: deny
organizations:
  acme:
    roles:
      坎:
        allow: ["file.read"]
        deny: ["payment.*", "shell.*"]
        require_approval: ["file.write"]
"""

JURISDICTION_SCENARIOS = [
    ("eu_high_risk_transfer", "payment:transfer", "eu", EnforcementLevel.ENFORCE),
    ("cn_production_deploy", "deploy:production", "cn", EnforcementLevel.ENFORCE),
    ("global_south_low_risk_read", "file.read", "global_south", EnforcementLevel.OBSERVE),
    ("unknown_jurisdiction_fails_closed", "file.read", "unknown", EnforcementLevel.ENFORCE),
]


@pytest.fixture()
def org_policy() -> OrganizationPolicy:
    return OrganizationPolicy.from_dict(
        {
            "version": 1,
            "epoch": "2026-10-19",
            "default_decision": "deny",
            "organizations": {
                "acme": {
                    "roles": {
                        "坎": {
                            "allow": ["file.read"],
                            "deny": ["payment.*", "shell.*"],
                            "require_approval": ["file.write"],
                        }
                    }
                }
            },
        }
    )


@pytest.fixture()
def pipeline(tmp_path: Path, org_policy: OrganizationPolicy) -> GovernedPipeline:
    return GovernedPipeline(
        audit_path=tmp_path / "audit.jsonl",
        hmac_key="test-key",
        org_policy=org_policy,
    )


@pytest.mark.parametrize(
    ("case", "action", "jurisdiction", "expected"),
    JURISDICTION_SCENARIOS,
    ids=[case[0] for case in JURISDICTION_SCENARIOS],
)
def test_jurisdiction_enforcement_matrix(
    case: str,
    action: str,
    jurisdiction: str,
    expected: EnforcementLevel,
):
    decision = RegulatoryPolicyMapper().map_action(action, jurisdiction)
    assert decision.enforcement == expected
    assert decision.blocked is (expected == EnforcementLevel.ENFORCE)
    if expected == EnforcementLevel.ENFORCE and jurisdiction != "unknown":
        assert decision.basis_regulations


def test_eu_high_risk_deny_is_auditable(pipeline: GovernedPipeline):
    result = pipeline.govern(
        GovernanceRequest(
            action="payment.transfer",
            agent_id="agent-eu",
            tenant_id="acme",
            role="坎",
            parameters={"org_id": "acme", "jurisdiction": "eu"},
        )
    )
    assert result.verdict == Verdict.DENY
    assert result.evidence_id

    bundle = RegulatoryEvidenceMapper().map_entries(pipeline.audit.read_all())
    covered = {claim.obligation.obligation_id for claim in bundle.claims if claim.event_count}
    assert {"Art.9", "Art.12", "Art.15"}.issubset(covered)
    assert bundle.evidence_ids == [result.evidence_id]
    assert bundle.merkle_root


def test_human_oversight_escalation_maps_to_art14(pipeline: GovernedPipeline):
    result = pipeline.govern(
        GovernanceRequest(
            action="file.write",
            agent_id="agent-eu",
            tenant_id="acme",
            role="坎",
            parameters={"org_id": "acme"},
        )
    )
    assert result.verdict == Verdict.ASK_USER
    assert result.hitl_event_id
    bundle = RegulatoryEvidenceMapper().map_entries(pipeline.audit.read_all())
    claims = {claim.obligation.obligation_id: claim for claim in bundle.claims}
    assert claims["Art.14"].event_count >= 1


def test_evidence_bundle_hands_off_to_annex_iv(pipeline: GovernedPipeline):
    pipeline.govern(
        GovernanceRequest(
            action="file.read",
            agent_id="agent-eu",
            tenant_id="acme",
            role="坎",
            parameters={"org_id": "acme"},
        )
    )
    bundle = RegulatoryEvidenceMapper().map_entries(pipeline.audit.read_all())
    docs = TechnicalDocumentation(
        system_name="MAREF-Agent",
        version="1.0.0",
        intended_purpose="Governed multi-agent execution",
        deployer="ACME",
    )
    bundle.apply_to_technical_documentation(docs)
    generated = docs.generate()
    assert generated["audit_evidence"]["merkle_root"] == bundle.merkle_root
    assert generated["audit_evidence"]["evidence_ids"] == bundle.evidence_ids
