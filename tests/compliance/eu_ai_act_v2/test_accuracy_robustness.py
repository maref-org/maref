"""Tests for EU AI Act Art.15 — Accuracy, Robustness & Cybersecurity."""

from __future__ import annotations

import pytest

from maref.compliance.eu_ai_act_v2.accuracy_robustness import (
    AccuracyDeclaration,
    AccuracyManager,
    AccuracyMetricType,
    Art15ComplianceReport,
    CybersecurityAssessment,
    CybersecurityManager,
    FeedbackLoopDetector,
    FeedbackLoopReport,
    RobustnessManager,
    RobustnessReport,
)


class TestAccuracyMetricType:
    def test_enum_values(self) -> None:
        assert AccuracyMetricType.FAR.value == "false_accept_rate"
        assert AccuracyMetricType.FRR.value == "false_reject_rate"
        assert AccuracyMetricType.EER.value == "equal_error_rate"
        assert AccuracyMetricType.AUC_ROC.value == "auc_roc"
        assert AccuracyMetricType.PRECISION.value == "precision"
        assert AccuracyMetricType.RECALL.value == "recall"
        assert AccuracyMetricType.F1.value == "f1"
        assert AccuracyMetricType.MSE.value == "mean_squared_error"
        assert AccuracyMetricType.CALIBRATION.value == "calibration_error"
        assert AccuracyMetricType.PREDICTIVE_PARITY.value == "predictive_parity"
        assert AccuracyMetricType.DISPARATE_IMPACT.value == "disparate_impact_ratio"
        assert AccuracyMetricType.PSI.value == "population_stability_index"

    def test_enum_count(self) -> None:
        assert len(AccuracyMetricType) == 12


class TestAccuracyDeclaration:
    def test_basic_construction(self) -> None:
        d = AccuracyDeclaration(
            metric=AccuracyMetricType.F1,
            value=0.95,
            threshold=0.8,
        )
        assert d.metric == AccuracyMetricType.F1
        assert d.value == 0.95
        assert d.threshold == 0.8

    def test_post_init_passed_when_value_above_threshold(self) -> None:
        d = AccuracyDeclaration(
            metric=AccuracyMetricType.F1,
            value=0.95,
            threshold=0.8,
        )
        assert d.passed is True

    def test_post_init_passed_when_value_equal_threshold(self) -> None:
        d = AccuracyDeclaration(
            metric=AccuracyMetricType.F1,
            value=0.8,
            threshold=0.8,
        )
        assert d.passed is True

    def test_post_init_passed_when_value_below_threshold(self) -> None:
        d = AccuracyDeclaration(
            metric=AccuracyMetricType.F1,
            value=0.7,
            threshold=0.8,
        )
        assert d.passed is False

    def test_demographic_breakdown(self) -> None:
        d = AccuracyDeclaration(
            metric=AccuracyMetricType.PRECISION,
            value=0.9,
            threshold=0.8,
            demographic_breakdown={"male": 0.92, "female": 0.88},
        )
        assert d.demographic_breakdown["male"] == 0.92
        assert d.demographic_breakdown["female"] == 0.88

    def test_known_limitations(self) -> None:
        d = AccuracyDeclaration(
            metric=AccuracyMetricType.AUC_ROC,
            value=0.85,
            threshold=0.7,
            known_limitations=["Small sample size", "Domain shift risk"],
        )
        assert len(d.known_limitations) == 2
        assert "Small sample size" in d.known_limitations

    def test_default_demographic_breakdown_is_empty(self) -> None:
        d = AccuracyDeclaration(
            metric=AccuracyMetricType.FAR,
            value=0.01,
            threshold=0.05,
        )
        assert d.demographic_breakdown == {}

    def test_default_known_limitations_is_empty(self) -> None:
        d = AccuracyDeclaration(
            metric=AccuracyMetricType.FRR,
            value=0.02,
            threshold=0.05,
        )
        assert d.known_limitations == []


