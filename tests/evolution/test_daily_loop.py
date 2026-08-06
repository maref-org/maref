from __future__ import annotations

from pathlib import Path

from maref.evolution.daily_loop import DailyEvolutionLoop
from maref.evolution.real_metrics import RealMetrics


class FakeMetricsCollector:
    def collect_incremental(self) -> RealMetrics:
        return RealMetrics(
            fnr=0.01,
            fpr=0.02,
            test_pass_rate=0.99,
            coverage_pct=80.0,
            total_tests=100,
            import_time_ms=50.0,
            cb_state="CLOSED",
        )


def test_daily_loop_runs_all_required_phases_with_fakes(tmp_path: Path) -> None:
    loop = DailyEvolutionLoop(
        vault_dir=tmp_path,
        dry_run=True,
        metrics_collector=FakeMetricsCollector(),
    )

    result = loop.run_once()

    assert result.phases == [
        "environment_check",
        "data_collection",
        "trend_analysis",
        "hypothesis_generation",
        "constitution_review",
        "experiment_execution",
        "result_persistence",
        "next_planning",
    ]
    assert result.real_writes_enabled is False
    assert (tmp_path / result.day / "metrics_snapshot.yaml").exists()
    assert (tmp_path / result.day / "next_plan.yaml").exists()


def test_daily_loop_result_to_dict(tmp_path: Path) -> None:
    result = DailyEvolutionLoop(
        vault_dir=tmp_path,
        dry_run=True,
        metrics_collector=FakeMetricsCollector(),
    ).run_once()

    data = result.to_dict()

    assert data["dry_run"] is True
    assert data["real_writes_enabled"] is False
