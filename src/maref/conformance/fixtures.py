"""Deterministic demo traces used by the self-tests and the CLI demo.

These fixtures are evidence *producers*: they show what a compliant trace and
a non-compliant trace look like.  They are not a reference runtime.
"""

from __future__ import annotations

import copy
from typing import Any

from .types import event_digest

_HASH_A = "sha256:" + "a" * 64
_HASH_B = "sha256:" + "b" * 64
_KEY = {"type": "ed25519", "key_id": "agent-key-1", "signature": "c2ln"}


def _manifest() -> dict[str, Any]:
    return {
        "type": "manifest",
        "run_id": "demo-run-001",
        "started_at": "2026-11-21T10:00:00Z",
        "allowed_tools": ["crm.read", "email.draft", "payments.transfer"],
        "tool_manifest_hash": _HASH_A,
        "policy_hash": _HASH_B,
        "genesis_hash": "genesis",
    }


def _events() -> list[dict[str, Any]]:
    return [
        {
            "ts": "2026-11-21T10:00:01Z",
            "actor": "agent:support-bot",
            "identity": copy.deepcopy(_KEY),
            "action": "tool_call",
            "tool": "crm.read",
            "params": {"customer_id": 42},
            "data_class": "internal",
            "external": False,
            "risk_level": "low",
            "decision": "allow",
            "policy": {"id": "pol-001", "hash": _HASH_B},
            "tool_manifest_hash": _HASH_A,
        },
        {
            "ts": "2026-11-21T10:00:02Z",
            "actor": "agent:support-bot",
            "identity": copy.deepcopy(_KEY),
            "action": "tool_call",
            "tool": "email.draft",
            "params": {"to": "customer@example.com"},
            "data_class": "internal",
            "external": False,
            "risk_level": "low",
            "decision": "allow",
            "policy": {"id": "pol-002", "hash": _HASH_B},
            "tool_manifest_hash": _HASH_A,
        },
        {
            "ts": "2026-11-21T10:00:03Z",
            "actor": "agent:support-bot",
            "identity": copy.deepcopy(_KEY),
            "action": "tool_call",
            "tool": "crm.read",
            "params": {"scope": "all"},
            "data_class": "internal",
            "external": False,
            "risk_level": "low",
            "decision": "deny",
            "reason": "pii_scope",
            "policy": {"id": "pol-003", "hash": _HASH_B},
            "tool_manifest_hash": _HASH_A,
        },
        {
            "ts": "2026-11-21T10:00:04Z",
            "actor": "agent:finance-bot",
            "identity": copy.deepcopy(_KEY),
            "action": "tool_call",
            "tool": "payments.transfer",
            "params": {"amount": 1200, "currency": "CNY"},
            "data_class": "confidential",
            "external": False,
            "risk_level": "high",
            "decision": "allow",
            "approval": {"approver": "human:alice", "ts": "2026-11-21T10:00:00Z"},
            "policy": {"id": "pol-004", "hash": _HASH_B},
            "tool_manifest_hash": _HASH_A,
        },
        {
            "ts": "2026-11-21T10:00:05Z",
            "actor": "agent:support-bot",
            "identity": copy.deepcopy(_KEY),
            "action": "tool_call",
            "tool": "crm.read",
            "params": {"export": True},
            "data_class": "confidential",
            "external": True,
            "risk_level": "medium",
            "decision": "allow",
            "policy": {"id": "pol-005", "hash": _HASH_B},
            "tool_manifest_hash": _HASH_A,
        },
    ]


def _seal(manifest: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    previous = manifest.get("genesis_hash", "genesis")
    for index, event in enumerate(events, 1):
        event["seq"] = index
        event["prev_hash"] = previous
        event.pop("hash", None)
        event["hash"] = event_digest(event)
        previous = event["hash"]
    return events


def build_trace(compliant: bool = True) -> list[dict[str, Any]]:
    """Return a sealed demo trace.

    The non-compliant variant violates AG-01/02/03/04/07/08/09 while keeping
    the hash chain valid, so that semantic failures are isolated from tamper
    detection.
    """
    manifest = _manifest()
    events = _events()
    if not compliant:
        events[0].pop("policy", None)  # AG-02
        events[1].pop("identity", None)  # AG-01
        events[1]["decision"] = "maybe"  # AG-03
        events[2]["tool"] = "shell.exec"  # AG-04 (allow outside the manifest)
        events[2]["decision"] = "allow"
        events[2].pop("reason", None)
        events[3].pop("approval", None)  # AG-07
        events[4].pop("data_class", None)  # AG-09
        manifest["tool_manifest_hash"] = "sha256:not-a-real-hash"  # AG-08
    return [manifest, *_seal(manifest, events)]


def tamper(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Modify a payload after sealing, without recomputing hashes."""
    mutated = copy.deepcopy(trace)
    mutated[1]["params"] = {"customer_id": 9999}
    return mutated
