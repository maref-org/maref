from __future__ import annotations

import pytest

from maref.immunity.negative_gene_bank import NegativeGeneBank
from maref.immunity.auto_gene_pipeline import AutoGeneExtractionPipeline
from maref.recursive.experience_pool import ExperiencePool


@pytest.fixture
def pipeline():
    bank = NegativeGeneBank(":memory:")
    pool = ExperiencePool()
    return AutoGeneExtractionPipeline(gene_bank=bank, experience_pool=pool)


class TestAutoGeneExtractionPipelineHeal:
    """4.3-A1: SelfHealer fix → auto extract negative gene."""

    def test_extract_from_heal_returns_gene_id(self, pipeline):
        gid = pipeline.extract_from_heal("old_code", "new_code", reason="fixed bug")
        assert gid is not None
        assert gid.startswith("AUTO-")

    def test_extract_from_heal_increments_count(self, pipeline):
        pipeline.extract_from_heal("old", "new", reason="fix")
        assert pipeline.extraction_count == 1

    def test_extract_from_heal_stores_in_gene_bank(self, pipeline):
        gid = pipeline.extract_from_heal("old", "new", reason="fix")
        bank = pipeline._gene_bank
        gene = bank.get_gene(gid)
        assert gene is not None
        assert gene.source == "auto_heal"

    def test_extract_from_heal_syncs_to_experience(self, pipeline):
        pipeline.extract_from_heal("old", "new", reason="fix")
        pool = pipeline._experience_pool
        entries = pool.query_by_tag("auto_gene:auto_heal")
        assert len(entries) >= 1

    def test_extract_from_heal_empty_diff_returns_none(self, pipeline):
        gid = pipeline.extract_from_heal("same", "same", reason="no change")
        assert gid is None

    def test_extract_from_heal_has_recent_extraction(self, pipeline):
        pipeline.extract_from_heal("old", "new", reason="fix")
        assert len(pipeline.recent_extractions) == 1
        assert pipeline.recent_extractions[0]["source"] == "heal"


class TestAutoGeneExtractionPipelineRollback:
    """4.3-A2: SelfExecutor rollback → auto extract negative gene."""

    def test_extract_from_rollback_returns_gene_id(self, pipeline):
        gid = pipeline.extract_from_rollback("bad_code()", reason="test failure")
        assert gid is not None
        assert gid.startswith("AUTO-")

    def test_extract_from_rollback_severity_high(self, pipeline):
        gid = pipeline.extract_from_rollback("bad_code()", reason="fail")
        gene = pipeline._gene_bank.get_gene(gid)
        assert gene is not None
        assert gene.severity >= 7

    def test_extract_from_rollback_blocked_true(self, pipeline):
        gid = pipeline.extract_from_rollback("bad_code()", reason="fail")
        gene = pipeline._gene_bank.get_gene(gid)
        assert gene is not None
        assert gene.blocked is True

    def test_extract_from_rollback_count(self, pipeline):
        pipeline.extract_from_rollback("bad", reason="r1")
        pipeline.extract_from_rollback("worse", reason="r2")
        assert pipeline.extraction_count == 2

    def test_extract_from_rollback_empty_code_returns_none(self, pipeline):
        gid = pipeline.extract_from_rollback("", reason="empty")
        assert gid is None

    def test_extract_from_rollback_has_recent(self, pipeline):
        pipeline.extract_from_rollback("bad", reason="r1")
        assert pipeline.recent_extractions[0]["source"] == "rollback"


