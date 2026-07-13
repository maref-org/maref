"""Tests for complexity_budget.py — ArchitectureComplexityBudget, edge registration, reports."""
from __future__ import annotations

import pytest

from maref.recursive.complexity_budget import (
    ArchitectureComplexityBudget,
    ComplexityAssessment,
    ComplexityBudgetConfig,
    GlobalComplexityReport,
    InteractionEdge,
)


class TestArchitectureComplexityBudget:
    def test_initial_state(self):
        budget = ArchitectureComplexityBudget()
        assert budget.config.max_interaction_edges_per_module == 6
        assert budget.blocked_modules == []

    def test_register_edge_new(self):
        budget = ArchitectureComplexityBudget()
        result = budget.register_edge("module_a", "module_b", "import")
        assert isinstance(result, ComplexityAssessment)
        assert result.module_name == "module_a"
        assert result.status == "OK"

    def test_register_edge_duplicate(self):
        budget = ArchitectureComplexityBudget()
        budget.register_edge("a", "b")
        result = budget.register_edge("a", "b")
        assert result is None

    def test_register_edge_warning(self):
        config = ComplexityBudgetConfig(
            max_interaction_edges_per_module=5,
            warn_at_percent=0.5,
            block_at_percent=0.9,
        )
        budget = ArchitectureComplexityBudget(config=config)
        for target in ["x", "y", "z"]:
            budget.register_edge("mod", target)
        assessment = budget.get_module_assessment("mod")
        assert assessment.status == "WARNING"

    def test_register_edge_blocked(self):
        config = ComplexityBudgetConfig(
            max_interaction_edges_per_module=2,
            warn_at_percent=0.5,
            block_at_percent=0.8,
        )
        budget = ArchitectureComplexityBudget(config=config)
        for target in ["x", "y"]:
            budget.register_edge("mod", target)
        assessment = budget.get_module_assessment("mod")
        assert assessment.status == "BLOCKED"

    def test_is_module_blocked(self):
        config = ComplexityBudgetConfig(
            max_interaction_edges_per_module=1,
            block_at_percent=0.5,
        )
        budget = ArchitectureComplexityBudget(config=config)
        budget.register_edge("mod", "x")
        budget.register_edge("mod", "y")
        assert budget.is_module_blocked("mod") is True
        assert budget.is_module_blocked("clean_mod") is False

    def test_get_global_report_empty(self):
        budget = ArchitectureComplexityBudget()
        report = budget.get_global_report()
        assert report.total_modules == 0
        assert report.global_status == "empty"

    def test_get_global_report_healthy(self):
        budget = ArchitectureComplexityBudget()
        budget.register_edge("a", "b")
        report = budget.get_global_report()
        assert report.total_modules == 1
        assert report.global_status == "HEALTHY"

    def test_get_global_report_with_near_limit(self):
        config = ComplexityBudgetConfig(
            max_interaction_edges_per_module=5,
            warn_at_percent=0.3,
            block_at_percent=1.0,
        )
        budget = ArchitectureComplexityBudget(config=config)
        for target in ["x", "y"]:
            budget.register_edge("mod", target)
        report = budget.get_global_report()
        assert report.global_status == "WARNING"

    def test_get_global_report_blocked(self):
        config = ComplexityBudgetConfig(
            max_interaction_edges_per_module=2,
            warn_at_percent=0.5,
            block_at_percent=0.8,
        )
        budget = ArchitectureComplexityBudget(config=config)
        for target in ["x", "y", "z"]:
            budget.register_edge("mod", target)
        report = budget.get_global_report()
        assert report.global_status == "BLOCKED"

    def test_suggest_edge_reduction_no_edges(self):
        budget = ArchitectureComplexityBudget()
        suggestions = budget.suggest_edge_reduction("nonexistent")
        assert suggestions == []

    def test_suggest_edge_reduction_within_budget(self):
        budget = ArchitectureComplexityBudget()
        budget.register_edge("mod", "x")
        suggestions = budget.suggest_edge_reduction("mod")
        assert "within budget" in suggestions[0].lower()

    def test_suggest_edge_reduction_needed(self):
        config = ComplexityBudgetConfig(
            max_interaction_edges_per_module=2,
        )
        budget = ArchitectureComplexityBudget(config=config)
        for target in ["a", "b", "c", "d"]:
            budget.register_edge("mod", target)
        suggestions = budget.suggest_edge_reduction("mod", target_edge_count=2)
        assert len(suggestions) >= 2

    def test_remove_edge(self):
        budget = ArchitectureComplexityBudget()
        budget.register_edge("a", "b")
        budget.remove_edge("a", "b")
        assessment = budget.get_module_assessment("a")
        assert assessment.current_edge_count == 0

    def test_remove_edge_nonexistent(self):
        budget = ArchitectureComplexityBudget()
        budget.remove_edge("a", "b")  # should not raise

    def test_check_complexity_budget(self):
        budget = ArchitectureComplexityBudget()
        budget.register_edge("mod", "x")
        assessment = budget.check_complexity_budget("mod")
        assert isinstance(assessment, ComplexityAssessment)

    def test_alerts_property(self):
        config = ComplexityBudgetConfig(
            max_interaction_edges_per_module=2,
            warn_at_percent=0.5,
            block_at_percent=0.8,
        )
        budget = ArchitectureComplexityBudget(config=config)
        budget.register_edge("mod", "x")
        budget.register_edge("mod", "y")
        budget.register_edge("mod", "z")
        assert len(budget.alerts) >= 1

    def test_clear(self):
        budget = ArchitectureComplexityBudget()
        budget.register_edge("a", "b")
        budget.clear()
        assert budget.alerts == []
        assert budget.blocked_modules == []

    def test_config_property(self):
        config = ComplexityBudgetConfig(max_interaction_edges_per_module=10)
        budget = ArchitectureComplexityBudget(config=config)
        assert budget.config.max_interaction_edges_per_module == 10
