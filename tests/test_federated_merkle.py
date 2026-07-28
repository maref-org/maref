"""Tests for FederatedMerkleAggregator."""

from __future__ import annotations

from maref.eivl.federated_merkle import (
    FederatedMerkleAggregator,
    FederatedProof,
    OrgRootEntry,
)


class TestFederatedMerkleAggregator:
    def test_empty_aggregator(self) -> None:
        agg = FederatedMerkleAggregator()
        assert agg.get_federated_root() is None
        assert agg.summary()["org_count"] == 0

    def test_submit_and_aggregate(self) -> None:
        agg = FederatedMerkleAggregator()
        agg.submit_root("org-1", "hash_a" * 8, tree_size=10)
        agg.submit_root("org-2", "hash_b" * 8, tree_size=20)
        agg.submit_root("org-3", "hash_c" * 8, tree_size=30)

        root = agg.get_federated_root()
        assert root is not None
        assert agg.summary()["org_count"] == 3
        assert agg.summary()["total_evidence_count"] == 60

    def test_generate_proof(self) -> None:
        agg = FederatedMerkleAggregator()
        agg.submit_root("org-1", "hash_a" * 8)
        agg.submit_root("org-2", "hash_b" * 8)

        proof = agg.generate_proof("org-1")
        assert proof is not None
        assert proof.org_id == "org-1"
        assert proof.org_root_hash == "hash_a" * 8
        assert proof.federated_root_hash == agg.get_federated_root()
        assert proof.org_count == 2

    def test_verify_proof_offline(self) -> None:
        """Proof is verifiable without the aggregator instance."""
        agg = FederatedMerkleAggregator()
        agg.submit_root("org-1", "hash_a" * 8)
        agg.submit_root("org-2", "hash_b" * 8)
        agg.submit_root("org-3", "hash_c" * 8)

        proof = agg.generate_proof("org-2")
        assert proof is not None
        # Verify offline -- only needs the proof object itself.
        assert proof.verify() is True

    def test_proof_detects_tampered_root(self) -> None:
        """Tampering with the federated root invalidates the proof."""
        agg = FederatedMerkleAggregator()
        agg.submit_root("org-1", "hash_a" * 8)
        agg.submit_root("org-2", "hash_b" * 8)

        proof = agg.generate_proof("org-1")
        assert proof is not None
        assert proof.verify() is True

        # Tamper with the federated root hash.
        tampered = FederatedProof(
            org_id=proof.org_id,
            org_root_hash=proof.org_root_hash,
            proof_path=proof.proof_path,
            federated_root_hash="0" * 64,
            org_count=proof.org_count,
            timestamp=proof.timestamp,
        )
        assert tampered.verify() is False

    def test_verify_org_inclusion(self) -> None:
        agg = FederatedMerkleAggregator()
        agg.submit_root("org-1", "hash_a" * 8)
        agg.submit_root("org-2", "hash_b" * 8)

        result = agg.verify_org_inclusion("org-1")
        assert result["valid"] is True
        assert result["org_id"] == "org-1"
        assert result["org_count"] == 2

    def test_verify_unknown_org(self) -> None:
        agg = FederatedMerkleAggregator()
        agg.submit_root("org-1", "hash_a" * 8)

        result = agg.verify_org_inclusion("unknown")
        assert result["valid"] is False

    def test_remove_org_changes_root(self) -> None:
        agg = FederatedMerkleAggregator()
        agg.submit_root("org-1", "hash_a" * 8)
        agg.submit_root("org-2", "hash_b" * 8)

        root_before = agg.get_federated_root()
        assert agg.remove_org("org-2") is True
        root_after = agg.get_federated_root()
        assert root_after is not None
        assert root_before != root_after
        assert agg.summary()["org_count"] == 1

    def test_remove_unknown_org(self) -> None:
        agg = FederatedMerkleAggregator()
        agg.submit_root("org-1", "hash_a" * 8)
        assert agg.remove_org("unknown") is False

    def test_update_root_changes_federated_root(self) -> None:
        agg = FederatedMerkleAggregator()
        agg.submit_root("org-1", "hash_a" * 8)
        agg.submit_root("org-2", "hash_b" * 8)

        root_before = agg.get_federated_root()
        agg.submit_root("org-1", "hash_x" * 8)  # Update org-1's root
        root_after = agg.get_federated_root()
        assert root_before != root_after

    def test_summary(self) -> None:
        agg = FederatedMerkleAggregator()
        agg.submit_root("org-1", "hash_a" * 8, tree_size=10)
        agg.submit_root("org-2", "hash_b" * 8, tree_size=20)

        s = agg.summary()
        assert s["org_count"] == 2
        assert s["federated_root"] is not None
        assert s["total_evidence_count"] == 30

    def test_list_orgs(self) -> None:
        agg = FederatedMerkleAggregator()
        agg.submit_root("org-1", "hash_a" * 8, metadata={"name": "Acme"})
        agg.submit_root("org-2", "hash_b" * 8)

        orgs = agg.list_orgs()
        assert len(orgs) == 2
        assert all(isinstance(o, OrgRootEntry) for o in orgs)
        assert orgs[0].org_id == "org-1"

    def test_single_org(self) -> None:
        """A single org's root IS the federated root."""
        agg = FederatedMerkleAggregator()
        agg.submit_root("org-1", "hash_a" * 8)

        root = agg.get_federated_root()
        assert root == "hash_a" * 8

        proof = agg.generate_proof("org-1")
        assert proof is not None
        assert proof.verify() is True


