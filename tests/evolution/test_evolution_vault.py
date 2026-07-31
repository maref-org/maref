from __future__ import annotations

from pathlib import Path

from maref.evolution.evolution_vault import EvolutionVault


def test_evolution_vault_persists_daily_artifacts(tmp_path: Path) -> None:
    vault = EvolutionVault(base_dir=tmp_path)
    day = vault.start_day("2026-06-19")
    vault.write_metrics_snapshot(day, {"fnr": 0.02, "coverage": 80.0})
    vault.write_experiment_result(day, {"stop_reason": "converged"})
    vault.write_daily_report("2026-06-19", "# Report")
    vault.write_next_plan(day, {"next": ["Task 12"]})

    assert (day / "metrics_snapshot.yaml").exists()
    assert (day / "experiment.yaml").exists()
    assert (day / "report.yaml").exists()
    assert (day / "next_plan.yaml").exists()


def test_evolution_vault_load_day_aggregates_artifacts(tmp_path: Path) -> None:
    vault = EvolutionVault(base_dir=tmp_path)
    day = vault.start_day("2026-06-19")
    vault.write_metrics_snapshot(day, {"fnr": 0.02, "coverage": 80.0})
    vault.write_next_plan(day, {"next": ["Task 12"]})

    loaded = vault.load_day("2026-06-19")

    assert loaded["metrics_snapshot"] == {"fnr": 0.02, "coverage": 80.0}
    assert loaded["next_plan"] == {"next": ["Task 12"]}


def test_evolution_vault_load_day_missing_day_returns_empty(tmp_path: Path) -> None:
    vault = EvolutionVault(base_dir=tmp_path)

    assert vault.load_day("2099-01-01") == {}
