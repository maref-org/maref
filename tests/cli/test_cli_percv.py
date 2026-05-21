"""Tests for the `maref percv` CLI subcommand."""

from __future__ import annotations

from unittest.mock import patch

from maref_lite.percv_cli import (
    cost_report,
    research_cycle,
    status,
    sync_cards,
)


class TestPercvCommands:
    def test_research_cycle_calls_orchestrator(self):
        with patch("maref_lite.percv_cli.PERCVResearchOrchestrator") as MockOrch:
            instance = MockOrch.return_value
            research_cycle(topic="test topic", budget=5000)
            instance.run_research_cycle.assert_called_once_with(topic="test topic")

    def test_status_calls_orchestrator(self):
        with patch("maref_lite.percv_cli.PERCVResearchOrchestrator") as MockOrch:
            instance = MockOrch.return_value
            instance.status = "initialized"
            instance.cycle_count = 0
            instance.get_history.return_value = []
            status()
            instance.get_history.assert_called_once()

    def test_sync_cards_prints_message(self):
        with patch("maref_lite.percv_cli.console") as MockConsole:
            sync_cards()
            MockConsole.print.assert_called_once()

    def test_cost_report_prints_message(self):
        with patch("maref_lite.percv_cli.console") as MockConsole:
            cost_report()
            MockConsole.print.assert_called_once()