class TestAccuracyManager:
    def test_declare_accuracy_stores_and_returns(self) -> None:
        mgr = AccuracyManager()
        d = mgr.declare_accuracy(
            metric=AccuracyMetricType.F1,
            value=0.95,
            threshold=0.8,
        )
        assert isinstance(d, AccuracyDeclaration)
        assert d.metric == AccuracyMetricType.F1
        assert d.passed is True

    def test_validate_all_returns_all_declarations(self) -> None:
        mgr = AccuracyManager()
        mgr.declare_accuracy(AccuracyMetricType.F1, 0.95, 0.8)
        mgr.declare_accuracy(AccuracyMetricType.MSE, 0.05, 0.1)
        results = mgr.validate_all()
        assert len(results) == 2
        assert all(isinstance(r, AccuracyDeclaration) for r in results)

    def test_validate_all_computes_passed(self) -> None:
        mgr = AccuracyManager()
        mgr.declare_accuracy(AccuracyMetricType.F1, 0.95, 0.8)
        mgr.declare_accuracy(AccuracyMetricType.F1, 0.7, 0.8)
        results = mgr.validate_all()
        assert results[0].passed is True
        assert results[1].passed is False

    def test_get_declarations_returns_all(self) -> None:
        mgr = AccuracyManager()
        assert mgr.get_declarations() == []
        mgr.declare_accuracy(AccuracyMetricType.PRECISION, 0.9, 0.8)
        mgr.declare_accuracy(AccuracyMetricType.RECALL, 0.85, 0.8)
        decls = mgr.get_declarations()
        assert len(decls) == 2

    def test_declare_with_demographic_breakdown(self) -> None:
        mgr = AccuracyManager()
        d = mgr.declare_accuracy(
            AccuracyMetricType.PREDICTIVE_PARITY, 0.95, 0.9,
            demographic_breakdown={"group_a": 0.96, "group_b": 0.94},
        )
        assert d.demographic_breakdown["group_a"] == 0.96

    def test_declare_with_known_limitations(self) -> None:
        mgr = AccuracyManager()
        d = mgr.declare_accuracy(
            AccuracyMetricType.CALIBRATION, 0.12, 0.15,
            known_limitations=["Calibration drift at extremes"],
        )
        assert len(d.known_limitations) == 1


class TestRobustnessReport:
    def test_default_construction(self) -> None:
        r = RobustnessReport(
            reproducibility_score=0.0,
            ood_degradation=0.0,
            psi_value=0.0,
            failsafe_verified=False,
        )
        assert r.reproducibility_score == 0.0
        assert r.ood_degradation == 0.0
        assert r.psi_value == 0.0
        assert r.failsafe_verified is False

    def test_overall_robust_true(self) -> None:
        r = RobustnessReport(
            reproducibility_score=0.95,
            ood_degradation=15.0,
            psi_value=0.2,
            failsafe_verified=True,
        )
        assert r.overall_robust is True

    def test_overall_robust_false_low_reproducibility(self) -> None:
        r = RobustnessReport(
            reproducibility_score=0.94,
            ood_degradation=10.0,
            psi_value=0.1,
            failsafe_verified=True,
        )
        assert r.overall_robust is False

    def test_overall_robust_false_high_ood(self) -> None:
        r = RobustnessReport(
            reproducibility_score=0.96,
            ood_degradation=15.1,
            psi_value=0.1,
            failsafe_verified=True,
        )
        assert r.overall_robust is False

    def test_overall_robust_false_high_psi(self) -> None:
        r = RobustnessReport(
            reproducibility_score=0.96,
            ood_degradation=10.0,
            psi_value=0.21,
            failsafe_verified=True,
        )
        assert r.overall_robust is False

    def test_overall_robust_false_no_failsafe(self) -> None:
        r = RobustnessReport(
            reproducibility_score=0.96,
            ood_degradation=10.0,
            psi_value=0.1,
            failsafe_verified=False,
        )
        assert r.overall_robust is False

    def test_overall_robust_edge_boundaries(self) -> None:
        r = RobustnessReport(
            reproducibility_score=0.95,
            ood_degradation=15.0,
            psi_value=0.2,
            failsafe_verified=True,
        )
        assert r.overall_robust is True


