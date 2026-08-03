from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from maref.governance.audit import AuditLogger
from maref.governance.state_machine import GovernanceStateMachine
from maref.identity.agent_dns import AgentDNS
from maref.identity.credential import CredentialStore, VerifiableCredential
from maref.identity.did_registry import (
    AgentDID,
    AgentIdentityRecord,
    DIDRegistry,
    DIDResolutionResult,
)


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


class TestDIDDocument:
    """P2-1: W3C DID Document generation and resolution."""

    def test_to_did_document_basic(self) -> None:
        did = AgentDID.parse("did:maref:test:abc123")
        doc = did.to_did_document()
        assert doc["@context"] == "https://www.w3.org/ns/did/v1"
        assert doc["id"] == "did:maref:test:abc123"
        assert "verificationMethod" not in doc

    def test_to_did_document_with_ed25519(self) -> None:
        did = AgentDID.generate()
        pem = "-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA...\n-----END PUBLIC KEY-----"
        doc = did.to_did_document(ed25519_public_key_pem=pem)
        assert "verificationMethod" in doc
        vm = doc["verificationMethod"][0]
        assert vm["type"] == "Ed25519VerificationKey2018"
        assert vm["controller"] == did.did_string
        assert vm["publicKeyPem"] == pem
        assert doc["authentication"] == [vm["id"]]
        assert doc["assertionMethod"] == [vm["id"]]

    def test_to_did_document_with_services(self) -> None:
        did = AgentDID.generate()
        services = [
            {
                "id": f"{did.did_string}#a2a",
                "type": "A2AAgentService",
                "serviceEndpoint": "https://agent.example.com/a2a",
            }
        ]
        doc = did.to_did_document(service_endpoints=services)
        assert "service" in doc
        assert doc["service"] == services

    def test_resolve_did_document_found(self) -> None:
        registry = DIDRegistry()
        sm = GovernanceStateMachine()
        did = AgentDID.generate()
        registry.register(did, sm)
        result = registry.resolve_did_document(did)
        assert result.resolved
        assert result.did_document is not None
        assert result.did_document["id"] == did.did_string
        assert result.resolution_metadata["method"] == "maref"

    def test_resolve_did_document_not_found(self) -> None:
        registry = DIDRegistry()
        did = AgentDID.generate()
        result = registry.resolve_did_document(did)
        assert not result.resolved
        assert result.did_document is None
        assert "notFound" in result.resolution_metadata.get("error", "")

    def test_resolve_did_document_includes_ed25519(self) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        registry = DIDRegistry()
        sm = GovernanceStateMachine()
        keypair = Ed25519KeyPair.generate()
        did = AgentDID.generate()
        record = registry.register(did, sm)
        record.metadata["ed25519_public_key_pem"] = keypair.public_key_pem

        result = registry.resolve_did_document(did)
        assert result.resolved
        assert result.did_document is not None
        vm = result.did_document.get("verificationMethod", [])
        assert len(vm) == 1
        assert vm[0]["publicKeyPem"] == keypair.public_key_pem

    def test_resolve_did_document_with_services(self) -> None:
        registry = DIDRegistry()
        sm = GovernanceStateMachine()
        did = AgentDID.generate()
        registry.register(did, sm)
        services = [{"id": f"{did.did_string}#endpoint", "type": "Endpoint", "serviceEndpoint": "https://x.com"}]
        result = registry.resolve_did_document(did, service_endpoints=services)
        assert result.did_document is not None
        assert result.did_document["service"] == services

    def test_did_resolution_result_to_dict(self) -> None:
        result = DIDResolutionResult(
            did_document={"id": "did:maref:test:abc"},
            resolution_metadata={"method": "maref", "resolved": True},
            document_metadata={"created": 1000.0, "updated": 1000.0, "deactivated": False},
        )
        d = result.to_dict()
        assert d["did_document"]["id"] == "did:maref:test:abc"
        assert d["resolution_metadata"]["method"] == "maref"

    def test_did_resolution_result_not_found_to_dict(self) -> None:
        result = DIDResolutionResult(
            did_document=None,
            resolution_metadata={"error": "notFound"},
            document_metadata={},
        )
        d = result.to_dict()
        assert "did_document" not in d
        assert d["resolution_metadata"]["error"] == "notFound"

    def test_agent_identity_record_ed25519_public_key(self) -> None:
        record = AgentIdentityRecord(
            did=AgentDID.generate(),
            state_machine=GovernanceStateMachine(),
            metadata={"ed25519_public_key_pem": "test-pem"},
        )
        assert record.ed25519_public_key() == "test-pem"

    def test_agent_identity_record_no_key(self) -> None:
        record = AgentIdentityRecord(
            did=AgentDID.generate(),
            state_machine=GovernanceStateMachine(),
        )
        assert record.ed25519_public_key() == ""


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


