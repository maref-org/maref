"""v0.49 P5 — Organization DID: structure, certificate issue/verify, lifecycle.

Acceptance: ``OrgDID`` parses ``did:maref:org:*`` strictly; ``OrgCertificate``
is issuable and verifiable with only the issuer public key; ``OrgDIDRegistry``
manages lifecycle (active / revoked / deactivated) with SQLite persistence.
"""

from __future__ import annotations

import pytest

from maref.crypto.ed25519_keys import Ed25519KeyPair
from maref.identity.org_did import (
    FEDERATION_ROOT_DID,
    OrgCertificate,
    OrgDID,
    OrgDIDRegistry,
)


class TestOrgDID:
    def test_did_string_format(self) -> None:
        org = OrgDID(org_name="acme", org_id="7f3a")
        assert org.did_string == "did:maref:org:acme:7f3a"

    def test_parse_round_trip(self) -> None:
        org = OrgDID.parse("did:maref:org:openclaw:001")
        assert org.org_name == "openclaw"
        assert org.org_id == "001"
        assert org.did_string == "did:maref:org:openclaw:001"

    def test_parse_rejects_malformed(self) -> None:
        for bad in (
            "did:maref:acme:001",          # missing org segment
            "did:maref:org:ACME:001",      # uppercase org_name
            "did:maref:org:acme:",         # empty org_id
            "did:maref:org:a:xyz$",        # invalid org_id chars
            "not-a-did",
        ):
            with pytest.raises(ValueError):
                OrgDID.parse(bad)

    def test_generate_unique_and_valid(self) -> None:
        a = OrgDID.generate("acme")
        b = OrgDID.generate("acme")
        assert a.org_name == "acme"
        assert a.org_id != b.org_id
        OrgDID.parse(a.did_string)  # must re-parse cleanly

    def test_to_did_document(self) -> None:
        org = OrgDID(org_name="acme", org_id="7f3a")
        doc = org.to_did_document(
            ed25519_public_key_pem="PEM",
            service_endpoints=[{"id": "x", "type": "Governance", "serviceEndpoint": ""}],
        )
        assert doc["id"] == "did:maref:org:acme:7f3a"
        assert doc["verificationMethod"][0]["publicKeyPem"] == "PEM"


class TestOrgCertificate:
    def test_issue_and_verify(self) -> None:
        root = Ed25519KeyPair.generate()
        cert = OrgCertificate(
            did="did:maref:org:acme:7f3a",
            name="Acme Inc.",
            public_key=Ed25519KeyPair.generate().public_key_pem,
            weight=2,
            roles=["member", "arbitrator"],
            jurisdiction="eu",
        )
        cert.issue(root)
        assert cert.signature
        assert cert.verify(root.public_key_pem) is True

    def test_tampered_certificate_fails(self) -> None:
        root = Ed25519KeyPair.generate()
        cert = OrgCertificate(
            did="did:maref:org:acme:7f3a",
            name="Acme Inc.",
            public_key=Ed25519KeyPair.generate().public_key_pem,
            weight=1,
        )
        cert.issue(root)
        cert.weight = 100  # tamper
        assert cert.verify(root.public_key_pem) is False

    def test_wrong_issuer_key_fails(self) -> None:
        cert = OrgCertificate(
            did="did:maref:org:acme:7f3a",
            name="Acme Inc.",
            public_key=Ed25519KeyPair.generate().public_key_pem,
        )
        cert.issue(Ed25519KeyPair.generate())
        other_root = Ed25519KeyPair.generate()
        assert cert.verify(other_root.public_key_pem) is False

    def test_serialization_round_trip(self) -> None:
        root = Ed25519KeyPair.generate()
        cert = OrgCertificate(
            did="did:maref:org:acme:7f3a",
            name="Acme Inc.",
            public_key="PK",
            weight=3,
            roles=["arbitrator"],
            jurisdiction="eu",
        )
        cert.issue(root)
        restored = OrgCertificate.from_dict(cert.to_dict())
        assert restored == cert
        assert restored.verify(root.public_key_pem) is True


class TestOrgDIDRegistry:
    def test_register_and_verify(self) -> None:
        root = Ed25519KeyPair.generate()
        registry = OrgDIDRegistry(issuer_key=root)
        org_did, cert = registry.register(
            "acme", name="Acme Inc.", weight=2, jurisdiction="eu"
        )
        assert org_did.did_string.startswith("did:maref:org:acme:")
        assert registry.resolve(org_did) is cert
        assert registry.verify_certificate(cert) is True
        assert registry.verify_did(org_did.did_string) is True
        assert registry.is_active(org_did) is True

    def test_issuer_defaults_to_federation_root(self) -> None:
        registry = OrgDIDRegistry(issuer_key=Ed25519KeyPair.generate())
        assert registry.issuer_did == FEDERATION_ROOT_DID

    def test_lifecycle_revoke_then_verify_fails(self) -> None:
        registry = OrgDIDRegistry(issuer_key=Ed25519KeyPair.generate())
        org_did, cert = registry.register("acme")
        revoked = registry.revoke(org_did, reason="audit failure", signer="root")
        assert revoked is not None
        assert revoked.status == "revoked"
        assert registry.is_active(org_did) is False
        assert registry.verify_did(org_did.did_string) is False

    def test_deactivate_irreversible(self) -> None:
        registry = OrgDIDRegistry(issuer_key=Ed25519KeyPair.generate())
        org_did, _ = registry.register("acme")
        registry.deactivate(org_did, reason="dissolved")
        assert registry.is_active(org_did) is False
        # deactivated cannot be re-activated via revoke
        assert registry.revoke(org_did) is not None
        assert registry.is_active(org_did) is False

    def test_persistence_across_registry_instances(self, tmp_path) -> None:
        root = Ed25519KeyPair.generate()
        r1 = OrgDIDRegistry(issuer_key=root, db_path=tmp_path / "orgs.db")
        org_did, cert = r1.register("hermes", name="Hermes", weight=1)

        # New registry over the same file — same issuer key so signatures verify.
        r2 = OrgDIDRegistry(issuer_key=root, db_path=tmp_path / "orgs.db")
        assert r2.org_count() == 1
        restored = r2.resolve(org_did)
        assert restored is not None
        assert restored.name == "Hermes"
        assert r2.verify_certificate(restored) is True

    def test_external_verifier_needs_only_public_key(self) -> None:
        """Any third party holding the root public key can verify membership."""
        root = Ed25519KeyPair.generate()
        registry = OrgDIDRegistry(issuer_key=root)
        org_did, cert = registry.register("acme")
        cert_copy = OrgCertificate.from_dict(cert.to_dict())
        # Verify using only the public key, without registry/private key access.
        assert cert_copy.verify(root.public_key_pem) is True
        assert OrgDID.parse(org_did.did_string).did_string == org_did.did_string
