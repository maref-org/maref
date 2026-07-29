"""Tests for FederatedAuditStore — SQLite persistence with restart consistency."""

from __future__ import annotations

import hashlib

from maref.eivl.federated_merkle import FederatedMerkleAggregator
from maref.eivl.federated_store import FederatedAuditStore


def _fake_hash(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


H1 = _fake_hash("org-1")
H2 = _fake_hash("org-2")
H3 = _fake_hash("org-3")


class TestFederatedAuditStore:
    def test_submit_and_read(self, tmp_path) -> None:
        db = tmp_path / "test.db"
        store = FederatedAuditStore(db)
        store.submit_root("org-1", H1, tree_size=10)
        assert store.get_federated_root() == H1
        assert store.summary()["org_count"] == 1
        assert store.summary()["total_evidence_count"] == 10

    def test_multiple_orgs(self, tmp_path) -> None:
        db = tmp_path / "test.db"
        store = FederatedAuditStore(db)
        store.submit_root("org-1", H1, tree_size=10)
        store.submit_root("org-2", H2, tree_size=20)
        root = store.get_federated_root()
        assert root is not None
        assert root != H1
        assert store.summary()["org_count"] == 2

    def test_restart_consistency_same_root(self, tmp_path) -> None:
        db = tmp_path / "test.db"
        store1 = FederatedAuditStore(db)
        store1.submit_root("org-1", H1, tree_size=10)
        store1.submit_root("org-2", H2, tree_size=20)
        root1 = store1.get_federated_root()

        store2 = FederatedAuditStore(db)
        root2 = store2.get_federated_root()
        assert root2 == root1
        assert store2.summary()["org_count"] == 2
        assert store2.assert_consistent()

    def test_restart_with_proof(self, tmp_path) -> None:
        db = tmp_path / "test.db"
        store1 = FederatedAuditStore(db)
        store1.submit_root("org-1", H1)
        store1.submit_root("org-2", H2)
        store1.submit_root("org-3", H3)
        proof1 = store1.generate_proof("org-2")
        assert proof1 is not None
        assert proof1.verify()

        store2 = FederatedAuditStore(db)
        proof2 = store2.generate_proof("org-2")
        assert proof2 is not None
        assert proof2.verify()
        assert proof2.federated_root_hash == proof1.federated_root_hash

    def test_restart_after_remove(self, tmp_path) -> None:
        db = tmp_path / "test.db"
        store1 = FederatedAuditStore(db)
        store1.submit_root("org-1", H1)
        store1.submit_root("org-2", H2)
        store1.remove_org("org-1")
        root1 = store1.get_federated_root()

        store2 = FederatedAuditStore(db)
        assert store2.summary()["org_count"] == 1
        assert store2.get_federated_root() == root1

    def test_restart_after_update(self, tmp_path) -> None:
        db = tmp_path / "test.db"
        store1 = FederatedAuditStore(db)
        store1.submit_root("org-1", H1)
        store1.submit_root("org-2", H2)
        store1.submit_root("org-1", H1 + "-v2")
        root1 = store1.get_federated_root()

        store2 = FederatedAuditStore(db)
        assert store2.summary()["org_count"] == 2
        assert store2.assert_consistent()
        assert store2.get_federated_root() == root1

    def test_multi_restart_cycles(self, tmp_path) -> None:
        db = tmp_path / "test.db"
        store = FederatedAuditStore(db)
        store.submit_root("org-1", H1)
        for i in range(5):
            store.submit_root(f"org-{i}", _fake_hash(f"org-{i}"))
            store = FederatedAuditStore(db)
            assert store.assert_consistent()
        assert store.summary()["org_count"] == 5  # org-1 + org-0..3 (org-1 updated in loop, not duplicate)

    def test_empty_store(self, tmp_path) -> None:
        db = tmp_path / "test.db"
        store = FederatedAuditStore(db)
        assert store.get_federated_root() is None
        assert store.summary()["org_count"] == 0
        assert store.assert_consistent()

    def test_assert_consistent_detects_tamper(self, tmp_path) -> None:
        db = tmp_path / "test.db"
        store = FederatedAuditStore(db)
        store.submit_root("org-1", H1)

        store2 = FederatedAuditStore(db)
        assert store2.assert_consistent()

    def test_generate_proof_after_restart(self, tmp_path) -> None:
        db = tmp_path / "test.db"
        store1 = FederatedAuditStore(db)
        store1.submit_root("org-1", H1)
        store1.submit_root("org-2", H2)
        store1.submit_root("org-3", H3)

        store2 = FederatedAuditStore(db)
        for org in ["org-1", "org-2", "org-3"]:
            proof = store2.generate_proof(org)
            assert proof is not None
            assert proof.verify(), f"Proof for {org} failed"

    def test_remove_unknown_org(self, tmp_path) -> None:
        db = tmp_path / "test.db"
        store = FederatedAuditStore(db)
        assert store.remove_org("nonexistent") is False

    def test_json_export_import(self, tmp_path) -> None:
        db = tmp_path / "test.db"
        json_path = tmp_path / "export.json"

        store1 = FederatedAuditStore(db)
        store1.submit_root("org-1", H1, tree_size=10)
        store1.submit_root("org-2", H2, tree_size=20)
        store1.export_json(json_path)

        loaded = FederatedMerkleAggregator.load_state(json_path)
        assert loaded.summary()["org_count"] == 2
        assert loaded.get_federated_root() == store1.get_federated_root()

    def test_json_import_to_store(self, tmp_path) -> None:
        db = tmp_path / "test.db"
        json_path = tmp_path / "export.json"

        agg = FederatedMerkleAggregator()
        agg.submit_root("org-1", H1, tree_size=10)
        agg.submit_root("org-2", H2, tree_size=20)
        agg.save_state(json_path)

        store = FederatedAuditStore.import_json(json_path, db)
        assert store.summary()["org_count"] == 2
        assert store.assert_consistent()

    def test_concurrent_persistence(self, tmp_path) -> None:
        import threading

        db = tmp_path / "test.db"
        store = FederatedAuditStore(db)

        errors: list[Exception] = []

        def _worker(i: int) -> None:
            try:
                store.submit_root(
                    f"org-{i}", _fake_hash(f"org-{i}"), tree_size=i
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent persistence errors: {errors}"
        assert store.summary()["org_count"] == 30

        store2 = FederatedAuditStore(db)
        assert store2.summary()["org_count"] == 30
        assert store2.assert_consistent()

    def test_list_orgs(self, tmp_path) -> None:
        db = tmp_path / "test.db"
        store = FederatedAuditStore(db)
        store.submit_root("org-1", H1, metadata={"name": "Acme"})
        store.submit_root("org-2", H2)

        orgs = store.list_orgs()
        assert len(orgs) == 2
        assert orgs[0].org_id == "org-1"
        assert orgs[0].metadata.get("name") == "Acme"

    def test_get_org_entry(self, tmp_path) -> None:
        db = tmp_path / "test.db"
        store = FederatedAuditStore(db)
        store.submit_root("org-1", H1, tree_size=42)
        entry = store.get_org_entry("org-1")
        assert entry is not None
        assert entry.org_id == "org-1"
        assert entry.tree_size == 42

    def test_get_org_entry_nonexistent(self, tmp_path) -> None:
        db = tmp_path / "test.db"
        store = FederatedAuditStore(db)
        assert store.get_org_entry("ghost") is None

    def test_verify_inclusion(self, tmp_path) -> None:
        db = tmp_path / "test.db"
        store = FederatedAuditStore(db)
        store.submit_root("org-1", H1)
        result = store.verify_org_inclusion("org-1")
        assert result["valid"] is True
        assert result["org_id"] == "org-1"

    def test_verify_inclusion_unknown(self, tmp_path) -> None:
        db = tmp_path / "test.db"
        store = FederatedAuditStore(db)
        result = store.verify_org_inclusion("ghost")
        assert result["valid"] is False
