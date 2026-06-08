"""Tests for TokenBudgetController."""

import time

import pytest

from maref.executor.budget import BudgetAction, TokenBudgetController


class TestTokenBudgetController:
    def test_allow_within_budget(self):
        ctrl = TokenBudgetController(tier="premium")
        result = ctrl.check_cost("task-1", "user-1", estimated_cost=1.0)
        assert result.action == BudgetAction.ALLOW

    def test_block_on_per_task_limit(self):
        ctrl = TokenBudgetController(tier="cheap")
        result = ctrl.check_cost("task-1", "user-1", estimated_cost=999.0)
        assert result.action == BudgetAction.BLOCK

    def test_downgrade_at_threshold(self):
        ctrl = TokenBudgetController(tier="standard")
        ctrl.record_cost("task-1", "user-1", actual_cost=85.0)
        result = ctrl.check_cost("task-2", "user-1", estimated_cost=1.0)
        assert result.action == BudgetAction.DOWNGRADE

    def test_interrupt_at_cap(self):
        ctrl = TokenBudgetController(tier="cheap")
        ctrl.record_cost("task-1", "user-1", actual_cost=19.0)
        result = ctrl.check_cost("task-2", "user-1", estimated_cost=2.0)
        assert result.action == BudgetAction.INTERRUPT

    def test_record_cost_accumulates(self):
        ctrl = TokenBudgetController()
        ctrl.record_cost("task-1", "user-1", actual_cost=5.0)
        ctrl.record_cost("task-2", "user-1", actual_cost=3.0)
        assert ctrl.get_user_cost("user-1") == 8.0

    def test_rate_limit_blocks(self):
        ctrl = TokenBudgetController(tier="cheap")
        for i in range(35):
            ctrl.record_cost(f"task-{i}", "user-1", actual_cost=0.01)
        result = ctrl.check_cost("task-late", "user-1", estimated_cost=0.01)
        assert result.action == BudgetAction.BLOCK

    def test_get_stats(self):
        ctrl = TokenBudgetController()
        ctrl.record_cost("task-1", "user-1", actual_cost=10.0)
        stats = ctrl.get_stats()
        assert stats["total_cost"] == 10.0
        assert stats["total_users"] == 1
        assert stats["total_tasks"] == 1
