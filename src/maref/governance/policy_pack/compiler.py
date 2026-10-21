from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Any

from maref.governance.core_pipeline import (
    ExtensionRuleHit,
    GovernanceRequest,
    Verdict,
)
from maref.governance.policy_pack.registry import PolicyPackRegistry
from maref.governance.policy_pack.schema import PackDecision, PolicyPack, PolicyPackRule


def _jurisdiction(req: GovernanceRequest) -> str:
    return str(req.jurisdiction or (req.parameters or {}).get("jurisdiction") or "")


def _hitl_tier(name: str) -> Any:
    from maref.integration.hitl import HITLTier

    return {
        "P0": HITLTier.P0_RESPONSE,
        "P1": HITLTier.P1_ESCALATE,
        "P2": HITLTier.P2_LOG,
    }[name]


def _context(req: GovernanceRequest) -> dict[str, Any]:
    context = dict(req.parameters or {})
    context.update(
        {
            "action": req.action,
            "role": req.role,
            "tenant_id": req.tenant_id,
            "trust_score": req.trust_score,
            "recursion_depth": req.recursion_depth,
            "jurisdiction": _jurisdiction(req),
        }
    )
    return context


def _rule_matches(pack: PolicyPack, rule: PolicyPackRule, req: GovernanceRequest) -> bool:
    if not rule.enabled:
        return False
    jurisdiction = _jurisdiction(req)
    if pack.jurisdiction != "*" and pack.jurisdiction != jurisdiction:
        return False
    if not fnmatchcase(req.action, rule.action):
        return False
    if rule.roles and req.role not in rule.roles:
        return False
    if rule.tenants and req.tenant_id not in rule.tenants:
        return False
    if rule.min_trust is not None and req.trust_score < rule.min_trust:
        return False
    if rule.max_trust is not None and req.trust_score > rule.max_trust:
        return False
    context = _context(req)
    for key, expected in rule.conditions.items():
        actual = context.get(key)
        if isinstance(expected, list):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def _to_verdict(decision: PackDecision) -> Verdict:
    return {
        PackDecision.ALLOW: Verdict.ALLOW,
        PackDecision.DENY: Verdict.DENY,
        PackDecision.DEFER: Verdict.ASK_USER,
    }[decision]


def compile_registry(
    registry: PolicyPackRegistry,
) -> list[tuple[int, Any]]:
    compiled: list[tuple[int, Any]] = []
    for pack in registry.list():
        for rule in pack.rules:
            def evaluator(
                req: GovernanceRequest,
                *,
                _pack: PolicyPack = pack,
                _rule: PolicyPackRule = rule,
            ) -> ExtensionRuleHit | None:
                if not _rule_matches(_pack, _rule, req):
                    return None
                verdict = _to_verdict(_rule.decision)
                return ExtensionRuleHit(
                    verdict=verdict,
                    reason=f"[{_pack.pack_id}/{_rule.rule_id}] {_rule.description or _rule.action}",
                    matched_rule=f"pack:{_pack.pack_id}:{_rule.rule_id}",
                    policy_pack_id=_pack.pack_id,
                    policy_pack_version=_pack.version,
                    policy_pack_hash=_pack.content_hash(),
                    hitl_tier=(
                        _hitl_tier(_rule.hitl_tier)
                        if verdict is Verdict.ASK_USER
                        else None
                    ),
                )

            compiled.append((rule.priority, evaluator))
    return compiled