class TestRobustnessManager:
    def test_test_reproducibility(self) -> None:
        mgr = RobustnessManager()
        result = mgr.test_reproducibility(0.97)
        assert result == 0.97

    def test_test_ood_robustness(self) -> None:
        mgr = RobustnessManager()
        result = mgr.test_ood_robustness(12.5)
        assert result == 12.5

    def test_test_temporal_stability(self) -> None:
        mgr = RobustnessManager()
        result = mgr.test_temporal_stability(0.15)
        assert result == 0.15

    def test_test_failsafe_behaviour(self) -> None:
        mgr = RobustnessManager()
        result = mgr.test_failsafe_behavior(True)
        assert result is True

    def test_run_all_returns_report(self) -> None:
        mgr = RobustnessManager()
        mgr.test_reproducibility(0.96)
        mgr.test_ood_robustness(10.0)
        mgr.test_temporal_stability(0.1)
        mgr.test_failsafe_behavior(True)
        report = mgr.run_all()
        assert isinstance(report, RobustnessReport)
        assert report.reproducibility_score == 0.96
        assert report.ood_degradation == 10.0
        assert report.psi_value == 0.1
        assert report.failsafe_verified is True

    def test_run_all_overall_robust_computed(self) -> None:
        mgr = RobustnessManager()
        mgr.test_reproducibility(0.95)
        mgr.test_ood_robustness(15.0)
        mgr.test_temporal_stability(0.2)
        mgr.test_failsafe_behavior(True)
        report = mgr.run_all()
        assert report.overall_robust is True

    def test_run_all_overall_not_robust(self) -> None:
        mgr = RobustnessManager()
        mgr.test_reproducibility(0.50)
        mgr.test_ood_robustness(50.0)
        mgr.test_temporal_stability(0.5)
        mgr.test_failsafe_behavior(False)
        report = mgr.run_all()
        assert report.overall_robust is False

    def test_initial_scores_are_zero(self) -> None:
        mgr = RobustnessManager()
        report = mgr.run_all()
        assert report.reproducibility_score == 0.0
        assert report.ood_degradation == 0.0
        assert report.psi_value == 0.0
        assert report.failsafe_verified is False


class TestCybersecurityAssessment:
    def test_construction(self) -> None:
        a = CybersecurityAssessment(
            vector="data_poisoning",
            controls_in_place=["input_validation", "anomaly_detection"],
            missing_controls=["training_data_sanitization"],
        )
        assert a.vector == "data_poisoning"
        assert len(a.controls_in_place) == 2
        assert len(a.missing_controls) == 1

    def test_risk_score_with_controls_and_missing(self) -> None:
        a = CybersecurityAssessment(
            vector="data_poisoning",
            controls_in_place=["input_validation"],
            missing_controls=["sanitization", "monitoring"],
        )
        # 1.0 - (1 / (1 + 2)) = 1.0 - 0.333... = 0.666...
        assert a.risk_score == pytest.approx(0.6666667, rel=1e-5)

    def test_risk_score_all_controls_no_missing(self) -> None:
        a = CybersecurityAssessment(
            vector="model_poisoning",
            controls_in_place=["secure_aggregation", "gradient_sanitization"],
            missing_controls=[],
        )
        # 1.0 - (2 / 2) = 0.0
        assert a.risk_score == 0.0

    def test_risk_score_no_controls_all_missing(self) -> None:
        a = CybersecurityAssessment(
            vector="adversarial_examples",
            controls_in_place=[],
            missing_controls=["adversarial_training", "input_transformation"],
        )
        # 1.0 - (0 / 2) = 1.0
        assert a.risk_score == 1.0

    def test_risk_score_no_controls_no_missing(self) -> None:
        a = CybersecurityAssessment(
            vector="confidentiality",
            controls_in_place=[],
            missing_controls=[],
        )
        assert a.risk_score == 1.0


