"""SelfHealingLoop P5.5 closure tests.

Validates that _run_one_cycle implements the full observe -> diagnose ->
heal -> verify loop (previously a stub returning status="completed").
Components are mocked to isolate from real pytest/probe execution.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from maref.recursive.self_diagnostician import DiagnosisReport, RiskLevel
from maref.recursive.self_healer import HealAction, HealingRecord
from maref.recursive.self_observer import SystemSnapshot
from maref_lite.self_healing_loop import SelfHealingConfig, SelfHealingLoop


def _make_loop(
    snapshot: SystemSnapshot | None = None,
    diagnosis: DiagnosisReport | None = None,
    healing: HealingRecord | None = None,
    triage: list[str] | None = None,
) -> SelfHealingLoop:
    """Build a SelfHealingLoop with mocked components for unit isolation."""
    loop = SelfHealingLoop(SelfHealingConfig(max_cycles=1))
    loop._observer = MagicMock()
    loop._observer.snapshot.return_value = snapshot or SystemSnapshot()
    loop._diagnostician = MagicMock()
    loop._diagnostician.diagnose.return_value = diagnosis or DiagnosisReport(
        snapshot_ref="test", overall_risk=RiskLevel.NORMAL
    )
    loop._healer = MagicMock()
    loop._healer.triage.return_value = triage or []
    loop._healer.heal_cycle.return_value = healing or HealingRecord(
        final_state="HEALTHY", converged=True, iterations=0
    )
    loop._audit = MagicMock()
    return loop


class TestSelfHealingLoopClosure:
    def test_healthy_cycle(self) -> None:
        loop = _make_loop()
        report = asyncio.run(loop._run_one_cycle())
        assert report.status == "healthy"
        assert report.converged is True
        assert report.risk_level == "low"
        assert report.details["overall_risk"] == "normal"
        assert report.cycle_id == 1

    def test_recovered_cycle(self) -> None:
        loop = _make_loop(
            diagnosis=DiagnosisReport(
                snapshot_ref="t", overall_risk=RiskLevel.WARNING
            ),
            healing=HealingRecord(
                final_state="RECOVERED", converged=True, iterations=1
            ),
            triage=["test_failure"],
        )
        report = asyncio.run(loop._run_one_cycle())
        assert report.status == "recovered"
        assert report.converged is True
        assert report.risk_level == "low"
        assert "test_failure" in report.problems_found

    def test_degraded_cycle(self) -> None:
        loop = _make_loop(
            diagnosis=DiagnosisReport(
                snapshot_ref="t", overall_risk=RiskLevel.CRITICAL
            ),
            healing=HealingRecord(
                final_state="DEGRADED", converged=False, iterations=3
            ),
            triage=["performance_regression"],
        )
        report = asyncio.run(loop._run_one_cycle())
        assert report.status == "degraded"
        assert report.converged is False
        assert report.risk_level == "high"

    def test_stable_with_risk(self) -> None:
        loop = _make_loop(
            healing=HealingRecord(
                final_state="STABLE_WITH_RISK", converged=True, iterations=2
            ),
        )
        report = asyncio.run(loop._run_one_cycle())
        assert report.status == "stable_with_risk"
        assert report.risk_level == "medium"

    def test_observe_failed(self) -> None:
        loop = _make_loop()
        loop._observer.snapshot.side_effect = RuntimeError("disk full")
        report = asyncio.run(loop._run_one_cycle())
        assert report.status == "observe_failed"
        assert report.converged is False
        assert "disk full" in report.problems_found[0]

    def test_diagnose_failed(self) -> None:
        loop = _make_loop()
        loop._diagnostician.diagnose.side_effect = RuntimeError("probe error")
        report = asyncio.run(loop._run_one_cycle())
        assert report.status == "diagnose_failed"
        assert report.converged is False

    def test_actions_recorded(self) -> None:
        loop = _make_loop(
            healing=HealingRecord(
                final_state="RECOVERED",
                converged=True,
                iterations=1,
                actions=[
                    HealAction(
                        problem_type="test_failure",
                        strategy="rerun_tests_with_verbose",
                        applied=True,
                        exit_code=0,
                        detail="pytest exit=0",
                    ),
                ],
            ),
            triage=["test_failure"],
        )
        report = asyncio.run(loop._run_one_cycle())
        assert len(report.actions_taken) == 1
        assert report.actions_taken[0]["strategy"] == "rerun_tests_with_verbose"
        assert report.actions_taken[0]["success"] is True

    def test_audit_recorded(self) -> None:
        loop = _make_loop(
            healing=HealingRecord(
                final_state="RECOVERED",
                converged=True,
                iterations=1,
                actions=[
                    HealAction(
                        problem_type="test_failure",
                        strategy="rerun_tests_with_verbose",
                    ),
                ],
            ),
            triage=["test_failure"],
        )
        asyncio.run(loop._run_one_cycle())
        assert loop._audit.log.called

    def test_history_accumulates(self) -> None:
        loop = _make_loop()
        asyncio.run(loop._run_one_cycle())
        asyncio.run(loop._run_one_cycle())
        assert len(loop.history) == 2
        assert loop.cycle_count == 2
