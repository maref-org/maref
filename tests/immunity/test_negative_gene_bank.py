import time

import pytest

from maref.immunity.negative_gene_bank import (
    GenePattern,
    GeneVariant,
    NegativeGene,
    NegativeGeneBank,
)


@pytest.fixture
def bank():
    with NegativeGeneBank(":memory:") as b:
        yield b


def _sample_gene(seed: int = 1) -> NegativeGene:
    return NegativeGene(
        gene_id=f"NEG-TEST-{seed:04d}",
        cwe_id="CWE-295",
        risk_level="HIGH",
        severity=8,
        blocked=True,
        title=f"Test Gene {seed}",
        description=f"Description for test gene {seed}",
        source="test",
        first_seen=time.time(),
        patterns=[
            GenePattern("", "", "regex", rf"verify\s*=\s*(False|{seed})", "primary", 1.0),
        ],
        variants=[
            GeneVariant("", "", "python", f"requests.get(url, verify={seed})"),
        ],
    )


# ── CRUD ─────────────────────────────────────────────────────────────────


class TestStoreAndGet:
    def test_store_and_retrieve(self, bank):
        g = _sample_gene(1)
        gid = bank.store_gene(g)
        retrieved = bank.get_gene(gid)
        assert retrieved is not None
        assert retrieved.title == "Test Gene 1"
        assert retrieved.cwe_id == "CWE-295"
        assert retrieved.hmac_signature != ""

    def test_store_generates_id(self, bank):
        g = NegativeGene("", "CWE-79", "CRITICAL", 10, True, "XSS", "desc", "test", time.time())
        gid = bank.store_gene(g)
        assert gid.startswith("NEG-")

    def test_store_updates_existing(self, bank):
        g = _sample_gene(2)
        gid = bank.store_gene(g)
        g.title = "Updated Title"
        bank.store_gene(g)
        retrieved = bank.get_gene(gid)
        assert retrieved is not None
        assert retrieved.title == "Updated Title"

    def test_get_nonexistent(self, bank):
        assert bank.get_gene("NEG-NONEXIST") is None


class TestDelete:
    def test_delete_existing(self, bank):
        gid = bank.store_gene(_sample_gene(3))
        assert bank.delete_gene(gid) is True
        assert bank.get_gene(gid) is None

    def test_delete_nonexistent(self, bank):
        assert bank.delete_gene("NEG-NONEXIST") is False


# ── Query ────────────────────────────────────────────────────────────────


class TestQuery:
    def test_query_by_cwe(self, bank):
        bank.store_gene(_sample_gene(10))
        bank.store_gene(_sample_gene(11))
        results = bank.query_by_cwe("CWE-295")
        assert len(results) >= 2

    def test_query_by_pattern(self, bank):
        bank.store_gene(_sample_gene(20))
        results = bank.query_by_pattern("verify")
        assert len(results) >= 1

    def test_query_by_pattern_requests_get(self, bank):
        g = NegativeGene(
            "",
            "CWE-295",
            "HIGH",
            9,
            True,
            "requests.get without verify",
            "desc",
            "test",
            time.time(),
            patterns=[GenePattern("", "", "regex", r"requests.get", "primary", 1.0)],
        )
        bank.store_gene(g)
        results = bank.query_by_pattern("requests.get")
        assert len(results) >= 1

    def test_query_by_risk(self, bank):
        bank.store_gene(_sample_gene(30))
        results = bank.query_by_risk("HIGH", blocked_only=True)
        assert len(results) >= 1

    def test_query_by_risk_unblocked(self, bank):
        g = _sample_gene(31)
        g.blocked = False
        bank.store_gene(g)
        results = bank.query_by_risk("HIGH", blocked_only=False)
        hits = [r for r in results if not r.blocked]
        assert len(hits) >= 1

    def test_query_by_source(self, bank):
        bank.store_gene(_sample_gene(40))
        results = bank.query_by_source("test")
        assert len(results) >= 1

    def test_search_fulltext(self, bank):
        bank.store_gene(_sample_gene(50))
        results = bank.search("Test Gene 50")
        assert len(results) >= 1

    def test_query_all(self, bank):
        for i in range(5):
            bank.store_gene(_sample_gene(60 + i))
        results = bank.query_all(limit=10)
        assert len(results) >= 5

    def test_query_all_pagination(self, bank):
        for i in range(10):
            bank.store_gene(_sample_gene(70 + i))
        page1 = bank.query_all(limit=5, offset=0)
        page2 = bank.query_all(limit=5, offset=5)
        assert len(page1) == 5
        assert len(page2) >= 5
        assert page1[0].gene_id != page2[0].gene_id


