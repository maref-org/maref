"""Tests for organization-scoped RBAC policy (P1-A)."""

from __future__ import annotations

from pathlib import Path

import pytest

from maref.governance.core_pipeline import GovernanceRequest, Verdict
from maref.governance.governed_pipeline import GovernedPipeline
from maref.governance.org_policy import OrganizationPolicy

POLICY = """
version: 7
epoch: "2026-10-19"
strict: false
default_decision: deny
organizations:
  acme:
    roles:
      坎:
        allow: ["file.*"]
        deny: ["shell.*"]
        require_approval: ["file.write"]
      震:
        inherits: ["坎"]
        allow: ["build.*"]
"""


@pytest.fixture()
def org_policy(tmp_path: Path) -> OrganizationPolicy:
    path = tmp_path / "org_policy.yaml"
    path.write_text(POLICY, encoding="utf-8")
    return OrganizationPolicy.from_path(path)


def test_role_allow(org_policy: OrganizationPolicy):
    decision = org_policy.evaluate("acme", "坎", "file.read")
    assert decision.decision == "allow"
    assert decision.policy_version == "7"
    assert decision.policy_epoch == "2026-10-19"


def test_role_deny_wins(org_policy: OrganizationPolicy):
    decision = org_policy.evaluate("acme", "坎", "shell.exec")
    assert decision.decision == "deny"
    assert decision.matched_rule == "org_policy:deny"


def test_role_require_approval(org_policy: OrganizationPolicy):
    decision = org_policy.evaluate("acme", "坎", "file.write")
    assert decision.decision == "require_approval"


def test_role_inheritance(org_policy: OrganizationPolicy):
    assert org_policy.evaluate("acme", "震", "file.read").decision == "allow"
    assert org_policy.evaluate("acme", "震", "build.run").decision == "allow"
    assert org_policy.evaluate("acme", "震", "shell.exec").decision == "deny"


def test_unknown_org_is_unmanaged_by_default(org_policy: OrganizationPolicy):
    assert org_policy.evaluate("other", "坎", "file.read").decision == "unmanaged"


def test_strict_unknown_org_fails_closed():
    policy = OrganizationPolicy.from_dict(
        {"strict": True, "organizations": {"acme": {"roles": {}}}}
    )
    assert policy.evaluate("other", "坎", "file.read").decision == "deny"


def test_unknown_role_fails_closed(org_policy: OrganizationPolicy):
    assert org_policy.evaluate("acme", "unknown", "file.read").decision == "deny"


def test_pipeline_enforces_org_deny(tmp_path: Path, org_policy: OrganizationPolicy):
    pipeline = GovernedPipeline(
        audit_path=tmp_path / "audit.jsonl",
        hmac_key="test-key",
        org_policy=org_policy,
    )
    result = pipeline.govern(
        GovernanceRequest(
            action="shell.exec",
            agent_id="agent-1",
            tenant_id="acme",
            role="坎",
            parameters={"org_id": "acme"},
        )
    )
    assert result.verdict == Verdict.DENY
    assert result.matched_rule == "org_policy:deny"
    assert result.evidence_id
    assert pipeline.verify_evidence(result.evidence_id) is True


def test_pipeline_escalates_org_approval(tmp_path: Path, org_policy: OrganizationPolicy):
    pipeline = GovernedPipeline(
        audit_path=tmp_path / "audit.jsonl",
        hmac_key="test-key",
        org_policy=org_policy,
    )
    result = pipeline.govern(
        GovernanceRequest(
            action="file.write",
            agent_id="agent-1",
            tenant_id="acme",
            role="坎",
            parameters={"org_id": "acme"},
        )
    )
    assert result.verdict == Verdict.ASK_USER
    assert result.hitl_event_id


def test_pipeline_skips_unmanaged_org(tmp_path: Path, org_policy: OrganizationPolicy):
    pipeline = GovernedPipeline(
        audit_path=tmp_path / "audit.jsonl",
        hmac_key="test-key",
        org_policy=org_policy,
    )
    result = pipeline.govern(
        GovernanceRequest(
            action="file.read",
            agent_id="agent-1",
            tenant_id="other",
            role="坎",
            parameters={"org_id": "other"},
        )
    )
    assert result.verdict == Verdict.ALLOW
