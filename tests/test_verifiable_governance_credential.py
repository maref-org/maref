"""Tests for VerifiableGovernanceCredential."""

from __future__ import annotations

import hashlib

import pytest

from maref.eivl.federated_merkle import FederatedMerkleAggregator, FederatedProof
from maref.governance.verifiable_governance_credential import (
    GOVERNANCE_SCOPES,
    GovernanceCredentialStore,
    VerifiableGovernanceCredential,
)
from maref.signing.signing_key import ReportSigningKey


def _fake_hash(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def _proof_for(org_id: str) -> FederatedProof:
    agg = FederatedMerkleAggregator()
    agg.submit_root(org_id, _fake_hash(org_id), tree_size=10)
    agg.submit_root("org-2", _fake_hash("org-2"), tree_size=20)
    proof = agg.generate_proof(org_id)
    assert proof is not None
    return proof


def _issue(
    scope: list[str] | None = None,
    ttl: float = 3600,
    signing_key: ReportSigningKey | None = None,
) -> tuple[VerifiableGovernanceCredential, ReportSigningKey]:
    key = signing_key or ReportSigningKey.generate()
    cred = VerifiableGovernanceCredential.issue(
        subject_did="did:maref:agent-alice",
        issuer_did="did:maref:org-governor",
        scope=scope or ["state_machine", "audit"],
        merkle_proof=_proof_for("org-1"),
        signing_key=key,
        ttl_seconds=ttl,
    )
    return cred, key


class TestIssueAndVerify:
    def test_issue_signature_valid(self) -> None:
        cred, key = _issue()
        assert cred.credential_id.startswith("vgc-")
        assert cred.verify_signature()
        assert cred.signer_public_key_pem == key.public_key_pem

    def test_full_verify_pass(self) -> None:
        cred, _ = _issue()
        result = cred.verify()
        assert result["valid"] is True
        assert result["signature_valid"] is True
        assert result["merkle_valid"] is True
        assert result["expired"] is False
        assert result["revoked"] is False

    def test_scope_validation(self) -> None:
        with pytest.raises(ValueError):
            VerifiableGovernanceCredential.issue(
                subject_did="did:maref:x",
                issuer_did="did:maref:y",
                scope=["not-a-dimension"],
                merkle_proof={},
                signing_key=ReportSigningKey.generate(),
            )

    def test_all_scopes_known(self) -> None:
        cred, _ = _issue(scope=list(GOVERNANCE_SCOPES))
        assert cred.verify()["valid"] is True


class TestTamperDetection:
    def test_signature_fails_after_tamper(self) -> None:
        cred, _ = _issue()
        cred.subject_did = "did:maref:eve"
        assert cred.verify_signature() is False
        assert cred.verify()["valid"] is False

    def test_signature_fails_after_scope_tamper(self) -> None:
        cred, _ = _issue()
        cred.scope = ["audit", "memory"]
        assert cred.verify_signature() is False


class TestMerkleBinding:
    def test_valid_inclusion_proof(self) -> None:
        cred, _ = _issue()
        assert cred.verify_merkle_inclusion() is True

    def test_empty_proof_skips_merkle_check(self) -> None:
        key = ReportSigningKey.generate()
        cred = VerifiableGovernanceCredential.issue(
            subject_did="did:maref:agent-bob",
            issuer_did="did:maref:org-governor",
            scope=["audit"],
            merkle_proof={},
            signing_key=key,
        )
        assert cred.verify_merkle_inclusion() is True
        # 不要求 Merkle 时仍可验证签名
        assert cred.verify()["valid"] is True

    def test_tampered_proof_fails(self) -> None:
        cred, _ = _issue()
        cred.merkle_proof["federated_root_hash"] = _fake_hash("evil")
        assert cred.verify_merkle_inclusion() is False
        assert cred.verify()["valid"] is False


class TestExpiryAndRevocation:
    def test_expired(self) -> None:
        cred, _ = _issue(ttl=1)
        assert cred.is_expired(now=cred.expires_at + 1)

    def test_expiry_blocked_in_verify(self) -> None:
        cred, _ = _issue(ttl=1)
        assert cred.verify(now=cred.expires_at + 1)["expired"] is True
        assert cred.verify(now=cred.expires_at + 1)["valid"] is False

    def test_store_revocation(self) -> None:
        cred, _ = _issue()
        store = GovernanceCredentialStore()
        store.store(cred)
        assert store.list_valid()
        store.revoke(cred.credential_id, reason="state drift detected")
        assert store.is_revoked(cred.credential_id)
        assert not store.list_valid()
        assert store.revocation_list()[cred.credential_id] == "state drift detected"

    def test_revoke_unknown_raises(self) -> None:
        store = GovernanceCredentialStore()
        with pytest.raises(ValueError):
            store.revoke("vgc-does-not-exist")


class TestSerialization:
    def test_dict_round_trip(self) -> None:
        cred, _ = _issue()
        restored = VerifiableGovernanceCredential.from_dict(cred.to_dict())
        assert restored.to_dict() == cred.to_dict()
        assert restored.verify()["valid"] is True

    def test_json_round_trip(self) -> None:
        cred, _ = _issue()
        restored = VerifiableGovernanceCredential.from_json(cred.to_json())
        assert restored.verify()["valid"] is True

    def test_file_round_trip(self, tmp_path) -> None:
        cred, _ = _issue()
        path = tmp_path / "credential.json"
        cred.to_file(path)
        restored = VerifiableGovernanceCredential.from_file(path)
        assert restored.verify()["valid"] is True


class TestRenewAndRefresh:
    def test_renew_extends_expiry_keeps_id(self) -> None:
        cred, key = _issue(ttl=100)
        old_id = cred.credential_id
        old_expiry = cred.expires_at
        cred.renew(key, ttl_seconds=500)
        assert cred.credential_id == old_id
        assert cred.expires_at > old_expiry
        assert cred.verify_signature()
        assert cred.verify()["valid"] is True

    def test_refresh_with_new_proof(self) -> None:
        cred, key = _issue(ttl=100)
        new_proof = _proof_for("org-1")  # 不同时间聚合的新证明
        cred.refresh(new_proof, key, ttl_seconds=200)
        assert cred.verify_merkle_inclusion() is True
        assert cred.verify()["valid"] is True


class TestStorePersistence:
    def test_save_load_round_trip(self, tmp_path) -> None:
        cred, _ = _issue()
        store = GovernanceCredentialStore()
        store.store(cred)
        store.revoke(cred.credential_id, reason="drift", source="did-revocation:did:maref/x")
        path = tmp_path / "store.json"
        store.save(path)
        restored = GovernanceCredentialStore.load(path)
        assert restored.count() == 1
        assert restored.is_revoked(cred.credential_id)
        assert restored.revoked_reason(cred.credential_id) == "drift"
        assert restored.revoked_source(cred.credential_id) == "did-revocation:did:maref/x"

    def test_revocation_list_export(self, tmp_path) -> None:
        cred, _ = _issue()
        store = GovernanceCredentialStore()
        store.store(cred)
        store.revoke(cred.credential_id, reason="audit override")
        path = tmp_path / "revocation.json"
        store.save_revocation_list(path)
        loaded = GovernanceCredentialStore()
        loaded.load_revocation_list(path)
        assert loaded.is_revoked(cred.credential_id)

    def test_revoke_with_source(self) -> None:
        cred, _ = _issue()
        store = GovernanceCredentialStore()
        store.store(cred)
        store.revoke(cred.credential_id, reason="DID revoked", source="did-revocation:did:maref/subject")
        assert store.revoked_source(cred.credential_id) == "did-revocation:did:maref/subject"
        assert not store.list_valid()

    def test_signed_revocation_list_round_trip(self) -> None:
        cred, _ = _issue()
        store = GovernanceCredentialStore()
        store.store(cred)
        store.revoke(cred.credential_id, reason="drift")
        key = ReportSigningKey.generate()
        data = store.build_signed_revocation_list(key, server_id="org-1")
        assert data["signature"]
        assert data["signer_public_key_pem"] == key.public_key_pem
        assert GovernanceCredentialStore.verify_signed_revocation_list(data) is True
        assert data["revoked"][cred.credential_id] == "drift"

    def test_signed_revocation_list_tamper_detected(self) -> None:
        cred, _ = _issue()
        store = GovernanceCredentialStore()
        store.store(cred)
        store.revoke(cred.credential_id, reason="drift")
        key = ReportSigningKey.generate()
        data = store.build_signed_revocation_list(key, server_id="org-1")
        data["revoked"] = {}  # 篡改：清空吊销列表
        assert GovernanceCredentialStore.verify_signed_revocation_list(data) is False

    def test_signed_revocation_list_missing_signature_invalid(self) -> None:
        store = GovernanceCredentialStore()
        assert store.verify_signed_revocation_list({"revoked": {}}) is False

    def test_save_load_signed_revocation_list(self, tmp_path) -> None:
        cred, _ = _issue()
        store = GovernanceCredentialStore()
        store.store(cred)
        store.revoke(cred.credential_id, reason="audit override")
        key = ReportSigningKey.generate()
        path = tmp_path / "signed_revocations.json"
        store.save_signed_revocation_list(path, key, server_id="org-1")
        loaded = GovernanceCredentialStore()
        loaded.load_signed_revocation_list(path)
        assert loaded.is_revoked(cred.credential_id)
        assert loaded.revoked_reason(cred.credential_id) == "audit override"

    def test_load_signed_revocation_list_invalid_raises(self, tmp_path) -> None:
        path = tmp_path / "bad.json"
        path.write_text('{"revoked": {}}', encoding="utf-8")
        store = GovernanceCredentialStore()
        with pytest.raises(ValueError):
            store.load_signed_revocation_list(path)

    def test_load_revocation_list_overwrites(self, tmp_path) -> None:
        cred, _ = _issue()
        store = GovernanceCredentialStore()
        store.store(cred)
        store.revoke(cred.credential_id, reason="first")
        path = tmp_path / "revocations.json"
        store.save_revocation_list(path)
        # 权威快照覆盖：外部列表不含该凭证 → 本地吊销状态被清空
        empty = GovernanceCredentialStore()
        empty.save_revocation_list(tmp_path / "empty.json")
        store.load_revocation_list(tmp_path / "empty.json")
        assert not store.is_revoked(cred.credential_id)


class TestDIDRevocationLinkage:
    """方案 E M3 / v0.44.0 I1：凭证吊销联动 DID 撤销。"""

    def _store_with_subject(
        self, subject_did: str, n: int = 2
    ) -> tuple[GovernanceCredentialStore, list[str]]:
        store = GovernanceCredentialStore()
        ids: list[str] = []
        for _ in range(n):
            key = ReportSigningKey.generate()
            cred = VerifiableGovernanceCredential.issue(
                subject_did=subject_did,
                issuer_did="did:maref:org-governor",
                scope=["state_machine", "audit"],
                merkle_proof=_proof_for("org-1"),
                signing_key=key,
                ttl_seconds=3600,
            )
            store.store(cred)
            ids.append(cred.credential_id)
        return store, ids

    def test_revoke_by_subject_did_revokes_all(self) -> None:
        store, ids = self._store_with_subject("did:maref:default:alice")
        count = store.revoke_by_subject_did("did:maref:default:alice")
        assert count == len(ids)
        assert all(store.is_revoked(i) for i in ids)

    def test_revoke_by_subject_did_sets_source(self) -> None:
        store, ids = self._store_with_subject("did:maref:default:alice")
        store.revoke_by_subject_did("did:maref:default:alice")
        assert store.revoked_source(ids[0]) == "did-revocation:did:maref:default:alice"
        assert store.revoked_reason(ids[0]) == "did_revoked"

    def test_revoke_by_subject_did_does_not_touch_others(self) -> None:
        store, _ = self._store_with_subject("did:maref:default:alice")
        store, ids_bob = self._store_with_subject("did:maref:default:bob", n=1)
        store.revoke_by_subject_did("did:maref:default:alice")
        assert not store.is_revoked(ids_bob[0])

    def test_revoke_by_subject_did_skips_already_revoked(self) -> None:
        store, ids = self._store_with_subject("did:maref:default:alice")
        store.revoke(ids[0], reason="manual")
        count = store.revoke_by_subject_did("did:maref:default:alice")
        assert count == len(ids) - 1
        assert store.is_revoked(ids[0])
        assert store.revoked_reason(ids[0]) == "manual"

    def test_revoke_by_subject_did_unknown_returns_zero(self) -> None:
        store, _ = self._store_with_subject("did:maref:default:alice")
        assert store.revoke_by_subject_did("did:maref:default:ghost") == 0

    def test_list_valid_excludes_did_revoked(self) -> None:
        store, ids = self._store_with_subject("did:maref:default:alice")
        store.revoke_by_subject_did("did:maref:default:alice")
        assert all(c.credential_id not in ids for c in store.list_valid())

    def test_attach_to_did_registry_revokes_on_revoke(self) -> None:
        from maref.governance.state_machine import GovernanceStateMachine
        from maref.identity.did_registry import AgentDID, DIDRegistry

        registry = DIDRegistry()
        did = AgentDID.generate(namespace="default")
        registry.register(did, GovernanceStateMachine())

        store, ids = self._store_with_subject(did.did_string)
        store.attach_to_did_registry(registry)

        registry.revoke(did, reason="compromised", signer="security")
        assert all(store.is_revoked(i) for i in ids)
        assert store.revoked_reason(ids[0]) == "did_revoked:compromised"
        assert store.revoked_source(ids[0]) == f"did-revocation:{did.did_string}"

    def test_attach_to_did_registry_revokes_on_deactivate(self) -> None:
        from maref.governance.state_machine import GovernanceStateMachine
        from maref.identity.did_registry import AgentDID, DIDRegistry

        registry = DIDRegistry()
        did = AgentDID.generate(namespace="default")
        registry.register(did, GovernanceStateMachine())

        store, ids = self._store_with_subject(did.did_string)
        store.attach_to_did_registry(registry)

        registry.deactivate(did, reason="retired")
        assert all(store.is_revoked(i) for i in ids)

    def test_detach_stops_linkage(self) -> None:
        from maref.governance.state_machine import GovernanceStateMachine
        from maref.identity.did_registry import AgentDID, DIDRegistry

        registry = DIDRegistry()
        did = AgentDID.generate(namespace="default")
        registry.register(did, GovernanceStateMachine())

        store, ids = self._store_with_subject(did.did_string)
        listener = store._on_did_revocation
        store.attach_to_did_registry(registry)
        assert registry.remove_revocation_listener(listener) is True

        registry.revoke(did, reason="compromised")
        assert not store.is_revoked(ids[0])

    def test_revocation_listener_error_does_not_block(self) -> None:
        from maref.governance.state_machine import GovernanceStateMachine
        from maref.identity.did_registry import AgentDID, DIDRegistry

        registry = DIDRegistry()

        def bad_listener(did_string: str, reason: str, signer: str) -> None:
            raise RuntimeError("listener down")

        registry.add_revocation_listener(bad_listener)

        did = AgentDID.generate(namespace="default")
        registry.register(did, GovernanceStateMachine())
        record = registry.revoke(did, reason="test")
        assert record is not None
        assert record.status == "revoked"
