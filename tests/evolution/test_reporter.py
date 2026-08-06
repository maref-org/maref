from __future__ import annotations

import json
import tempfile
from pathlib import Path

from maref.evolution.metrics import (
    AcceptanceCriteria,
    CycleResult,
    EvolutionMetrics,
    EvolutionResult,
)
from maref.evolution.reporter import generate_cycle_report, generate_final_report


class TestGenerateCycleReport:
    def test_generates_csv_and_json(self, tmp_path: Path) -> None:
        em = EvolutionMetrics()
        em.fnr_series.extend([0.1, 0.2])
        em.fpr_series.extend([0.05, 0.06])
        em.entropy_series.extend([1, 2])
        em.transition_count_series.extend([8, 9])
        em.learning_rate_series.extend([0.02, 0.019])
        cr = CycleResult(cycle_id="c1", name="Baseline", rounds_completed=2, rounds_total=50, metrics=em, acceptance={"fnr": True}, passed=True)
        criteria = AcceptanceCriteria()
        result = generate_cycle_report(cr, criteria, tmp_path)
        assert result.exists()
        assert (tmp_path / "metrics.csv").exists()
        csv_content = (tmp_path / "metrics.csv").read_text()
        assert "round,fnr,fpr,entropy,transition_count,learning_rate" in csv_content
        assert "0.1" in csv_content
        summary = json.loads(result.read_text())
        assert summary["cycle_id"] == "c1"
        assert summary["passed"] is True

    def test_generates_with_partial_metrics(self, tmp_path: Path) -> None:
        em = EvolutionMetrics()
        em.fnr_series.extend([0.1])
        cr = CycleResult(cycle_id="c1", name="Partial", rounds_completed=1, rounds_total=50, metrics=em, acceptance={}, passed=False)
        criteria = AcceptanceCriteria()
        generate_cycle_report(cr, criteria, tmp_path)
        csv_content = (tmp_path / "metrics.csv").read_text()
        lines = csv_content.strip().split("\n")
        assert len(lines) == 2


class TestGenerateFinalReport:
    def test_generates_final_report(self, tmp_path: Path) -> None:
        em = EvolutionMetrics()
        em.fnr_series.extend([0.1, 0.2])
        em.fpr_series.extend([0.05, 0.06])
        cr = CycleResult(cycle_id="c1", name="Baseline", rounds_completed=2, rounds_total=50, metrics=em, acceptance={"fnr": True}, passed=True)
        result = EvolutionResult(cycles=[cr], stop_reason="normal_completion", total_rounds=2, all_passed=True)
        criteria = AcceptanceCriteria()
        report_path = generate_final_report(result, criteria, tmp_path)
        assert Path(report_path).exists()
        content = Path(report_path).read_text()
        assert "MAREF Recursive Evolution" in content
        assert "PASSED" in content
        assert "0.1000" in content

    def test_generates_failed_report(self, tmp_path: Path) -> None:
        em = EvolutionMetrics()
        cr = CycleResult(cycle_id="c1", name="Failed Cycle", rounds_completed=1, rounds_total=50, metrics=em, acceptance={"fnr": False}, passed=False)
        result = EvolutionResult(cycles=[cr], stop_reason="normal_completion", total_rounds=1, all_passed=False)
        criteria = AcceptanceCriteria()
        report_path = generate_final_report(result, criteria, tmp_path)
        content = Path(report_path).read_text()
        assert "FAILED" in content
