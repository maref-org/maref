"""Tests for EU AI Act risk management system (Art.9)."""

from __future__ import annotations

from maref.compliance.eu_ai_act_v2.risk_management import (
    RiskAssessment,
    RiskLikelihood,
    RiskManagementLifecycleState,
    RiskManagementSystem,
    RiskMitigationMeasure,
    RiskSeverity,
)


class TestRiskSeverity:
    def test_negligible_weight(self) -> None:
        assert RiskSeverity.NEGLIGIBLE.weight == 1

    def test_minor_weight(self) -> None:
        assert RiskSeverity.MINOR.weight == 2

    def test_moderate_weight(self) -> None:
        assert RiskSeverity.MODERATE.weight == 3

    def test_significant_weight(self) -> None:
        assert RiskSeverity.SIGNIFICANT.weight == 4

    def test_severe_weight(self) -> None:
        assert RiskSeverity.SEVERE.weight == 5

    def test_values_use_value_property(self) -> None:
        assert RiskSeverity.NEGLIGIBLE.value == "negligible"
        assert RiskSeverity.MINOR.value == "minor"
        assert RiskSeverity.MODERATE.value == "moderate"
        assert RiskSeverity.SIGNIFICANT.value == "significant"
        assert RiskSeverity.SEVERE.value == "severe"

    def test_weights_are_sequential(self) -> None:
        weights = [e.weight for e in RiskSeverity]
        assert weights == [1, 2, 3, 4, 5]


class TestRiskLikelihood:
    def test_improbable_weight(self) -> None:
        assert RiskLikelihood.IMPROBABLE.weight == 1

    def test_remote_weight(self) -> None:
        assert RiskLikelihood.REMOTE.weight == 2

    def test_occasional_weight(self) -> None:
        assert RiskLikelihood.OCCASIONAL.weight == 3

    def test_probable_weight(self) -> None:
        assert RiskLikelihood.PROBABLE.weight == 4

    def test_frequent_weight(self) -> None:
        assert RiskLikelihood.FREQUENT.weight == 5

    def test_weights_are_sequential(self) -> None:
        weights = [e.weight for e in RiskLikelihood]
        assert weights == [1, 2, 3, 4, 5]


class TestRiskManagementLifecycleState:
    def test_states_defined(self) -> None:
        states = list(RiskManagementLifecycleState)
        assert len(states) == 6

    def test_state_order(self) -> None:
        states = list(RiskManagementLifecycleState)
        assert states == [
            RiskManagementLifecycleState.IDENTIFY,
            RiskManagementLifecycleState.ANALYZE,
            RiskManagementLifecycleState.EVALUATE,
            RiskManagementLifecycleState.MITIGATE,
            RiskManagementLifecycleState.MONITOR,
            RiskManagementLifecycleState.REVIEW,
        ]


class TestRiskAssessment:
    def test_default_risk_id_generated(self) -> None:
        risk = RiskAssessment(description="Test risk")
        assert isinstance(risk.risk_id, str)
        assert len(risk.risk_id) == 12

    def test_unique_ids(self) -> None:
        ids = {RiskAssessment().risk_id for _ in range(100)}
        assert len(ids) == 100

    def test_default_severity_and_likelihood(self) -> None:
        risk = RiskAssessment()
        assert risk.severity == RiskSeverity.NEGLIGIBLE
        assert risk.likelihood == RiskLikelihood.IMPROBABLE


class TestRiskMitigationMeasure:
    def test_default_measure_id_generated(self) -> None:
        measure = RiskMitigationMeasure(description="Test measure")
        assert isinstance(measure.measure_id, str)
        assert len(measure.measure_id) == 12

    def test_default_effectiveness(self) -> None:
        measure = RiskMitigationMeasure(description="Test")
        assert measure.effectiveness == 0.0