class TestCybersecurityManager:
    def test_assess_vector_returns_assessment(self) -> None:
        mgr = CybersecurityManager()
        a = mgr.assess_vector(
            "data_poisoning",
            ["input_validation"],
        )
        assert isinstance(a, CybersecurityAssessment)
        assert a.vector == "data_poisoning"

    def test_assess_all_returns_five_assessments(self) -> None:
        mgr = CybersecurityManager()
        assessments = mgr.assess_all()
        assert len(assessments) == 5
        vectors = [a.vector for a in assessments]
        assert "data_poisoning" in vectors
        assert "model_poisoning" in vectors
        assert "adversarial_examples" in vectors
        assert "confidentiality" in vectors
        assert "model_flaws" in vectors

    def test_assess_all_with_pre_registered(self) -> None:
        mgr = CybersecurityManager()
        mgr.assess_vector("data_poisoning", ["input_validation"])
        assessments = mgr.assess_all()
        data_poisoning = [a for a in assessments if a.vector == "data_poisoning"]
        assert len(data_poisoning) == 1
        assert data_poisoning[0].controls_in_place == ["input_validation"]

    def test_assess_all_unregistered_have_empty_controls(self) -> None:
        mgr = CybersecurityManager()
        assessments = mgr.assess_all()
        for a in assessments:
            assert a.controls_in_place == []

    def test_gap_analysis_returns_dict(self) -> None:
        mgr = CybersecurityManager()
        mgr.assess_vector("data_poisoning", ["input_validation"])
        gaps = mgr.gap_analysis()
        assert isinstance(gaps, dict)
        assert "data_poisoning" in gaps

    def test_gap_analysis_lists_missing_controls(self) -> None:
        mgr = CybersecurityManager()
        mgr.assess_vector("data_poisoning", ["input_validation"])
        gaps = mgr.gap_analysis()
        assert len(gaps["data_poisoning"]) > 0

    def test_gap_analysis_all_five_vectors(self) -> None:
        mgr = CybersecurityManager()
        gaps = mgr.gap_analysis()
        assert len(gaps) == 5
        expected_vectors = {
            "data_poisoning", "model_poisoning", "adversarial_examples",
            "confidentiality", "model_flaws",
        }
        assert set(gaps.keys()) == expected_vectors


class TestFeedbackLoopReport:
    def test_construction(self) -> None:
        r = FeedbackLoopReport(
            contamination_detected=True,
            contamination_score=0.8,
            affected_inputs=["input_1", "input_2"],
            recommendations=["Purge affected inputs", "Retrain model"],
        )
        assert r.contamination_detected is True
        assert r.contamination_score == 0.8
        assert len(r.affected_inputs) == 2
        assert len(r.recommendations) == 2

    def test_default_affected_inputs(self) -> None:
        r = FeedbackLoopReport(
            contamination_detected=False,
            contamination_score=0.0,
        )
        assert r.affected_inputs == []
        assert r.recommendations == []


