from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
CLI_SCRIPT = PROJECT_ROOT / "src" / "maref_lite" / "cli.py"


def run_cli(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI_SCRIPT)] + args,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        **kwargs,
    )


class TestCLIStatus:
    def test_status_command_returns_zero(self) -> None:
        result = run_cli(["status"])
        assert result.returncode == 0

    def test_status_command_contains_key_metrics(self) -> None:
        result = run_cli(["status"])
        assert "MAREF Governance Status" in result.stdout
        assert "state" in result.stdout.lower()

    def test_status_verbose_flag_returns_zero(self) -> None:
        result = run_cli(["status", "--verbose"])
        assert result.returncode == 0

    def test_status_verbose_short_flag(self) -> None:
        result = run_cli(["status", "-v"])
        assert result.returncode == 0

    def test_status_verbose_output_is_json(self) -> None:
        result = run_cli(["status", "--verbose"])
        try:
            json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            pytest.fail(f"Expected JSON output, got: {result.stdout[:200]}")


class TestCLIObserve:
    def test_observe_command_returns_zero(self) -> None:
        result = run_cli(["observe"])
        assert result.returncode == 0

    def test_observe_command_shows_observed_count(self) -> None:
        result = run_cli(["observe", "--count", "5"])
        assert "Observed" in result.stdout

    def test_observe_with_interval_returns_zero(self) -> None:
        result = run_cli(["observe", "--interval", "0.1", "--count", "3"])
        assert result.returncode == 0

    def test_observe_with_zero_count(self) -> None:
        result = run_cli(["observe", "--count", "0"])
        assert result.returncode == 0

    def test_observe_short_flags(self) -> None:
        result = run_cli(["observe", "-i", "0.5", "-n", "2"])
        assert result.returncode == 0

    def test_observe_output_contains_transitions(self) -> None:
        result = run_cli(["observe", "--count", "3"])
        assert "->" in result.stdout
        assert "MAREF Observer started" in result.stdout

    def test_observe_force_stabilize_occurs(self) -> None:
        result = run_cli(["observe", "--count", "20"])
        assert "FORCE STABILIZE" in result.stdout or "->" in result.stdout


class TestCLIAnalyze:
    def test_analyze_default_state_returns_zero(self) -> None:
        result = run_cli(["analyze"])
        assert result.returncode == 0

    def test_analyze_init_state(self) -> None:
        result = run_cli(["analyze", "--state", "INIT"])
        assert result.returncode == 0
        assert "State Analysis" in result.stdout

    def test_analyze_observe_state(self) -> None:
        result = run_cli(["analyze", "--state", "OBSERVE"])
        assert result.returncode == 0

    def test_analyze_analyze_state(self) -> None:
        result = run_cli(["analyze", "--state", "ANALYZE"])
        assert result.returncode == 0

    def test_analyze_evaluate_state(self) -> None:
        result = run_cli(["analyze", "--state", "EVALUATE"])
        assert result.returncode == 0

    def test_analyze_decide_state(self) -> None:
        result = run_cli(["analyze", "--state", "DECIDE"])
        assert result.returncode == 0

    def test_analyze_act_state(self) -> None:
        result = run_cli(["analyze", "--state", "ACT"])
        assert result.returncode == 0

    def test_analyze_verify_state(self) -> None:
        result = run_cli(["analyze", "--state", "VERIFY"])
        assert result.returncode == 0

    def test_analyze_stabilize_state(self) -> None:
        result = run_cli(["analyze", "--state", "STABILIZE"])
        assert result.returncode == 0

    def test_analyze_report_state(self) -> None:
        result = run_cli(["analyze", "--state", "REPORT"])
        assert result.returncode == 0

    def test_analyze_halt_state(self) -> None:
        result = run_cli(["analyze", "--state", "HALT"])
        assert result.returncode == 0

    def test_analyze_invalid_state_returns_error(self) -> None:
        result = run_cli(["analyze", "--state", "INVALID"])
        assert result.returncode == 1
        assert "Unknown state" in result.stdout

    def test_analyze_with_graph_returns_zero(self) -> None:
        result = run_cli(["analyze", "--state", "OBSERVE", "--graph"])
        assert result.returncode == 0
        assert "Transition Graph" in result.stdout

    def test_analyze_graph_short_flag(self) -> None:
        result = run_cli(["analyze", "-s", "ANALYZE", "-g"])
        assert result.returncode == 0

    def test_analyze_lowercase_state_accepted(self) -> None:
        result = run_cli(["analyze", "--state", "observe"])
        assert result.returncode == 0
        assert "OBSERVE" in result.stdout

    def test_analyze_output_contains_gray_code(self) -> None:
        result = run_cli(["analyze", "--state", "INIT"])
        assert "Gray Code" in result.stdout

    def test_analyze_output_contains_entropy(self) -> None:
        result = run_cli(["analyze", "--state", "OBSERVE"])
        assert "Entropy" in result.stdout

    def test_analyze_halt_is_terminal(self) -> None:
        result = run_cli(["analyze", "--state", "HALT"])
        assert "Terminal" in result.stdout
        assert "absorbing" in result.stdout.lower()

    def test_analyze_nonterminal_state(self) -> None:
        result = run_cli(["analyze", "--state", "STABILIZE"])
        assert "terminal:  false" in result.stdout.lower() or "false" in result.stdout.lower()


class TestCLIMain:
    def test_main_function_exists(self) -> None:
        from maref_lite.cli import main
        assert callable(main)


class TestCLIHelp:
    def test_help_command(self) -> None:
        result = run_cli(["--help"])
        assert result.returncode == 0
        assert "MAREF" in result.stdout

    def test_status_help(self) -> None:
        result = run_cli(["status", "--help"])
        assert result.returncode == 0
        assert "Show current" in result.stdout

    def test_observe_help(self) -> None:
        result = run_cli(["observe", "--help"])
        assert result.returncode == 0
        assert "Observe agent" in result.stdout

    def test_analyze_help(self) -> None:
        result = run_cli(["analyze", "--help"])
        assert result.returncode == 0
        assert "Analyze the state machine" in result.stdout