class TestRiskManagementSystem:
    def test_initial_state(self) -> None:
        system = RiskManagementSystem()
        assert system.state == RiskManagementLifecycleState.IDENTIFY
        assert system.catalog == {}
        assert system.mitigations == {}

    def test_identify_risks_seeds_defaults(self) -> None:
        system = RiskManagementSystem()
        risks = system.identify_risks()
        assert len(risks) == 7
        assert all(isinstance(r, RiskAssessment) for r in risks)

    def test_identify_risks_stable(self) -> None:
        system = RiskManagementSystem()
        first = system.identify_risks()
        second = system.identify_risks()
        assert len(first) == len(second)
        assert first == second

    def test_register_risk_returns_with_score(self) -> None:
        system = RiskManagementSystem()
        risk = RiskAssessment(
            description="New risk",
            category="safety",
            severity=RiskSeverity.SEVERE,
            likelihood=RiskLikelihood.FREQUENT,
        )
        registered = system.register_risk(risk)
        assert registered.risk_score == 25  # 5 x 5

    def test_register_risk_adds_to_catalog(self) -> None:
        system = RiskManagementSystem()
        risk = RiskAssessment(
            description="Another risk",
            category="privacy",
            severity=RiskSeverity.MODERATE,
            likelihood=RiskLikelihood.PROBABLE,
        )
        system.register_risk(risk)
        assert risk.risk_id in system.catalog

    def test_register_risk_computes_score(self) -> None:
        system = RiskManagementSystem()
        risk = RiskAssessment(
            description="Score check",
            severity=RiskSeverity.MODERATE,
            likelihood=RiskLikelihood.OCCASIONAL,
        )
        system.register_risk(risk)
        assert risk.risk_score == 9  # 3 x 3

    def test_duplicate_risk_id_overwrites(self) -> None:
        system = RiskManagementSystem()
        risk1 = RiskAssessment(
            risk_id="fixed-id",
            description="Original",
            severity=RiskSeverity.NEGLIGIBLE,
            likelihood=RiskLikelihood.IMPROBABLE,
        )
        risk2 = RiskAssessment(
            risk_id="fixed-id",
            description="Overwritten",
            severity=RiskSeverity.SEVERE,
            likelihood=RiskLikelihood.FREQUENT,
        )
        system.register_risk(risk1)
        system.register_risk(risk2)
        assert len(system.catalog) == 1
        assert system.catalog["fixed-id"].description == "Overwritten"
        assert system.catalog["fixed-id"].risk_score == 25

    def test_evaluate_risks_empty_catalog(self) -> None:
        system = RiskManagementSystem()
        result = system.evaluate_risks()
        assert result["total_risks"] == 0
        assert result["risk_scores"] == []

    def test_evaluate_risks_with_defaults(self) -> None:
        system = RiskManagementSystem()
        system.identify_risks()
        result = system.evaluate_risks()
        assert result["total_risks"] == 7
        assert result["highest_score"] == 15
        assert result["lowest_score"] == 8
        assert len(result["high_priority"]) > 0
        assert len(result["medium_priority"]) > 0
        assert len(result["low_priority"]) == 0

    def test_evaluate_risks_priority_tiers(self) -> None:
        system = RiskManagementSystem()

        low = RiskAssessment(
            severity=RiskSeverity.NEGLIGIBLE,
            likelihood=RiskLikelihood.IMPROBABLE,
        )
        system.register_risk(low)

        medium = RiskAssessment(
            severity=RiskSeverity.MODERATE,
            likelihood=RiskLikelihood.OCCASIONAL,
        )
        system.register_risk(medium)

        high = RiskAssessment(
            severity=RiskSeverity.SEVERE,
            likelihood=RiskLikelihood.FREQUENT,
        )
        system.register_risk(high)

        result = system.evaluate_risks()
        assert result["total_risks"] == 3
        assert len(result["high_priority"]) == 1
        assert len(result["medium_priority"]) == 1
        assert len(result["low_priority"]) == 1

    def test_evaluate_risks_categorized(self) -> None:
        system = RiskManagementSystem()
        system.identify_risks()
        result = system.evaluate_risks()
        assert "minors" in result["categorized"]
        assert "safety" in result["categorized"]
        assert "vulnerable_groups" in result["categorized"]

    def test_propose_mitigations(self) -> None:
        system = RiskManagementSystem()
        system.identify_risks()
        minors_risk = next(r for r in system.catalog.values() if r.category == "minors")
        measures = system.propose_mitigations(minors_risk.risk_id)
        assert len(measures) > 0
        assert all(isinstance(m, RiskMitigationMeasure) for m in measures)

    def test_propose_mitigations_unknown_risk_raises(self) -> None:
        system = RiskManagementSystem()
        try:
            system.propose_mitigations("nonexistent")
            raise AssertionError("Expected KeyError")
        except KeyError:
            pass

    def test_apply_mitigation(self) -> None:
        system = RiskManagementSystem()
        system.identify_risks()
        risk = next(iter(system.catalog.values()))
        measures = system.propose_mitigations(risk.risk_id)
        result = system.apply_mitigation(risk.risk_id, measures[0].measure_id)
        assert result.mitigated
        assert result.mitigation == measures[0].description
        assert measures[0].implemented

    def test_apply_mitigation_unknown_risk_raises(self) -> None:
        system = RiskManagementSystem()
        try:
            system.apply_mitigation("missing", "measure-1")
            raise AssertionError("Expected KeyError")
        except KeyError:
            pass

    def test_apply_mitigation_unknown_measure_raises(self) -> None:
        system = RiskManagementSystem()
        system.identify_risks()
        risk = next(iter(system.catalog.values()))
        try:
            system.apply_mitigation(risk.risk_id, "nonexistent-measure")
            raise AssertionError("Expected KeyError")
        except KeyError:
            pass

    def test_get_risk_matrix_empty(self) -> None:
        system = RiskManagementSystem()
        matrix = system.get_risk_matrix()
        assert len(matrix) == 5
        for sev in RiskSeverity:
            row = matrix[sev.value]
            assert len(row) == 5
            for like in RiskLikelihood:
                assert row[like.value] == 0

    def test_get_risk_matrix_with_risks(self) -> None:
        system = RiskManagementSystem()
        system.identify_risks()
        matrix = system.get_risk_matrix()
        assert matrix["severe"]["occasional"] == 1  # minors risk
        assert matrix["significant"]["occasional"] == 2  # discrimination + vulnerable
        assert matrix["moderate"]["probable"] == 1  # transparency
        assert matrix["moderate"]["occasional"] == 1  # privacy
        assert matrix["significant"]["remote"] == 1  # human_oversight
        assert matrix["severe"]["remote"] == 1  # safety

    def test_risk_matrix_all_cells_present(self) -> None:
        system = RiskManagementSystem()
        system.identify_risks()
        matrix = system.get_risk_matrix()
        for sev in RiskSeverity:
            for like in RiskLikelihood:
                assert like.value in matrix[sev.value]

    def test_assess_vulnerable_groups_impact_with_risks(self) -> None:
        system = RiskManagementSystem()
        system.identify_risks()
        result = system.assess_vulnerable_groups_impact()
        assert result["has_identified_impact"]
        assert len(result["minors_risks"]) == 1
        assert len(result["vulnerable_groups_risks"]) == 1
        assert result["highest_risk_score"] == 15
        assert result["overall_risk_level"] == "critical"

    def test_assess_vulnerable_groups_impact_no_risks(self) -> None:
        system = RiskManagementSystem()
        result = system.assess_vulnerable_groups_impact()
        assert not result["has_identified_impact"]
        assert result["minors_risks"] == []
        assert result["vulnerable_groups_risks"] == []

    def test_assess_vulnerable_groups_impact_recommendations(self) -> None:
        system = RiskManagementSystem()
        system.identify_risks()
        result = system.assess_vulnerable_groups_impact()
        assert len(result["recommendations"]) > 0

    def test_assess_vulnerable_groups_impact_counts_mitigated(self) -> None:
        system = RiskManagementSystem()
        system.identify_risks()
        # Mitigate one vulnerable risk
        minors = next(r for r in system.catalog.values() if r.category == "minors")
        measures = system.propose_mitigations(minors.risk_id)
        system.apply_mitigation(minors.risk_id, measures[0].measure_id)
        result = system.assess_vulnerable_groups_impact()
        assert result["mitigated_risk_count"] == 1
        assert result["unmitigated_risk_count"] == 1

    def test_review_cycle_initial(self) -> None:
        system = RiskManagementSystem()
        result = system.review_cycle()
        assert result["lifecycle_state"] == "identify"
        assert result["total_risks"] == 0
        assert result["mitigated_risks"] == 0

    def test_review_cycle_after_mitigation(self) -> None:
        system = RiskManagementSystem()
        system.identify_risks()
        risk = next(iter(system.catalog.values()))
        measures = system.propose_mitigations(risk.risk_id)
        system.apply_mitigation(risk.risk_id, measures[0].measure_id)
        result = system.review_cycle()
        assert result["total_risks"] == 7
        assert result["mitigated_risks"] == 1
        assert result["unmitigated_risks"] == 6
        assert result["mitigation_rate"] > 0

    def test_review_cycle_phase_booleans(self) -> None:
        system = RiskManagementSystem()
        system.identify_risks()
        result = system.review_cycle()
        assert result["phase"]["identify"]
        assert result["phase"]["analyze"]
        assert result["phase"]["evaluate"]
        assert not result["phase"]["mitigate"]  # no mitigations applied yet
        assert result["phase"]["monitor"]
        assert result["phase"]["review"]

    def test_generate_report_structure(self) -> None:
        system = RiskManagementSystem()
        system.identify_risks()
        report = system.generate_report()
        assert report["system"] == "EU AI Act Art.9 Risk Management System"
        assert "lifecycle" in report
        assert "risk_matrix" in report
        assert "vulnerable_groups_impact" in report
        assert "evaluation" in report

    def test_generate_report_empty(self) -> None:
        system = RiskManagementSystem()
        report = system.generate_report()
        assert report["lifecycle"]["total_risks"] == 0
        assert report["evaluation"]["total_risks"] == 0

    def test_generate_report_after_full_lifecycle(self) -> None:
        system = RiskManagementSystem()
        risks = system.identify_risks()

        for risk in risks:
            measures = system.propose_mitigations(risk.risk_id)
            system.apply_mitigation(risk.risk_id, measures[0].measure_id)

        system.state = RiskManagementLifecycleState.REVIEW
        report = system.generate_report()
        assert report["lifecycle"]["total_risks"] == 7
        assert report["lifecycle"]["mitigated_risks"] == 7
        assert report["lifecycle"]["mitigation_rate"] == 1.0
        assert report["vulnerable_groups_impact"]["has_identified_impact"]