class TestFeedbackLoopDetector:
    def test_contamination_detected_above_threshold(self) -> None:
        detector = FeedbackLoopDetector()
        report = detector.check_feedback_contamination(score=0.5)
        assert report.contamination_detected is True
        assert report.contamination_score == 0.5

    def test_contamination_detected_at_threshold_boundary(self) -> None:
        detector = FeedbackLoopDetector()
        report = detector.check_feedback_contamination(score=0.3001)
        assert report.contamination_detected is True

    def test_no_contamination_below_threshold(self) -> None:
        detector = FeedbackLoopDetector()
        report = detector.check_feedback_contamination(score=0.2)
        assert report.contamination_detected is False
        assert report.contamination_score == 0.2

    def test_no_contamination_at_threshold(self) -> None:
        detector = FeedbackLoopDetector()
        report = detector.check_feedback_contamination(score=0.3)
        assert report.contamination_detected is False

    def test_contamination_with_affected_inputs(self) -> None:
        detector = FeedbackLoopDetector()
        report = detector.check_feedback_contamination(
            score=0.7,
            affected=["input_a", "input_b"],
        )
        assert report.contamination_detected is True
        assert report.affected_inputs == ["input_a", "input_b"]

    def test_contamination_includes_recommendations(self) -> None:
        detector = FeedbackLoopDetector()
        report = detector.check_feedback_contamination(score=0.8)
        assert len(report.recommendations) > 0

    def test_no_contamination_recommendations_empty(self) -> None:
        detector = FeedbackLoopDetector()
        report = detector.check_feedback_contamination(score=0.0)
        assert report.recommendations == []


class TestArt15ComplianceReport:
    def test_default_construction(self) -> None:
        report = Art15ComplianceReport()
        assert report.accuracy_declarations == []
        assert report.robustness_report is None
        assert report.cybersecurity_assessments == []
        assert report.feedback_loop_report is None
        assert report.overall_compliant is False

    def test_compliant_with_all_conditions_met(self) -> None:
        decls = [
            AccuracyDeclaration(AccuracyMetricType.F1, 0.95, 0.8),
        ]
        robust = RobustnessReport(
            reproducibility_score=0.95,
            ood_degradation=15.0,
            psi_value=0.2,
            failsafe_verified=True,
        )
        cybers = [
            CybersecurityAssessment(
                vector="data_poisoning",
                controls_in_place=["all_controls"],
                missing_controls=[],
            ),
        ]
        report = Art15ComplianceReport(
            accuracy_declarations=decls,
            robustness_report=robust,
            cybersecurity_assessments=cybers,
        )
        assert report.overall_compliant is True

    def test_not_compliant_when_accuracy_fails(self) -> None:
        decls = [
            AccuracyDeclaration(AccuracyMetricType.F1, 0.5, 0.8),
        ]
        robust = RobustnessReport(
            reproducibility_score=0.95,
            ood_degradation=15.0,
            psi_value=0.2,
            failsafe_verified=True,
        )
        cybers = [
            CybersecurityAssessment(
                vector="data_poisoning",
                controls_in_place=["all"],
                missing_controls=[],
            ),
        ]
        report = Art15ComplianceReport(
            accuracy_declarations=decls,
            robustness_report=robust,
            cybersecurity_assessments=cybers,
        )
        assert report.overall_compliant is False

    def test_not_compliant_when_robustness_fails(self) -> None:
        decls = [
            AccuracyDeclaration(AccuracyMetricType.F1, 0.95, 0.8),
        ]
        robust = RobustnessReport(
            reproducibility_score=0.5,
            ood_degradation=50.0,
            psi_value=0.5,
            failsafe_verified=False,
        )
        cybers = [
            CybersecurityAssessment(
                vector="data_poisoning",
                controls_in_place=["all"],
                missing_controls=[],
            ),
        ]
        report = Art15ComplianceReport(
            accuracy_declarations=decls,
            robustness_report=robust,
            cybersecurity_assessments=cybers,
        )
        assert report.overall_compliant is False

    def test_not_compliant_when_cybersecurity_high_risk(self) -> None:
        decls = [
            AccuracyDeclaration(AccuracyMetricType.F1, 0.95, 0.8),
        ]
        robust = RobustnessReport(
            reproducibility_score=0.95,
            ood_degradation=15.0,
            psi_value=0.2,
            failsafe_verified=True,
        )
        cybers = [
            CybersecurityAssessment(
                vector="data_poisoning",
                controls_in_place=[],
                missing_controls=["input_validation"],
            ),
        ]
        report = Art15ComplianceReport(
            accuracy_declarations=decls,
            robustness_report=robust,
            cybersecurity_assessments=cybers,
        )
        assert report.overall_compliant is False

    def test_no_robustness_report_not_compliant(self) -> None:
        decls = [
            AccuracyDeclaration(AccuracyMetricType.F1, 0.95, 0.8),
        ]
        report = Art15ComplianceReport(
            accuracy_declarations=decls,
        )
        assert report.overall_compliant is False

    def test_empty_declarations_allowed(self) -> None:
        robust = RobustnessReport(
            reproducibility_score=0.95,
            ood_degradation=15.0,
            psi_value=0.2,
            failsafe_verified=True,
        )
        cybers = [
            CybersecurityAssessment(
                vector="data_poisoning",
                controls_in_place=["all"],
                missing_controls=[],
            ),
        ]
        report = Art15ComplianceReport(
            robustness_report=robust,
            cybersecurity_assessments=cybers,
        )
        assert report.overall_compliant is True

    def test_full_integration_scenario(self) -> None:
        mgr = AccuracyManager()
        mgr.declare_accuracy(AccuracyMetricType.F1, 0.95, 0.8)
        mgr.declare_accuracy(AccuracyMetricType.AUC_ROC, 0.92, 0.7)

        robust_mgr = RobustnessManager()
        robust_mgr.test_reproducibility(0.96)
        robust_mgr.test_ood_robustness(12.0)
        robust_mgr.test_temporal_stability(0.15)
        robust_mgr.test_failsafe_behavior(True)

        cyber_mgr = CybersecurityManager()
        cyber_mgr.assess_vector("data_poisoning", ["input_validation", "anomaly_detection"])
        cyber_mgr.assess_vector("model_poisoning", ["secure_aggregation"])
        cyber_mgr.assess_vector("adversarial_examples", ["adversarial_training"])
        cyber_mgr.assess_vector("confidentiality", ["differential_privacy"])
        cyber_mgr.assess_vector("model_flaws", ["penetration_testing"])

        detector = FeedbackLoopDetector()
        feedback = detector.check_feedback_contamination(score=0.2)

        report = Art15ComplianceReport(
            accuracy_declarations=mgr.validate_all(),
            robustness_report=robust_mgr.run_all(),
            cybersecurity_assessments=cyber_mgr.assess_all(),
            feedback_loop_report=feedback,
        )
        assert report.overall_compliant is True


