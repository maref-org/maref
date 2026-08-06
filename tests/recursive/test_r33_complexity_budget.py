from __future__ import annotations

from maref.recursive.complexity_budget import (
    ArchitectureComplexityBudget,
    ComplexityAssessment,
    ComplexityBudgetConfig,
    GlobalComplexityReport,
    InteractionEdge,
)


class TestComplexityBudgetConfig:
    def test_default_config(self) -> None:
        config = ComplexityBudgetConfig()
        assert config.max_interaction_edges_per_module == 6
        assert config.max_total_edges == 200
        assert config.warn_at_percent == 0.75
        assert config.block_at_percent == 0.95

    def test_custom_config(self) -> None:
        config = ComplexityBudgetConfig(max_interaction_edges_per_module=4, warn_at_percent=0.6)
        assert config.max_interaction_edges_per_module == 4
        assert config.warn_at_percent == 0.6


class TestInteractionEdge:
    def test_create_edge(self) -> None:
        edge = InteractionEdge(
            source_module="A",
            target_module="B",
            edge_type="import",
        )
        assert edge.source_module == "A"
        assert edge.target_module == "B"
        assert edge.call_count == 0


class TestComplexityAssessment:
    def test_ok_assessment(self) -> None:
        assessment = ComplexityAssessment(
            module_name="m1",
            current_edge_count=2,
            max_allowed=6,
            usage_percent=33.3,
            status="OK",
        )
        assert assessment.status == "OK"

    def test_warning_assessment(self) -> None:
        assessment = ComplexityAssessment(
            module_name="m2",
            current_edge_count=5,
            max_allowed=6,
            usage_percent=83.3,
            status="WARNING",
            recommendations=["Reduce edges"],
        )
        assert assessment.status == "WARNING"
        assert len(assessment.recommendations) >= 1

    def test_blocked_assessment(self) -> None:
        assessment = ComplexityAssessment(
            module_name="m3",
            current_edge_count=6,
            max_allowed=6,
            usage_percent=100.0,
            status="BLOCKED",
        )
        assert assessment.status == "BLOCKED"


class TestGlobalComplexityReport:
    def test_empty_report(self) -> None:
        report = GlobalComplexityReport(
            total_modules=0,
            total_interaction_edges=0,
            total_unused_edges=0,
            max_module_edge_count=0,
            avg_edges_per_module=0.0,
            global_status="empty",
        )
        assert report.total_modules == 0


class TestArchitectureComplexityBudget:
    def setup_method(self) -> None:
        self.budget = ArchitectureComplexityBudget()

    def test_default_config(self) -> None:
        assert self.budget.config.max_interaction_edges_per_module == 6

    def test_register_single_edge(self) -> None:
        result = self.budget.register_edge("module_A", "module_B", "import")
        assert result is None or result.status in ("OK", "WARNING", "BLOCKED")

    def test_multiple_edges_same_module(self) -> None:
        for i in range(3):
            self.budget.register_edge("multi_mod", f"dep_{i}", "import")
        assessment = self.budget.get_module_assessment("multi_mod")
        assert assessment.current_edge_count == 3

    def test_check_complexity_budget(self) -> None:
        self.budget.register_edge("check_mod", "dep_1", "import")
        assessment = self.budget.check_complexity_budget("check_mod")
        assert assessment.module_name == "check_mod"
        assert assessment.current_edge_count >= 1

    def test_module_not_blocked_initially(self) -> None:
        assert not self.budget.is_module_blocked("any_module")

    def test_empty_module_assessment(self) -> None:
        assessment = self.budget.get_module_assessment("empty_mod")
        assert assessment.module_name == "empty_mod"
        assert assessment.current_edge_count == 0
        assert assessment.status == "OK"

    def test_global_report(self) -> None:
        self.budget.register_edge("A", "B", "import")
        self.budget.register_edge("C", "D", "read")
        report = self.budget.get_global_report()
        assert report.total_modules >= 2
        assert report.total_interaction_edges >= 2

    def test_blocked_when_full(self) -> None:
        for i in range(6):
            self.budget.register_edge("full_mod", f"dep_{i}", "import")
        assessment = self.budget.get_module_assessment("full_mod")
        assert assessment.status == "BLOCKED"

    def test_is_module_blocked(self) -> None:
        for i in range(6):
            self.budget.register_edge("blocked_mod", f"dep_{i}", "import")
        assert self.budget.is_module_blocked("blocked_mod")

    def test_suggest_edge_reduction(self) -> None:
        for i in range(5):
            self.budget.register_edge("reduce_mod", f"dep_{i}", "import")
        suggestions = self.budget.suggest_edge_reduction("reduce_mod", target_edge_count=3)
        assert len(suggestions) >= 2

    def test_suggest_no_reduction_needed(self) -> None:
        self.budget.register_edge("ok_mod", "dep_1", "import")
        suggestions = self.budget.suggest_edge_reduction("ok_mod")
        assert len(suggestions) == 1

    def test_remove_edge(self) -> None:
        self.budget.register_edge("rm_mod", "dep_1", "import")
        len(self.budget.get_module_assessment("rm_mod").recommendations)
        self.budget.remove_edge("rm_mod", "dep_1", "import")
        assessment = self.budget.get_module_assessment("rm_mod")
        assert assessment.current_edge_count == 0

    def test_alerts_empty(self) -> None:
        assert self.budget.alerts == []

    def test_same_edge_increments_count(self) -> None:
        self.budget.register_edge("inc_mod", "dep_1", "import")
        self.budget.register_edge("inc_mod", "dep_1", "import")
        assessment = self.budget.get_module_assessment("inc_mod")
        assert assessment.current_edge_count == 1

    def test_no_alert_for_ok_module(self) -> None:
        self.budget.register_edge("ok_mod", "dep_1", "import")
        assert self.budget.is_module_blocked("ok_mod") is False

    def test_empty_module_blocked(self) -> None:
        assert not self.budget.is_module_blocked("nonexistent")

    def test_global_report_healthy(self) -> None:
        self.budget.register_edge("a1", "b1")
        self.budget.register_edge("a2", "b2")
        report = self.budget.get_global_report()
        assert report.global_status in ("HEALTHY", "empty")
