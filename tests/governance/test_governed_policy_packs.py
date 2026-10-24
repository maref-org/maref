from __future__ import annotations

import json
from pathlib import Path

from maref.governance.core_pipeline import GovernanceRequest, Verdict
from maref.governance.governed_pipeline import GovernedPipeline
from maref.governance.policy_pack.registry import PolicyPackRegistry
from maref.governance.policy_pack.schema import PolicyPack
from maref.governance.trust_boundary import TrustBoundaryManager


def _eu_pack():
    return PolicyPack.model_validate(
        {
            "pack_format": 1,
            "pack_id": "eu-ai-act",
            "name": "EU AI Act",
            "version": "1.0.0",
            "jurisdiction": "eu",
            "rules": [
                {
                    "rule_id": "eu-payment-deny",
                    "action": "payment.*",
                    "decision": "deny",
                    "regulation_ref": "EU AI Act Art. 6",
                    "description": "high-risk payment",
                }
            ],
        }
    )


def test_governed_pipeline_applies_pack(tmp_path: Path):
    registry = PolicyPackRegistry([_eu_pack()])
    pipeline = GovernedPipeline(
        audit_path=tmp_path / "audit.jsonl",
        hmac_key="test-key",
        boundary=TrustBoundaryManager(fail_closed=False),
        policy_packs=registry,
    )
    result = pipeline.govern(
        GovernanceRequest(
            action="payment.transfer",
            agent_id="agent-a",
            jurisdiction="eu",
        )
    )
    assert result.verdict is Verdict.DENY
    assert result.policy_pack_id == "eu-ai-act"
    assert result.matched_rule == "pack:eu-ai-act:eu-payment-deny"


def test_governed_pipeline_audit_contains_pack_metadata(tmp_path: Path):
    registry = PolicyPackRegistry([_eu_pack()])
    audit_path = tmp_path / "audit.jsonl"
    pipeline = GovernedPipeline(
        audit_path=audit_path,
        hmac_key="test-key",
        boundary=TrustBoundaryManager(fail_closed=False),
        policy_packs=registry,
    )
    pipeline.govern(
        GovernanceRequest(
            action="payment.transfer",
            agent_id="agent-a",
            jurisdiction="eu",
        )
    )
    entry = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[-1])
    metadata = entry["metadata"]
    assert metadata["policy_pack_id"] == "eu-ai-act"
    assert metadata["policy_pack_version"] == "1.0.0"
    assert len(metadata["policy_pack_hash"]) == 64


def test_no_packs_keeps_existing_behavior(tmp_path: Path):
    pipeline = GovernedPipeline(audit_path=tmp_path / "audit.jsonl", hmac_key="test-key")
    result = pipeline.govern(GovernanceRequest(action="file.read", agent_id="a"))
    assert result.verdict is Verdict.ALLOW
    assert result.policy_pack_id == ""