# ---------------------------------------------------------------------------
# 方案 E：DID 版本化撤销
# ---------------------------------------------------------------------------


class TestDIDVersionedRevocation:
    def test_active_record_metadata(self) -> None:
        registry = DIDRegistry()
        sm = GovernanceStateMachine()
        did = AgentDID.generate()
        registry.register(did, sm)
        result = registry.resolve_did_document(did)
        md = result.document_metadata
        assert md["status"] == "active"
        assert md["version"] == 1
        assert md["deactivated"] is False

    def test_revoke_sets_status_and_entry(self) -> None:
        registry = DIDRegistry()
        sm = GovernanceStateMachine()
        did = AgentDID.generate()
        registry.register(did, sm)
        record = registry.revoke(did, reason="compromised", signer="security")
        assert record is not None
        assert record.status == "revoked"
        assert record.version == 2
        assert record.revocation_entry["reason"] == "compromised"
        assert record.revocation_entry["signer"] == "security"
        assert record.revocation_entry["version"] == 2

    def test_revoked_resolves_to_revoked(self) -> None:
        registry = DIDRegistry()
        sm = GovernanceStateMachine()
        did = AgentDID.generate()
        registry.register(did, sm)
        registry.revoke(did, reason="policy")
        result = registry.resolve_did_document(did)
        md = result.document_metadata
        assert md["status"] == "revoked"
        assert md["deactivated"] is True
        assert "revocation_entry" in md
        assert result.resolved  # 保留历史，仍可解析

    def test_revoke_keeps_history_in_registry(self) -> None:
        """撤销不删除注册，历史版本可查。"""
        registry = DIDRegistry()
        sm = GovernanceStateMachine()
        did = AgentDID.generate()
        registry.register(did, sm)
        registry.revoke(did, reason="r1")
        assert registry.resolve(did) is not None
        assert registry.agent_count() == 1

    def test_deactivate_is_terminal(self) -> None:
        registry = DIDRegistry()
        sm = GovernanceStateMachine()
        did = AgentDID.generate()
        registry.register(did, sm)
        registry.deactivate(did, reason="retired")
        result = registry.resolve_did_document(did)
        assert result.document_metadata["status"] == "deactivated"
        assert result.document_metadata["deactivated"] is True

    def test_is_active_after_revoke(self) -> None:
        registry = DIDRegistry()
        sm = GovernanceStateMachine()
        did = AgentDID.generate()
        registry.register(did, sm)
        assert registry.is_active(did) is True
        registry.revoke(did)
        assert registry.is_active(did) is False

    def test_revoke_unknown_returns_none(self) -> None:
        registry = DIDRegistry()
        assert registry.revoke(AgentDID.generate()) is None

    def test_deactivated_cannot_be_revoked_again(self) -> None:
        """deactivated 是不可逆终态：再次 revoke 不得改写其状态/版本。"""
        registry = DIDRegistry()
        sm = GovernanceStateMachine()
        did = AgentDID.generate()
        registry.register(did, sm)
        registry.deactivate(did, reason="retired")
        before = registry.resolve(did)
        assert before is not None
        assert before.status == "deactivated"
        version_before = before.version

        registry.revoke(did, reason="later")
        after = registry.resolve(did)
        assert after is not None
        assert after.status == "deactivated"
        assert after.version == version_before
        assert after.revocation_entry["reason"] == "retired"


# ---------------------------------------------------------------------------
# 方案 E M2：Agent DNS（DID → 能力目录解析）


def _make_registered_dns() -> tuple[AgentDNS, DIDRegistry, AgentDID]:
    registry = DIDRegistry()
    sm = GovernanceStateMachine()
    did = AgentDID.generate()
    registry.register(did, sm)
    dns = AgentDNS(did_registry=registry)
    return dns, registry, did


