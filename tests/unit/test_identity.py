from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from maref.governance.audit import AuditLogger
from maref.governance.state_machine import GovernanceStateMachine
from maref.identity.credential import CredentialStore, VerifiableCredential
from maref.identity.did_registry import AgentDID, DIDRegistry


@pytest.fixture
def state_machine() -> GovernanceStateMachine:
    return GovernanceStateMachine()


@pytest.fixture
def audit_path() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        return Path(f.name)


@pytest.fixture
def audit_logger(audit_path: Path) -> AuditLogger:
    return AuditLogger(audit_path)


class TestAgentDID:
    def test_generate_default_namespace(self) -> None:
        did = AgentDID.generate()
        assert did.namespace == "default"
        assert len(did.agent_short_id) == 8
        assert did.did_string.startswith("did:maref:default:")

    def test_generate_custom_namespace(self) -> None:
        did = AgentDID.generate(namespace="production")
        assert did.namespace == "production"
        assert did.did_string.startswith("did:maref:production:")

    def test_parse_valid_did(self) -> None:
        did = AgentDID.parse("did:maref:production:agent-a3f2b")
        assert did.namespace == "production"
        assert did.agent_short_id == "agent-a3f2b"

    def test_parse_invalid_did_raises(self) -> None:
        with pytest.raises(ValueError):
            AgentDID.parse("did:invalid:production:xxx")
        with pytest.raises(ValueError):
            AgentDID.parse("not-a-did")
        with pytest.raises(ValueError):
            AgentDID.parse("did:maref:too:many:parts")

    def test_did_string_property(self) -> None:
        did = AgentDID(namespace="test", agent_short_id="abc123")
        assert did.did_string == "did:maref:test:abc123"

    def test_did_uniqueness(self) -> None:
        dids = [AgentDID.generate() for _ in range(100)]
        strings = [d.did_string for d in dids]
        assert len(set(strings)) == 100

    def test_did_is_frozen(self) -> None:
        did = AgentDID.generate()
        with pytest.raises(Exception):  # noqa: B017
            did.namespace = "changed"  # type: ignore[misc]


class TestDIDRegistry:
    @pytest.fixture
    def registry(self) -> DIDRegistry:
        return DIDRegistry()

    def test_register_agent(
        self, registry: DIDRegistry, state_machine: GovernanceStateMachine
    ) -> None:
        did = AgentDID.generate()
        record = registry.register(did, state_machine, initial_roles=["worker"])
        assert record.did == did
        assert record.roles == ["worker"]

    def test_resolve_registered(
        self, registry: DIDRegistry, state_machine: GovernanceStateMachine
    ) -> None:
        did = AgentDID.generate()
        registry.register(did, state_machine)
        resolved = registry.resolve(did)
        assert resolved is not None
        assert resolved.did == did

    def test_resolve_unregistered(self, registry: DIDRegistry) -> None:
        did = AgentDID.generate()
        assert registry.resolve(did) is None

    def test_list_all(self, registry: DIDRegistry, state_machine: GovernanceStateMachine) -> None:
        for _ in range(3):
            registry.register(AgentDID.generate(), state_machine)
        assert registry.agent_count() == 3
        assert len(registry.list_all()) == 3


class TestVerifiableCredential:
    def test_issue_and_verify(self) -> None:
        issuer = AgentDID.generate()
        subject = AgentDID.generate()
        secret = b"test-secret-key-32-bytes-long!!"
        vc = VerifiableCredential.issue(
            issuer=issuer,
            subject=subject,
            credential_type="MAREFCapability",
            claims={"can_delegate": True},
            issuer_secret=secret,
        )
        assert vc.issuer == issuer
        assert vc.subject == subject
        assert vc.verify(secret) is True

    def test_verify_fails_with_wrong_secret(self) -> None:
        issuer = AgentDID.generate()
        subject = AgentDID.generate()
        vc = VerifiableCredential.issue(
            issuer=issuer,
            subject=subject,
            credential_type="MAREFCapability",
            claims={"can_delegate": True},
            issuer_secret=b"correct-secret-key-for-issuer!",
        )
        assert vc.verify(b"wrong-secret-key-used-here!!!!!") is False

    def test_is_expired_with_ttl(self) -> None:
        issuer = AgentDID.generate()
        subject = AgentDID.generate()
        vc = VerifiableCredential.issue(
            issuer=issuer,
            subject=subject,
            credential_type="MAREFCapability",
            claims={},
            ttl_seconds=0.01,
        )
        time.sleep(0.02)
        assert vc.is_expired() is True

    def test_not_expired_without_ttl(self) -> None:
        issuer = AgentDID.generate()
        subject = AgentDID.generate()
        vc = VerifiableCredential.issue(
            issuer=issuer,
            subject=subject,
            credential_type="MAREFCapability",
            claims={},
            ttl_seconds=None,
        )
        assert vc.is_expired() is False

    def test_to_json_ld_format(self) -> None:
        issuer = AgentDID.generate()
        subject = AgentDID.generate()
        vc = VerifiableCredential.issue(
            issuer=issuer,
            subject=subject,
            credential_type="MAREFCapability",
            claims={"can_delegate": True},
        )
        ld = vc.to_json_ld()
        assert ld["id"] == vc.id
        assert ld["issuer"] == issuer.did_string
        assert "MAREFCapability" in ld["type"]
        assert ld["credentialSubject"]["id"] == subject.did_string


class TestCredentialStore:
    def test_store_and_get(self) -> None:
        store = CredentialStore()
        issuer = AgentDID.generate()
        subject = AgentDID.generate()
        vc = VerifiableCredential.issue(issuer, subject, "Test", {})
        store.store(vc)
        assert store.get(vc.id) == vc
        assert store.count() == 1

    def test_revoke(self) -> None:
        store = CredentialStore()
        issuer = AgentDID.generate()
        subject = AgentDID.generate()
        vc = VerifiableCredential.issue(issuer, subject, "Test", {})
        store.store(vc)
        store.revoke(vc.id, "compromised")
        assert store.is_revoked(vc.id) is True
        assert store.revoked_count() == 1

    def test_revoke_unknown_raises(self) -> None:
        store = CredentialStore()
        with pytest.raises(ValueError):
            store.revoke("nonexistent")

    def test_list_valid_excludes_revoked(self) -> None:
        store = CredentialStore()
        issuer = AgentDID.generate()
        sub1 = AgentDID.generate()
        sub2 = AgentDID.generate()
        vc1 = VerifiableCredential.issue(issuer, sub1, "Test", {})
        vc2 = VerifiableCredential.issue(issuer, sub2, "Test", {})
        store.store(vc1)
        store.store(vc2)
        store.revoke(vc1.id, "test")
        valid = store.list_valid()
        assert len(valid) == 1
        assert valid[0].id == vc2.id

    def test_list_valid_excludes_expired(self) -> None:
        store = CredentialStore()
        issuer = AgentDID.generate()
        subject = AgentDID.generate()
        vc = VerifiableCredential.issue(issuer, subject, "Test", {}, ttl_seconds=0.01)
        store.store(vc)
        time.sleep(0.02)
        assert store.list_valid() == []

    def test_capacity_query_performance(self) -> None:
        store = CredentialStore()
        issuer = AgentDID.generate()
        for _ in range(1000):
            vc = VerifiableCredential.issue(
                issuer, AgentDID.generate(), "Test", {}, ttl_seconds=3600
            )
            store.store(vc)
        start = time.time()
        result = store.get(list(store._credentials.keys())[500])
        elapsed = (time.time() - start) * 1000
        assert result is not None
        assert elapsed < 50
