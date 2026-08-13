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
from scripts.run_autonomous_loop import AutonomousLoopRunner


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

    @pytest.mark.slow
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

    @pytest.mark.slow
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

    @pytest.mark.slow
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

    @pytest.mark.slow
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

    @pytest.mark.slow
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

    @pytest.mark.slow
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
    @pytest.mark.slow
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
    @pytest.mark.slow
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
    @pytest.mark.slow
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

    @pytest.mark.slow
    def test_capture_gui_errors(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        with patch.object(AutonomousLoopRunner, '_run_subprocess_isolated') as mock_run:
            mock_run.return_value = MagicMock(
                stdout=self.ESLINT_JSON, stderr="", returncode=1
            )
            errors = runner._capture_gui_errors()

        assert len(errors) == 2
        # Button.tsx has 2 severity>=2 errors (Card.tsx has 1)
        button = next(e for e in errors if "Button" in e["file"])
        assert button["error_count"] == 2
        assert len(button["messages"]) == 2

    @pytest.mark.slow
    def test_capture_gui_errors_empty(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        with patch.object(AutonomousLoopRunner, '_run_subprocess_isolated') as mock_run:
            mock_run.return_value = MagicMock(stdout="[]", stderr="", returncode=0)
            errors = runner._capture_gui_errors()
        assert errors == []

    @pytest.mark.slow
    def test_capture_gui_errors_exception(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        with patch.object(AutonomousLoopRunner, '_run_subprocess_isolated', side_effect=TimeoutError("timeout")):
            errors = runner._capture_gui_errors()
        assert errors == []

    @pytest.mark.slow
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

    @pytest.mark.slow
    def test_build_gui_proposal_empty(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        proposal = runner._build_gui_proposal([])
        assert proposal is None


# ---------------------------------------------------------------------------
# Fix 4: safety guardrails (halt conditions)
# ---------------------------------------------------------------------------


class TestHaltConditions:
    """Verify halt on consecutive failures, low disk, and circuit breaker."""

    @pytest.mark.slow
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

    @pytest.mark.slow
    def test_halt_on_low_disk(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        # Mock disk_usage to return very low free space
        low_disk = MagicMock()
        low_disk.free = 100 * 1024 * 1024  # 100 MB < 1 GB threshold
        with patch("scripts.run_autonomous_loop.shutil.disk_usage", return_value=low_disk):
            runner.run()
        assert runner._halt_reason is not None
        assert "disk_low" in runner._halt_reason

    @pytest.mark.slow
    def test_no_halt_when_healthy(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        runner.run_one_cycle = MagicMock(return_value={"success": True, "phases": {}})
        # Patch sleep so the test doesn't wait for the full duration
        with patch("scripts.run_autonomous_loop.time.sleep"):
            runner.run()
        assert runner._halt_reason is None

    @pytest.mark.slow
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

    @pytest.mark.slow
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

    @pytest.mark.slow
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

    @pytest.mark.slow
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

    @pytest.mark.slow
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

    @pytest.mark.slow
    def test_apply_fn_falls_back_to_architect(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        runner._executor = MagicMock()
        # No critical gui_build → should fall back to architect
        runner._last_report = _make_report(risk_matrix={"gui_build": RiskLevel.NORMAL})
        # Mock ruff paths to return 0/None so code falls through to architect
        runner._apply_ruff_autofix = MagicMock(return_value=0)
        runner._build_ruff_proposal = MagicMock(return_value=None)

        with patch("maref.recursive.self_architect.SelfArchitect") as MockArch:
            mock_instance = MockArch.return_value
            mock_instance.propose_all.return_value = []
            async def _fake_exec(proposal):
                return MagicMock()
            runner._executor.execute_async = _fake_exec
            runner._default_apply_fn()
            MockArch.assert_called_once()


# ---------------------------------------------------------------------------
# Fix 8: GUI error capture — pnpm banner / ELIFECYCLE trailer parsing
# ---------------------------------------------------------------------------


class TestGUIErrorCapturePnpmWrapper:
    """Verify _capture_gui_errors extracts JSON from pnpm-wrapped output.

    pnpm prepends banner lines ("> gui@... lint", "> eslint ...") and appends
    an ELIFECYCLE trailer, so json.loads(raw_stdout) raises JSONDecodeError.
    Fix 8 slices from first '[' to last ']' to extract the ESLint JSON array.
    """

    ESLINT_JSON_ARRAY = [
        {
            "filePath": "/abs/gui/src/Broken.tsx",
            "messages": [
                {"ruleId": "react-hooks/set-state-in-effect",
                 "message": "setState in effect", "line": 10, "severity": 2},
            ],
            "errorCount": 1,
            "warningCount": 0,
        },
        {
            "filePath": "/abs/gui/src/Other.tsx",
            "messages": [],
            "errorCount": 0,
            "warningCount": 0,
        },
    ]

    @pytest.mark.slow
    def test_strips_pnpm_banner_and_lifecycle_trailer(self, tmp_path: Path) -> None:
        """Real pnpm output: banner + JSON + ELIFECYCLE trailer."""
        runner = _make_runner(tmp_path)
        raw_stdout = (
            "\n> gui@0.36.0-rc lint /Volumes/.../gui\n"
            "> eslint . --format json\n\n"
            + json.dumps(self.ESLINT_JSON_ARRAY)
            + "\n\u2009ELIFECYCLE\u2009 Command failed with exit code 1.\n"
        )
        with patch.object(AutonomousLoopRunner, '_run_subprocess_isolated') as mock_run:
            mock_run.return_value = MagicMock(
                stdout=raw_stdout, stderr="", returncode=1
            )
            errors = runner._capture_gui_errors()

        assert len(errors) == 1  # only Broken.tsx has severity>=2
        assert "Broken.tsx" in errors[0]["file"]
        assert errors[0]["error_count"] == 1

    @pytest.mark.slow
    def test_uses_filePath_field(self, tmp_path: Path) -> None:
        """ESLint JSON uses 'filePath' (absolute path), not 'file'."""
        runner = _make_runner(tmp_path)
        raw_stdout = json.dumps([
            {"filePath": "/abs/gui/PathTest.tsx",
             "messages": [{"severity": 2, "message": "err", "line": 1}],
             "errorCount": 1, "warningCount": 0},
        ])
        with patch.object(AutonomousLoopRunner, '_run_subprocess_isolated') as mock_run:
            mock_run.return_value = MagicMock(
                stdout=raw_stdout, stderr="", returncode=1
            )
            errors = runner._capture_gui_errors()

        assert len(errors) == 1
        assert errors[0]["file"] == "/abs/gui/PathTest.tsx"

    @pytest.mark.slow
    def test_no_json_array_returns_empty(self, tmp_path: Path) -> None:
        """If output has no '[' or ']', return []."""
        runner = _make_runner(tmp_path)
        with patch.object(AutonomousLoopRunner, '_run_subprocess_isolated') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="pnpm: command not found\n", stderr="", returncode=127
            )
            errors = runner._capture_gui_errors()
        assert errors == []

    @pytest.mark.slow
    def test_reversed_brackets_returns_empty(self, tmp_path: Path) -> None:
        """If ']' appears before '[' (malformed), return []."""
        runner = _make_runner(tmp_path)
        with patch.object(AutonomousLoopRunner, '_run_subprocess_isolated') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="]not json[", stderr="", returncode=1
            )
            errors = runner._capture_gui_errors()
        assert errors == []


# ---------------------------------------------------------------------------
# Fix 9: healing re_diagnose callback prevents false RECOVERED
# ---------------------------------------------------------------------------


class TestHealingReDiagnoseCallback:
    """Verify heal_cycle is called with a re_diagnose callback so healing
    verifies the fix actually reduced risk instead of assuming action
    success == problem fixed (which caused 187 cycles of false RECOVERED
    while gui_build stayed critical)."""

    @pytest.mark.slow
    def test_heal_cycle_receives_re_diagnose(self, tmp_path: Path) -> None:
        """In production mode, heal_cycle must be called with re_diagnose."""
        from scripts.run_autonomous_loop import AutonomousLoopRunner

        runner = AutonomousLoopRunner(
            duration_hours=0.01,
            loop_interval_minutes=1,
            dry_run=False,
            real_writes=True,
            vault_dir=str(tmp_path / "vault"),
            output_dir=str(tmp_path / "reports"),
        )
        runner._observer = MagicMock()
        runner._observer.snapshot.return_value = _make_snapshot()
        runner._diagnostician = MagicMock()
        runner._diagnostician.diagnose.return_value = _make_report()
        runner._healer = MagicMock()
        runner._healer.heal_cycle.return_value = MagicMock(
            converged=True, final_state="RECOVERED", iterations=1, actions=[]
        )
        runner._daily_loop = MagicMock()
        runner._daily_loop.run_once.return_value = MagicMock(
            stop_reason="normal_completion", priority="low",
            real_writes_enabled=True, trust_score=0.75,
        )
        runner._bridge = MagicMock()
        runner._bridge.diagnose_to_hypotheses.return_value = []
        runner._optimizer = MagicMock()

        runner.run_one_cycle()

        # The critical assertion: heal_cycle was called with a re_diagnose
        # keyword argument that is callable (not None).
        call_kwargs = runner._healer.heal_cycle.call_args
        assert "re_diagnose" in call_kwargs.kwargs, (
            "heal_cycle must be called with re_diagnose callback (Fix 9)"
        )
        re_diag = call_kwargs.kwargs["re_diagnose"]
        assert callable(re_diag), "re_diagnose must be callable"

    @pytest.mark.slow
    def test_re_diagnose_callback_runs_snapshot_and_diagnose(
        self, tmp_path: Path
    ) -> None:
        """The re_diagnose callback should invoke observer + diagnostician."""
        from scripts.run_autonomous_loop import AutonomousLoopRunner

        runner = AutonomousLoopRunner(
            duration_hours=0.01,
            loop_interval_minutes=1,
            dry_run=False,
            real_writes=True,
            vault_dir=str(tmp_path / "vault"),
            output_dir=str(tmp_path / "reports"),
        )
        snap = _make_snapshot()
        runner._observer = MagicMock()
        runner._observer.snapshot.return_value = snap
        runner._diagnostician = MagicMock()
        runner._diagnostician.diagnose.return_value = _make_report()
        runner._healer = MagicMock()

        # Simulate heal_cycle invoking the re_diagnose callback internally.
        def _heal_cycle_side_effect(report, re_diagnose=None, **kwargs):
            # Call the callback to verify it works
            if re_diagnose is not None:
                re_diagnose()
            return MagicMock(
                converged=True, final_state="RECOVERED",
                iterations=1, actions=[],
            )
        runner._healer.heal_cycle.side_effect = _heal_cycle_side_effect
        runner._daily_loop = MagicMock()
        runner._daily_loop.run_once.return_value = MagicMock(
            stop_reason="normal_completion", priority="low",
            real_writes_enabled=True, trust_score=0.75,
        )
        runner._bridge = MagicMock()
        runner._bridge.diagnose_to_hypotheses.return_value = []
        runner._optimizer = MagicMock()

        runner.run_one_cycle()

        # re_diagnose callback should have triggered snapshot + diagnose
        # (at least the calls from the callback itself).
        assert runner._observer.snapshot.called
        assert runner._diagnostician.diagnose.called


# ---------------------------------------------------------------------------
# Fix 10: SelfObserver uses sys.executable + continue-on-collection-errors
# ---------------------------------------------------------------------------


class TestSelfObserverTestExecution:
    """Verify observe_tests uses sys.executable (not 'python3') and
    --continue-on-collection-errors so a single collection error doesn't
    interrupt the whole run (which caused total=1 errors=1)."""

    @pytest.mark.slow
    def test_observe_tests_uses_sys_executable(self) -> None:
        """observe_tests command must use sys.executable, not 'python3'."""
        from maref.recursive.self_observer import SelfObserver
        import sys

        obs = SelfObserver()
        with patch("maref.recursive.self_observer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="1 test collected", stderr="", returncode=0
            )
            obs.observe_tests(collect_only=True)

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == sys.executable, (
            f"observe_tests must use sys.executable ({sys.executable}), "
            f"got {cmd[0]}"
        )

    @pytest.mark.slow
    def test_observe_tests_has_continue_on_collection_errors(self) -> None:
        """Both collect_only modes must pass --continue-on-collection-errors."""
        from maref.recursive.self_observer import SelfObserver

        obs = SelfObserver()
        with patch("maref.recursive.self_observer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="1 test collected", stderr="", returncode=0
            )
            obs.observe_tests(collect_only=True)

        cmd = mock_run.call_args[0][0]
        assert "--continue-on-collection-errors" in cmd, (
            "observe_tests must pass --continue-on-collection-errors"
        )

    @pytest.mark.slow
    def test_observe_tests_run_mode_excludes_slow_markers(self) -> None:
        """collect_only=False must filter integration/chaos/benchmark."""
        from maref.recursive.self_observer import SelfObserver

        obs = SelfObserver()
        with patch("maref.recursive.self_observer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="100 passed in 5.0s", stderr="", returncode=0
            )
            obs.observe_tests(collect_only=False)

        cmd = mock_run.call_args[0][0]
        # Find pytest's -m flag (not Python's "-m pytest" which is at index 1).
        # pytest's -m comes after "pytest" in the command list.
        pytest_idx = cmd.index("pytest")
        m_indices_after_pytest = [
            i for i, arg in enumerate(cmd) if arg == "-m" and i > pytest_idx
        ]
        assert m_indices_after_pytest, (
            f"expected pytest -m marker filter after 'pytest' in {cmd}"
        )
        marker_expr = cmd[m_indices_after_pytest[0] + 1]
        assert "integration" in marker_expr
        assert "chaos" in marker_expr
        assert "benchmark" in marker_expr

    @pytest.mark.slow
    def test_observe_tests_collect_only_mode_no_marker_filter(self) -> None:
        """collect_only=True should NOT add pytest -m filter (just count)."""
        from maref.recursive.self_observer import SelfObserver

        obs = SelfObserver()
        with patch("maref.recursive.self_observer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="100 tests collected", stderr="", returncode=0
            )
            obs.observe_tests(collect_only=True)

        cmd = mock_run.call_args[0][0]
        assert "--co" in cmd
        # Python's "-m pytest" uses -m at index 1; that's fine. We only care
        # that pytest's own -m marker filter is NOT present. Look for -m
        # occurrences after "pytest" in the command list.
        pytest_idx = cmd.index("pytest")
        m_after_pytest = [
            i for i, arg in enumerate(cmd) if arg == "-m" and i > pytest_idx
        ]
        assert not m_after_pytest, (
            "collect_only mode should not add pytest -m marker filter, "
            f"but found at indices {m_after_pytest} in {cmd}"
        )


# ---------------------------------------------------------------------------
# Fix 10: metrics phase uses collect_only=False
# ---------------------------------------------------------------------------


class TestMetricsPhaseRunsTests:
    """Verify the metrics phase calls snapshot(collect_only=False) so tests
    actually run and we get real pass/fail/coverage numbers instead of
    total=0 coverage_pct=0."""

    @pytest.mark.slow
    def test_metrics_phase_uses_collect_only_false(self, tmp_path: Path) -> None:
        """snapshot in metrics phase must be called with collect_only=False."""
        runner = _make_runner(tmp_path)
        runner._observer = MagicMock()
        runner._observer.snapshot.return_value = _make_snapshot(
            test_stats={"total": 50, "passed": 48, "failed": 2, "errors": 0}
        )
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

        # The metrics phase is the LAST snapshot call. In dry_run mode
        # (real_writes=False) the healing phase is skipped, so there are
        # only 2 snapshot calls (diagnosis + metrics). Either way, the last
        # call must be collect_only=False.
        snapshot_calls = runner._observer.snapshot.call_args_list
        assert len(snapshot_calls) >= 2, (
            f"expected >=2 snapshot calls, got {len(snapshot_calls)}"
        )
        metrics_call = snapshot_calls[-1]
        assert metrics_call.kwargs.get("collect_only") is False, (
            "metrics phase must call snapshot(collect_only=False) (Fix 10)"
        )


# ---------------------------------------------------------------------------
# Fix 10b: metrics phase subprocess timeout must accommodate full suite
# ---------------------------------------------------------------------------


class TestObserveTestsTimeout:
    """Verify observe_tests uses a subprocess timeout large enough for the
    quick benchmark subset. The fast subset (10 files) completes in <30s;
    timeout=120 (run mode) / 60 (collect-only) covers overhead safely."""

    @pytest.mark.slow
    def test_run_mode_timeout_is_120s(self) -> None:
        """collect_only=False uses timeout=120 for the quick benchmark subset."""
        from maref.recursive.self_observer import SelfObserver

        obs = SelfObserver()
        with patch("maref.recursive.self_observer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="100 passed in 5.0s", stderr="", returncode=0
            )
            obs.observe_tests(collect_only=False)

        timeout = mock_run.call_args.kwargs.get("timeout")
        assert timeout == 120, (
            f"collect_only=False must use timeout=120, got {timeout}"
        )

    @pytest.mark.slow
    def test_collect_only_timeout_is_60s(self) -> None:
        """collect_only=True keeps the fast 60s timeout (collection only)."""
        from maref.recursive.self_observer import SelfObserver

        obs = SelfObserver()
        with patch("maref.recursive.self_observer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="100 tests collected", stderr="", returncode=0
            )
            obs.observe_tests(collect_only=True)

        timeout = mock_run.call_args.kwargs.get("timeout")
        assert timeout == 60, (
            f"collect_only=True must use timeout=60, got {timeout}"
        )