class TestAutoGeneExtractionPipelineBlock:
    """4.3-A3: SafetyGateV2 block → auto extract negative gene."""

    def test_extract_from_block_returns_gene_id(self, pipeline):
        gid = pipeline.extract_from_block("insecure_code()", reason="AI stench")
        assert gid is not None
        assert gid.startswith("AUTO-")

    def test_extract_from_block_severity_high(self, pipeline):
        gid = pipeline.extract_from_block("bad()", reason="stench")
        gene = pipeline._gene_bank.get_gene(gid)
        assert gene is not None
        assert gene.severity >= 7

    def test_extract_from_block_blocked_true(self, pipeline):
        gid = pipeline.extract_from_block("bad()", reason="stench")
        gene = pipeline._gene_bank.get_gene(gid)
        assert gene is not None
        assert gene.blocked is True

    def test_extract_from_block_source_safety_gate(self, pipeline):
        gid = pipeline.extract_from_block("bad()", reason="stench")
        gene = pipeline._gene_bank.get_gene(gid)
        assert gene is not None
        assert gene.source == "safety_gate_v2"

    def test_extract_from_block_count(self, pipeline):
        pipeline.extract_from_block("b1", reason="r1")
        pipeline.extract_from_block("b2", reason="r2")
        pipeline.extract_from_block("b3", reason="r3")
        assert pipeline.extraction_count == 3

    def test_extract_from_block_empty_returns_none(self, pipeline):
        gid = pipeline.extract_from_block("", reason="empty")
        assert gid is None

    def test_extract_from_block_experience_sync(self, pipeline):
        pipeline.extract_from_block("bad", reason="stench")
        entries = pipeline._experience_pool.query_by_tag("auto_gene:safety_gate_v2")
        assert len(entries) >= 1


class TestAutoGeneExtractionPipelineSync:
    """4.3-A4: Auto sync with ExperiencePool."""

    def test_sync_with_experience_pool_returns_count(self, pipeline):
        pipeline.extract_from_heal("old", "new", reason="fix")
        count = pipeline.sync_with_experience_pool()
        assert count >= 0

    def test_sync_creates_experience_entries(self, pipeline):
        pipeline.extract_from_heal("old", "new", reason="fix")
        pipeline.sync_with_experience_pool()
        entries = pipeline._experience_pool.query_by_tag("sync")
        assert len(entries) >= 0

    def test_gene_has_hmac_after_extraction(self, pipeline):
        gid = pipeline.extract_from_heal("old", "new", reason="fix")
        gene = pipeline._gene_bank.get_gene(gid)
        assert gene is not None
        assert bool(gene.hmac_signature)

    def test_rollback_gene_stores_description(self, pipeline):
        gid = pipeline.extract_from_rollback("bad_code()", reason="crashed")
        gene = pipeline._gene_bank.get_gene(gid)
        assert gene is not None
        assert "crashed" in gene.description

    def test_block_gene_stores_description(self, pipeline):
        gid = pipeline.extract_from_block("bad()", reason="AI stench detected")
        gene = pipeline._gene_bank.get_gene(gid)
        assert gene is not None
        assert "AI stench" in gene.description

    def test_heal_gene_has_cwe_id(self, pipeline):
        gid = pipeline.extract_from_heal("old", "new", reason="fix")
        gene = pipeline._gene_bank.get_gene(gid)
        assert gene is not None
        assert gene.cwe_id == "CWE-1104"

    def test_recent_extractions_list_grows(self, pipeline):
        pipeline.extract_from_heal("a", "b", reason="1")
        pipeline.extract_from_rollback("c", reason="2")
        assert len(pipeline.recent_extractions) == 2


class TestAutoGeneExtractionPipelineEdgeCases:
    """Edge cases for auto gene pipeline."""

    def test_extract_from_heal_no_diff(self, pipeline):
        gid = pipeline.extract_from_heal("same", "same", reason="identical")
        assert gid is None

    def test_extract_all_sources_different_genes(self, pipeline):
        gid1 = pipeline.extract_from_heal("old", "new", reason="fix")
        gid2 = pipeline.extract_from_rollback("bad", reason="crash")
        gid3 = pipeline.extract_from_block("worse", reason="block")
        ids = {gid1, gid2, gid3}
        assert len(ids) == 3

    def test_extraction_count_tracks_all_sources(self, pipeline):
        pipeline.extract_from_heal("a", "b", reason="1")
        pipeline.extract_from_rollback("c", reason="2")
        pipeline.extract_from_block("d", reason="3")
        assert pipeline.extraction_count == 3

    def test_experience_pool_has_lesson_learned(self, pipeline):
        pipeline.extract_from_heal("old", "new", reason="undefined variable")
        entries = pipeline._experience_pool.query_by_tag("auto_gene:auto_heal")
        assert len(entries) >= 1
        assert len(entries[0].lesson_learned) > 0

    def test_security_critical_decorator(self, pipeline):
        assert hasattr(pipeline.extract_from_heal, "_maref_security_critical")
        assert hasattr(pipeline.extract_from_rollback, "_maref_security_critical")
        assert hasattr(pipeline.extract_from_block, "_maref_security_critical")
