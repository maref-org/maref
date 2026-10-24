from __future__ import annotations

from maref.governance.core_pipeline import GovernanceRequest, Verdict
from maref.governance.policy_pack.compiler import compile_registry
from maref.governance.policy_pack.registry import PolicyPackRegistry
from maref.governance.policy_pack.schema import PolicyPack


def _registry(rules):
    pack = PolicyPack.model_validate(
        {
            "pack_format": 1,
            "pack_id": "test-pack",
            "name": "Test",
            "version": "1.0.0",
            "jurisdiction": "eu",
            "rules": rules,
        }
    )
    return PolicyPackRegistry([pack])


def test_compiles_rule_hit():
    registry = _registry(
        [
            {
                "rule_id": "eu-payment-deny",
                "action": "payment.*",
                "decision": "deny",
                "regulation_ref": "internal://test",
                "description": "block payment",
            }
        ]
    )
    rules = compile_registry(registry)
    request = GovernanceRequest(
        action="payment.transfer",
        agent_id="agent-a",
        jurisdiction="eu",
    )
    hit = rules[0][1](request)
    assert hit is not None
    assert hit.verdict is Verdict.DENY
    assert hit.matched_rule == "pack:test-pack:eu-payment-deny"


def test_jurisdiction_filter():
    registry = _registry(
        [
            {
                "rule_id": "eu-payment-deny",
                "action": "payment.*",
                "decision": "deny",
                "regulation_ref": "internal://test",
            }
        ]
    )
    rule = compile_registry(registry)[0][1]
    assert rule(GovernanceRequest(action="payment.transfer", agent_id="a", jurisdiction="eu"))
    assert not rule(GovernanceRequest(action="payment.transfer", agent_id="a", jurisdiction="cn"))
