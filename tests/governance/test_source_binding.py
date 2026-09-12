"""T-P0-4：授权侧源事件绑定测试。

依据 EAL 授权洗钱（arXiv 2609.01836）：无源事件的权限变更可被伪造
（50.2% 造假率 / 98.6% 执行率）。源绑定使授权可溯源到触发它的有效事件。
"""

from __future__ import annotations

import hashlib

import pytest

from maref.eivl.federated_merkle import FederatedMerkleAggregator
from maref.governance.verifiable_governance_credential import (
    GovernanceCredentialStore,
    VerifiableGovernanceCredential,
)
from maref.signing.signing_key import ReportSigningKey


def _proof(tag: str = "org-1"):
    agg = FederatedMerkleAggregator()
    agg.submit_root(tag, hashlib.sha256(tag.encode()).hexdigest(), tree_size=10)
    agg.submit_root("org-2", hashlib.sha256(b"org-2").hexdigest(), tree_size=20)
    return agg.generate_proof(tag)


def _issue(source_event: str = ""):
    key = ReportSigningKey.generate()
    cred = VerifiableGovernanceCredential.issue(
        subject_did="did:maref:agent-alice",
        issuer_did="did:maref:org-governor",
        scope=["state_machine", "audit"],
        merkle_proof=_proof(),
        signing_key=key,
        source_event=source_event,
    )
    return cred, key


class TestSourceBinding:
    def test_unbound_by_default(self) -> None:
        cred, _ = _issue()
        assert cred.source_event == ""
        assert cred.is_source_bound() is False
        assert cred.has_valid_source_event() is False

    def test_bound_when_provided(self) -> None:
        cred, _ = _issue(source_event="did-revocation:did:maref:agent-alice")
        assert cred.source_event == "did-revocation:did:maref:agent-alice"
        assert cred.is_source_bound() is True
        assert cred.has_valid_source_event() is True

    def test_prefix_check(self) -> None:
        cred, _ = _issue(source_event="event:grant:abc123")
        assert cred.has_valid_source_event(expected_prefix="event:grant:") is True
        assert cred.has_valid_source_event(expected_prefix="did-revocation:") is False

    def test_source_event_bound_into_signature(self) -> None:
        """绑定源事件后，篡改 source_event 应使签名失效。"""
        cred, _ = _issue(source_event="event:grant:abc123")
        assert cred.verify_signature() is True
        cred.source_event = "event:grant:EVIL"
        assert cred.verify_signature() is False

    def test_unbound_signature_backward_compatible(self) -> None:
        """无源事件凭证签名不受 T-P0-4 影响（向后兼容）。"""
        cred, _ = _issue()
        assert cred.verify_signature() is True

    def test_serialization_roundtrip(self) -> None:
        cred, _ = _issue(source_event="event:grant:xyz")
        restored = VerifiableGovernanceCredential.from_dict(cred.to_dict())
        assert restored.source_event == "event:grant:xyz"
        assert restored.verify_signature() is True


class TestStoreSourceBindingPolicy:
    def test_default_accepts_unbound(self) -> None:
        cred, _ = _issue()
        store = GovernanceCredentialStore()
        store.store(cred)
        assert store.get(cred.credential_id) is not None

    def test_strict_rejects_unbound(self) -> None:
        cred, _ = _issue()
        store = GovernanceCredentialStore(require_source_binding=True)
        with pytest.raises(ValueError, match="无源事件绑定"):
            store.store(cred)

    def test_strict_accepts_bound(self) -> None:
        cred, _ = _issue(source_event="event:grant:ok")
        store = GovernanceCredentialStore(require_source_binding=True)
        store.store(cred)
        assert store.get(cred.credential_id) is not None
