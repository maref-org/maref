from maref.federation.jurisdiction_router import JurisdictionPolicyRouter
from maref.federation.policy import PolicyDecision, PolicyScope
from maref.federation.policy_pack_adapter import install_policy_pack
from maref.governance.policy_pack.builtin import load_builtin_pack
from maref.governance.policy_pack.schema import PolicyPack


def test_install_eu_pack_into_router():
    router = JurisdictionPolicyRouter()
    pack = load_builtin_pack("eu-ai-act")
    install_policy_pack(router, pack)
    result = router.route_action("qian", "payment.transfer", {})
    assert result.final_decision is PolicyDecision.DENY


def test_disabled_rule_is_not_installed():
    pack = PolicyPack.model_validate(
        {
            "pack_format": 1,
            "pack_id": "disabled-rule",
            "name": "Disabled rule",
            "version": "1.0.0",
            "jurisdiction": "eu",
            "rules": [
                {
                    "rule_id": "disabled-deny",
                    "action": "payment.*",
                    "decision": "deny",
                    "regulation_ref": "internal://test",
                    "enabled": False,
                }
            ],
        }
    )
    router = JurisdictionPolicyRouter()
    install_policy_pack(router, pack)
    engine = router.get_jurisdiction("eu").policy_engine
    assert engine is not None
    assert engine.list_rules(PolicyScope.LOCAL) == []


def test_federation_and_core_agree(tmp_path):
    from maref.governance.core_pipeline import GovernanceRequest, Verdict
    from maref.governance.governed_pipeline import GovernedPipeline
    from maref.governance.policy_pack.registry import PolicyPackRegistry
    from maref.governance.trust_boundary import TrustBoundaryManager

    pack = load_builtin_pack("eu-ai-act")
    router = JurisdictionPolicyRouter()
    install_policy_pack(router, pack)
    federation = router.route_action("qian", "payment.transfer", {})

    pipeline = GovernedPipeline(
        policy_packs=PolicyPackRegistry([pack]),
        hmac_key="test-key",
        audit_path=tmp_path / "audit.jsonl",
        boundary=TrustBoundaryManager(fail_closed=False),
    )
    core = pipeline.govern(
        GovernanceRequest(
            action="payment.transfer",
            agent_id="a",
            jurisdiction="eu",
        )
    )
    assert federation.final_decision is PolicyDecision.DENY
    assert core.verdict is Verdict.DENY
