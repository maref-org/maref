from __future__ import annotations

from pathlib import Path

from maref.evolution.evolution_vault import EvolutionVault


def test_evolution_vault_persists_daily_artifacts(tmp_path: Path) -> None:
    vault = EvolutionVault(base_dir=tmp_path)
    day = vault.start_day("2026-06-19")
    vault.write_metrics_snapshot("2026-06-19", {"fnr": 0.02, "coverage": 80.0})
    vault.write_hypothesis_record("2026-06-19", {"id": "H1", "source": "percv"})
    vault.write_daily_report("2026-06-19", "# Report")
    vault.write_next_plan("2026-06-19", {"next": ["Task 12"]})

    assert (day / "metrics_snapshot.yaml").exists()
    assert (day / "hypotheses.yaml").exists()
    assert (day / "experiment_results.yaml").exists()
    assert (day / "daily_report.md").exists()
    assert (day / "next_plan.yaml").exists()


def test_evolution_vault_appends_hypothesis_records(tmp_path: Path) -> None:
    vault = EvolutionVault(base_dir=tmp_path)
    vault.write_hypothesis_record("2026-06-19", {"id": "H1"})
    vault.write_hypothesis_record("2026-06-19", {"id": "H2"})

    records = vault.load_day("2026-06-19")["hypotheses"]

    assert records == [{"id": "H1"}, {"id": "H2"}]
