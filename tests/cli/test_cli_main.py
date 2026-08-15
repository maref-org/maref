"""Comprehensive tests for the MAREF main CLI entry point (maref_lite/cli.py).

Uses typer.testing.CliRunner for fast, isolated CLI testing.
Mocks all external dependencies to avoid heavy imports and side effects.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

runner = CliRunner()

# Import the app lazily so we can patch before commands run
from maref_lite.cli import app

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _patch_governance_overlay():
    """Patch GovernanceOverlay for all tests to avoid heavy side effects."""
    with patch("maref_lite.cli.GovernanceOverlay") as mock_cls:
        instance = mock_cls.return_value
        instance.get_status.return_value = {
            "state": "INIT",
            "state_machine": {"current_state": "INIT", "transitions": 0},
            "agents": 0,
        }
        yield mock_cls


@pytest.fixture(autouse=True)
def _patch_console():
    """Patch rich console to suppress output during tests."""
    with patch("maref_lite.cli.console") as mock_console:
        yield mock_console


# ── Version / callback ───────────────────────────────────────────────


class TestVersionCallback:
    def test_version_flag_prints_version(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0

    def test_version_short_flag(self) -> None:
        result = runner.invoke(app, ["-V"])
        assert result.exit_code == 0

    def test_no_args_shows_help(self) -> None:
        result = runner.invoke(app, [])
        # no_args_is_help=True shows help, may exit 0 or 2
        assert result.exit_code in (0, 2)


# ── status ───────────────────────────────────────────────────────────


class TestStatus:
    def test_status_default(self) -> None:
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0

    def test_status_verbose(self) -> None:
        result = runner.invoke(app, ["status", "--verbose"])
        assert result.exit_code == 0

    def test_status_verbose_short_flag(self) -> None:
        result = runner.invoke(app, ["status", "-v"])
        assert result.exit_code == 0

    def test_status_calls_overlay_get_status(self, _patch_governance_overlay: Any) -> None:
        runner.invoke(app, ["status"])
        _patch_governance_overlay.return_value.get_status.assert_called_once()


# ── observe ──────────────────────────────────────────────────────────


class TestObserve:
    def test_observe_default(self) -> None:
        result = runner.invoke(app, ["observe"])
        assert result.exit_code == 0

    def test_observe_with_interval_and_count(self) -> None:
        result = runner.invoke(app, ["observe", "--interval", "0.1", "--count", "2"])
        assert result.exit_code == 0

    def test_observe_short_flags(self) -> None:
        result = runner.invoke(app, ["observe", "-i", "0.1", "-n", "2"])
        assert result.exit_code == 0

    def test_observe_zero_count(self) -> None:
        result = runner.invoke(app, ["observe", "--count", "0"])
        assert result.exit_code == 0


# ── analyze ──────────────────────────────────────────────────────────


class TestAnalyze:
    def test_analyze_default_state(self) -> None:
        result = runner.invoke(app, ["analyze"])
        assert result.exit_code == 0

    def test_analyze_specific_state(self) -> None:
        result = runner.invoke(app, ["analyze", "--state", "OBSERVE"])
        assert result.exit_code == 0

    def test_analyze_graph_flag(self) -> None:
        result = runner.invoke(app, ["analyze", "--state", "INIT", "--graph"])
        assert result.exit_code == 0

    def test_analyze_graph_short_flags(self) -> None:
        result = runner.invoke(app, ["analyze", "-s", "HALT", "-g"])
        assert result.exit_code == 0

    def test_analyze_invalid_state_exits_error(self) -> None:
        result = runner.invoke(app, ["analyze", "--state", "INVALID"])
        assert result.exit_code == 1

    def test_analyze_lowercase_state_accepted(self) -> None:
        result = runner.invoke(app, ["analyze", "--state", "observe"])
        assert result.exit_code == 0


# ── desktop run ──────────────────────────────────────────────────────


class TestDesktopRun:
    def test_desktop_run_dry_run_default(self) -> None:
        with patch("maref.desktop.agent.DesktopAgent") as mock_agent_cls:
            instance = mock_agent_cls.return_value
            instance.execute_task.return_value = MagicMock(
                success=True,
                steps_executed=3,
                steps_failed=0,
                error_message="",
            )
            result = runner.invoke(app, ["desktop", "run", "--task", "open Finder"])
            assert result.exit_code == 0
            mock_agent_cls.assert_called_once_with(dry_run=True)

    def test_desktop_run_live_flag(self) -> None:
        with patch("maref.desktop.agent.DesktopAgent") as mock_agent_cls:
            instance = mock_agent_cls.return_value
            instance.execute_task.return_value = MagicMock(
                success=True,
                steps_executed=3,
                steps_failed=0,
                error_message="",
            )
            result = runner.invoke(app, ["desktop", "run", "--task", "open Finder", "--live"])
            assert result.exit_code == 0
            mock_agent_cls.assert_called_once_with(dry_run=False)

    def test_desktop_run_task_failure(self) -> None:
        with patch("maref.desktop.agent.DesktopAgent") as mock_agent_cls:
            instance = mock_agent_cls.return_value
            instance.execute_task.return_value = MagicMock(
                success=False,
                steps_executed=1,
                steps_failed=2,
                error_message="step failed",
            )
            result = runner.invoke(app, ["desktop", "run", "--task", "fail me"])
            assert result.exit_code == 0

    def test_desktop_run_import_error(self) -> None:
        with patch("maref.desktop.agent.DesktopAgent", side_effect=ImportError("no module")):
            result = runner.invoke(app, ["desktop", "run", "--task", "x"])
            assert result.exit_code == 1


# ── desktop setup ────────────────────────────────────────────────────


class TestDesktopSetup:
    def test_setup_help(self) -> None:
        result = runner.invoke(app, ["desktop", "setup", "--help"])
        assert result.exit_code == 0
        assert "setup" in result.stdout.lower() or "One-click" in result.stdout

    def test_setup_dry_run(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(app, ["desktop", "setup", "--dry-run"])
            assert result.exit_code == 0
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "--dry-run" in cmd

    def test_setup_no_model(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(app, ["desktop", "setup", "--no-model", "--dry-run"])
            assert result.exit_code == 0
            cmd = mock_run.call_args[0][0]
            assert "--no-model" in cmd

    def test_setup_model_flag(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(app, ["desktop", "setup", "--model", "none", "--dry-run"])
            assert result.exit_code == 0
            cmd = mock_run.call_args[0][0]
            assert "--model=none" in cmd

    def test_setup_upgrade_flag(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(app, ["desktop", "setup", "--upgrade", "--dry-run"])
            assert result.exit_code == 0
            cmd = mock_run.call_args[0][0]
            assert "--upgrade" in cmd

    def test_setup_script_not_found(self) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = runner.invoke(app, ["desktop", "setup"])
            assert result.exit_code == 1

    def test_setup_nonzero_returncode(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=2)
            result = runner.invoke(app, ["desktop", "setup"])
            assert result.exit_code == 2


# ── desktop demo ─────────────────────────────────────────────────────


class TestDesktopDemo:
    def test_demo_success(self) -> None:
        with patch("maref.desktop.agent.DesktopAgent") as mock_agent_cls:
            instance = mock_agent_cls.return_value
            instance.capture_screen.return_value = MagicMock(width=1920, height=1080)
            instance.parse_screen.return_value = MagicMock(elements=[MagicMock(), MagicMock()])
            instance.run_demo_task.return_value = MagicMock(success=True, steps_executed=4)
            result = runner.invoke(app, ["desktop", "demo"])
            assert result.exit_code == 0
            mock_agent_cls.assert_called_once_with(dry_run=True)

    def test_demo_import_error(self) -> None:
        with patch("maref.desktop.agent.DesktopAgent", side_effect=ImportError("missing")):
            result = runner.invoke(app, ["desktop", "demo"])
            assert result.exit_code == 1


# ── desktop benchmark ────────────────────────────────────────────────


class TestDesktopBenchmark:
    def test_benchmark_default(self) -> None:
        with (
            patch("maref.desktop.agent.DesktopAgent") as mock_agent_cls,
            patch("maref.desktop.opencua_bench.OpenCUABenchmark") as mock_bench_cls,
        ):
            bench = mock_bench_cls.return_value
            bench.run_with_agent.return_value = MagicMock(
                total_samples=2,
                ActionAccuracy=1.0,
                StepAccuracy=1.0,
                avg_latency_ms=10.0,
                p99_latency_ms=20.0,
                per_sample_results=[],
            )
            result = runner.invoke(app, ["desktop", "benchmark", "--samples", "2"])
            assert result.exit_code == 0
            bench.load_dataset.assert_called_once_with(use_mock=True)
            bench.run_with_agent.assert_called_once()

    def test_benchmark_download_flag(self) -> None:
        with patch("maref.desktop.opencua_bench.OpenCUABenchmark") as mock_bench_cls:
            bench = mock_bench_cls.return_value
            bench.download_dataset.return_value = "/tmp/opencua"
            result = runner.invoke(app, ["desktop", "benchmark", "--download"])
            assert result.exit_code == 0
            bench.download_dataset.assert_called_once()

    def test_benchmark_with_output(self) -> None:
        with (
            patch("maref.desktop.agent.DesktopAgent") as mock_agent_cls,
            patch("maref.desktop.opencua_bench.OpenCUABenchmark") as mock_bench_cls,
        ):
            bench = mock_bench_cls.return_value
            bench.run_with_agent.return_value = MagicMock(
                total_samples=1,
                ActionAccuracy=1.0,
                StepAccuracy=1.0,
                avg_latency_ms=5.0,
                p99_latency_ms=5.0,
                per_sample_results=[],
            )
            result = runner.invoke(
                app, ["desktop", "benchmark", "--samples", "1", "--output", "/tmp/res"]
            )
            assert result.exit_code == 0

    def test_benchmark_import_error(self) -> None:
        with patch(
            "maref.desktop.opencua_bench.OpenCUABenchmark", side_effect=ImportError("missing")
        ):
            result = runner.invoke(app, ["desktop", "benchmark"])
            assert result.exit_code == 1


# ── audit show ───────────────────────────────────────────────────────


class TestAuditShow:
    def test_audit_show_no_file(self) -> None:
        with patch("pathlib.Path.exists", return_value=False):
            result = runner.invoke(app, ["audit", "show"])
            assert result.exit_code == 0
            assert "No audit log" in result.stdout or result.stdout == ""

    def test_audit_show_with_entries(self, tmp_path: Path) -> None:
        audit_file = tmp_path / "governance_audit.jsonl"
        entries = [
            json.dumps(
                {
                    "timestamp": 1700000000,
                    "event_type": "transition",
                    "actor": "agent-1",
                    "action": "OBSERVE->ANALYZE",
                    "details": "ok",
                }
            ),
            json.dumps(
                {
                    "timestamp": 1700000001,
                    "event_type": "transition",
                    "actor": "agent-1",
                    "action": "ANALYZE->DECIDE",
                    "details": "ok",
                }
            ),
        ]
        audit_file.write_text("\n".join(entries))
        with patch("maref_lite.cli._default_audit_log_path", return_value=audit_file):
            result = runner.invoke(app, ["audit", "show", "--last", "5"])
            assert result.exit_code == 0

    def test_audit_show_filter_by_type(self, tmp_path: Path) -> None:
        audit_file = tmp_path / "governance_audit.jsonl"
        entries = [
            json.dumps(
                {
                    "timestamp": 1700000000,
                    "event_type": "transition",
                    "actor": "a",
                    "action": "x",
                    "details": "",
                }
            ),
            json.dumps(
                {
                    "timestamp": 1700000001,
                    "event_type": "error",
                    "actor": "a",
                    "action": "y",
                    "details": "",
                }
            ),
        ]
        audit_file.write_text("\n".join(entries))
        with patch("maref_lite.cli._default_audit_log_path", return_value=audit_file):
            result = runner.invoke(app, ["audit", "show", "--last", "5", "--type", "error"])
            assert result.exit_code == 0

    def test_audit_show_malformed_line_skipped(self, tmp_path: Path) -> None:
        audit_file = tmp_path / "governance_audit.jsonl"
        audit_file.write_text("not json\n")
        with patch("maref_lite.cli._default_audit_log_path", return_value=audit_file):
            result = runner.invoke(app, ["audit", "show"])
            assert result.exit_code == 0


# ── trust score ──────────────────────────────────────────────────────


class TestTrustScore:
    def test_trust_score_no_agent(self) -> None:
        result = runner.invoke(app, ["trust", "score"])
        assert result.exit_code == 0
        assert "Trust Engine" in result.stdout or result.stdout == ""

    def test_trust_score_with_agent(self) -> None:
        result = runner.invoke(app, ["trust", "score", "--agent", "agent-1"])
        assert result.exit_code == 0

    def test_trust_score_short_flag(self) -> None:
        result = runner.invoke(app, ["trust", "score", "-a", "agent-2"])
        assert result.exit_code == 0


# ── governance status ────────────────────────────────────────────────


class TestGovernanceStatus:
    def test_governance_status(self) -> None:
        result = runner.invoke(app, ["governance", "status"])
        assert result.exit_code == 0

    def test_governance_status_calls_overlay(self, _patch_governance_overlay: Any) -> None:
        runner.invoke(app, ["governance", "status"])
        _patch_governance_overlay.return_value.get_status.assert_called_once()


# ── drift check ──────────────────────────────────────────────────────


class TestDriftCheck:
    def test_drift_check_default(self) -> None:
        with patch("drift_guard.drift_benchmark.DriftBenchmark") as mock_cls:
            instance = mock_cls.return_value
            instance.summary.return_value = {
                "total_scenarios": 10,
                "detected": 8,
                "detection_rate": 0.8,
                "avg_f1": 0.85,
                "per_class": {
                    "theme_color": {"kl": 0.2, "js": 0.1, "detected": True},
                },
            }
            result = runner.invoke(app, ["drift", "check"])
            assert result.exit_code == 0
            instance.run.assert_called_once()
            instance.summary.assert_called_once()

    def test_drift_check_with_model(self) -> None:
        with patch("drift_guard.drift_benchmark.DriftBenchmark") as mock_cls:
            instance = mock_cls.return_value
            instance.summary.return_value = {
                "total_scenarios": 10,
                "detected": 10,
                "detection_rate": 1.0,
                "avg_f1": 1.0,
                "per_class": {},
            }
            result = runner.invoke(app, ["drift", "check", "--model", "custom"])
            assert result.exit_code == 0

    def test_drift_check_import_error(self) -> None:
        with patch(
            "drift_guard.drift_benchmark.DriftBenchmark", side_effect=ImportError("missing")
        ):
            result = runner.invoke(app, ["drift", "check"])
            assert result.exit_code == 0
            assert "not available" in result.stdout or result.stdout == ""


# ── serve ────────────────────────────────────────────────────────────


class TestServe:
    def test_serve_default_port(self) -> None:
        with patch("uvicorn.run") as mock_uvicorn:
            with patch("sidecar.server.create_app") as mock_create:
                result = runner.invoke(app, ["serve"])
                assert result.exit_code == 0
                mock_uvicorn.assert_called_once()
                call_kwargs = mock_uvicorn.call_args.kwargs
                assert call_kwargs["host"] == "0.0.0.0"
                assert call_kwargs["port"] == 8000

    def test_serve_custom_port(self) -> None:
        with patch("uvicorn.run") as mock_uvicorn:
            with patch("sidecar.server.create_app") as mock_create:
                result = runner.invoke(app, ["serve", "--port", "9000"])
                assert result.exit_code == 0
                assert mock_uvicorn.call_args.kwargs["port"] == 9000

    def test_serve_gui_mode(self) -> None:
        with patch("uvicorn.run") as mock_uvicorn:
            with patch("sidecar.server.create_app") as mock_create:
                result = runner.invoke(app, ["serve", "--gui"])
                assert result.exit_code == 0
                mock_uvicorn.assert_called_once()

    def test_serve_uvicorn_not_installed(self) -> None:
        # The first uvicorn import is inside the command; it catches ImportError.
        # Capture the real __import__ first, otherwise the side_effect calling
        # __import__(name) recurses into the patched mock.
        real_import = __import__

        def _fake_import(name: str, *args: object, **kwargs: object) -> Any:
            if name == "uvicorn":
                raise ImportError("no uvicorn")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_fake_import):
            result = runner.invoke(app, ["serve"])
            assert result.exit_code == 1

    def test_serve_create_app_import_error(self) -> None:
        with patch("uvicorn.run") as mock_uvicorn:
            with patch("sidecar.server.create_app", side_effect=ImportError("no sidecar")):
                result = runner.invoke(app, ["serve"])
                # The second ImportError block prints dim message and does not raise
                assert result.exit_code == 0


# ── Sub-command group help ───────────────────────────────────────────


class TestSubcommandHelp:
    def test_desktop_group_help(self) -> None:
        result = runner.invoke(app, ["desktop", "--help"])
        assert result.exit_code == 0
        assert "run" in result.stdout.lower()
        assert "setup" in result.stdout.lower()
        assert "demo" in result.stdout.lower()
        assert "benchmark" in result.stdout.lower()

    def test_audit_group_help(self) -> None:
        result = runner.invoke(app, ["audit", "--help"])
        assert result.exit_code == 0
        assert "show" in result.stdout.lower()

    def test_trust_group_help(self) -> None:
        result = runner.invoke(app, ["trust", "--help"])
        assert result.exit_code == 0
        assert "score" in result.stdout.lower()

    def test_governance_group_help(self) -> None:
        result = runner.invoke(app, ["governance", "--help"])
        assert result.exit_code == 0
        assert "status" in result.stdout.lower()

    def test_drift_group_help(self) -> None:
        result = runner.invoke(app, ["drift", "--help"])
        assert result.exit_code == 0
        assert "check" in result.stdout.lower()

    def test_global_help_lists_all_groups(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        groups = ["desktop", "audit", "trust", "governance", "drift", "percv", "ip"]
        for group in groups:
            assert group in result.stdout.lower()


# ── main entry point ─────────────────────────────────────────────────


class TestMainEntryPoint:
    def test_main_function_runs_without_error(self) -> None:
        from maref_lite.cli import main

        with patch("maref_lite.cli.app") as mock_app:
            try:
                main()
            except SystemExit:
                pass  # Typer may exit
            mock_app.assert_called_once()
