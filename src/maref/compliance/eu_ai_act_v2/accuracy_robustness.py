"""EU AI Act Art.15 — Accuracy, Robustness & Cybersecurity.

Art.15(1)-(3): Accuracy Declarations
Art.15(4):     Robustness Testing
Art.15(5):     Cybersecurity Threat Assessment
Art.15(4) pl:  Feedback Loop Detection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AccuracyMetricType(Enum):
    """Accuracy metric types for Art.15(1)-(3) declarations."""

    FAR = "false_accept_rate"
    FRR = "false_reject_rate"
    EER = "equal_error_rate"
    AUC_ROC = "auc_roc"
    PRECISION = "precision"
    RECALL = "recall"
    F1 = "f1"
    MSE = "mean_squared_error"
    CALIBRATION = "calibration_error"
    PREDICTIVE_PARITY = "predictive_parity"
    DISPARATE_IMPACT = "disparate_impact_ratio"
    PSI = "population_stability_index"


@dataclass
class AccuracyDeclaration:
    """A single accuracy metric declaration (Art.15(1)-(3))."""

    metric: AccuracyMetricType
    value: float
    threshold: float
    passed: bool = False
    demographic_breakdown: dict[str, float] = field(default_factory=dict)
    known_limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Auto-compute passed: value >= threshold means the metric passes."""
        self.passed = self.value >= self.threshold


class AccuracyManager:
    """Manages accuracy metric declarations (Art.15(1)-(3))."""

    def __init__(self) -> None:
        self._declarations: list[AccuracyDeclaration] = []

    def declare_accuracy(
        self,
        metric: AccuracyMetricType,
        value: float,
        threshold: float,
        **kwargs: Any,
    ) -> AccuracyDeclaration:
        """Create and store an accuracy declaration."""
        declaration = AccuracyDeclaration(
            metric=metric,
            value=value,
            threshold=threshold,
            **kwargs,
        )
        self._declarations.append(declaration)
        return declaration

    def validate_all(self) -> list[AccuracyDeclaration]:
        """Return all declarations with computed passed values."""
        return list(self._declarations)

    def get_declarations(self) -> list[AccuracyDeclaration]:
        """Return all stored declarations."""
        return list(self._declarations)


@dataclass
class RobustnessReport:
    """Report of robustness testing results (Art.15(4))."""

    reproducibility_score: float
    ood_degradation: float
    psi_value: float
    failsafe_verified: bool
    overall_robust: bool = False

    def __post_init__(self) -> None:
        """Auto-compute overall_robust."""
        self.overall_robust = (
            self.reproducibility_score >= 0.95
            and self.ood_degradation <= 15.0
            and self.psi_value <= 0.2
            and self.failsafe_verified
        )


class RobustnessManager:
    """Manages robustness testing (Art.15(4))."""

    def __init__(self) -> None:
        self._reproducibility_score: float = 0.0
        self._ood_degradation: float = 0.0
        self._psi_value: float = 0.0
        self._failsafe_verified: bool = False

    def test_reproducibility(self, score: float) -> float:
        """Accept and store a reproducibility score.

        Args:
            score: Reproducibility score (0.0 - 1.0).

        Returns:
            The same score.
        """
        self._reproducibility_score = score
        return score

    def test_ood_robustness(self, degradation: float) -> float:
        """Accept and store an OOD degradation value.

        Args:
            degradation: OOD degradation in percentage points.

        Returns:
            The same degradation value.
        """
        self._ood_degradation = degradation
        return degradation

    def test_temporal_stability(self, psi_value: float) -> float:
        """Accept and store a PSI value.

        Args:
            psi_value: Population Stability Index value.

        Returns:
            The same PSI value.
        """
        self._psi_value = psi_value
        return psi_value

    def test_failsafe_behavior(self, verified: bool) -> bool:
        """Accept and store a failsafe verification flag.

        Args:
            verified: Whether failsafe behaviour was verified.

        Returns:
            The same verification flag.
        """
        self._failsafe_verified = verified
        return verified

    def run_all(self) -> RobustnessReport:
        """Run all tests and return a complete RobustnessReport."""
        return RobustnessReport(
            reproducibility_score=self._reproducibility_score,
            ood_degradation=self._ood_degradation,
            psi_value=self._psi_value,
            failsafe_verified=self._failsafe_verified,
        )


_DEFAULT_MISSING_CONTROLS: dict[str, list[str]] = {
    "data_poisoning": [
        "training_data_sanitization",
        "input_validation",
        "anomaly_detection",
    ],
    "model_poisoning": [
        "secure_aggregation",
        "gradient_sanitization",
        "model_signed_executables",
    ],
    "adversarial_examples": [
        "adversarial_training",
        "input_transformation",
        "detection_network",
    ],
    "confidentiality": [
        "differential_privacy",
        "encryption_at_rest",
        "access_control",
    ],
    "model_flaws": [
        "penetration_testing",
        "code_review",
        "fuzzing",
    ],
}


