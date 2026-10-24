from __future__ import annotations

import pytest

from maref.governance.policy_pack.registry import PolicyPackRegistry
from maref.governance.policy_pack.schema import PolicyPack


def _pack(pack_id="eu", jurisdiction="eu", version="1.0.0"):
    return PolicyPack.model_validate(
        {
            "pack_format": 1,
            "pack_id": pack_id,
            "name": pack_id,
            "version": version,
            "jurisdiction": jurisdiction,
            "rules": [
                {
                    "rule_id": f"{pack_id}-deny",
                    "action": "payment.*",
                    "decision": "deny",
                    "regulation_ref": "internal://test",
                }
            ],
        }
    )


def test_register_and_list():
    registry = PolicyPackRegistry([_pack()])
    assert registry.get("eu").pack_id == "eu"
    assert len(registry.list()) == 1


def test_duplicate_pack_rejected():
    registry = PolicyPackRegistry([_pack()])
    with pytest.raises(ValueError):
        registry.register(_pack())


def test_active_for_jurisdiction():
    registry = PolicyPackRegistry([_pack(), _pack("global", "*")])
    active = registry.active_for("eu")
    assert {pack.pack_id for pack in active} == {"eu", "global"}
    assert {pack.pack_id for pack in registry.active_for("cn")} == {"global"}
