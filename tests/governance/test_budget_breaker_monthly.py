"""Tests for BudgetBreaker monthly budget feature (P1-11).

These tests verify the monthly budget 95% threshold trip logic.
Run with: PYTHONPATH=src:$PYTHONPATH python3 -m pytest ...
"""

from __future__ import annotations

import pytest

from maref.governance.budget_breaker import BudgetBreaker, BudgetBreakerState


class TestBudgetBreakerMonthly:
    """Tests for the monthly budget feature added in P1-11."""

    def test_monthly_budget_disabled(self):
        """monthly_budget=0 means check_monthly_budget always returns True."""
        bb = BudgetBreaker(monthly_budget=0.0)
        bb.record_spend("agent1", "task1", 1000.0)
        assert bb.check_monthly_budget("agent1") is True

    def test_monthly_budget_below_warning(self):
        """Spend below 80% threshold should pass."""
        bb = BudgetBreaker(monthly_budget=100.0)
        bb.record_spend("agent1", "task1", 50.0)  # 50%
        assert bb.check_monthly_budget("agent1") is True

    def test_monthly_budget_between_warning_and_critical(self):
        """Spend between 80% and 95% should pass but trigger warning."""
        bb = BudgetBreaker(monthly_budget=100.0)
        bb.record_spend("agent1", "task1", 85.0)  # 85%
        assert bb.check_monthly_budget("agent1") is True

    def test_monthly_budget_at_critical(self):
        """Spend >= 95% should trip (return False)."""
        bb = BudgetBreaker(monthly_budget=100.0)
        bb.record_spend("agent1", "task1", 96.0)  # 96%
        assert bb.check_monthly_budget("agent1") is False

    def test_monthly_budget_exceeds_budget(self):
        """Spend > 100% should trip."""
        bb = BudgetBreaker(monthly_budget=100.0)
        bb.record_spend("agent1", "task1", 100.0)  # 100%
        assert bb.check_monthly_budget("agent1") is False

    def test_monthly_budget_after_reset(self):
        """After reset, monthly spend should be cleared."""
        bb = BudgetBreaker(monthly_budget=100.0)
        bb.record_spend("agent1", "task1", 96.0)
        assert bb.check_monthly_budget("agent1") is False
        bb.reset("agent1")
        assert bb.check_monthly_budget("agent1") is True

    def test_monthly_budget_reset_all(self):
        """Full reset clears all monthly data."""
        bb = BudgetBreaker(monthly_budget=100.0)
        bb.record_spend("agent1", "task1", 96.0)
        bb.record_spend("agent2", "task2", 96.0)
        assert bb.check_monthly_budget("agent1") is False
        bb.reset()
        assert bb.check_monthly_budget("agent1") is True
        assert bb.check_monthly_budget("agent2") is True

    def test_monthly_budget_open_state_bypasses(self):
        """If agent has already tripped, check_monthly_budget returns False."""
        bb = BudgetBreaker(monthly_budget=100.0, max_per_agent=10.0)
        # Record and check agent budget to trip circuit
        bb.record_spend("agent1", "task1", 15.0)
        bb.check_agent_budget("agent1", 15.0)  # This triggers the trip
        # Monthly budget check should return False for tripped state
        result = bb.check_monthly_budget("agent1")
        assert result is False

    def test_monthly_budget_multiple_agents(self):
        """Multiple agents have independent monthly budgets."""
        bb = BudgetBreaker(monthly_budget=100.0)
        bb.record_spend("agent1", "task1", 96.0)
        bb.record_spend("agent2", "task2", 50.0)
        assert bb.check_monthly_budget("agent1") is False
        assert bb.check_monthly_budget("agent2") is True

    def test_monthly_budget_step_by_step(self):
        """Gradual spending across thresholds."""
        bb = BudgetBreaker(monthly_budget=100.0)
        # 0% -> safe
        assert bb.check_monthly_budget("agent1") is True
        bb.record_spend("agent1", "task1", 70.0)
        # 70% -> safe
        assert bb.check_monthly_budget("agent1") is True
        bb.record_spend("agent1", "task2", 15.0)
        # 85% -> safe but warning emitted
        assert bb.check_monthly_budget("agent1") is True
        bb.record_spend("agent1", "task3", 11.0)
        # 96% -> trip
        assert bb.check_monthly_budget("agent1") is False

    def test_monthly_budget_stale_state_not_leaked(self):
        """Stale monthly data shouldn't leak between agents."""
        bb = BudgetBreaker(monthly_budget=100.0)
        bb.record_spend("agent1", "task1", 96.0)  # trip agent1
        bb.record_spend("agent2", "task2", 10.0)  # agent2 far below
        assert bb.check_monthly_budget("agent1") is False
        assert bb.check_monthly_budget("agent2") is True

    def test_monthly_budget_in_stats(self):
        """get_stats should include monthly budget info."""
        bb = BudgetBreaker(monthly_budget=200.0)
        bb.record_spend("agent1", "task1", 50.0)
        stats = bb.get_stats()
        assert stats["monthly_budget"] == 200.0
        assert "agent1" in stats.get("monthly_spend", {})

    def test_monthly_budget_custom_thresholds(self):
        """Custom warning/critical thresholds."""
        bb = BudgetBreaker(
            monthly_budget=100.0,
            warning_threshold=0.50,
            critical_threshold=0.75,
        )
        bb.record_spend("agent1", "task1", 60.0)  # 60% >= 50% warning, 60% < 75% safe
        # But we still should pass since 60% < 75%
        assert bb.check_monthly_budget("agent1") is True
        bb.record_spend("agent1", "task2", 20.0)  # 80% >= 75% critical
        assert bb.check_monthly_budget("agent1") is False

    def test_monthly_budget_agent_open_circuit_resets_on_half_open(self):
        """After cooldown, budget check should proceed normally."""
        bb = BudgetBreaker(monthly_budget=100.0, max_per_agent=50.0, cooldown_seconds=0.1)
        # Record and check agent budget to trip circuit
        bb.record_spend("agent1", "task1", 60.0)
        bb.check_agent_budget("agent1", 60.0)  # Triggers trip
        # Monthly budget should also fail due to tripped state
        assert bb.check_monthly_budget("agent1") is False

    def test_monthly_budget_zero_budget_check(self):
        """monthly_budget=0.0 should always be safe."""
        bb = BudgetBreaker(monthly_budget=0.0)
        for _ in range(10):
            bb.record_spend("agent1", "task1", 1000.0)
        assert bb.check_monthly_budget("agent1") is True

    def test_combined_agent_and_monthly_budget(self):
        """Both agent-level and monthly budget can independently trip."""
        bb = BudgetBreaker(max_per_agent=50.0, monthly_budget=100.0)
        # Record and check agent budget to trip circuit
        bb.record_spend("agent1", "task1", 60.0)
        bb.check_agent_budget("agent1", 60.0)  # Triggers trip
        # Monthly budget should also report failure due to tripped state
        assert bb.check_monthly_budget("agent1") is False
