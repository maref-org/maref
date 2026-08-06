from __future__ import annotations

import json
import tempfile
from pathlib import Path

from maref.vault.evolution_vault import EvolutionVault, ExperimentRecord


class TestEvolutionVault:
    def test_record_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = EvolutionVault(vault_path=td)
            vault.record(ExperimentRecord(
                timestamp="2026-07-01T10:00:00",
                target="prompts/distill_v1.yaml",
                consistency_score=0.85,
                action="keep",
                dimensions={"correctness": 0.9, "testing": 0.8},
                notes="improved clarity",
            ))
            records = vault.load_all()
            assert len(records) == 1
            assert records[0].target == "prompts/distill_v1.yaml"
            assert records[0].consistency_score == 0.85
            assert records[0].action == "keep"
            assert records[0].dimensions["correctness"] == 0.9

    def test_load_empty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = EvolutionVault(vault_path=td)
            records = vault.load_all()
            assert records == []

    def test_multiple_records(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = EvolutionVault(vault_path=td)
            for i in range(5):
                vault.record(ExperimentRecord(
                    timestamp=f"2026-07-01T10:0{i}:00",
                    target="prompts/distill_v1.yaml",
                    consistency_score=0.7 + i * 0.05,
                    action="keep" if i % 2 == 0 else "discard",
                ))
            records = vault.load_all()
            assert len(records) == 5

    def test_get_trend_empty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = EvolutionVault(vault_path=td)
            trend = vault.get_trend("nonexistent")
            assert trend.total_runs == 0
            assert trend.score_trend == "stable"

    def test_get_trend_improving(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = EvolutionVault(vault_path=td)
            for i in range(10):
                vault.record(ExperimentRecord(
                    timestamp=f"2026-07-01T10:0{i}:00",
                    target="test_target",
                    consistency_score=0.5 + i * 0.04,
                    action="keep" if i > 3 else "discard",
                ))
            trend = vault.get_trend("test_target")
            assert trend.total_runs == 10
            assert trend.score_trend == "improving"
            assert trend.best_score > trend.avg_score

    def test_get_trend_declining(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = EvolutionVault(vault_path=td)
            for i in range(10):
                vault.record(ExperimentRecord(
                    timestamp=f"2026-07-01T10:0{i}:00",
                    target="test_target",
                    consistency_score=0.9 - i * 0.04,
                    action="discard",
                ))
            trend = vault.get_trend("test_target")
            assert trend.score_trend == "declining"

    def test_get_trend_stable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = EvolutionVault(vault_path=td)
            for i in range(10):
                vault.record(ExperimentRecord(
                    timestamp=f"2026-07-01T10:0{i}:00",
                    target="test_target",
                    consistency_score=0.75,
                    action="keep",
                ))
            trend = vault.get_trend("test_target")
            assert trend.score_trend == "stable"

    def test_all_targets(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = EvolutionVault(vault_path=td)
            vault.record(ExperimentRecord(timestamp="t1", target="a", consistency_score=0.5, action="keep"))
            vault.record(ExperimentRecord(timestamp="t2", target="b", consistency_score=0.6, action="discard"))
            vault.record(ExperimentRecord(timestamp="t3", target="a", consistency_score=0.7, action="keep"))
            targets = vault.all_targets()
            assert sorted(targets) == ["a", "b"]

    def test_summary_report(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = EvolutionVault(vault_path=td)
            for i in range(6):
                vault.record(ExperimentRecord(
                    timestamp=f"t{i}",
                    target="test_target",
                    consistency_score=0.5 + i * 0.05,
                    action="keep" if i % 2 == 0 else "discard",
                ))
            report = vault.summary_report()
            assert report["total_records"] == 6
            assert report["total_targets"] == 1
            assert report["keeps"] == 3
            assert report["discards"] == 3
            assert report["keep_rate"] == 0.5

    def test_generate_dashboard_html(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = EvolutionVault(vault_path=td)
            for i in range(5):
                vault.record(ExperimentRecord(
                    timestamp=f"2026-07-01T10:0{i}:00",
                    target="test_target",
                    consistency_score=0.7 + i * 0.02,
                    action="keep",
                ))
            html = vault.generate_dashboard_html(Path(td) / "dashboard.html")
            assert "EvolutionVault" in html
            assert "Score Timeline" in html
            assert "Action Distribution" in html
            assert "test_target" in html
            assert Path(td, "dashboard.html").exists()
