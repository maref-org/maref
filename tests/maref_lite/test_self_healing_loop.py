"""Comprehensive pytest tests for maref_lite.self_healing_loop."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from maref_lite.self_healing_loop import (
    SelfHealingConfig,
    HealingCycleReport,
    SelfHealingLoop,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_deps():
    """Patch all recursive dependencies imported lazily by SelfHealingLoop."""
    with (
        patch("maref.recursive.self_observer.SelfObserver") as MockObserver,
        patch("maref.recursive.self_diagnostician.SelfDiagnostician") as MockDiagnostician,
        patch("maref.recursive.self_healer.SelfHealer") as MockHealer,
        patch("maref.recursive.self_architect.SelfArchitect") as MockArchitect,
        patch("maref.recursive.self_executor.SelfExecutor") as MockExecutor,
        patch("maref.recursive.unified_audit.UnifiedAuditStore") as MockAuditStore,
    ):
        observer_inst = MockObserver.return_value
        observer_inst.snapshot.return_value = MagicMock(
            source_file_count=5,
            test_stats={"total": 3},
        )

        diag_report = MagicMock()
        diag_report.overall_risk.value = "LOW"
        diag_report.risk_matrix = {}

        diag_inst = MockDiagnostician.return_value
        diag_inst.diagnose.return_value = diag_report

        healer_inst = MockHealer.return_value
        healer_inst.triage.return_value = []

        audit_inst = MockAuditStore.return_value
        audit_inst.count.return_value = 0

        yield {
            "classes": {
                "observer": MockObserver,
                "diagnostician": MockDiagnostician,
                "healer": MockHealer,
                "architect": MockArchitect,
                "executor": MockExecutor,
                "audit_store": MockAuditStore,
            },
            "instances": {
                "observer": observer_inst,
                "diagnostician": diag_inst,
                "healer": healer_inst,
                "architect": MockArchitect.return_value,
                "executor": MockExecutor.return_value,
                "audit_store": audit_inst,
            },
            "diag_report": diag_report,
        }


@pytest.fixture
def loop_no_audit(mock_deps):
    """Pre-initialized loop with audit and proposals disabled for baseline tests."""
    config = SelfHealingConfig(
        check_interval_seconds=0.01,
        enable_audit=False,
        enable_architecture_proposals=False,
    )
    loop = SelfHealingLoop(config=config, root_path="/tmp/test")
    loop._lazy_init()
    return loop


# ── SelfHealingConfig ─────────────────────────────────────────────────


class TestSelfHealingConfig:
    def test_default_construction(self):
        config = SelfHealingConfig()
        assert config.check_interval_seconds == 300.0
        assert config.max_heal_iterations == 3
        assert config.enable_architecture_proposals is True
        assert config.arch_proposal_interval_cycles == 12
        assert config.log_dir == ".self_healing_logs"
        assert config.enable_audit is True
        assert config.enable_proposal_execution is True
        assert config.max_proposals_per_cycle == 3
        assert config.proposal_dry_run is False

    def test_custom_construction(self):
        config = SelfHealingConfig(
            check_interval_seconds=60.0,
            max_heal_iterations=5,
            enable_architecture_proposals=False,
            arch_proposal_interval_cycles=6,
            log_dir="/tmp/logs",
            enable_audit=False,
            enable_proposal_execution=False,
            max_proposals_per_cycle=1,
            proposal_dry_run=True,
        )
        assert config.check_interval_seconds == 60.0
        assert config.max_heal_iterations == 5
        assert config.enable_architecture_proposals is False
        assert config.arch_proposal_interval_cycles == 6
        assert config.log_dir == "/tmp/logs"
        assert config.enable_audit is False
        assert config.enable_proposal_execution is False
        assert config.max_proposals_per_cycle == 1
        assert config.proposal_dry_run is True


# ── HealingCycleReport ────────────────────────────────────────────────


class TestHealingCycleReport:
    def test_construction_and_defaults(self):
        report = HealingCycleReport(
            cycle_id=1,
            timestamp=1234567890.0,
            risk_level="LOW",
            risk_matrix={"code": "MEDIUM"},
            problems_found=[],
            actions_taken=[],
            converged=True,
            final_state="HEALTHY",
            duration_ms=123.456,
        )
        assert report.cycle_id == 1
        assert report.timestamp == 1234567890.0
        assert report.risk_level == "LOW"
        assert report.risk_matrix == {"code": "MEDIUM"}
        assert report.problems_found == []
        assert report.actions_taken == []
        assert report.converged is True
        assert report.final_state == "HEALTHY"
        assert report.duration_ms == 123.456
        # defaults
        assert report.proposals_generated == 0
        assert report.proposals_executed == 0
        assert report.proposals_succeeded == 0
        assert report.proposals_failed == 0

    def test_to_dict(self):
        report = HealingCycleReport(
            cycle_id=2,
            timestamp=1234567890.0,
            risk_level="HIGH",
            risk_matrix={"security": "CRITICAL"},
            problems_found=["missing_tests"],
            actions_taken=[{"strategy": "generate"}],
            converged=False,
            final_state="DEGRADED",
            duration_ms=99.999,
            proposals_generated=3,
            proposals_executed=2,
            proposals_succeeded=1,
            proposals_failed=1,
        )
        d = report.to_dict()
        assert d["cycle_id"] == 2
        assert d["timestamp"] == 1234567890.0
        assert d["risk_level"] == "HIGH"
        assert d["risk_matrix"] == {"security": "CRITICAL"}
        assert d["problems_found"] == ["missing_tests"]
        assert d["actions_taken"] == [{"strategy": "generate"}]
        assert d["converged"] is False
        assert d["final_state"] == "DEGRADED"
        assert d["duration_ms"] == 100.0  # rounded to 2 decimals
        assert d["proposals_generated"] == 3
        assert d["proposals_executed"] == 2
        assert d["proposals_succeeded"] == 1
        assert d["proposals_failed"] == 1


# ── SelfHealingLoop Initialization ────────────────────────────────────


class TestSelfHealingLoopInit:
    def test_default_init(self):
        loop = SelfHealingLoop()
        assert loop.running is False
        assert loop.cycle_count == 0
        assert loop.history == []
        assert loop._config == SelfHealingConfig()
        assert loop._root_path == Path.cwd()
        assert loop._observer is None
        assert loop._diagnostician is None
        assert loop._healer is None
        assert loop._architect is None
        assert loop._audit_store is None
        assert loop._executor is None

    def test_custom_init(self):
        config = SelfHealingConfig(check_interval_seconds=60.0)
        loop = SelfHealingLoop(config=config, root_path="/tmp/test")
        assert loop._config is config
        assert loop._root_path == Path("/tmp/test")

    def test_init_with_path_object(self):
        loop = SelfHealingLoop(root_path=Path("/tmp/test2"))
        assert loop._root_path == Path("/tmp/test2")

    def test_history_returns_copy(self):
        loop = SelfHealingLoop()
        loop._history.append(MagicMock())
        h = loop.history
        h.pop()
        assert len(loop._history) == 1


# ── SelfHealingLoop Lazy Init ─────────────────────────────────────────


class TestSelfHealingLoopLazyInit:
    def test_lazy_init_creates_instances(self, mock_deps):
        loop = SelfHealingLoop(root_path="/tmp/test")
        loop._lazy_init()
        assert loop._observer is mock_deps["instances"]["observer"]
        assert loop._diagnostician is mock_deps["instances"]["diagnostician"]
        assert loop._healer is mock_deps["instances"]["healer"]
        assert loop._architect is mock_deps["instances"]["architect"]
        assert loop._audit_store is mock_deps["instances"]["audit_store"]
        assert loop._executor is mock_deps["instances"]["executor"]

        # Verify constructor calls
        mock_deps["classes"]["observer"].assert_called_once_with(root_path="/tmp/test")
        mock_deps["classes"]["healer"].assert_called_once_with(max_iterations=3)
        mock_deps["classes"]["architect"].assert_called_once_with(
            audit_store=mock_deps["instances"]["audit_store"]
        )
        mock_deps["classes"]["executor"].assert_called_once_with(
            project_root="/tmp/test",
            audit_store=mock_deps["instances"]["audit_store"],
        )

    def test_lazy_init_skips_when_already_initialized(self, mock_deps):
        loop = SelfHealingLoop()
        loop._lazy_init()
        call_count = mock_deps["classes"]["observer"].call_count
        loop._lazy_init()
        assert mock_deps["classes"]["observer"].call_count == call_count

    def test_lazy_init_without_proposal_execution(self, mock_deps):
        config = SelfHealingConfig(enable_proposal_execution=False)
        loop = SelfHealingLoop(config=config)
        loop._lazy_init()
        assert loop._executor is None
        mock_deps["classes"]["executor"].assert_not_called()


# ── SelfHealingLoop _run_one_cycle ────────────────────────────────────


class TestSelfHealingLoopRunOneCycle:
    @pytest.mark.asyncio
    async def test_healthy_cycle_no_problems(self, loop_no_audit, mock_deps):
        loop = loop_no_audit
        loop._cycle_count = 1
        report = await loop._run_one_cycle()
        assert report.cycle_id == 1
        assert report.risk_level == "LOW"
        assert report.problems_found == []
        assert report.converged is True
        assert report.final_state == "HEALTHY"
        assert report.actions_taken == []
        assert report.proposals_generated == 0
        assert report.proposals_executed == 0
        assert report.proposals_succeeded == 0
        assert report.proposals_failed == 0
        assert report.duration_ms >= 0
        mock_deps["instances"]["observer"].snapshot.assert_called_once()
        mock_deps["instances"]["diagnostician"].diagnose.assert_called_once()
        mock_deps["instances"]["healer"].triage.assert_called_once()

    @pytest.mark.asyncio
    async def test_cycle_with_problems_converged(self, loop_no_audit, mock_deps):
        loop = loop_no_audit
        loop._cycle_count = 1

        healer = mock_deps["instances"]["healer"]
        healer.triage.return_value = ["missing_tests"]

        mock_action = MagicMock()
        mock_action.problem_type = "missing_tests"
        mock_action.strategy = "generate_tests"
        mock_action.success = True
        mock_action.detail = "a" * 250  # test truncation
        mock_action.exit_code = 0

        healing_record = MagicMock()
        healing_record.converged = True
        healing_record.final_state = "HEALTHY"
        healing_record.actions = [mock_action]
        healing_record.to_unified.return_value = []

        healer.heal_cycle.return_value = healing_record

        report = await loop._run_one_cycle()
        assert report.problems_found == ["missing_tests"]
        assert report.converged is True
        assert report.final_state == "HEALTHY"
        assert len(report.actions_taken) == 1
        action = report.actions_taken[0]
        assert action["problem_type"] == "missing_tests"
        assert action["strategy"] == "generate_tests"
        assert action["success"] is True
        assert action["detail"] == "a" * 200  # truncated to 200 chars
        assert action["exit_code"] == 0

        healer.heal_cycle.assert_called_once_with(
            report=mock_deps["diag_report"],
            auto_re_diagnose=True,
            _observer=mock_deps["instances"]["observer"],
            _diagnostician=mock_deps["instances"]["diagnostician"],
        )

    @pytest.mark.asyncio
    async def test_cycle_with_problems_not_converged(self, loop_no_audit, mock_deps):
        loop = loop_no_audit
        loop._cycle_count = 1

        healer = mock_deps["instances"]["healer"]
        healer.triage.return_value = ["high_complexity"]

        healing_record = MagicMock()
        healing_record.converged = False
        healing_record.final_state = "DEGRADED"
        healing_record.actions = []
        healing_record.to_unified.return_value = []

        healer.heal_cycle.return_value = healing_record

        report = await loop._run_one_cycle()
        assert report.converged is False
        assert report.final_state == "DEGRADED"
        assert report.actions_taken == []

    @pytest.mark.asyncio
    async def test_cycle_unknown_problem_skips_heal(self, loop_no_audit, mock_deps):
        loop = loop_no_audit
        loop._cycle_count = 1

        healer = mock_deps["instances"]["healer"]
        healer.triage.return_value = ["unknown"]

        report = await loop._run_one_cycle()
        assert report.problems_found == ["unknown"]
        assert report.converged is True
        assert report.final_state == "HEALTHY"
        healer.heal_cycle.assert_not_called()

    @pytest.mark.asyncio
    async def test_cycle_empty_problem_list_skips_heal(self, loop_no_audit, mock_deps):
        loop = loop_no_audit
        loop._cycle_count = 1

        healer = mock_deps["instances"]["healer"]
        healer.triage.return_value = []

        report = await loop._run_one_cycle()
        assert report.problems_found == []
        assert report.converged is True
        assert report.final_state == "HEALTHY"
        healer.heal_cycle.assert_not_called()

    @pytest.mark.asyncio
    async def test_cycle_with_risk_matrix(self, mock_deps):
        config = SelfHealingConfig(
            check_interval_seconds=0.01,
            enable_audit=False,
            enable_architecture_proposals=False,
        )
        loop = SelfHealingLoop(config=config, root_path="/tmp/test")
        loop._lazy_init()
        loop._cycle_count = 1

        diag_report = mock_deps["diag_report"]
        diag_report.overall_risk.value = "HIGH"
        mock_risk = MagicMock()
        mock_risk.value = "CRITICAL"
        diag_report.risk_matrix = {"security": mock_risk}

        report = await loop._run_one_cycle()
        assert report.risk_level == "HIGH"
        assert report.risk_matrix == {"security": "CRITICAL"}

    @pytest.mark.asyncio
    async def test_cycle_with_audit_enabled(self, mock_deps):
        with (
            patch("maref.recursive.unified_audit.UnifiedAuditRecord") as MockRecord,
            patch("maref.recursive.unified_audit.make_record_id") as mock_make_id,
        ):
            mock_make_id.return_value = "AUDIT-001"
            mock_record_inst = MagicMock()
            MockRecord.return_value = mock_record_inst

            config = SelfHealingConfig(
                check_interval_seconds=0.01,
                enable_audit=True,
                enable_architecture_proposals=False,
            )
            loop = SelfHealingLoop(config=config, root_path="/tmp/test")
            loop._lazy_init()
            loop._cycle_count = 1

            healer = mock_deps["instances"]["healer"]
            healer.triage.return_value = ["missing_tests"]

            healing_record = MagicMock()
            healing_record.converged = True
            healing_record.final_state = "HEALTHY"
            healing_record.actions = []
            healing_record.to_unified.return_value = [{"type": "heal"}]

            healer.heal_cycle.return_value = healing_record

            audit_store = mock_deps["instances"]["audit_store"]

            report = await loop._run_one_cycle()

            healing_record.to_unified.assert_called_once_with(round_num=1)
            assert audit_store.append.call_count == 2
            MockRecord.assert_called_once()
            mock_make_id.assert_called_once()
            assert report.converged is True


# ── Architecture Proposal Tests ───────────────────────────────────────


class TestSelfHealingLoopArchitectureProposals:
    @pytest.mark.asyncio
    async def test_cycle_with_proposals_execution(self, mock_deps):
        config = SelfHealingConfig(
            check_interval_seconds=0.01,
            enable_audit=False,
            enable_architecture_proposals=True,
            arch_proposal_interval_cycles=2,
            enable_proposal_execution=True,
            proposal_dry_run=False,
            max_proposals_per_cycle=2,
        )
        loop = SelfHealingLoop(config=config, root_path="/tmp/test")
        loop._lazy_init()
        loop._cycle_count = 2  # divisible by 2

        architect = mock_deps["instances"]["architect"]
        executor = mock_deps["instances"]["executor"]

        p1, p2, p3 = MagicMock(), MagicMock(), MagicMock()
        p1.proposal_id = "P1"
        p2.proposal_id = "P2"
        p3.proposal_id = "P3"

        architect.propose_all.return_value = [p1, p2, p3]
        architect.validate_proposal.side_effect = [True, True, False]

        exec_record = MagicMock()
        exec_record.final_state = "SUCCESS"
        executor.execute.return_value = exec_record

        report = await loop._run_one_cycle()
        assert report.proposals_generated == 3
        assert report.proposals_executed == 2  # capped by max_proposals_per_cycle
        assert report.proposals_succeeded == 2
        assert report.proposals_failed == 0

        executor.execute.assert_has_calls([
            call(p1, round_num=2),
            call(p2, round_num=2),
        ])
        executor.dry_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_cycle_with_proposal_dry_run(self, mock_deps):
        config = SelfHealingConfig(
            check_interval_seconds=0.01,
            enable_audit=False,
            enable_architecture_proposals=True,
            arch_proposal_interval_cycles=1,
            enable_proposal_execution=True,
            proposal_dry_run=True,
            max_proposals_per_cycle=5,
        )
        loop = SelfHealingLoop(config=config, root_path="/tmp/test")
        loop._lazy_init()
        loop._cycle_count = 1

        architect = mock_deps["instances"]["architect"]
        executor = mock_deps["instances"]["executor"]

        proposal = MagicMock()
        proposal.proposal_id = "P1"
        architect.propose_all.return_value = [proposal]
        architect.validate_proposal.return_value = True

        exec_record = MagicMock()
        exec_record.final_state = "DRY_RUN_OK"
        executor.dry_run.return_value = exec_record

        report = await loop._run_one_cycle()
        assert report.proposals_executed == 1
        assert report.proposals_succeeded == 1
        executor.dry_run.assert_called_once_with(proposal)
        executor.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_cycle_with_proposal_execution_failure(self, mock_deps):
        config = SelfHealingConfig(
            check_interval_seconds=0.01,
            enable_audit=False,
            enable_architecture_proposals=True,
            arch_proposal_interval_cycles=1,
            enable_proposal_execution=True,
            proposal_dry_run=False,
        )
        loop = SelfHealingLoop(config=config, root_path="/tmp/test")
        loop._lazy_init()
        loop._cycle_count = 1

        architect = mock_deps["instances"]["architect"]
        executor = mock_deps["instances"]["executor"]

        proposal = MagicMock()
        proposal.proposal_id = "P1"
        architect.propose_all.return_value = [proposal]
        architect.validate_proposal.return_value = True

        exec_record = MagicMock()
        exec_record.final_state = "FAILED"
        executor.execute.return_value = exec_record

        report = await loop._run_one_cycle()
        assert report.proposals_executed == 1
        assert report.proposals_succeeded == 0
        assert report.proposals_failed == 1

    @pytest.mark.asyncio
    async def test_cycle_with_proposal_execution_exception(self, mock_deps):
        config = SelfHealingConfig(
            check_interval_seconds=0.01,
            enable_audit=False,
            enable_architecture_proposals=True,
            arch_proposal_interval_cycles=1,
            enable_proposal_execution=True,
        )
        loop = SelfHealingLoop(config=config, root_path="/tmp/test")
        loop._lazy_init()
        loop._cycle_count = 1

        architect = mock_deps["instances"]["architect"]
        executor = mock_deps["instances"]["executor"]

        proposal = MagicMock()
        proposal.proposal_id = "P1"
        architect.propose_all.return_value = [proposal]
        architect.validate_proposal.return_value = True

        executor.execute.side_effect = RuntimeError("exec failed")

        report = await loop._run_one_cycle()
        assert report.proposals_executed == 1
        assert report.proposals_failed == 1

    @pytest.mark.asyncio
    async def test_cycle_architecture_proposal_exception(self, mock_deps):
        config = SelfHealingConfig(
            check_interval_seconds=0.01,
            enable_audit=False,
            enable_architecture_proposals=True,
            arch_proposal_interval_cycles=1,
        )
        loop = SelfHealingLoop(config=config, root_path="/tmp/test")
        loop._lazy_init()
        loop._cycle_count = 1

        architect = mock_deps["instances"]["architect"]
        architect.propose_all.side_effect = RuntimeError("proposal failed")

        report = await loop._run_one_cycle()
        assert report.proposals_generated == 0
        assert report.proposals_executed == 0

    @pytest.mark.asyncio
    async def test_cycle_architecture_proposals_without_executor(self, mock_deps):
        config = SelfHealingConfig(
            check_interval_seconds=0.01,
            enable_audit=False,
            enable_architecture_proposals=True,
            arch_proposal_interval_cycles=1,
            enable_proposal_execution=False,
        )
        loop = SelfHealingLoop(config=config, root_path="/tmp/test")
        loop._lazy_init()
        loop._cycle_count = 1

        architect = mock_deps["instances"]["architect"]
        proposal = MagicMock()
        proposal.proposal_id = "P1"
        architect.propose_all.return_value = [proposal]

        report = await loop._run_one_cycle()
        assert report.proposals_generated == 1
        assert report.proposals_executed == 0

    @pytest.mark.asyncio
    async def test_cycle_architecture_proposals_not_on_interval(self, mock_deps):
        config = SelfHealingConfig(
            check_interval_seconds=0.01,
            enable_audit=False,
            enable_architecture_proposals=True,
            arch_proposal_interval_cycles=5,
        )
        loop = SelfHealingLoop(config=config, root_path="/tmp/test")
        loop._lazy_init()
        loop._cycle_count = 3  # not divisible by 5

        architect = mock_deps["instances"]["architect"]

        report = await loop._run_one_cycle()
        assert report.proposals_generated == 0
        architect.propose_all.assert_not_called()


# ── SelfHealingLoop run() ─────────────────────────────────────────────


class TestSelfHealingLoopRun:
    @pytest.mark.asyncio
    async def test_run_single_cycle_then_stop(self, mock_deps):
        loop = SelfHealingLoop(config=SelfHealingConfig(check_interval_seconds=0.1))
        loop._lazy_init()
        loop._run_one_cycle = AsyncMock(return_value=MagicMock(cycle_id=1, converged=True))

        async def stop_after():
            await asyncio.sleep(0.05)
            loop.stop()

        asyncio.create_task(stop_after())
        await loop.run()

        assert loop.cycle_count == 1
        assert len(loop.history) == 1
        assert loop.running is False
        loop._run_one_cycle.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_handles_cycle_exception(self, mock_deps):
        loop = SelfHealingLoop(config=SelfHealingConfig(check_interval_seconds=0.1))
        loop._lazy_init()
        loop._run_one_cycle = AsyncMock(side_effect=[
            RuntimeError("fail"),
            MagicMock(cycle_id=2, converged=True),
        ])

        async def stop_after():
            await asyncio.sleep(0.15)
            loop.stop()

        asyncio.create_task(stop_after())
        await loop.run()

        assert loop.cycle_count == 2
        assert len(loop.history) == 1
        assert loop._run_one_cycle.await_count == 2

    @pytest.mark.asyncio
    async def test_run_handles_cancelled_error(self, mock_deps):
        loop = SelfHealingLoop(config=SelfHealingConfig(check_interval_seconds=10.0))
        loop._lazy_init()

        run_task = asyncio.create_task(loop.run())
        await asyncio.sleep(0.01)
        run_task.cancel()

        # run() catches CancelledError and does not re-raise
        await run_task
        assert loop.running is False

    @pytest.mark.asyncio
    async def test_run_zero_interval_no_sleep(self, mock_deps):
        loop = SelfHealingLoop(config=SelfHealingConfig(check_interval_seconds=0.0))
        loop._lazy_init()

        call_count = 0
        async def mock_cycle():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                loop.stop()
            return MagicMock(cycle_id=call_count, converged=True)

        loop._run_one_cycle = mock_cycle
        await loop.run()
        assert call_count == 1


# ── SelfHealingLoop _log_cycle_result ─────────────────────────────────


class TestSelfHealingLoopLog:
    def test_log_cycle_result_converged(self, caplog):
        loop = SelfHealingLoop()
        report = HealingCycleReport(
            cycle_id=1,
            timestamp=0.0,
            risk_level="LOW",
            risk_matrix={},
            problems_found=[],
            actions_taken=[{"strategy": "fix"}],
            converged=True,
            final_state="HEALTHY",
            duration_ms=50.0,
            proposals_generated=1,
            proposals_executed=1,
            proposals_succeeded=1,
            proposals_failed=0,
        )
        with caplog.at_level(logging.INFO, logger="maref.self_healing_loop"):
            loop._log_cycle_result(report)
        assert "Cycle 1" in caplog.text
        assert "risk=LOW" in caplog.text
        assert "converged=True" in caplog.text
        assert "proposals=1/1/1" in caplog.text

    def test_log_cycle_result_not_converged(self, caplog):
        loop = SelfHealingLoop()
        report = HealingCycleReport(
            cycle_id=2,
            timestamp=0.0,
            risk_level="HIGH",
            risk_matrix={},
            problems_found=["x"],
            actions_taken=[],
            converged=False,
            final_state="DEGRADED",
            duration_ms=100.0,
        )
        with caplog.at_level(logging.INFO, logger="maref.self_healing_loop"):
            loop._log_cycle_result(report)
        assert "Cycle 2" in caplog.text
        assert "converged=False" in caplog.text


# ── SelfHealingLoop get_status_summary ────────────────────────────────


class TestSelfHealingLoopStatusSummary:
    def test_get_status_summary_no_history(self, mock_deps):
        loop = SelfHealingLoop(config=SelfHealingConfig(check_interval_seconds=60.0))
        loop._lazy_init()
        summary = loop.get_status_summary()
        assert summary["running"] is False
        assert summary["cycle_count"] == 0
        assert summary["config"]["check_interval_seconds"] == 60.0
        assert summary["config"]["max_heal_iterations"] == 3
        assert summary["recent_cycles"] == []
        assert summary["audit_record_count"] == 0

    def test_get_status_summary_with_history(self, mock_deps):
        loop = SelfHealingLoop()
        loop._lazy_init()

        report = HealingCycleReport(
            cycle_id=1,
            timestamp=0.0,
            risk_level="LOW",
            risk_matrix={},
            problems_found=[],
            actions_taken=[],
            converged=True,
            final_state="HEALTHY",
            duration_ms=10.0,
        )
        loop._history.append(report)
        loop._cycle_count = 1

        summary = loop.get_status_summary()
        assert summary["cycle_count"] == 1
        assert len(summary["recent_cycles"]) == 1
        assert summary["recent_cycles"][0]["cycle_id"] == 1
        assert summary["audit_record_count"] == 0

    def test_get_status_summary_limits_recent_to_five(self, mock_deps):
        loop = SelfHealingLoop()
        loop._lazy_init()

        for i in range(1, 8):
            report = HealingCycleReport(
                cycle_id=i,
                timestamp=float(i),
                risk_level="LOW",
                risk_matrix={},
                problems_found=[],
                actions_taken=[],
                converged=True,
                final_state="HEALTHY",
                duration_ms=1.0,
            )
            loop._history.append(report)
        loop._cycle_count = 7

        summary = loop.get_status_summary()
        assert len(summary["recent_cycles"]) == 5
        assert summary["recent_cycles"][0]["cycle_id"] == 3
        assert summary["recent_cycles"][-1]["cycle_id"] == 7

    def test_get_status_summary_audit_count(self, mock_deps):
        loop = SelfHealingLoop()
        loop._lazy_init()
        mock_deps["instances"]["audit_store"].count.return_value = 42
        summary = loop.get_status_summary()
        assert summary["audit_record_count"] == 42
