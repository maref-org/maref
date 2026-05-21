"""Unit tests for the `maref percv` CLI subcommand using CliRunner.

All external dependencies (PERCVResearchOrchestrator, feature development
pipeline, etc.) are mocked so these tests run quickly and without network
or filesystem side effects.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from maref.integration.percv.orchestrator import (
    CyclePhase,
    OrchestratorCycle,
    OrchestratorCycleResult,
)
from maref.integration.test_platform.schema import EvalStatus
from maref_lite.cli import app

runner = CliRunner()


# ── Helpers ─────────────────────────────────────────────────────────


def _make_cycle_result(
    cycle_type: OrchestratorCycle,
    phase: CyclePhase = CyclePhase.COMPLETED,
    result: dict | None = None,
) -> OrchestratorCycleResult:
    return OrchestratorCycleResult(
        cycle_type=cycle_type,
        cycle_id=f"{cycle_type.value}-test-0",
        phase=phase,
        started_at=0.0,
        completed_at=1.0,
        result=result or {},
    )


# ── research-cycle ──────────────────────────────────────────────────


class TestResearchCycle:
    def test_research_cycle_default_budget(self):
        with patch("maref_lite.percv_cli.PERCVResearchOrchestrator") as MockOrch:
            instance = MockOrch.return_value
            instance.run_research_cycle.return_value = _make_cycle_result(
                OrchestratorCycle.RESEARCH,
                result={"topic": "test topic"},
            )
            result = runner.invoke(app, ["percv", "research-cycle", "test topic"])
            assert result.exit_code == 0
            instance.run_research_cycle.assert_called_once_with(topic="test topic")

    def test_research_cycle_custom_budget(self):
        with patch("maref_lite.percv_cli.PERCVResearchOrchestrator") as MockOrch:
            instance = MockOrch.return_value
            instance.run_research_cycle.return_value = _make_cycle_result(
                OrchestratorCycle.RESEARCH,
                result={"topic": "custom topic"},
            )
            result = runner.invoke(
                app, ["percv", "research-cycle", "custom topic", "--budget", "10000"]
            )
            assert result.exit_code == 0
            instance.run_research_cycle.assert_called_once_with(topic="custom topic")

    def test_research_cycle_short_budget_flag(self):
        with patch("maref_lite.percv_cli.PERCVResearchOrchestrator") as MockOrch:
            instance = MockOrch.return_value
            instance.run_research_cycle.return_value = _make_cycle_result(
                OrchestratorCycle.RESEARCH,
            )
            result = runner.invoke(
                app, ["percv", "research-cycle", "t", "-b", "2000"]
            )
            assert result.exit_code == 0
            instance.run_research_cycle.assert_called_once_with(topic="t")

    def test_research_cycle_missing_topic_error(self):
        result = runner.invoke(app, ["percv", "research-cycle"])
        assert result.exit_code != 0


# ── status ──────────────────────────────────────────────────────────


class TestStatus:
    def test_status_shows_json(self):
        with patch("maref_lite.percv_cli.PERCVResearchOrchestrator") as MockOrch:
            instance = MockOrch.return_value
            instance.status = "initialized"
            instance.cycle_count = 3
            instance.get_history.return_value = [{"cycle_type": "research"}]
            result = runner.invoke(app, ["percv", "status"])
            assert result.exit_code == 0
            assert "initialized" in result.stdout
            instance.get_history.assert_called_once()

    def test_status_with_enum_status(self):
        from maref.integration.percv.orchestrator import OrchestratorStatus

        with patch("maref_lite.percv_cli.PERCVResearchOrchestrator") as MockOrch:
            instance = MockOrch.return_value
            instance.status = OrchestratorStatus.INITIALIZED
            instance.cycle_count = 0
            instance.get_history.return_value = []
            result = runner.invoke(app, ["percv", "status"])
            assert result.exit_code == 0


# ── sync-cards / cost-report (not implemented) ──────────────────────


class TestNotImplementedCommands:
    def test_sync_cards_prints_warning(self):
        result = runner.invoke(app, ["percv", "sync-cards"])
        assert result.exit_code == 0
        assert "not yet implemented" in result.stdout.lower()

    def test_cost_report_prints_warning(self):
        result = runner.invoke(app, ["percv", "cost-report"])
        assert result.exit_code == 0
        assert "not yet implemented" in result.stdout.lower()


# ── auto-cycle ──────────────────────────────────────────────────────


class TestAutoCycle:
    def test_auto_cycle_default_topic_and_iterations(self):
        with patch("maref_lite.percv_cli.PERCVResearchOrchestrator") as MockOrch:
            instance = MockOrch.return_value
            instance.cycle_count = 4
            instance.get_history.return_value = []
            instance.get_research_directions.return_value = []
            instance.run_research_cycle.return_value = _make_cycle_result(
                OrchestratorCycle.RESEARCH,
                result={"topic": "ecosystem-analysis (iter 1)"},
            )
            instance.run_evaluate_cycle.return_value = _make_cycle_result(
                OrchestratorCycle.EVALUATE,
            )
            instance.run_evolve_cycle.return_value = _make_cycle_result(
                OrchestratorCycle.EVOLVE,
                result={"verdict": "approved"},
            )
            instance.run_verify_cycle.return_value = _make_cycle_result(
                OrchestratorCycle.VERIFY,
            )
            result = runner.invoke(app, ["percv", "auto-cycle"])
            assert result.exit_code == 0
            assert "Cycle 1/1" in result.stdout
            instance.initialize.assert_called_once()

    def test_auto_cycle_custom_topic_and_iterations(self):
        with patch("maref_lite.percv_cli.PERCVResearchOrchestrator") as MockOrch:
            instance = MockOrch.return_value
            instance.cycle_count = 8
            instance.get_history.return_value = []
            instance.get_research_directions.return_value = []
            instance.run_research_cycle.return_value = _make_cycle_result(
                OrchestratorCycle.RESEARCH,
                result={"topic": "custom (iter 1)"},
            )
            instance.run_evaluate_cycle.return_value = _make_cycle_result(
                OrchestratorCycle.EVALUATE,
            )
            instance.run_evolve_cycle.return_value = _make_cycle_result(
                OrchestratorCycle.EVOLVE,
                result={"verdict": "approved"},
            )
            instance.run_verify_cycle.return_value = _make_cycle_result(
                OrchestratorCycle.VERIFY,
            )
            result = runner.invoke(
                app,
                ["percv", "auto-cycle", "custom", "--iterations", "2"],
            )
            assert result.exit_code == 0
            assert "Cycle 1/2" in result.stdout
            assert "Cycle 2/2" in result.stdout
            assert instance.run_research_cycle.call_count == 2

    def test_auto_cycle_shows_feedback_directions(self):
        with patch("maref_lite.percv_cli.PERCVResearchOrchestrator") as MockOrch:
            instance = MockOrch.return_value
            instance.cycle_count = 4
            instance.get_history.return_value = []
            instance.get_research_directions.return_value = [
                {"priority": "high", "topic": "improve coverage"},
                {"priority": "critical", "topic": "fix latency"},
            ]
            instance.run_research_cycle.return_value = _make_cycle_result(
                OrchestratorCycle.RESEARCH,
                result={"topic": "t (iter 1)"},
            )
            instance.run_evaluate_cycle.return_value = _make_cycle_result(
                OrchestratorCycle.EVALUATE,
            )
            instance.run_evolve_cycle.return_value = _make_cycle_result(
                OrchestratorCycle.EVOLVE,
                result={"verdict": "approved"},
            )
            instance.run_verify_cycle.return_value = _make_cycle_result(
                OrchestratorCycle.VERIFY,
            )
            result = runner.invoke(app, ["percv", "auto-cycle", "t"])
            assert result.exit_code == 0
            assert "feedback" in result.stdout.lower()

    def test_auto_cycle_short_iterations_flag(self):
        with patch("maref_lite.percv_cli.PERCVResearchOrchestrator") as MockOrch:
            instance = MockOrch.return_value
            instance.cycle_count = 4
            instance.get_history.return_value = []
            instance.get_research_directions.return_value = []
            instance.run_research_cycle.return_value = _make_cycle_result(
                OrchestratorCycle.RESEARCH,
                result={"topic": "t (iter 1)"},
            )
            instance.run_evaluate_cycle.return_value = _make_cycle_result(
                OrchestratorCycle.EVALUATE,
            )
            instance.run_evolve_cycle.return_value = _make_cycle_result(
                OrchestratorCycle.EVOLVE,
                result={"verdict": "approved"},
            )
            instance.run_verify_cycle.return_value = _make_cycle_result(
                OrchestratorCycle.VERIFY,
            )
            result = runner.invoke(app, ["percv", "auto-cycle", "t", "-n", "3"])
            assert result.exit_code == 0
            assert instance.run_research_cycle.call_count == 3


# ── develop-feature (simplified - only test doc not found) ──────────


class TestDevelopFeature:
    def test_develop_feature_missing_doc(self):
        result = runner.invoke(app, ["percv", "develop-feature", "/nonexistent.md"])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()


# ── feature-status (simplified) ─────────────────────────────────────


class TestFeatureStatus:
    def test_feature_status_no_reports_dir(self):
        with patch("maref_lite.percv_cli.Path.exists", return_value=False):
            result = runner.invoke(app, ["percv", "feature-status"])
            assert result.exit_code == 0
            assert "no feature development reports found" in result.stdout.lower()


# ── develop-verify (simplified - only test doc not found) ───────────


class TestDevelopVerify:
    def test_develop_verify_missing_doc(self):
        result = runner.invoke(
            app, ["percv", "develop-verify", "/nonexistent.md"]
        )
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()


# ── Help / no-args ──────────────────────────────────────────────────


class TestPercvHelp:
    def test_percv_no_args_shows_help(self):
        result = runner.invoke(app, ["percv"])
        # Typer no_args_is_help=True shows help but may exit with code 2
        assert result.exit_code in (0, 2)
        assert "PERCV integration commands" in result.stdout

    def test_percv_help_flag(self):
        result = runner.invoke(app, ["percv", "--help"])
        assert result.exit_code == 0
        assert "research-cycle" in result.stdout
        assert "status" in result.stdout
        assert "sync-cards" in result.stdout
        assert "cost-report" in result.stdout
        assert "auto-cycle" in result.stdout
        assert "develop-feature" in result.stdout
        assert "feature-status" in result.stdout
        assert "develop-verify" in result.stdout

    def test_research_cycle_help(self):
        result = runner.invoke(app, ["percv", "research-cycle", "--help"])
        assert result.exit_code == 0
        assert "topic" in result.stdout.lower()

    def test_auto_cycle_help(self):
        result = runner.invoke(app, ["percv", "auto-cycle", "--help"])
        assert result.exit_code == 0
        assert "iterations" in result.stdout.lower()

    def test_develop_feature_help(self):
        result = runner.invoke(app, ["percv", "develop-feature", "--help"])
        assert result.exit_code == 0
        assert "feature-name" in result.stdout.lower()
        assert "iterations" in result.stdout.lower()
        assert "output" in result.stdout.lower()
        assert "verify" in result.stdout.lower()

    def test_feature_status_help(self):
        result = runner.invoke(app, ["percv", "feature-status", "--help"])
        assert result.exit_code == 0
        assert "name" in result.stdout.lower()
        assert "latest" in result.stdout.lower()

    def test_develop_verify_help(self):
        result = runner.invoke(app, ["percv", "develop-verify", "--help"])
        assert result.exit_code == 0
        assert "iterations" in result.stdout.lower()
        assert "output" in result.stdout.lower()
