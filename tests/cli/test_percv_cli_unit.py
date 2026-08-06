"""Unit tests for the `maref percv` CLI subcommand using CliRunner.

All external dependencies (PERCVResearchOrchestrator, feature development
pipeline, etc.) are mocked so these tests run quickly and without network
or filesystem side effects.
"""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from maref.integration.percv.orchestrator import (
    CyclePhase,
    OrchestratorCycle,
    OrchestratorCycleResult,
)
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
            result = runner.invoke(app, ["percv", "research-cycle", "t", "-b", "2000"])
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
        result = runner.invoke(app, ["percv", "develop-verify", "/nonexistent.md"])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()


# ── Help / no-args ──────────────────────────────────────────────────


class TestPercvHelp:
    def test_percv_no_args_shows_help(self):
        result = runner.invoke(app, ["percv"])
        # Typer no_args_is_help=True shows help but may exit with code 2
        assert result.exit_code in (0, 2)
        assert "research-cycle" in result.stdout
        assert "status" in result.stdout

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
        assert "cross-analyze" in result.stdout
        assert "meta-diagnose" in result.stdout
        assert "meta-sandbox" in result.stdout
        assert "rsi-report" in result.stdout
        assert "vault-dashboard" in result.stdout
        assert "redlines" in result.stdout

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
        assert "feature_doc" in result.stdout.lower()
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

    def test_rsi_report_help(self):
        result = runner.invoke(app, ["percv", "rsi-report", "--help"])
        assert result.exit_code == 0
        assert "json" in result.stdout.lower()

    def test_cross_analyze_help(self):
        result = runner.invoke(app, ["percv", "cross-analyze", "--help"])
        assert result.exit_code == 0
        assert "window" in result.stdout.lower()
        assert "json" in result.stdout.lower()

    def test_meta_diagnose_help(self):
        result = runner.invoke(app, ["percv", "meta-diagnose", "--help"])
        assert result.exit_code == 0
        assert "target" in result.stdout.lower()
        assert "json" in result.stdout.lower()

    def test_meta_sandbox_help(self):
        result = runner.invoke(app, ["percv", "meta-sandbox", "--help"])
        assert result.exit_code == 0
        assert "config-key" in result.stdout.lower()
        assert "rounds" in result.stdout.lower()

    def test_vault_dashboard_help(self):
        result = runner.invoke(app, ["percv", "vault-dashboard", "--help"])
        assert result.exit_code == 0
        assert "open" in result.stdout.lower()

    def test_redlines_help(self):
        result = runner.invoke(app, ["percv", "redlines", "--help"])
        assert result.exit_code == 0
        assert "redlines" in result.stdout.lower()


# ── rsi-report ──────────────────────────────────────────────────────


class TestRsiReport:
    def test_rsi_report_no_vault_returns_empty(self):
        result = runner.invoke(app, ["percv", "rsi-report"])
        assert result.exit_code == 0

    def test_rsi_report_json_flag(self):
        result = runner.invoke(app, ["percv", "rsi-report", "--json"])
        assert result.exit_code == 0


# ── cross-analyze ───────────────────────────────────────────────────


class TestCrossAnalyze:
    def test_cross_analyze_default(self):
        with patch("maref_lite.percv_cli.CrossDimensionalAnalyzer") as MockCA:
            instance = MockCA.return_value
            instance.detect_cross_effects.return_value = []
            result = runner.invoke(app, ["percv", "cross-analyze"])
            assert result.exit_code == 0
            instance.detect_cross_effects.assert_called_once_with(window=20)

    def test_cross_analyze_custom_window(self):
        with patch("maref_lite.percv_cli.CrossDimensionalAnalyzer") as MockCA:
            instance = MockCA.return_value
            instance.detect_cross_effects.return_value = []
            result = runner.invoke(app, ["percv", "cross-analyze", "--window", "10"])
            assert result.exit_code == 0
            instance.detect_cross_effects.assert_called_once_with(window=10)

    def test_cross_analyze_json(self):
        with patch("maref_lite.percv_cli.CrossDimensionalAnalyzer") as MockCA:
            instance = MockCA.return_value
            instance.detect_cross_effects.return_value = []
            result = runner.invoke(app, ["percv", "cross-analyze", "--json"])
            assert result.exit_code == 0


