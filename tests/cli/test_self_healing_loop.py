from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from maref_lite.self_healing_loop import (
    HealingCycleReport,
    SelfHealingConfig,
    SelfHealingLoop,
)


class TestSelfHealingConfig:
    def test_defaults(self) -> None:
        config = SelfHealingConfig()
        assert config.check_interval_seconds == 300.0
        assert config.max_heal_iterations == 3
        assert config.enable_architecture_proposals is True
        assert config.enable_proposal_execution is True
        assert config.proposal_dry_run is True
        assert config.max_proposals_per_cycle == 3

    def test_custom(self) -> None:
        config = SelfHealingConfig(
            check_interval_seconds=60.0,
            max_heal_iterations=5,
            enable_architecture_proposals=False,
        )
        assert config.check_interval_seconds == 60.0
        assert config.max_heal_iterations == 5
        assert config.enable_architecture_proposals is False


class TestHealingCycleReport:
    def test_to_dict(self) -> None:
        report = HealingCycleReport(
            cycle_id=1,
            timestamp=100.0,
            risk_level="low",
            risk_matrix={"code": "green"},
            problems_found=[],
            actions_taken=[],
            converged=True,
            final_state="HEALTHY",
            duration_ms=50.5,
        )
        d = report.to_dict()
        assert d["cycle_id"] == 1
        assert d["risk_level"] == "low"
        assert d["converged"] is True
        assert d["duration_ms"] == 50.5

    def test_with_proposals(self) -> None:
        report = HealingCycleReport(
            cycle_id=2,
            timestamp=200.0,
            risk_level="medium",
            risk_matrix={"code": "yellow"},
            problems_found=["test_failure"],
            actions_taken=[{"problem_type": "test", "strategy": "fix", "success": True}],
            converged=False,
            final_state="DEGRADED",
            duration_ms=100.0,
            proposals_generated=3,
            proposals_executed=2,
            proposals_succeeded=1,
            proposals_failed=1,
        )
        d = report.to_dict()
        assert d["problems_found"] == ["test_failure"]
        assert d["proposals_generated"] == 3
        assert d["proposals_succeeded"] == 1