@dataclass
class CybersecurityAssessment:
    """A cybersecurity threat assessment for a single vector (Art.15(5))."""

    vector: str
    controls_in_place: list[str]
    missing_controls: list[str]
    risk_score: float = 0.0

    def __post_init__(self) -> None:
        """Auto-compute risk_score."""
        total = len(self.controls_in_place) + len(self.missing_controls)
        if total == 0:
            self.risk_score = 1.0
        else:
            self.risk_score = 1.0 - (
                len(self.controls_in_place) / total
            )


class CybersecurityManager:
    """Manages cybersecurity threat assessments (Art.15(5))."""

    def __init__(self) -> None:
        self._assessments: dict[str, CybersecurityAssessment] = {}

    def assess_vector(
        self,
        vector: str,
        controls_in_place: list[str],
    ) -> CybersecurityAssessment:
        """Assess a cybersecurity vector with given controls.

        Args:
            vector: The threat vector name.
            controls_in_place: List of controls already in place.

        Returns:
            A CybersecurityAssessment with computed risk_score.
        """
        missing = list(_DEFAULT_MISSING_CONTROLS.get(vector, []))
        for control in controls_in_place:
            if control in missing:
                missing.remove(control)
        assessment = CybersecurityAssessment(
            vector=vector,
            controls_in_place=list(controls_in_place),
            missing_controls=missing,
        )
        self._assessments[vector] = assessment
        return assessment

    def assess_all(self) -> list[CybersecurityAssessment]:
        """Return assessments for all 5 known vectors.

        Vectors not yet assessed will be assessed with empty controls.
        """
        results: list[CybersecurityAssessment] = []
        for vector in _DEFAULT_MISSING_CONTROLS:
            if vector in self._assessments:
                results.append(self._assessments[vector])
            else:
                results.append(self.assess_vector(vector, []))
        return results

    def gap_analysis(self) -> dict[str, list[str]]:
        """Return a dict mapping each vector to its missing controls."""
        result: dict[str, list[str]] = {}
        for assessment in self.assess_all():
            result[assessment.vector] = list(assessment.missing_controls)
        return result


@dataclass
class FeedbackLoopReport:
    """Report of feedback loop contamination detection (Art.15(4) last para)."""

    contamination_detected: bool
    contamination_score: float
    affected_inputs: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class FeedbackLoopDetector:
    """Detects feedback loop contamination (Art.15(4) last paragraph)."""

    def check_feedback_contamination(
        self,
        score: float,
        affected: list[str] | None = None,
    ) -> FeedbackLoopReport:
        """Check for feedback loop contamination.

        Args:
            score: Contamination score (0.0 - 1.0). Scores > 0.3 indicate
                contamination.
            affected: Optional list of affected input identifiers.

        Returns:
            A FeedbackLoopReport with detection results.
        """
        contamination_detected = score > 0.3
        recommendations: list[str] = []
        if contamination_detected:
            recommendations = [
                "Isolate contaminated inputs from training pipeline",
                "Purge affected model versions",
                "Implement input provenance tracking",
                "Add monitoring for feedback loop indicators",
            ]
        return FeedbackLoopReport(
            contamination_detected=contamination_detected,
            contamination_score=score,
            affected_inputs=list(affected) if affected else [],
            recommendations=recommendations,
        )


@dataclass
class Art15ComplianceReport:
    """Aggregate compliance report for EU AI Act Art.15.

    overall_compliant is True iff:
    - All accuracy declarations passed
    - Robustness report is overall_robust
    - No cybersecurity assessment has risk_score > 0.7
    """

    accuracy_declarations: list[AccuracyDeclaration] = field(default_factory=list)
    robustness_report: RobustnessReport | None = None
    cybersecurity_assessments: list[CybersecurityAssessment] = field(default_factory=list)
    feedback_loop_report: FeedbackLoopReport | None = None
    overall_compliant: bool = False

    def __post_init__(self) -> None:
        """Auto-compute overall_compliant."""
        all_accuracy_passed = all(
            d.passed for d in self.accuracy_declarations
        )
        robustness_ok = (
            self.robustness_report is not None
            and self.robustness_report.overall_robust
        )
        cybersecurity_exists = len(self.cybersecurity_assessments) > 0
        no_high_risk_cyber = cybersecurity_exists and not any(
            a.risk_score > 0.7 for a in self.cybersecurity_assessments
        )
        self.overall_compliant = (
            all_accuracy_passed and robustness_ok and no_high_risk_cyber
        )
