"""Tests for CostMonitor — PERCV cost tracking to MAREF governance bridge."""

from __future__ import annotations

from unittest.mock import MagicMock

from maref.integration.percv.cost_monitor import CostMonitor


class TestCostMonitor:
    def test_init(self) -> None:
        gateway = MagicMock()
        monitor = CostMonitor(gateway_adapter=gateway)
        assert monitor._warning_pct == 80.0
        assert monitor._critical_pct == 95.0

    def test_check_ok(self) -> None:
        gateway = MagicMock()
        gateway.get_budget_status.return_value = {
            "monthly_budget": 5000.0,
            "spent": 1000.0,
            "pct_used": 20.0,
        }
        monitor = CostMonitor(gateway_adapter=gateway)
        result = monitor.check_and_act()
        assert result["alert"] == "ok"
        assert result["monthly_cost"] == 1000.0

    def test_check_warning(self) -> None:
        gateway = MagicMock()
        gateway.get_budget_status.return_value = {
            "monthly_budget": 5000.0,
            "spent": 4200.0,
            "pct_used": 84.0,
        }
        monitor = CostMonitor(gateway_adapter=gateway)
        result = monitor.check_and_act()
        assert result["alert"] == "warning"

    def test_check_critical(self) -> None:
        gateway = MagicMock()
        gateway.get_budget_status.return_value = {
            "monthly_budget": 5000.0,
            "spent": 4800.0,
            "pct_used": 96.0,
        }
        cb = MagicMock()
        monitor = CostMonitor(gateway_adapter=gateway, circuit_breaker=cb)
        result = monitor.check_and_act()
        assert result["alert"] == "critical"
        cb.trip.assert_called_once()

    def test_check_exceeded(self) -> None:
        gateway = MagicMock()
        gateway.get_budget_status.return_value = {
            "monthly_budget": 5000.0,
            "spent": 5100.0,
            "pct_used": 102.0,
        }
        cb = MagicMock()
        monitor = CostMonitor(gateway_adapter=gateway, circuit_breaker=cb)
        result = monitor.check_and_act()
        assert result["alert"] == "exceeded"
        assert "budget_exceeded" in result["actions_taken"]

    def test_check_exceeded_triggers_state_halt(self) -> None:
        gateway = MagicMock()
        gateway.get_budget_status.return_value = {
            "monthly_budget": 5000.0,
            "spent": 6000.0,
            "pct_used": 120.0,
        }
        sm = MagicMock()
        monitor = CostMonitor(gateway_adapter=gateway, state_machine=sm)
        monitor.check_and_act()
        sm.transition.assert_called_once()

    def test_should_downgrade_model(self) -> None:
        gateway = MagicMock()
        gateway.get_budget_status.return_value = {
            "monthly_budget": 5000.0,
            "spent": 4500.0,
            "pct_used": 90.0,
        }
        monitor = CostMonitor(gateway_adapter=gateway)
        monitor.check_and_act()
        assert monitor.should_downgrade_model()

    def test_should_not_downgrade(self) -> None:
        gateway = MagicMock()
        gateway.get_budget_status.return_value = {
            "monthly_budget": 5000.0,
            "spent": 500.0,
            "pct_used": 10.0,
        }
        monitor = CostMonitor(gateway_adapter=gateway)
        monitor.check_and_act()
        assert not monitor.should_downgrade_model()

    def test_get_status(self) -> None:
        gateway = MagicMock()
        monitor = CostMonitor(gateway_adapter=gateway)
        assert monitor.get_status()["alert"] == "never_checked"

    def test_reset_monthly(self) -> None:
        gateway = MagicMock()
        gateway.get_budget_status.return_value = {
            "monthly_budget": 5000.0,
            "spent": 3000.0,
            "pct_used": 60.0,
        }
        monitor = CostMonitor(gateway_adapter=gateway)
        monitor.check_and_act()
        monitor.reset_monthly()
        assert monitor.get_status()["alert"] == "never_checked"

    def test_gateway_error(self) -> None:
        gateway = MagicMock()
        gateway.get_budget_status.side_effect = RuntimeError("gateway down")
        monitor = CostMonitor(gateway_adapter=gateway)
        result = monitor.check_and_act()
        assert result["alert"] == "error"
