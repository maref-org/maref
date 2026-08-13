from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from maref.evolution.constitution_harness import ConstitutionHarness, EvolutionChange
from maref.evolution.engine import EvolutionConfig, RecursiveEvolutionEngine
from maref.evolution.real_metrics import RealMetrics
from maref_lite.self_healing_loop import SelfHealingConfig, SelfHealingLoop


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


@pytest.mark.asyncio
async def test_recursive_safe_loop_dry_run_real_metrics_and_constitution(tmp_path: Path) -> None:
    target = tmp_path / "target.py"
    target.write_text("VALUE = 1\n")

    with (
        patch("maref.recursive.self_observer.SelfObserver") as MockObserver,
        patch("maref.recursive.self_diagnostician.SelfDiagnostician") as MockDiagnostician,
        patch("maref.recursive.self_healer.SelfHealer") as MockHealer,
        patch("maref.recursive.self_architect.SelfArchitect") as MockArchitect,
        patch("maref.recursive.self_executor.SelfExecutor") as MockExecutor,
        patch("maref.recursive.unified_audit.UnifiedAuditStore"),
    ):
        MockObserver.return_value.snapshot.return_value = MagicMock(
            source_file_count=1,
            test_stats={"total": 1},
        )
        report = MagicMock()
        report.overall_risk.value = "LOW"
        report.risk_matrix = {}
        MockDiagnostician.return_value.diagnose.return_value = report
        MockHealer.return_value.triage.return_value = []
        proposal = MagicMock()
        proposal.proposal_id = "P1"
        MockArchitect.return_value.propose_all.return_value = [proposal]
        MockArchitect.return_value.validate_proposal.return_value = True
        dry_run_record = MagicMock()
        dry_run_record.final_state = "DRY_RUN_OK"
        MockExecutor.return_value.dry_run.return_value = dry_run_record

        loop = SelfHealingLoop(
            config=SelfHealingConfig(
                arch_proposal_interval_cycles=1,
                proposal_dry_run=True,
            ),
        )
        loop._lazy_init()
        loop._cycle_count = 1
        loop_report = await loop._run_one_cycle()

        assert isinstance(loop_report.actions_taken, list)
        MockExecutor.return_value.execute.assert_not_called()
        assert target.read_text() == "VALUE = 1\n"

    config = EvolutionConfig(dry_run=True, metrics_mode="real")
    engine = RecursiveEvolutionEngine(config=config, metrics_collector=FakeMetricsCollector())
    engine._running = True
    snapshot = await engine._run_one_round("c1", 0, config.cycles["c1"])
    assert snapshot["metrics_source"] == "real"

    constitution = ConstitutionHarness()
    result = constitution.check_change(
        EvolutionChange(
            change_id="bad",
            files=["src/maref/recursive/meta_agent_closure.py"],
            description="bad change",
            diff_text="- RL-001\n+ changed",
        )
    )
    assert result.allowed is False