class TestFederatedProofSerialization:
    """V5: FederatedProof serialization (JSON/signing)."""

    def test_to_dict_roundtrip(self) -> None:
        agg = FederatedMerkleAggregator()
        agg.submit_root("org-1", "hash_a" * 8)
        agg.submit_root("org-2", "hash_b" * 8)
        proof = agg.generate_proof("org-1")
        assert proof is not None

        d = proof.to_dict()
        assert d["org_id"] == "org-1"
        assert d["org_count"] == 2
        assert d["federated_root_hash"] is not None

        restored = FederatedProof.from_dict(d)
        assert restored.verify() is True
        assert restored.org_id == proof.org_id
        assert restored.federated_root_hash == proof.federated_root_hash

    def test_json_roundtrip(self) -> None:
        agg = FederatedMerkleAggregator()
        agg.submit_root("org-1", "hash_a" * 8)
        proof = agg.generate_proof("org-1")
        assert proof is not None

        json_str = proof.to_json()
        restored = FederatedProof.from_json(json_str)
        assert restored.verify() is True
        assert restored.org_id == "org-1"

    def test_file_roundtrip(self, tmp_path) -> None:
        agg = FederatedMerkleAggregator()
        agg.submit_root("org-1", "hash_a" * 8)
        proof = agg.generate_proof("org-1")
        assert proof is not None

        f = tmp_path / "proof.json"
        proof.to_file(f)
        restored = FederatedProof.from_file(f)
        assert restored.verify() is True
        assert restored.org_root_hash == "hash_a" * 8

    def test_sign_and_verify(self) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        kp = Ed25519KeyPair.generate()
        agg = FederatedMerkleAggregator()
        agg.submit_root("org-1", "hash_a" * 8)
        proof = agg.generate_proof("org-1")
        assert proof is not None

        proof.sign(kp)
        d = proof.to_dict()
        assert d["ed25519_signature"] is not None
        assert d["signer_fingerprint"] == kp.fingerprint

        assert proof.verify_signature(kp.public_key_pem) is True

    def test_verify_signature_wrong_key(self) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        kp = Ed25519KeyPair.generate()
        wrong_kp = Ed25519KeyPair.generate()
        agg = FederatedMerkleAggregator()
        agg.submit_root("org-1", "hash_a" * 8)
        proof = agg.generate_proof("org-1")
        assert proof is not None

        proof.sign(kp)
        assert proof.verify_signature(wrong_kp.public_key_pem) is False

    def test_verify_signature_no_signature(self) -> None:
        agg = FederatedMerkleAggregator()
        agg.submit_root("org-1", "hash_a" * 8)
        proof = agg.generate_proof("org-1")
        assert proof is not None

        assert proof.verify_signature("any_pem") is False
