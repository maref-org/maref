from __future__ import annotations

import pytest
from pydantic import ValidationError

from maref.governance.policy_pack.schema import (
    PackDecision,
    PolicyPack,
    PolicyPackRule,
)


def _rule(**overrides):
    data = {
        "rule_id": "eu-payment-deny",
        "action": "payment.*",
        "decision": "deny",
        "priority": 100,
        "regulation_ref": "EU AI Act Art. 6",
        "description": "High-risk payment transfer",
    }
    data.update(overrides)
    return data


def _pack(**overrides):
    data = {
        "pack_format": 1,
        "pack_id": "eu-ai-act",
        "name": "EU AI Act",
        "version": "1.0.0",
        "jurisdiction": "eu",
        "rules": [_rule()],
    }
    data.update(overrides)
    return data


def test_valid_pack_round_trip():
    pack = PolicyPack.model_validate(_pack())
    assert pack.pack_id == "eu-ai-act"
    assert pack.rules[0].decision is PackDecision.DENY
    assert len(pack.content_hash()) == 64


def test_duplicate_rule_id_rejected():
    with pytest.raises(ValidationError):
        PolicyPack.model_validate(_pack(rules=[_rule(), _rule(description="duplicate")]))


def test_deny_requires_regulation_ref():
    with pytest.raises(ValidationError):
        PolicyPack.model_validate(_pack(rules=[_rule(regulation_ref="")]))


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        PolicyPack.model_validate(_pack(entrypoint="evil.module"))


def test_invalid_decision_rejected():
    with pytest.raises(ValidationError):
        PolicyPack.model_validate(_pack(rules=[_rule(decision="allow_all")]))


def test_pack_hash_is_stable():
    first = PolicyPack.model_validate(_pack()).content_hash()
    second = PolicyPack.model_validate(_pack()).content_hash()
    assert first == second


def test_core_compatibility_bounds():
    pack = PolicyPack.model_validate(_pack())
    assert pack.is_compatible("0.54.3")
    assert not pack.is_compatible("0.56.0")


def test_nested_condition_rejected():
    with pytest.raises(ValidationError):
        PolicyPackRule.model_validate(_rule(conditions={"meta": {"nested": True}}))