class TestSelfHealingLoop:
    def test_init_defaults(self) -> None:
        loop = SelfHealingLoop()
        assert loop._config.check_interval_seconds == 300.0
        assert loop._running is False
        assert loop._cycle_count == 0
        assert loop._history == []

    def test_init_custom_config(self) -> None:
        config = SelfHealingConfig(check_interval_seconds=10.0)
        loop = SelfHealingLoop(config=config)
        assert loop._config.check_interval_seconds == 10.0

    def test_running_property(self) -> None:
        loop = SelfHealingLoop()
        assert loop.running is False
        loop._running = True
        assert loop.running is True

    def test_cycle_count_property(self) -> None:
        loop = SelfHealingLoop()
        assert loop.cycle_count == 0
        loop._cycle_count = 5
        assert loop.cycle_count == 5

    def test_history_property(self) -> None:
        loop = SelfHealingLoop()
        report = HealingCycleReport(
            cycle_id=1,
            timestamp=time.time(),
            risk_level="low",
            risk_matrix={},
            problems_found=[],
            actions_taken=[],
            converged=True,
            final_state="HEALTHY",
            duration_ms=0.0,
        )
        loop._history.append(report)
        assert len(loop.history) == 1
        assert loop.history[0].cycle_id == 1

    def test_stop(self) -> None:
        loop = SelfHealingLoop()
        loop._running = True
        loop.stop()
        assert loop._running is False

    def test_get_status_summary_before_run(self) -> None:
        loop = SelfHealingLoop()
        summary = loop.get_status_summary()
        assert summary["running"] is False
        assert summary["cycle_count"] == 0
        assert "config" in summary
        assert "recent_cycles" in summary

    def test_get_status_summary_after_cycles(self) -> None:
        loop = SelfHealingLoop()
        loop._cycle_count = 3
        for i in range(3):
            loop._history.append(
                HealingCycleReport(
                    cycle_id=i + 1,
                    timestamp=float(i),
                    risk_level="low",
                    risk_matrix={},
                    problems_found=[],
                    actions_taken=[],
                    converged=True,
                    final_state="HEALTHY",
                    duration_ms=10.0,
                )
            )
        summary = loop.get_status_summary()
        assert summary["cycle_count"] == 3
        assert len(summary["recent_cycles"]) == 3

    def test_get_status_summary_recent_capped(self) -> None:
        loop = SelfHealingLoop()
        for i in range(10):
            loop._history.append(
                HealingCycleReport(
                    cycle_id=i + 1,
                    timestamp=float(i),
                    risk_level="low",
                    risk_matrix={},
                    problems_found=[],
                    actions_taken=[],
                    converged=True,
                    final_state="HEALTHY",
                    duration_ms=10.0,
                )
            )
        summary = loop.get_status_summary()
        assert len(summary["recent_cycles"]) == 5

    def test_lazy_init_not_called_if_observer_set(self) -> None:
        loop = SelfHealingLoop()
        loop._observer = MagicMock()
        initial = loop._observer
        loop._lazy_init()
        assert loop._observer is initial

    def test_log_cycle_result_does_not_raise(self) -> None:
        loop = SelfHealingLoop()
        report = HealingCycleReport(
            cycle_id=1,
            timestamp=time.time(),
            risk_level="low",
            risk_matrix={},
            problems_found=[],
            actions_taken=[],
            converged=True,
            final_state="HEALTHY",
            duration_ms=10.0,
        )
        loop._log_cycle_result(report)

    @pytest.mark.asyncio
    async def test_run_cancelled(self) -> None:
        loop = SelfHealingLoop(config=SelfHealingConfig(check_interval_seconds=0.01))
        with (
            patch.object(loop, "_lazy_init"),
            patch.object(loop, "_run_one_cycle") as mock_run,
        ):
            mock_run.return_value = HealingCycleReport(
                cycle_id=1,
                timestamp=time.time(),
                risk_level="low",
                risk_matrix={},
                problems_found=[],
                actions_taken=[],
                converged=True,
                final_state="HEALTHY",
                duration_ms=0.0,
            )
            loop._running = True
            task = asyncio.create_task(loop.run())
            await asyncio.sleep(0.05)
            loop.stop()
            await task

    @pytest.mark.asyncio
    async def test_run_cycle_error_handled(self) -> None:
        loop = SelfHealingLoop(config=SelfHealingConfig(check_interval_seconds=0.01))
        with (
            patch.object(loop, "_lazy_init"),
            patch.object(loop, "_run_one_cycle", side_effect=ValueError("test error")),
        ):
            loop._running = True
            task = asyncio.create_task(loop.run())
            await asyncio.sleep(0.05)
            loop.stop()
            await task
            assert loop.cycle_count >= 1

    @pytest.mark.asyncio
    async def test_run_one_cycle_lazy_inits(self) -> None:
        loop = SelfHealingLoop(config=SelfHealingConfig(check_interval_seconds=0.01))
        with (
            patch("maref.recursive.self_observer.SelfObserver") as MockObs,
            patch("maref.recursive.self_diagnostician.SelfDiagnostician") as MockDiag,
            patch("maref.recursive.self_healer.SelfHealer") as MockHealer,
            patch("maref.recursive.self_architect.SelfArchitect") as MockArch,
            patch("maref.recursive.unified_audit.UnifiedAuditStore"),
            patch("maref.recursive.self_executor.SelfExecutor"),
        ):
            loop._lazy_init()

            mock_snapshot = MagicMock()
            mock_snapshot.source_file_count = 5
            mock_snapshot.test_stats = {"total": 10}
            MockObs.return_value.snapshot.return_value = mock_snapshot

            mock_diag_report = MagicMock()
            mock_diag_report.overall_risk.value = "low"
            rm = MagicMock()
            rm.value = "green"
            mock_diag_report.risk_matrix = {"code": rm}
            MockDiag.return_value.diagnose.return_value = mock_diag_report

            mock_healing_record = MagicMock()
            mock_healing_record.converged = True
            mock_healing_record.final_state = "HEALTHY"
            mock_healing_record.actions = []
            MockHealer.return_value.triage.return_value = []
            MockHealer.return_value.heal_cycle.return_value = mock_healing_record

            MockArch.return_value.propose_all.return_value = []

            loop._cycle_count = 1
            report = await loop._run_one_cycle()
            assert report.cycle_id == 1
            assert report.risk_level == "low"
            assert report.converged is True
