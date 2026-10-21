from __future__ import annotations

from maref.governance.core_pipeline import (
    GovernancePipeline,
    GovernanceRequest,
    Verdict,
)
from maref.governance.policy_pack.registry import PolicyPackRegistry
from maref.governance.policy_pack.schema import PolicyPack


def _allow_pack():
    return PolicyPack.model_validate(
        {
            "pack_format": 1,
            "pack_id": "allow-pack",
            "name": "Allow",
            "version": "1.0.0",
            "jurisdiction": "*",
            "rules": [
                {
                    "rule_id": "allow-everything",
                    "action": "*",
                    "decision": "allow",
                    "regulation_ref": "internal://test",
                }
            ],
        }
    )


def test_pack_allow_cannot_downgrade_core_deny():
    pipeline = GovernancePipeline(
        extension_rules=PolicyPackRegistry([_allow_pack()]).compile_rules()
    )
    result = pipeline.govern(GovernanceRequest(action="file.read", agent_id="a", trust_score=10))
    assert result.verdict is Verdict.DENY
