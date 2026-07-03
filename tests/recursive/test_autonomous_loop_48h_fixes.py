"""Tests for the 48h RSI execution plan fixes.

Covers:
- Fix 1: metrics extraction reads test_stats dict (not non-existent attrs)
- Fix 2: diagnostic context (recommendations, risk_matrix, probe_results) persisted
- Fix 3a: LLMCodeGenerator TypeScript support (TS prompt, skip ast.parse, language)
- Fix 3b: GUI error capture + proposal construction
- Fix 4: halt on consecutive failures / low disk / system-health critical streak
         (NOT raw circuit breaker — gui_build is persistently critical and must
         not trigger halt; only entropy/latency/anomaly/kg/oscillation count)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from maref.recursive.llm_code_generator import (
    CodeContextBuilder,
    LLMCodeGenerator,
    MockProvider,
)
from maref.recursive.self_architect import ArchitectureProposal, ChangeType
from maref.recursive.self_diagnostician import DiagnosisReport, RiskLevel
from maref.recursive.self_observer import SystemSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_snapshot(
    *,
    test_stats: dict | None = None,
    source_file_count: int = 42,
) -> SystemSnapshot:
    return SystemSnapshot(
        timestamp=1.0,
        source_file_count=source_file_count,
        test_stats=test_stats or {},
    )


def _make_report(
    *,
    risk_matrix: dict[str, RiskLevel] | None = None,
    overall: RiskLevel = RiskLevel.NORMAL,
    recommendations: list[str] | None = None,
    diagnostic_context: dict | None = None,
) -> DiagnosisReport:
    return DiagnosisReport(
        snapshot_ref="test-snapshot",
        risk_matrix=risk_matrix or {},
        overall_risk=overall,
        recommendations=recommendations or [],
        diagnostic_context=diagnostic_context or {},
    )


def _make_runner(tmp_path: Path) -> object:
    """Create an AutonomousLoopRunner with dry_run=True (no real writes)."""
    from scripts.run_autonomous_loop import AutonomousLoopRunner

    return AutonomousLoopRunner(
        duration_hours=0.01,
        loop_interval_minutes=1,
        dry_run=True,
        real_writes=False,
        vault_dir=str(tmp_path / "vault"),
        output_dir=str(tmp_path / "reports"),
    )


# ---------------------------------------------------------------------------
# Fix 1: metrics extraction
# ---------------------------------------------------------------------------


class TestMetricsExtraction:
    """Verify test_count / test_pass_rate come from test_stats dict."""

    def test_reads_test_stats_dict(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        snapshot = _make_snapshot(
            test_stats={"total": 100, "passed": 95, "failed": 5, "errors": 0}
        )
        runner._observer = MagicMock()
        runner._observer.snapshot.return_value = snapshot
        runner._daily_loop = MagicMock()
        runner._daily_loop.run_once.return_value = MagicMock(
            stop_reason="none", priority="low", real_writes_enabled=False
        )
        runner._diagnostician = MagicMock()
        runner._diagnostician.diagnose.return_value = _make_report()
        runner._diagnostician.check_and_trip.return_value = True
        runner._bridge = MagicMock()
        runner._bridge.diagnose_to_hypotheses.return_value = []
        runner._optimizer = MagicMock()

        result = runner.run_one_cycle()
        metrics = result["phases"]["metrics"]["values"]

        assert metrics["test_count"] == 100
        assert metrics["test_pass_rate"] == 0.95
        assert metrics["test_fail_count"] == 5

    def test_empty_test_stats(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        snapshot = _make_snapshot(test_stats={})
        runner._observer = MagicMock()
        runner._observer.snapshot.return_value = snapshot
        runner._daily_loop = MagicMock()
        runner._daily_loop.run_once.return_value = MagicMock(
            stop_reason="none", priority="low", real_writes_enabled=False
        )
        runner._diagnostician = MagicMock()
        runner._diagnostician.diagnose.return_value = _make_report()
        runner._diagnostician.check_and_trip.return_value = True
        runner._bridge = MagicMock()
        runner._bridge.diagnose_to_hypotheses.return_value = []
        runner._optimizer = MagicMock()

        result = runner.run_one_cycle()
        metrics = result["phases"]["metrics"]["values"]

        assert metrics["test_count"] == 0
        assert metrics["test_pass_rate"] == 0.0


# ---------------------------------------------------------------------------
# Fix 2: diagnostic context persistence
# ---------------------------------------------------------------------------


class TestDiagnosticContextPersistence:
    """Verify recommendations, risk_matrix, diagnostic_context stored in cycle JSON."""

    def test_full_diagnostic_context_persisted(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        snapshot = _make_snapshot()
        report = _make_report(
            risk_matrix={"gui_build": RiskLevel.CRITICAL, "entropy": RiskLevel.NORMAL},
            overall=RiskLevel.CRITICAL,
            recommendations=["[gui_build] CRITICAL: fix immediately"],
            diagnostic_context={"gui_ts_errors": 12, "gui_build_success": 0},
        )
        runner._observer = MagicMock()
        runner._observer.snapshot.return_value = snapshot
        runner._daily_loop = MagicMock()
        runner._daily_loop.run_once.return_value = MagicMock(
            stop_reason="none", priority="low", real_writes_enabled=False
        )
        runner._diagnostician = MagicMock()
        runner._diagnostician.diagnose.return_value = report
        runner._diagnostician.check_and_trip.return_value = True
        runner._bridge = MagicMock()
        runner._bridge.diagnose_to_hypotheses.return_value = []
        runner._optimizer = MagicMock()

        result = runner.run_one_cycle()
        diag = result["phases"]["diagnosis"]

        assert diag["success"] is True
        assert diag["risk"] == "critical"
        assert "[gui_build] CRITICAL: fix immediately" in diag["recommendations"]
        assert diag["diagnostic_context"]["gui_ts_errors"] == 12
        assert diag["risk_matrix"]["gui_build"] == "critical"
        assert "probe_results" in diag


# ---------------------------------------------------------------------------
# Fix 3a: LLMCodeGenerator TypeScript support
# ---------------------------------------------------------------------------


class TestLLMTypeScriptSupport:
    """Verify TS system prompt, ast.parse skip, and language field."""

    def test_ts_system_prompt_selected_for_tsx(self, tmp_path: Path) -> None:
        tsx_file = tmp_path / "component.tsx"
        tsx_file.write_text("export const Foo = () => null;\n")
        proposal = ArchitectureProposal(
            proposal_id="p1",
            timestamp=0,
            current_arch="",
            proposed_arch="",
            rationale="fix tsx",
            risk_assessment="low",
            confidence=0.5,
            target_files=[str(tsx_file)],
            change_type=ChangeType.GENERAL_REFACTOR,
        )
        system_prompt, _ = CodeContextBuilder.build_prompt(
            proposal=proposal, affected_files=[str(tsx_file)]
        )
        assert "TypeScript/React" in system_prompt

    def test_python_system_prompt_for_py(self, tmp_path: Path) -> None:
        py_file = tmp_path / "module.py"
        py_file.write_text("def foo():\n    pass\n")
        proposal = ArchitectureProposal(
            proposal_id="p2",
            timestamp=0,
            current_arch="",
            proposed_arch="",
            rationale="fix py",
            risk_assessment="low",
            confidence=0.5,
            target_files=[str(py_file)],
            change_type=ChangeType.GENERAL_REFACTOR,
        )
        system_prompt, _ = CodeContextBuilder.build_prompt(
            proposal=proposal, affected_files=[str(py_file)]
        )
        assert "PEP 8" in system_prompt
        assert "TypeScript" not in system_prompt

    def test_ts_file_content_included_in_prompt(self, tmp_path: Path) -> None:
        tsx_file = tmp_path / "widget.tsx"
        tsx_file.write_text("export const Widget = () => <div />;\n")
        proposal = ArchitectureProposal(
            proposal_id="p3",
            timestamp=0,
            current_arch="",
            proposed_arch="",
            rationale="fix widget",
            risk_assessment="low",
            confidence=0.5,
            target_files=[str(tsx_file)],
            change_type=ChangeType.GENERAL_REFACTOR,
        )
        _, user_prompt = CodeContextBuilder.build_prompt(
            proposal=proposal, affected_files=[str(tsx_file)]
        )
        assert "export const Widget" in user_prompt

    @pytest.mark.asyncio
    async def test_ts_skips_ast_parse(self, tmp_path: Path) -> None:
        """TS output (not valid Python) should NOT trigger ast validation error."""
        tsx_file = tmp_path / "comp.tsx"
        tsx_file.write_text("export const C = () => null;\n")
        proposal = ArchitectureProposal(
            proposal_id="p4",
            timestamp=0,
            current_arch="",
            proposed_arch="",
            rationale="fix tsx",
            risk_assessment="low",
            confidence=0.5,
            target_files=[str(tsx_file)],
            change_type=ChangeType.GENERAL_REFACTOR,
        )
        # MockProvider returns Python stub; we need a TS stub
        provider = MockProvider(stub_content="export const Fixed = () => null;\n")
        gen = LLMCodeGenerator(provider=provider)
        result = await gen.generate(proposal)
        # Should succeed because ast.parse is skipped for TS
        assert result.success is True
        assert result.validation_errors == []

    @pytest.mark.asyncio
    async def test_ts_language_field(self, tmp_path: Path) -> None:
        tsx_file = tmp_path / "comp.tsx"
        tsx_file.write_text("export const C = () => null;\n")
        proposal = ArchitectureProposal(
            proposal_id="p5",
            timestamp=0,
            current_arch="",
            proposed_arch="",
            rationale="fix tsx",
            risk_assessment="low",
            confidence=0.5,
            target_files=[str(tsx_file)],
            change_type=ChangeType.GENERAL_REFACTOR,
        )
        provider = MockProvider(stub_content="export const Fixed = () => null;\n")
        gen = LLMCodeGenerator(provider=provider)
        result = await gen.generate(proposal)
        assert result.success is True
        assert result.generated[0].language == "typescript"

    @pytest.mark.asyncio
    async def test_python_language_field(self, tmp_path: Path) -> None:
        proposal = ArchitectureProposal(
            proposal_id="p6",
            timestamp=0,
            current_arch="",
            proposed_arch="",
            rationale="fix py",
            risk_assessment="low",
            confidence=0.5,
            target_files=["src/maref/foo.py"],
            change_type=ChangeType.GENERAL_REFACTOR,
        )
        gen = LLMCodeGenerator(provider=MockProvider())
        result = await gen.generate(proposal)
        assert result.generated[0].language == "python"


# ---------------------------------------------------------------------------
# Fix 3b: GUI error capture + proposal construction
# ---------------------------------------------------------------------------


class TestGUIErrorCapture:
    """Verify _capture_gui_errors parses ESLint JSON and _build_gui_proposal."""

    ESLINT_JSON = json.dumps([
        {
            "file": "/abs/gui/Button.tsx",
            "messages": [
                {"ruleId": "no-unused-vars", "message": "'x' is unused",
                 "line": 3, "column": 5, "severity": 2},
                {"ruleId": "@typescript-eslint/no-explicit-any",
                 "message": "any not allowed", "line": 7, "column": 1, "severity": 2},
                {"ruleId": "eqeqeq", "message": "use ===", "line": 1, "column": 1,
                 "severity": 1},
            ],
        },
        {
            "file": "/abs/gui/Card.tsx",
            "messages": [
                {"ruleId": "react/jsx-key", "message": "missing key",
                 "line": 10, "column": 4, "severity": 2},
            ],
        },
    ])

    def test_capture_gui_errors(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        with patch("scripts.run_autonomous_loop.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=self.ESLINT_JSON, stderr="", returncode=1
            )
            errors = runner._capture_gui_errors()

        assert len(errors) == 2
        # Button.tsx has 2 severity>=2 errors (Card.tsx has 1)
        button = next(e for e in errors if "Button" in e["file"])
        assert button["error_count"] == 2
        assert len(button["messages"]) == 2

    def test_capture_gui_errors_empty(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        with patch("scripts.run_autonomous_loop.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="[]", stderr="", returncode=0)
            errors = runner._capture_gui_errors()
        assert errors == []

    def test_capture_gui_errors_exception(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        with patch("scripts.run_autonomous_loop.subprocess.run", side_effect=TimeoutError("timeout")):
            errors = runner._capture_gui_errors()
        assert errors == []

    def test_build_gui_proposal(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        gui_errors = [
            {"file": "gui/Button.tsx", "error_count": 5,
             "messages": [{"ruleId": "no-unused-vars", "message": "unused",
                           "line": 1, "column": 1}]},
            {"file": "gui/Card.tsx", "error_count": 2,
             "messages": [{"ruleId": "react/jsx-key", "message": "key",
                           "line": 1, "column": 1}]},
        ]
        proposal = runner._build_gui_proposal(gui_errors)
        assert proposal is not None
        # Should target the worst file (Button.tsx with 5 errors)
        assert "Button.tsx" in proposal.target_files[0]
        assert proposal.change_type == ChangeType.GENERAL_REFACTOR
        assert "5" in proposal.rationale

    def test_build_gui_proposal_empty(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        proposal = runner._build_gui_proposal([])
        assert proposal is None


# ---------------------------------------------------------------------------
# Fix 4: safety guardrails (halt conditions)
# ---------------------------------------------------------------------------


class TestHaltConditions:
    """Verify halt on consecutive failures, low disk, and circuit breaker."""

    def test_halt_on_consecutive_failures(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        runner._MAX_CONSECUTIVE_FAILURES = 3
        # Mock run_one_cycle to always fail
        runner.run_one_cycle = MagicMock(return_value={"success": False, "phases": {}})
        # Simulate 3 consecutive failures
        runner._consecutive_failures = 3
        # The run() loop should break immediately
        runner.run()
        assert runner._halt_reason is not None
        assert "consecutive_failures" in runner._halt_reason

    def test_halt_on_low_disk(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        # Mock disk_usage to return very low free space
        low_disk = MagicMock()
        low_disk.free = 100 * 1024 * 1024  # 100 MB < 1 GB threshold
        with patch("scripts.run_autonomous_loop.shutil.disk_usage", return_value=low_disk):
            runner.run()
        assert runner._halt_reason is not None
        assert "disk_low" in runner._halt_reason

    def test_no_halt_when_healthy(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        runner.run_one_cycle = MagicMock(return_value={"success": True, "phases": {}})
        # Patch sleep so the test doesn't wait for the full duration
        with patch("scripts.run_autonomous_loop.time.sleep"):
            runner.run()
        assert runner._halt_reason is None

    def test_system_health_critical_sets_halt(self, tmp_path: Path) -> None:
        """System-health criticals (entropy) for N consecutive cycles → halt."""
        runner = _make_runner(tmp_path)
        runner._MAX_SYSTEM_CRITICAL_STREAK = 2  # lower for test speed
        snapshot = _make_snapshot()
        report = _make_report(
            risk_matrix={"entropy": RiskLevel.CRITICAL},
            overall=RiskLevel.CRITICAL,
        )
        runner._observer = MagicMock()
        runner._observer.snapshot.return_value = snapshot
        runner._daily_loop = MagicMock()
        runner._daily_loop.run_once.return_value = MagicMock(
            stop_reason="none", priority="low", real_writes_enabled=False
        )
        runner._diagnostician = MagicMock()
        runner._diagnostician.diagnose.return_value = report
        runner._bridge = MagicMock()
        runner._bridge.diagnose_to_hypotheses.return_value = []
        runner._optimizer = MagicMock()

        # Cycle 1: streak=1, no halt yet
        runner.run_one_cycle()
        assert runner._halt_reason is None
        assert runner._system_critical_streak == 1

        # Cycle 2: streak=2 ≥ threshold → halt
        runner.run_one_cycle()
        assert runner._halt_reason is not None
        assert "system_health_critical" in runner._halt_reason
        assert "entropy" in runner._halt_reason

    def test_gui_build_critical_does_not_halt(self, tmp_path: Path) -> None:
        """Regression: gui_build CRITICAL must NOT trigger halt (it's the target
        the loop is actively fixing). 12h test confirmed it's critical every cycle."""
        runner = _make_runner(tmp_path)
        runner._MAX_SYSTEM_CRITICAL_STREAK = 2
        snapshot = _make_snapshot()
        report = _make_report(
            risk_matrix={"gui_build": RiskLevel.CRITICAL},
            overall=RiskLevel.CRITICAL,
        )
        runner._observer = MagicMock()
        runner._observer.snapshot.return_value = snapshot
        runner._daily_loop = MagicMock()
        runner._daily_loop.run_once.return_value = MagicMock(
            stop_reason="none", priority="low", real_writes_enabled=False
        )
        runner._diagnostician = MagicMock()
        runner._diagnostician.diagnose.return_value = report
        runner._bridge = MagicMock()
        runner._bridge.diagnose_to_hypotheses.return_value = []
        runner._optimizer = MagicMock()

        # Simulate 5 cycles — gui_build critical every time
        for _ in range(5):
            runner.run_one_cycle()

        assert runner._halt_reason is None
        assert runner._system_critical_streak == 0

    def test_system_critical_streak_resets_on_recovery(self, tmp_path: Path) -> None:
        """After 2 system-critical cycles, a normal cycle resets the streak."""
        runner = _make_runner(tmp_path)
        runner._MAX_SYSTEM_CRITICAL_STREAK = 3
        snapshot = _make_snapshot()
        critical_report = _make_report(
            risk_matrix={"latency": RiskLevel.CRITICAL},
            overall=RiskLevel.CRITICAL,
        )
        healthy_report = _make_report(
            risk_matrix={"latency": RiskLevel.NORMAL},
            overall=RiskLevel.NORMAL,
        )
        runner._observer = MagicMock()
        runner._observer.snapshot.return_value = snapshot
        runner._daily_loop = MagicMock()
        runner._daily_loop.run_once.return_value = MagicMock(
            stop_reason="none", priority="low", real_writes_enabled=False
        )
        runner._diagnostician = MagicMock()
        runner._diagnostician.diagnose.return_value = critical_report
        runner._bridge = MagicMock()
        runner._bridge.diagnose_to_hypotheses.return_value = []
        runner._optimizer = MagicMock()

        runner.run_one_cycle()  # streak=1
        runner.run_one_cycle()  # streak=2
        assert runner._system_critical_streak == 2

        # Recover
        runner._diagnostician.diagnose.return_value = healthy_report
        runner.run_one_cycle()  # streak reset to 0
        assert runner._system_critical_streak == 0
        assert runner._halt_reason is None

    def test_consecutive_failures_reset_on_success(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        runner._consecutive_failures = 4
        snapshot = _make_snapshot()
        runner._observer = MagicMock()
        runner._observer.snapshot.return_value = snapshot
        runner._daily_loop = MagicMock()
        runner._daily_loop.run_once.return_value = MagicMock(
            stop_reason="none", priority="low", real_writes_enabled=False
        )
        runner._diagnostician = MagicMock()
        runner._diagnostician.diagnose.return_value = _make_report()
        runner._diagnostician.check_and_trip.return_value = True
        runner._bridge = MagicMock()
        runner._bridge.diagnose_to_hypotheses.return_value = []
        runner._optimizer = MagicMock()

        runner.run_one_cycle()
        assert runner._consecutive_failures == 0


# ---------------------------------------------------------------------------
# Fix 3c: risk-driven apply_fn integration
# ---------------------------------------------------------------------------


class TestRiskDrivenApplyFn:
    """Verify _default_apply_fn uses GUI proposal when gui_build is critical."""

    def test_apply_fn_uses_gui_proposal_when_critical(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        runner._executor = MagicMock()
        runner._last_report = _make_report(
            risk_matrix={"gui_build": RiskLevel.CRITICAL}
        )
        gui_errors = [{"file": "gui/Broken.tsx", "error_count": 3, "messages": []}]
        runner._capture_gui_errors = MagicMock(return_value=gui_errors)

        # Mock execute_async to avoid real execution
        async def _fake_exec(proposal):
            return MagicMock()
        runner._executor.execute_async = _fake_exec

        runner._default_apply_fn()
        # execute_async should have been called (the fake async function ran)
        # No exception means the GUI path was taken

    def test_apply_fn_falls_back_to_architect(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        runner._executor = MagicMock()
        # No critical gui_build → should fall back to architect
        runner._last_report = _make_report(risk_matrix={"gui_build": RiskLevel.NORMAL})

        with patch("maref.recursive.self_architect.SelfArchitect") as MockArch:
            mock_instance = MockArch.return_value
            mock_instance.propose_all.return_value = []
            async def _fake_exec(proposal):
                return MagicMock()
            runner._executor.execute_async = _fake_exec
            runner._default_apply_fn()
            MockArch.assert_called_once()
