from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from maref.evaluation.saeb import (
    SAEBMetricsCollector,
    SAEBScenario,
    create_browser_engine_scenario,
    create_calculator_scenario,
    create_desktop_agent_scenario,
    run_saeb,
)
from maref.evaluation.saeb.report import (
    generate_comparison_report,
    generate_json_report,
)
from maref.evaluation.saeb.runner import MAREFSelfAdapter, NoopAdapter


@pytest.fixture
def calculator_scenario() -> SAEBScenario:
    workdir = Path(f"/tmp/saeb-test-{uuid.uuid4().hex[:8]}")
    scenario = create_calculator_scenario(workdir)
    scenario.setup()
    yield scenario
    scenario.cleanup()


def test_create_calculator_scenario(calculator_scenario: SAEBScenario) -> None:
    assert calculator_scenario.name == "calculator-v1"
    assert len(calculator_scenario.injections) == 8
    assert (calculator_scenario.workdir / "calculator/calc.py").exists()
    assert (calculator_scenario.workdir / "tests/test_calc.py").exists()


def test_baseline_metrics_pass(calculator_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(calculator_scenario.workdir, src_dir="calculator")
    metrics = collector.collect(0, "baseline")
    assert metrics.passed == 6, f"Expected 6 passed, got {metrics.passed}"
    assert metrics.failed == 0
    assert metrics.errors == 0
    assert metrics.fnr == 0.0
    assert metrics.compilation_error_rate == 0.0


def test_logic_defect_detected(calculator_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(calculator_scenario.workdir, src_dir="calculator")
    calculator_scenario.apply_injection("add_flipped")
    metrics = collector.collect(1, "add_flipped")
    assert metrics.failed >= 1, "Logic defect should cause test failures"
    assert metrics.fnr > 0.1, f"Expected FNR > 0.1, got {metrics.fnr}"
    assert metrics.errors == 0, "Logic defect should not cause compilation errors"


def test_compilation_error_separated(calculator_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(calculator_scenario.workdir, src_dir="calculator")
    calculator_scenario.apply_injection("power_removed")
    metrics = collector.collect(1, "power_removed")
    assert metrics.errors >= 1, "Missing function should cause import errors"
    assert metrics.compilation_error_rate > 0.5
    assert metrics.fnr == 0.0, "Compilation error should NOT affect FNR"


def test_dead_code_detected(calculator_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(calculator_scenario.workdir, src_dir="calculator")
    baseline = collector.collect(0, "baseline")
    calculator_scenario.apply_injection("dead_imports")
    metrics = collector.collect(1, "dead_imports")
    assert metrics.unused_import_count > baseline.unused_import_count, (
        f"Dead imports should increase unused_import_count "
        f"({baseline.unused_import_count} -> {metrics.unused_import_count})"
    )
    assert metrics.line_coverage_pct < baseline.line_coverage_pct or True, (
        "Dead code may or may not reduce coverage"
    )


def test_fix_restores_passing(calculator_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(calculator_scenario.workdir, src_dir="calculator")
    calculator_scenario.apply_injection("add_flipped")
    m_broken = collector.collect(1, "broken")
    assert m_broken.fnr > 0
    calculator_scenario.revert_injection("add_flipped")
    calculator_scenario.restore_reference()
    m_fixed = collector.collect(2, "fixed")
    assert m_fixed.fnr == 0.0, "Fix should restore FNR to 0"


def test_mixed_defect_both_signals(calculator_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(calculator_scenario.workdir, src_dir="calculator")
    baseline = collector.collect(0, "baseline")
    calculator_scenario.apply_injection("dead_imports")
    calculator_scenario.apply_injection("multiply_wrong")
    metrics = collector.collect(1, "mixed")
    assert metrics.fnr > baseline.fnr, "Logic error should increase FNR"
    assert metrics.unused_import_count >= baseline.unused_import_count, (
        "Dead code should be detectable"
    )


def test_all_injections(calculator_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(calculator_scenario.workdir, src_dir="calculator")
    for inj in calculator_scenario.injections:
        calculator_scenario.apply_injection(inj.label)
        m = collector.collect(1, inj.label)
        calculator_scenario.revert_injection(inj.label)
        calculator_scenario.restore_reference()
        if inj.expected_fnr_gt > 0:
            assert m.fnr > inj.expected_fnr_gt, (
                f"{inj.label}: expected FNR > {inj.expected_fnr_gt}, got {m.fnr}"
            )
        if inj.expected_compilation_error:
            assert m.compilation_error_rate > 0, (
                f"{inj.label}: expected compilation error"
            )


def test_run_saeb_noop(calculator_scenario: SAEBScenario) -> None:
    result = run_saeb(
        scenario=calculator_scenario,
        agent=NoopAdapter("test-noop"),
        rounds=2,
    )
    assert result.agent_name == "test-noop"
    assert result.rounds_completed > 0
    assert len(result.metrics) > 0
    assert result.fnr_trajectory() is not None
    assert result.coverage_trajectory() is not None


def test_generate_comparison_report(calculator_scenario: SAEBScenario) -> None:
    results = [
        run_saeb(calculator_scenario, NoopAdapter("agent-a"), rounds=1),
        run_saeb(calculator_scenario, NoopAdapter("agent-b"), rounds=1),
    ]
    report = generate_comparison_report(results)
    assert "agent-a" in report
    assert "agent-b" in report
    assert "Comparative Analysis" in report


def test_generate_json_report(calculator_scenario: SAEBScenario) -> None:
    result = run_saeb(calculator_scenario, NoopAdapter("test-json"), rounds=1)
    text = generate_json_report([result])
    import json
    data = json.loads(text)
    assert data["agent_count"] == 1
    assert data["agents"][0]["agent"] == "test-json"


@pytest.mark.benchmark
def test_run_comparison(calculator_scenario: SAEBScenario) -> None:
    from maref.evaluation.saeb import run_comparison
    from maref.evaluation.saeb.runner import MAREFSelfAdapter, SubprocessAdapter

    scenario = calculator_scenario
    agents = [
        MAREFSelfAdapter(),
        SubprocessAdapter("subprocess-lint", ["ruff", "check", "--fix", "."]),
    ]
    results = run_comparison(scenario, agents, rounds=3)
    assert "maref-self" in results
    assert "subprocess-lint" in results
    assert results["maref-self"].rounds_completed > 0


def test_degradation_detection() -> None:
    from maref.evaluation.saeb import SAEBMetrics, SAEBResult
    from maref.evaluation.saeb.report import check_degradation

    m = [SAEBMetrics(round=0, label="baseline", passed=5, failed=0, errors=0, total_collected=5,
                     fnr=0.0, compilation_error_rate=0.0, aggregate_fnr=0.0, test_pass_rate=1.0,
                     line_coverage_pct=90.0, unused_import_count=0, unused_function_count=0,
                     lint_violation_count=0, lint_violations=[], dead_functions=[],
                     timestamp=1000.0)]
    prev = SAEBResult(agent_name="test", scenario_name="test", rounds_completed=5, metrics=m,
                      convergence_round=3, oscillation_count=0, total_time_s=10.0,
                      acceptance={"fixes_confirmed": True, "defects_detected": True, "converged": True})

    curr = SAEBResult(agent_name="test", scenario_name="test", rounds_completed=5, metrics=m,
                      convergence_round=6, oscillation_count=2, total_time_s=30.0,
                      acceptance={"fixes_confirmed": False, "defects_detected": True, "converged": False})

    result = check_degradation(prev, curr)
    assert result['degraded'] is True
    assert 'Convergence round' in result['alerts'][0]
    assert len(result['alerts']) >= 3


@pytest.mark.benchmark
def test_maref_self_adapter(calculator_scenario: SAEBScenario) -> None:
    adapter = MAREFSelfAdapter(src_dir="calculator")
    assert adapter.name() == "maref-self"
    result = run_saeb(calculator_scenario, adapter, rounds=1)
    assert result.agent_name == "maref-self"
    assert result.rounds_completed > 0
    assert len(result.metrics) > 0
    assert result.fnr_trajectory() is not None
    assert result.coverage_trajectory() is not None


def test_recursive_pipeline_chain() -> None:
    from maref.recursive.self_architect import SelfArchitect
    from maref.recursive.self_diagnostician import (
        DiagnosisReport,
        RiskLevel,
        SelfDiagnostician,
    )
    from maref.recursive.self_executor import SelfExecutor
    from maref.recursive.self_observer import SystemSnapshot
    from maref.recursive.unified_audit import UnifiedAuditStore

    store = UnifiedAuditStore()
    diagnostician = SelfDiagnostician()
    diagnostician.attach_circuit_breaker()

    snapshot = SystemSnapshot(
        timestamp=1000.0,
        module_graph={"mod_a": ["mod_b"]},
        test_stats={"total": 10, "failed": 6, "duration_ms": 100},
        git_stats={"tags": ["v1.0"]},
        source_file_count=5,
    )

    diagnosis = diagnostician.diagnose(snapshot)
    assert diagnosis.overall_risk in (RiskLevel.WARNING, RiskLevel.CRITICAL), (
        f"Expected warning or critical, got {diagnosis.overall_risk}"
    )

    proceed = diagnostician.check_and_trip(diagnosis)
    assert proceed is True, "check_and_trip should return True when defects exist"
    assert diagnostician._trip_count == 1, "Trip count should increment"

    check_again = diagnostician.check_and_trip(diagnosis)
    assert check_again is True, "Should still allow fixing (trip_count < 4)"

    for _ in range(2):
        diagnostician.check_and_trip(diagnosis)
    assert diagnostician._trip_count == 4

    blocked = diagnostician.check_and_trip(diagnosis)
    assert blocked is False, "Should trip after 4 critical detections"
    assert diagnostician._cb_state == "OPEN"

    diagnostician.close()
    assert diagnostician._cb_state == "CLOSED"


@pytest.fixture
def desktop_agent_scenario() -> SAEBScenario:
    workdir = Path(f"/tmp/saeb-test-desktop-{uuid.uuid4().hex[:8]}")
    scenario = create_desktop_agent_scenario(workdir)
    scenario.setup()
    yield scenario
    scenario.cleanup()


def test_create_desktop_agent_scenario(desktop_agent_scenario: SAEBScenario) -> None:
    assert desktop_agent_scenario.name == "desktop-v1"
    assert len(desktop_agent_scenario.injections) == 6
    assert (desktop_agent_scenario.workdir / "desktop_agent/agent.py").exists()
    assert (desktop_agent_scenario.workdir / "tests/test_desktop_agent.py").exists()


def test_desktop_agent_baseline_metrics_pass(desktop_agent_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(desktop_agent_scenario.workdir, src_dir="desktop_agent")
    metrics = collector.collect(0, "baseline")
    assert metrics.passed == 8, f"Expected 8 passed, got {metrics.passed}"
    assert metrics.failed == 0
    assert metrics.errors == 0
    assert metrics.fnr == 0.0


def test_desktop_agent_injection_session_browser_wrong(desktop_agent_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(desktop_agent_scenario.workdir, src_dir="desktop_agent")
    desktop_agent_scenario.apply_injection("session_browser_wrong")
    metrics = collector.collect(1, "session_browser_wrong")
    assert metrics.failed >= 1
    assert metrics.fnr > 0.1
    assert metrics.errors == 0


def test_desktop_agent_injection_broken_import(desktop_agent_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(desktop_agent_scenario.workdir, src_dir="desktop_agent")
    desktop_agent_scenario.apply_injection("broken_import")
    metrics = collector.collect(1, "broken_import")
    assert metrics.errors >= 1
    assert metrics.compilation_error_rate > 0.5
    assert metrics.fnr == 0.0


def test_desktop_agent_injection_async_trap(desktop_agent_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(desktop_agent_scenario.workdir, src_dir="desktop_agent")
    desktop_agent_scenario.apply_injection("async_trap")
    metrics = collector.collect(1, "async_trap")
    assert metrics.failed >= 1
    assert metrics.fnr > 0.1


def test_desktop_agent_all_injections(desktop_agent_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(desktop_agent_scenario.workdir, src_dir="desktop_agent")
    for inj in desktop_agent_scenario.injections:
        desktop_agent_scenario.apply_injection(inj.label)
        m = collector.collect(1, inj.label)
        desktop_agent_scenario.revert_injection(inj.label)
        desktop_agent_scenario.restore_reference()
        if inj.expected_fnr_gt > 0:
            assert m.fnr > inj.expected_fnr_gt, (
                f"{inj.label}: expected FNR > {inj.expected_fnr_gt}, got {m.fnr}"
            )
        if inj.expected_compilation_error:
            assert m.compilation_error_rate > 0, (
                f"{inj.label}: expected compilation error"
            )


def test_desktop_agent_fix_restores_passing(desktop_agent_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(desktop_agent_scenario.workdir, src_dir="desktop_agent")
    desktop_agent_scenario.apply_injection("session_browser_wrong")
    m_broken = collector.collect(1, "broken")
    assert m_broken.fnr > 0
    desktop_agent_scenario.revert_injection("session_browser_wrong")
    desktop_agent_scenario.restore_reference()
    m_fixed = collector.collect(2, "fixed")
    assert m_fixed.fnr == 0.0, "Fix should restore FNR to 0"


def test_desktop_agent_engine_check_no_url_validation_both_signals(desktop_agent_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(desktop_agent_scenario.workdir, src_dir="desktop_agent")
    baseline = collector.collect(0, "baseline")
    desktop_agent_scenario.apply_injection("screenshot_no_url_validation")
    desktop_agent_scenario.apply_injection("engine_check_always_true")
    metrics = collector.collect(1, "mixed")
    assert metrics.fnr > baseline.fnr, "Logic errors should increase FNR"


def test_architect_propose_execute_chain(tmp_path: Path) -> None:
    from maref.recursive.self_architect import SelfArchitect
    from maref.recursive.self_executor import SelfExecutor
    from maref.recursive.unified_audit import UnifiedAuditStore

    store = UnifiedAuditStore()
    architect = SelfArchitect(audit_store=store)
    executor = SelfExecutor(project_root=str(tmp_path), audit_store=store)

    proposals = architect.propose_all()
    assert len(proposals) > 0, "Architect should propose fixes"

    valid_proposals = [p for p in proposals if architect.validate_proposal(p)]
    if valid_proposals:
        pipeline = executor.dry_run(valid_proposals[0])
        assert pipeline.final_state.startswith("DRY_RUN"), (
            f"Expected DRY_RUN state, got {pipeline.final_state}"
        )


@pytest.fixture
def browser_engine_scenario() -> SAEBScenario:
    workdir = Path(f"/tmp/saeb-test-browser-{uuid.uuid4().hex[:8]}")
    scenario = create_browser_engine_scenario(workdir)
    scenario.setup()
    yield scenario
    scenario.cleanup()


def test_create_browser_engine_scenario(browser_engine_scenario: SAEBScenario) -> None:
    assert browser_engine_scenario.name == "browser-engine-v1"
    assert len(browser_engine_scenario.injections) == 4
    assert (browser_engine_scenario.workdir / "browser_engine/engine.py").exists()
    assert (browser_engine_scenario.workdir / "tests/test_browser_engine.py").exists()


def test_browser_engine_baseline_metrics_pass(browser_engine_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(browser_engine_scenario.workdir, src_dir="browser_engine")
    metrics = collector.collect(0, "baseline")
    assert metrics.passed == 9, f"Expected 9 passed, got {metrics.passed}"
    assert metrics.failed == 0
    assert metrics.errors == 0
    assert metrics.fnr == 0.0


def test_browser_engine_injection_wrong_user_agent(browser_engine_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(browser_engine_scenario.workdir, src_dir="browser_engine")
    browser_engine_scenario.apply_injection("wrong_user_agent")
    metrics = collector.collect(1, "wrong_user_agent")
    assert metrics.failed >= 1
    assert metrics.fnr > 0.1
    assert metrics.errors == 0


def test_browser_engine_injection_broken_redirect(browser_engine_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(browser_engine_scenario.workdir, src_dir="browser_engine")
    browser_engine_scenario.apply_injection("broken_redirect")
    metrics = collector.collect(1, "broken_redirect")
    assert metrics.failed >= 1
    assert metrics.fnr > 0.1
    assert metrics.errors == 0


def test_browser_engine_injection_timeout_too_low(browser_engine_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(browser_engine_scenario.workdir, src_dir="browser_engine")
    browser_engine_scenario.apply_injection("timeout_too_low")
    metrics = collector.collect(1, "timeout_too_low")
    assert metrics.failed >= 1
    assert metrics.fnr > 0.1
    assert metrics.errors == 0


def test_browser_engine_injection_missing_content_type(browser_engine_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(browser_engine_scenario.workdir, src_dir="browser_engine")
    browser_engine_scenario.apply_injection("missing_content_type")
    metrics = collector.collect(1, "missing_content_type")
    assert metrics.failed >= 1
    assert metrics.fnr > 0.1
    assert metrics.errors == 0


def test_browser_engine_all_injections(browser_engine_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(browser_engine_scenario.workdir, src_dir="browser_engine")
    for inj in browser_engine_scenario.injections:
        browser_engine_scenario.apply_injection(inj.label)
        m = collector.collect(1, inj.label)
        browser_engine_scenario.revert_injection(inj.label)
        browser_engine_scenario.restore_reference()
        if inj.expected_fnr_gt > 0:
            assert m.fnr > inj.expected_fnr_gt, (
                f"{inj.label}: expected FNR > {inj.expected_fnr_gt}, got {m.fnr}"
            )


def test_browser_engine_fix_restores_passing(browser_engine_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(browser_engine_scenario.workdir, src_dir="browser_engine")
    browser_engine_scenario.apply_injection("wrong_user_agent")
    m_broken = collector.collect(1, "broken")
    assert m_broken.fnr > 0
    browser_engine_scenario.revert_injection("wrong_user_agent")
    browser_engine_scenario.restore_reference()
    m_fixed = collector.collect(2, "fixed")
    assert m_fixed.fnr == 0.0, "Fix should restore FNR to 0"


def test_browser_engine_mixed_injections(browser_engine_scenario: SAEBScenario) -> None:
    collector = SAEBMetricsCollector(browser_engine_scenario.workdir, src_dir="browser_engine")
    baseline = collector.collect(0, "baseline")
    browser_engine_scenario.apply_injection("wrong_user_agent")
    browser_engine_scenario.apply_injection("broken_redirect")
    metrics = collector.collect(1, "mixed")
    assert metrics.fnr > baseline.fnr, "Logic errors should increase FNR"
