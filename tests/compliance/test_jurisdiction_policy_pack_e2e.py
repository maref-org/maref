from __future__ import annotations

from maref.governance.core_pipeline import GovernanceRequest, Verdict
from maref.governance.governed_pipeline import GovernedPipeline
from maref.governance.policy_pack.builtin import load_builtin_pack
from maref.governance.policy_pack.registry import PolicyPackRegistry
from maref.governance.trust_boundary import TrustBoundaryManager


def _pipeline(tmp_path, pack_id: str):
    registry = PolicyPackRegistry([load_builtin_pack(pack_id)])
    return GovernedPipeline(
        audit_path=tmp_path / f"{pack_id}.jsonl",
        hmac_key="test-key",
        boundary=TrustBoundaryManager(fail_closed=False),
        policy_packs=registry,
    )


def test_eu_and_cn_differ_for_same_action(tmp_path):
    eu = _pipeline(tmp_path, "eu-ai-act")
    cn = _pipeline(tmp_path, "cn-genai")
    request = GovernanceRequest(
        action="cross_border_transfer",
        agent_id="agent-a",
        parameters={"data_type": "pii"},
    )
    eu_result = eu.govern(
        GovernanceRequest(
            action=request.action,
            agent_id=request.agent_id,
            parameters=request.parameters,
            jurisdiction="eu",
        )
    )
    cn_result = cn.govern(
        GovernanceRequest(
            action=request.action,
            agent_id=request.agent_id,
            parameters=request.parameters,
            jurisdiction="cn",
        )
    )
    assert eu_result.verdict is Verdict.ASK_USER
    assert cn_result.verdict is Verdict.DENY
