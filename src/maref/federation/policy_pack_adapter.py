from __future__ import annotations

from maref.federation.jurisdiction_router import (
    JurisdictionConfig,
    JurisdictionPolicyRouter,
)
from maref.federation.policy import PolicyDecision
from maref.governance.policy_pack.registry import PolicyPackRegistry
from maref.governance.policy_pack.schema import PackDecision, PolicyPack


def _to_policy_decision(decision: PackDecision) -> PolicyDecision:
    return {
        PackDecision.ALLOW: PolicyDecision.ALLOW,
        PackDecision.DENY: PolicyDecision.DENY,
        PackDecision.DEFER: PolicyDecision.DEFER,
    }[decision]


def install_policy_pack(router: JurisdictionPolicyRouter, pack: PolicyPack) -> None:
    if pack.jurisdiction == "*":
        raise ValueError("wildcard policy packs are core-only; give them a jurisdiction")
    router.register_jurisdiction(
        JurisdictionConfig(
            name=pack.jurisdiction,
            description=pack.description,
            weight=1,
            metadata={
                "pack_id": pack.pack_id,
                "pack_version": pack.version,
                "pack_hash": pack.content_hash(),
            },
        )
    )
    for rule in pack.rules:
        if not rule.enabled:
            continue
        router.add_jurisdiction_rule(
            jurisdiction=pack.jurisdiction,
            rule_id=f"{pack.pack_id}:{rule.rule_id}",
            action=rule.action,
            decision=_to_policy_decision(rule.decision),
            priority=rule.priority,
            conditions=dict(rule.conditions),
            description=f"[{rule.regulation_ref}] {rule.description}",
        )


def install_policy_pack_registry(
    router: JurisdictionPolicyRouter, registry: PolicyPackRegistry
) -> None:
    for pack in registry.list():
        install_policy_pack(router, pack)