class TestRiskManagementSystemEdgeCases:
    def test_empty_catalog_all_methods(self) -> None:
        system = RiskManagementSystem()
        assert system.evaluate_risks()["total_risks"] == 0
        assert system.review_cycle()["total_risks"] == 0
        assert not system.assess_vulnerable_groups_impact()["has_identified_impact"]
        matrix = system.get_risk_matrix()
        for sev in RiskSeverity:
            for like in RiskLikelihood:
                assert matrix[sev.value][like.value] == 0

    def test_risk_score_formula(self) -> None:
        """Verify risk_score = severity.weight x likelihood.weight."""
        system = RiskManagementSystem()
        for severity in RiskSeverity:
            for likelihood in RiskLikelihood:
                risk = RiskAssessment(
                    severity=severity,
                    likelihood=likelihood,
                )
                system.register_risk(risk)
                expected = severity.weight * likelihood.weight
                assert risk.risk_score == expected, (
                    f"Expected {expected} for {severity.value} x {likelihood.value}, "
                    f"got {risk.risk_score}"
                )

    def test_risk_score_range(self) -> None:
        """Scores should be in range 1-25."""
        system = RiskManagementSystem()
        for severity in RiskSeverity:
            for likelihood in RiskLikelihood:
                risk = RiskAssessment(severity=severity, likelihood=likelihood)
                system.register_risk(risk)
                assert 1 <= risk.risk_score <= 25

    def test_register_many_risks(self) -> None:
        system = RiskManagementSystem()
        for i in range(50):
            risk = RiskAssessment(
                description=f"Risk {i}",
                severity=RiskSeverity.MODERATE,
                likelihood=RiskLikelihood.OCCASIONAL,
            )
            system.register_risk(risk)
        assert len(system.catalog) == 50
        result = system.evaluate_risks()
        assert result["total_risks"] == 50

    def test_mitigation_does_not_affect_other_risks(self) -> None:
        system = RiskManagementSystem()
        system.identify_risks()
        risks = list(system.catalog.values())
        measures = system.propose_mitigations(risks[0].risk_id)
        system.apply_mitigation(risks[0].risk_id, measures[0].measure_id)
        for i in range(1, len(risks)):
            assert not risks[i].mitigated