class TestAgentDNS:
    def test_register_and_resolve(self) -> None:
        dns, _, did = _make_registered_dns()
        card = dns.register(
            did,
            name="researcher",
            description="research agent",
            skills=[{"id": "s1", "name": "search", "description": "web search"}],
            endpoints=["https://agent.example.com/a2a"],
            capabilities={"streaming": True},
        )
        assert card.status == "active"
        resolved = dns.resolve(did)
        assert resolved is not None
        assert resolved.did == did
        assert resolved.name == "researcher"
        assert resolved.skills[0]["id"] == "s1"

    def test_register_unregistered_did_rejected(self) -> None:
        registry = DIDRegistry()
        dns = AgentDNS(did_registry=registry)
        with pytest.raises(ValueError):
            dns.register(AgentDID.generate(), name="ghost", description="no identity")

    def test_register_allow_unregistered(self) -> None:
        registry = DIDRegistry()
        dns = AgentDNS(did_registry=registry)
        did = AgentDID.generate()
        card = dns.register(did, name="ghost", description="no identity", require_registered=False)
        assert dns.resolve(did) is not None
        assert card.name == "ghost"

    def test_register_revoked_did_rejected(self) -> None:
        dns, registry, did = _make_registered_dns()
        registry.revoke(did, reason="compromised")
        with pytest.raises(ValueError):
            dns.register(did, name="x", description="y")

    def test_resolve_after_revoke_returns_none(self) -> None:
        """DID 撤销后能力目录同步失效。"""
        dns, registry, did = _make_registered_dns()
        dns.register(did, name="researcher", description="research agent")
        assert dns.resolve(did) is not None
        registry.revoke(did, reason="compromised")
        assert dns.resolve(did) is None

    def test_resolve_after_deactivate_returns_none(self) -> None:
        dns, registry, did = _make_registered_dns()
        dns.register(did, name="researcher", description="research agent")
        registry.deactivate(did, reason="retired")
        assert dns.resolve(did) is None

    def test_resolve_by_did_string(self) -> None:
        dns, _, did = _make_registered_dns()
        dns.register(did, name="researcher", description="research agent")
        assert dns.resolve_did_string(did.did_string) is not None
        assert dns.resolve_did_string("did:maref:bad") is None
        assert dns.resolve_did_string(did.did_string + ":extra") is None

    def test_resolve_unknown_returns_none(self) -> None:
        dns, _, _ = _make_registered_dns()
        assert dns.resolve(AgentDID.generate()) is None

    def test_unregister(self) -> None:
        dns, _, did = _make_registered_dns()
        dns.register(did, name="researcher", description="research agent")
        removed = dns.unregister(did)
        assert removed is not None
        assert dns.resolve(did) is None
        assert dns.unregister(did) is None

    def test_unregister_by_did_string(self) -> None:
        dns, _, did = _make_registered_dns()
        dns.register(did, name="researcher", description="research agent")
        assert dns.unregister_did_string(did.did_string) is not None
        assert dns.unregister_did_string("invalid::did") is None

    def test_list_cards_active_only(self) -> None:
        dns, registry, did = _make_registered_dns()
        did2 = AgentDID.generate()
        registry.register(did2, GovernanceStateMachine())
        dns.register(did, name="a", description="1")
        dns.register(did2, name="b", description="2")
        assert len(dns.list_cards()) == 2
        registry.revoke(did, reason="r")
        assert len(dns.list_cards()) == 1
        assert dns.list_cards()[0].did == did2
        assert len(dns.list_cards(active_only=False)) == 2

    def test_count(self) -> None:
        dns, _, did = _make_registered_dns()
        assert dns.count() == 0
        dns.register(did, name="a", description="1")
        assert dns.count() == 1

    def test_to_a2a_card_shape(self) -> None:
        dns, _, did = _make_registered_dns()
        dns.register(
            did,
            name="researcher",
            description="research agent",
            skills=[{"id": "s1", "name": "search", "description": "web search"}],
            endpoints=["https://agent.example.com/a2a"],
            capabilities={"streaming": True},
        )
        card = dns.resolve(did)
        assert card is not None
        a2a = card.to_a2a_card()
        assert a2a["name"] == "researcher"
        assert a2a["url"] == "https://agent.example.com/a2a"
        assert a2a["protocolVersion"] == "1.0"
        assert a2a["skills"][0]["id"] == "s1"
        assert a2a["capabilities"]["streaming"] is True

    def test_to_a2a_card_fallback_base_url(self) -> None:
        dns, _, did = _make_registered_dns()
        dns.register(did, name="a", description="1")
        card = dns.resolve(did)
        assert card is not None
        assert card.to_a2a_card(base_url="https://fallback.example.com")["url"] == (
            "https://fallback.example.com"
        )

    def test_roundtrip_serialization(self) -> None:
        dns, registry, did = _make_registered_dns()
        dns.register(
            did,
            name="researcher",
            description="research agent",
            skills=[{"id": "s1", "name": "search", "description": "web search"}],
            endpoints=["https://agent.example.com/a2a"],
            capabilities={"streaming": True},
        )
        restored = AgentDNS.from_dict(dns.to_dict())
        restored._did_registry = registry
        card = restored.resolve(did)
        assert card is not None
        assert card.name == "researcher"
        assert card.skills[0]["id"] == "s1"




# ---------------------------------------------------------------------------
# v0.44.0 I3：AgentIdentityService 统一身份编排门面
# ---------------------------------------------------------------------------


