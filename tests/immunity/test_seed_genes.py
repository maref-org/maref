import time

import pytest

from maref.immunity.negative_gene_bank import NegativeGene, NegativeGeneBank
from maref.immunity.seed_genes import BUILTIN_SEED_SOURCES, seed_all


@pytest.fixture
def bank():
    return NegativeGeneBank(":memory:")


class TestSeedCount:
    def test_seed_all_count(self, bank):
        count = seed_all(bank)
        assert count >= 500, f"Seed count {count} < 500"

    def test_seed_all_queries(self, bank):
        count = seed_all(bank)
        assert bank.gene_count() == count


class TestSeedCategories:
    def test_cwe_genes_present(self, bank):
        seed_all(bank)
        cwe_genes = bank.query_by_source("cwe")
        assert len(cwe_genes) >= 80  # 92 expected

    def test_veracode_genes_present(self, bank):
        seed_all(bank)
        veracode_genes = bank.query_by_source("veracode")
        assert len(veracode_genes) >= 15

    def test_coderabbit_genes_present(self, bank):
        seed_all(bank)
        rabbit_genes = bank.query_by_source("coderabbit")
        assert len(rabbit_genes) >= 15

    def test_curl_genes_present(self, bank):
        seed_all(bank)
        curl_genes = bank.query_by_source("curl")
        assert len(curl_genes) >= 5

    def test_supply_chain_genes_present(self, bank):
        seed_all(bank)
        sc_genes = bank.query_by_source("owasp")
        assert len(sc_genes) >= 10


class TestSeedQuality:
    def test_every_gene_has_cwe(self, bank):
        seed_all(bank)
        for gene in bank.query_all():
            assert gene.cwe_id != "", f"Gene {gene.gene_id} missing CWE ID"

    def test_every_gene_has_risk_level(self, bank):
        seed_all(bank)
        for gene in bank.query_all():
            assert gene.risk_level in (
                "CRITICAL",
                "HIGH",
                "MEDIUM",
                "LOW",
            ), f"Gene {gene.gene_id} invalid risk {gene.risk_level}"

    def test_every_blocked_gene_has_regex_pattern(self, bank):
        seed_all(bank)
        for gene in bank.query_all():
            if gene.blocked:
                assert len(gene.patterns) > 0, f"Blocked gene {gene.gene_id} has no patterns"

    def test_hmac_integrity(self, bank):
        seed_all(bank)
        ok, tampered = bank.verify_integrity()
        assert ok is True, f"Tampered genes: {tampered}"

    def test_seed_genes_have_variants(self, bank):
        """0.3-A3: At least some seed genes have variant coverage."""
        seed_all(bank)
        genes = bank.query_all(limit=500)
        genes_with_variants = [g for g in genes if len(g.variants) >= 2]
        assert (
            len(genes_with_variants) >= 2
        ), f"Only {len(genes_with_variants)} genes have >=2 variants"

    def test_blocked_status_distinction(self, bank):
        """0.3-A4: Security genes -> blocked=True, quality genes -> blocked=False."""
        seed_all(bank)
        genes = bank.query_all()
        for g in genes:
            if g.risk_level == "CRITICAL":
                assert g.blocked is True, f"{g.cwe_id} (CRITICAL) should be blocked=True"
            elif g.risk_level == "LOW":
                assert (
                    g.blocked is False
                ), f"{g.cwe_id} (LOW) should be blocked=False (quality warning)"

    def test_seed_sources_registered(self, bank):
        seed_all(bank)
        sources = bank.count_by_source()
        for src_name in BUILTIN_SEED_SOURCES:
            assert src_name in sources or src_name in {
                s.lower() for s in sources
            }, f"Source {src_name} not found in {set(sources.keys())}"


class TestSeedExtend:
    def test_can_add_after_seed(self, bank):
        seed_all(bank)
        before = bank.gene_count()
        g = NegativeGene(
            "", "CWE-001", "LOW", 1, False, "Extra Gene", "Extra", "manual", time.time()
        )
        bank.store_gene(g)
        assert bank.gene_count() == before + 1
