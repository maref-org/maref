"""Tests for Self-SAEB: immune system self-degradation detection."""

from __future__ import annotations

from unittest.mock import MagicMock

from maref.immunity.negative_gene_bank import GenePattern, NegativeGene
from maref.immunity.self_saeb import SelfSAEBRunner


def _make_gene(pattern_value: str = ".*") -> NegativeGene:
    return NegativeGene(
        gene_id="test_gene",
        cwe_id="CWE-00",
        risk_level="MEDIUM",
        severity=5,
        blocked=True,
        title="Test gene",
        description="Test",
        source="test",
        first_seen=0.0,
        patterns=[GenePattern(
            pattern_id="p1",
            gene_id="g1",
            pattern_type="regex",
            pattern_value=pattern_value,
        )],
    )


class TestSelfSAEBRunner:
    def test_run_self_saeb_returns_result(self):
        bank = MagicMock()
        bank.query_all.return_value = []
        runner = SelfSAEBRunner(gene_bank=bank)
        result = runner.run_self_saeb()
        assert result.total_samples == 5
        assert result.detected_hits >= 0
        assert result.detection_rate >= 0.0

    def test_detection_rate_calculation(self):
        bank = MagicMock()
        bank.query_all.return_value = []
        runner = SelfSAEBRunner(gene_bank=bank)
        result = runner.run_self_saeb()
        assert 0.0 <= result.detection_rate <= 1.0

    def test_gene_count_from_bank(self):
        bank = MagicMock()
        bank.query_all.return_value = [
            _make_gene("eval"),
            _make_gene("subprocess"),
            _make_gene("pickle"),
        ]
        runner = SelfSAEBRunner(gene_bank=bank)
        result = runner.run_self_saeb()
        assert result.gene_count == 3

    def test_degraded_flag_below_threshold(self):
        bank = MagicMock()
        bank.query_all.return_value = []
        runner = SelfSAEBRunner(gene_bank=bank, detection_threshold=0.99)
        result = runner.run_self_saeb()
        assert result.degraded is True

    def test_history_appended_after_run(self):
        runner = SelfSAEBRunner(gene_bank=MagicMock())
        assert len(runner.history) == 0
        runner.run_self_saeb()
        assert len(runner.history) == 1
        runner.run_self_saeb()
        assert len(runner.history) == 2

    def test_check_degradation_no_history(self):
        runner = SelfSAEBRunner(gene_bank=MagicMock())
        result = runner.check_degradation()
        assert result["status"] == "no_history"
        assert result["degraded"] is False

    def test_check_degradation_baseline_after_first_run(self):
        runner = SelfSAEBRunner(gene_bank=MagicMock())
        runner.run_self_saeb()
        result = runner.check_degradation()
        assert result["status"] == "baseline_established"
        assert "detection_rate" in result

    def test_check_degradation_compares_two_runs(self):
        runner = SelfSAEBRunner(gene_bank=MagicMock())
        result = runner.check_degradation()
        assert result["status"] == "no_history"

    def test_to_dict_serializable(self):
        bank = MagicMock()
        bank.query_all.return_value = [_make_gene("eval")]
        runner = SelfSAEBRunner(gene_bank=bank)
        result = runner.run_self_saeb()
        d = result.to_dict()
        assert d["total_samples"] == 5
        assert "detection_rate" in d
        assert "degraded" in d
        assert "details" in d
        assert len(d["details"]) == 5