# ── Stats ────────────────────────────────────────────────────────────────


class TestStats:
    def test_count_by_cwe(self, bank):
        bank.store_gene(_sample_gene(80))
        stats = bank.count_by_cwe()
        assert "CWE-295" in stats

    def test_count_by_risk(self, bank):
        bank.store_gene(_sample_gene(81))
        stats = bank.count_by_risk()
        assert "HIGH" in stats

    def test_gene_count(self, bank):
        bank.store_gene(_sample_gene(82))
        assert bank.gene_count() >= 1

    def test_top_blocked_patterns(self, bank):
        bank.store_gene(_sample_gene(83))
        top = bank.top_blocked_patterns(limit=5)
        # top is list of (pattern, count) tuples
        assert len(top) >= 1


# ── Integrity ────────────────────────────────────────────────────────────


class TestIntegrity:
    def test_integrity_passes_clean(self, bank):
        bank.store_gene(_sample_gene(90))
        ok, tampered = bank.verify_integrity()
        assert ok is True
        assert tampered == []

    def test_integrity_detects_tamper(self, bank):
        gid = bank.store_gene(_sample_gene(91))
        # simulate tamper via raw SQL
        bank._conn.execute("UPDATE negative_genes SET title='EVIL' WHERE gene_id=?", (gid,))
        bank._conn.commit()
        ok, tampered = bank.verify_integrity()
        assert ok is False
        assert gid in tampered


# ── Variant ──────────────────────────────────────────────────────────────


class TestVariant:
    def test_register_variant(self, bank):
        g = _sample_gene(100)
        gid = bank.store_gene(g)
        v = GeneVariant("", "", "python", "requests.get(url, verify=0)")
        bank.register_variant(gid, v)
        retrieved = bank.get_gene(gid)
        assert retrieved is not None
        assert len(retrieved.variants) >= 1

    def test_increment_occurrence(self, bank):
        g = _sample_gene(101)
        gid = bank.store_gene(g)
        bank.increment_occurrence(gid)
        retrieved = bank.get_gene(gid)
        assert retrieved is not None
        assert retrieved.occurrences >= 2

    def test_increment_occurrence_preserves_hmac(self, bank):
        gid = bank.store_gene(_sample_gene(102))
        bank.increment_occurrence(gid)
        ok, tampered = bank.verify_integrity()
        assert ok is True, f"HMAC broken after increment: {tampered}"


# ── Maintenance ──────────────────────────────────────────────────────────


class TestMaintenance:
    def test_purge_stale(self, bank):
        old = NegativeGene(
            "NEG-OLD-001",
            "CWE-999",
            "LOW",
            1,
            False,
            "Old Gene",
            "Should be purged",
            "test",
            first_seen=time.time() - (800 * 86400),  # > 730d
        )
        bank.store_gene(old)
        fresh = _sample_gene(110)
        bank.store_gene(fresh)
        purged = bank.purge_stale()
        assert purged >= 1
        # Verify remaining genes have valid HMAC (0.1-A4: audit chain preserved)
        ok, tampered = bank.verify_integrity()
        assert ok is True, f"Integrity broken after purge: {tampered}"

    def test_close_and_reopen(self):
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        b1 = NegativeGeneBank(db_path)
        g = _sample_gene(120)
        gid = b1.store_gene(g)
        b1.close()

        b2 = NegativeGeneBank(db_path)
        retrieved = b2.get_gene(gid)
        b2.close()

        assert retrieved is not None
        assert retrieved.title == "Test Gene 120"
        import os

        os.unlink(db_path)


# ── Edge Cases ───────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_database(self, bank):
        assert bank.gene_count() == 0
        assert bank.query_all() == []
        assert bank.search("anything") == []
        ok, _ = bank.verify_integrity()
        assert ok is True

    def test_variant_detection(self, bank):
        g = _sample_gene(130)
        gid = bank.store_gene(g)
        v = GeneVariant("", "", "python", "requests.get(url, verify=False)")
        bank.register_variant(gid, v)
        retrieved = bank.get_gene(gid)
        assert retrieved is not None
        # should have original + newly added variant
        assert len(retrieved.variants) >= 1