class TestAgentIdentityService:
    def _service(self) -> tuple:
        from maref.identity.agent_identity_service import AgentIdentityService

        registry = DIDRegistry()
        dns = AgentDNS(did_registry=registry)
        service = AgentIdentityService(
            did_registry=registry,
            agent_dns=dns,
        )
        sm = GovernanceStateMachine()
        did = AgentDID.generate()
        registry.register(did, sm)
        dns.register(
            did,
            name="researcher",
            description="research agent",
            endpoints=["https://agent.example.com/a2a"],
        )
        return service, registry, dns, did

    def test_resolve_aggregates_all_views(self) -> None:
        service, _reg, _dns, did = self._service()
        result = service.resolve(did.did_string)
        assert result is not None
        assert result["status"] == "active"
        assert result["did_document_metadata"]["version"] == 1
        assert result["agent_card"]["name"] == "researcher"
        assert result["trust"] is None  # 未评估

    def test_resolve_unknown_did_returns_none(self) -> None:
        service, _reg, _dns, _did = self._service()
        assert service.resolve("did:maref:default:ghost") is None
        assert service.resolve("not-a-did") is None

    def test_resolve_agent_card_only(self) -> None:
        service, _reg, _dns, did = self._service()
        card = service.resolve_agent_card(did.did_string)
        assert card is not None
        assert card.name == "researcher"

    def test_issue_requires_registered_did(self) -> None:
        from maref.signing.signing_key import ReportSigningKey

        service, _reg, _dns, did = self._service()
        key = ReportSigningKey.generate()
        cred = service.issue(
            subject_did=did.did_string,
            scope=["state_machine", "audit"],
            signing_key=key,
        )
        assert cred.subject_did == did.did_string
        assert cred.verify_signature()

    def test_issue_unregistered_did_raises(self) -> None:
        from maref.signing.signing_key import ReportSigningKey

        service, _reg, _dns, _did = self._service()
        key = ReportSigningKey.generate()
        with pytest.raises(ValueError, match="未注册"):
            service.issue(
                subject_did="did:maref:default:ghost",
                scope=["audit"],
                signing_key=key,
            )

    def test_issue_inactive_did_raises(self) -> None:
        from maref.signing.signing_key import ReportSigningKey

        service, registry, _dns, did = self._service()
        registry.revoke(did, reason="compromised")
        key = ReportSigningKey.generate()
        with pytest.raises(ValueError, match="非 active"):
            service.issue(
                subject_did=did.did_string,
                scope=["audit"],
                signing_key=key,
            )

    def test_issue_without_key_raises(self) -> None:
        service, _reg, _dns, did = self._service()
        with pytest.raises(ValueError, match="密钥"):
            service.issue(subject_did=did.did_string, scope=["audit"])

    def test_verify_reports_revoked(self) -> None:
        from maref.signing.signing_key import ReportSigningKey

        service, _reg, _dns, did = self._service()
        key = ReportSigningKey.generate()
        cred = service.issue(
            subject_did=did.did_string,
            scope=["state_machine"],
            signing_key=key,
        )
        result = service.verify(cred)
        assert result["valid"] is True
        assert result["revoked"] is False

        service._credential_store.revoke(cred.credential_id, reason="policy")
        result = service.verify(cred)
        assert result["valid"] is False
        assert result["revoked"] is True
        assert result["revoked_reason"] == "policy"

    def test_revoke_cascades_credentials_and_card(self) -> None:
        from maref.signing.signing_key import ReportSigningKey

        service, _reg, _dns, did = self._service()
        key = ReportSigningKey.generate()
        service.issue(
            subject_did=did.did_string,
            scope=["state_machine", "audit"],
            signing_key=key,
        )
        result = service.revoke(did.did_string, reason="compromised", signer="admin")
        assert result["revoked"] is True
        assert result["status"] == "revoked"
        assert result["card_active"] is False
        assert result["credential_revoked_total"] == 1
        # 联动吊销：凭证进入吊销列表
        assert service._credential_store.revoked_count() == 1

    def test_revoke_unknown_did(self) -> None:
        service, _reg, _dns, _did = self._service()
        result = service.revoke("did:maref:default:ghost")
        assert result["revoked"] is False

    def test_is_active_and_list(self) -> None:
        service, _reg, _dns, did = self._service()
        assert service.is_active(did.did_string) is True
        assert service.is_active("did:maref:default:ghost") is False
        agents = service.list_agents(active_only=True)
        assert len(agents) == 1
        assert agents[0]["did"] == did.did_string

    def test_summary(self) -> None:
        service, _reg, _dns, _did = self._service()
        s = service.summary()
        assert s["agents"] == 1
        assert s["cards"] == 1
        assert s["credentials"] == 0
