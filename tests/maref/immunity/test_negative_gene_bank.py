from __future__ import annotations

import time

from maref.immunity.negative_gene_bank import (
    GeneMapping,
    GenePattern,
    GeneVariant,
    NegativeGene,
    NegativeGeneBank,
    _compute_hash,
    _new_id,
)


class TestHelpers:
    def test_new_id(self) -> None:
        nid = _new_id()
        assert nid.startswith("NEG-")
        assert len(nid) > 4

    def test_new_id_custom_prefix(self) -> None:
        nid = _new_id(prefix="PAT")
        assert nid.startswith("PAT-")

    def test_compute_hash(self) -> None:
        result = _compute_hash("hello", b"secret-key")
        assert isinstance(result, str)
        assert len(result) == 64  # sha256 hexdigest


class TestGenePattern:
    def test_defaults(self) -> None:
        gp = GenePattern(
            pattern_id="p1",
            gene_id="g1",
            pattern_type="regex",
            pattern_value=".*",
        )
        assert gp.variant_group == "primary"
        assert gp.match_score == 1.0

    def test_custom(self) -> None:
        gp = GenePattern(
            pattern_id="p2",
            gene_id="g2",
            pattern_type="ast_node",
            pattern_value="Call",
            variant_group="secondary",
            match_score=0.75,
        )
        assert gp.variant_group == "secondary"
        assert gp.match_score == 0.75


class TestGeneVariant:
    def test_defaults(self) -> None:
        gv = GeneVariant(variant_id="v1", gene_id="g1")
        assert gv.language == "python"
        assert gv.variant_code == ""
        assert gv.detected_count == 0
        assert gv.last_detected_at is None


class TestGeneMapping:
    def test_defaults(self) -> None:
        gm = GeneMapping(mapping_id="m1", gene_id="g1", entity_type="file", entity_id="/path")
        assert gm.relation_type == "affected_by"
        assert gm.confidence == 0.8


class TestNegativeGene:
    def test_defaults(self) -> None:
        gene = NegativeGene(
            gene_id="g1",
            cwe_id="CWE-79",
            risk_level="HIGH",
            severity=7,
            blocked=True,
            title="XSS",
            description="Cross-site scripting",
            source="test",
            first_seen=time.time(),
        )
        assert gene.occurrences == 1
        assert gene.retention_days == 730
        assert gene.hmac_signature == ""
        assert gene.patterns == []

    def test_hmac_roundtrip(self) -> None:
        gene = NegativeGene(
            gene_id="g1",
            cwe_id="CWE-79",
            risk_level="HIGH",
            severity=7,
            blocked=True,
            title="XSS",
            description="Cross-site scripting",
            source="test",
            first_seen=1000.0,
        )
        key = b"test-hmac-key"
        gene.update_hmac(key)
        assert gene.hmac_signature != ""
        assert gene.verify_hmac(key) is True
        assert gene.verify_hmac(b"wrong-key") is False

    def test_with_patterns_and_variants(self) -> None:
        pat = GenePattern(pattern_id="p1", gene_id="g1", pattern_type="regex", pattern_value="alert")
        var = GeneVariant(variant_id="v1", gene_id="g1", language="javascript")
        gene = NegativeGene(
            gene_id="g2",
            cwe_id="CWE-89",
            risk_level="CRITICAL",
            severity=10,
            blocked=True,
            title="SQLi",
            description="SQL injection",
            source="test",
            first_seen=2000.0,
            patterns=[pat],
            variants=[var],
        )
        assert len(gene.patterns) == 1
        assert len(gene.variants) == 1


class TestNegativeGeneBank:
    def test_init_default(self) -> None:
        bank = NegativeGeneBank()
        assert bank._hmac_key is not None

    def test_store_and_get(self) -> None:
        bank = NegativeGeneBank()
        gene = NegativeGene(
            gene_id="",
            cwe_id="CWE-79",
            risk_level="HIGH",
            severity=7,
            blocked=True,
            title="XSS",
            description="XSS vuln",
            source="test",
            first_seen=1000.0,
        )
        gid = bank.store_gene(gene)
        assert gid
        retrieved = bank.get_gene(gid)
        assert retrieved is not None
        assert retrieved.title == "XSS"

    def test_store_and_delete(self) -> None:
        bank = NegativeGeneBank()
        gene = NegativeGene(
            gene_id="",
            cwe_id="CWE-89",
            risk_level="CRITICAL",
            severity=10,
            blocked=True,
            title="SQLi",
            description="SQLi vuln",
            source="test",
            first_seen=2000.0,
        )
        gid = bank.store_gene(gene)
        assert bank.delete_gene(gid) is True
        assert bank.delete_gene("nonexistent") is False

    def test_query_all(self) -> None:
        bank = NegativeGeneBank()
        gene = NegativeGene(
            gene_id="", cwe_id="CWE-79", risk_level="HIGH", severity=7,
            blocked=True, title="XSS", description="xss", source="src1",
            first_seen=1000.0,
        )
        bank.store_gene(gene)
        results = bank.query_all()
        assert len(results) >= 1

    def test_query_by_cwe(self) -> None:
        bank = NegativeGeneBank()
        gene = NegativeGene(
            gene_id="", cwe_id="CWE-79", risk_level="HIGH", severity=7,
            blocked=True, title="XSS", description="xss", source="src1",
            first_seen=1000.0,
        )
        bank.store_gene(gene)
        results = bank.query_by_cwe("CWE-79")
        assert len(results) >= 1
        assert bank.query_by_cwe("CWE-999") == []

    def test_query_by_risk(self) -> None:
        bank = NegativeGeneBank()
        gene = NegativeGene(
            gene_id="", cwe_id="CWE-79", risk_level="CRITICAL", severity=10,
            blocked=True, title="Test", description="desc", source="src1",
            first_seen=1000.0,
        )
        bank.store_gene(gene)
        results = bank.query_by_risk("CRITICAL")
        assert len(results) >= 1

    def test_query_by_source(self) -> None:
        bank = NegativeGeneBank()
        gene = NegativeGene(
            gene_id="", cwe_id="CWE-79", risk_level="HIGH", severity=7,
            blocked=True, title="XSS", description="xss", source="my-source",
            first_seen=1000.0,
        )
        bank.store_gene(gene)
        results = bank.query_by_source("my-source")
        assert len(results) >= 1

    def test_update_gene(self) -> None:
        bank = NegativeGeneBank()
        gene = NegativeGene(
            gene_id="", cwe_id="CWE-79", risk_level="HIGH", severity=7,
            blocked=True, title="XSS", description="xss", source="src",
            first_seen=1000.0,
        )
        gid = bank.store_gene(gene)
        gene.title = "XSS v2"
        bank.update_gene(gene)
        retrieved = bank.get_gene(gid)
        assert retrieved is not None
        assert retrieved.title == "XSS v2"

    def test_query_by_pattern(self) -> None:
        bank = NegativeGeneBank()
        pat = GenePattern(pattern_id="", gene_id="", pattern_type="regex", pattern_value="dangerous_func")
        gene = NegativeGene(
            gene_id="", cwe_id="CWE-79", risk_level="HIGH", severity=7,
            blocked=True, title="Test", description="desc", source="src",
            first_seen=1000.0, patterns=[pat],
        )
        bank.store_gene(gene)
        results = bank.query_by_pattern("dangerous")
        assert len(results) >= 1
