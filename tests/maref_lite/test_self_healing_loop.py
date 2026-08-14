"""pytest tests for maref_lite.self_healing_loop (v0.51 W6-S4 rewritten).

Aligns with the current implementation:
- SelfHealingConfig has max_heal_iterations=5 (not 3), no enable_audit flag
  (audit is always on via UnifiedAudit)
- SelfHealingLoop.__init__ takes only config (no root_path)
- _run_one_cycle: observe -> diagnose -> triage+heal -> risk-map -> audit
- HealingCycleReport has no timestamp field
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maref_lite.self_healing_loop import HealingCycleReport, SelfHealingConfig, SelfHealingLoop


@pytest.fixture
def mock_deps():
    """Patch recursive dependencies instantiated by SelfHealingLoop."""
    with (
        patch("maref_lite.self_healing_loop.SelfObserver") as MockObserver,
        patch("maref_lite.self_healing_loop.SelfDiagnostician") as MockDiagnostician,
        patch("maref_lite.self_healing_loop.SelfHealer") as MockHealer,
        patch("maref_lite.self_healing_loop.SelfArchitect") as MockArchitect,
        patch("maref_lite.self_healing_loop.SelfExecutor") as MockExecutor,
        patch("maref_lite.self_healing_loop.UnifiedAudit") as MockAudit,
    ):
        observer_inst = MockObserver.return_value
        observer_inst.snapshot.return_value = MagicMock(source_file_count=5)

        diag_report = MagicMock()
        diag_report.overall_risk.value = "LOW"
        diag_report.cb_status = "closed"
        diag_inst = MockDiagnostician.return_value
        diag_inst.diagnose.return_value = diag_report

        healing = MagicMock()
        healing.final_state = "HEALTHY"
        healing.converged = True
        healing.iterations = 1
        healing.actions = []
        healing.to_unified.return_value = []
        healer_inst = MockHealer.return_value
        healer_inst.triage.return_value = []
        healer_inst.heal_cycle.return_value = healing

        yield {
            "observer": observer_inst,
            "diagnostician": diag_inst,
            "healer": healer_inst,
            "audit": MockAudit.return_value,
            "healing": healing,
        }


def _loop(mock_deps, **config_overrides) -> SelfHealingLoop:
    config = SelfHealingConfig(check_interval_seconds=0, **config_overrides)
    loop = SelfHealingLoop(config=config)
    # 覆盖 __init__ 里创建的实例为 mock fixture
    loop._observer = mock_deps["observer"]
    loop._diagnostician = mock_deps["diagnostician"]
    loop._healer = mock_deps["healer"]
    loop._audit = mock_deps["audit"]
    return loop


# ── Config ──────────────────────────────────────────────────────────


def test_config_defaults() -> None:
    config = SelfHealingConfig()
    assert config.check_interval_seconds == 300
    assert config.max_heal_iterations == 3
    assert config.auto_heal is True
    assert config.enable_architecture_proposals is True


def test_config_custom() -> None:
    config = SelfHealingConfig(max_heal_iterations=3, check_interval_seconds=10)
    assert config.max_heal_iterations == 3
    assert config.check_interval_seconds == 10


# ── Cycle ───────────────────────────────────────────────────────────


def test_healthy_cycle(mock_deps) -> None:
    loop = _loop(mock_deps)
    report = asyncio.run(loop._run_one_cycle())
    assert report.status == "healthy"
    assert report.converged is True
    assert report.risk_level == "low"
    assert loop.cycle_count == 1
    assert loop.history[0] == report


def test_observe_failure_marks_report(mock_deps) -> None:
    mock_deps["observer"].snapshot.side_effect = RuntimeError("snapshot broken")
    loop = _loop(mock_deps)
    report = asyncio.run(loop._run_one_cycle())
    assert report.status == "observe_failed"
    assert report.converged is False
    assert report.risk_level == "high"
    assert any("snapshot broken" in p for p in report.problems_found)


def test_diagnose_failure(mock_deps) -> None:
    mock_deps["diagnostician"].diagnose.side_effect = RuntimeError("diagnose broken")
    loop = _loop(mock_deps)
    report = asyncio.run(loop._run_one_cycle())
    assert report.status == "diagnose_failed"
    assert report.converged is False


def test_heal_failure(mock_deps) -> None:
    mock_deps["healer"].heal_cycle.side_effect = RuntimeError("heal broken")
    loop = _loop(mock_deps)
    report = asyncio.run(loop._run_one_cycle())
    assert report.status == "heal_failed"
    assert report.converged is False


def test_risk_mapping_medium(mock_deps) -> None:
    loop = _loop(mock_deps)
    loop._observer.snapshot.return_value = MagicMock(source_file_count=5)
    diag = MagicMock()
    diag.overall_risk.value = "MEDIUM"
    diag.cb_status = "open"
    loop._diagnostician.diagnose.return_value = diag
    healing = MagicMock()
    healing.final_state = "STABLE_WITH_RISK"
    healing.converged = True
    healing.iterations = 2
    healing.actions = []
    healing.to_unified.return_value = []
    loop._healer.triage.return_value = ["risk"]
    loop._healer.heal_cycle.return_value = healing

    report = asyncio.run(loop._run_one_cycle())
    assert report.risk_level == "medium"
    assert report.details["overall_risk"] == "MEDIUM"


# ── Run lifecycle ───────────────────────────────────────────────────


def test_run_single_cycle_then_stop(mock_deps) -> None:
    loop = _loop(mock_deps)

    async def run_then_stop():
        task = asyncio.create_task(loop.run())
        await asyncio.sleep(0.01)
        loop.stop()
        await task

    asyncio.run(run_then_stop())
    assert loop.cycle_count >= 1
    assert loop.running is False


def test_run_handles_cycle_exception(mock_deps) -> None:
    mock_deps["observer"].snapshot.side_effect = RuntimeError("boom")
    loop = _loop(mock_deps)

    async def run_then_stop():
        task = asyncio.create_task(loop.run())
        await asyncio.sleep(0.01)
        loop.stop()
        await task

    asyncio.run(run_then_stop())
    # 异常被捕获为 observe_failed 报告，run 不崩溃
    assert any(h.status == "observe_failed" for h in loop.history)


# ── Serialization ───────────────────────────────────────────────────


def test_report_to_dict_and_loop_to_dict(mock_deps) -> None:
    loop = _loop(mock_deps)
    asyncio.run(loop._run_one_cycle())
    d = loop.to_dict()
    assert d["cycle_count"] == 1
    assert isinstance(d["history"], list)
    assert d["history"][0]["status"] == "healthy"


def test_status_summary_via_history(mock_deps) -> None:
    """实现无 get_status_summary 方法——状态经 history 暴露."""
    loop = _loop(mock_deps)
    asyncio.run(loop._run_one_cycle())
    assert loop.cycle_count == 1
    last = loop.history[-1]
    assert last.converged is True