class TestEdgeCases:
    def test_accuracy_declaration_mse_value_above_threshold_passes(self) -> None:
        d = AccuracyDeclaration(
            metric=AccuracyMetricType.MSE,
            value=0.15,
            threshold=0.1,
        )
        assert d.passed is True

    def test_robustness_report_all_zeros_not_robust(self) -> None:
        r = RobustnessReport(
            reproducibility_score=0.0,
            ood_degradation=0.0,
            psi_value=0.0,
            failsafe_verified=False,
        )
        assert r.overall_robust is False

    def test_cybersecurity_assessment_risk_score_one(self) -> None:
        a = CybersecurityAssessment(
            vector="model_flaws",
            controls_in_place=[],
            missing_controls=[],
        )
        assert a.risk_score == 1.0

    def test_feedback_loop_exact_threshold_no_contamination(self) -> None:
        detector = FeedbackLoopDetector()
        report = detector.check_feedback_contamination(score=0.3)
        assert report.contamination_detected is False

    def test_art15_no_cybersecurity_not_compliant(self) -> None:
        decls = [
            AccuracyDeclaration(AccuracyMetricType.F1, 0.95, 0.8),
        ]
        robust = RobustnessReport(
            reproducibility_score=0.95,
            ood_degradation=15.0,
            psi_value=0.2,
            failsafe_verified=True,
        )
        report = Art15ComplianceReport(
            accuracy_declarations=decls,
            robustness_report=robust,
        )
        assert report.overall_compliant is False