# ── meta-diagnose ───────────────────────────────────────────────────


class TestMetaDiagnose:
    def test_meta_diagnose_default(self):
        with patch("maref_lite.percv_cli.MetaRatchet") as MockMR:
            instance = MockMR.return_value
            instance.diagnose_stagnation.return_value = (
                TestMetaDiagnose._make_diagnosis("none", "normal")
            )
            instance.propose_protocol_change.return_value = None
            result = runner.invoke(app, ["percv", "meta-diagnose"])
            assert result.exit_code == 0

    def test_meta_diagnose_json(self):
        with patch("maref_lite.percv_cli.MetaRatchet") as MockMR:
            instance = MockMR.return_value
            instance.diagnose_stagnation.return_value = (
                TestMetaDiagnose._make_diagnosis("none", "normal")
            )
            result = runner.invoke(app, ["percv", "meta-diagnose", "--json"])
            assert result.exit_code == 0

    @staticmethod
    def _make_diagnosis(d_type: str, severity: str) -> object:
        from types import SimpleNamespace
        return SimpleNamespace(
            diagnosis_type=d_type,
            severity=severity,
            details="ok",
            suggested_action="none",
        )


# ── meta-sandbox ────────────────────────────────────────────────────


class TestMetaSandbox:
    def test_meta_sandbox_default(self):
        with patch("maref_lite.percv_cli.MetaRatchet") as MockMR:
            instance = MockMR.return_value
            instance.sandbox_test.return_value = (
                TestMetaSandbox._make_result(0.7, 0.8)
            )
            result = runner.invoke(app, ["percv", "meta-sandbox"])
            assert result.exit_code == 0

    def test_meta_sandbox_json(self):
        with patch("maref_lite.percv_cli.MetaRatchet") as MockMR:
            instance = MockMR.return_value
            instance.sandbox_test.return_value = (
                TestMetaSandbox._make_result(0.7, 0.8)
            )
            result = runner.invoke(app, ["percv", "meta-sandbox", "--json"])
            assert result.exit_code == 0

    @staticmethod
    def _make_result(old: float, new: float) -> object:
        from types import SimpleNamespace
        return SimpleNamespace(
            old_avg_score=old,
            new_avg_score=new,
            improvement=new - old,
            adopted=False,
            is_production_safe=True,
            rounds_completed=10,
        )


# ── vault-dashboard ─────────────────────────────────────────────────


class TestVaultDashboard:
    def test_vault_dashboard_no_vault(self):
        with patch("maref_lite.percv_cli.Path.exists", return_value=False):
            result = runner.invoke(app, ["percv", "vault-dashboard"])
            assert result.exit_code == 0

    def test_vault_dashboard_html(self):
        with patch("maref_lite.percv_cli.Path.exists", return_value=True):
            with patch("maref_lite.percv_cli.EvolutionVault") as MockEV:
                instance = MockEV.return_value
                instance.generate_dashboard_html.return_value = "<html></html>"
                result = runner.invoke(app, ["percv", "vault-dashboard"])
                assert result.exit_code == 0


# ── redlines ────────────────────────────────────────────────────────


class TestRedlines:
    def test_redlines_default(self):
        result = runner.invoke(app, ["percv", "redlines"])
        assert result.exit_code == 0
        assert "RL-001" in result.stdout or "RSI" in result.stdout


# ── ratchet ─────────────────────────────────────────────────────────


class TestRatchet:
    def test_ratchet_dry_run(self):
        with patch("maref_lite.percv_cli.MultiTargetRatchet") as MockMTR:
            instance = MockMTR.return_value
            result = runner.invoke(app, ["percv", "ratchet"])
            assert result.exit_code == 0


# ── learn ───────────────────────────────────────────────────────────


class TestLearn:
    def test_learn_default(self):
        result = runner.invoke(app, ["percv", "learn"])
        assert result.exit_code == 0

    def test_learn_custom_rounds(self):
        result = runner.invoke(app, ["percv", "learn", "--rounds", "3"])
        assert result.exit_code == 0
