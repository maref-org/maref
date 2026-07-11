"""EU AI Act Data Governance — Article 10.

Implements Art.10 requirements for dataset governance, quality metrics,
bias detection, and special category data processing conditions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass
class DatasetGovernanceRecord:
    """Art.10(2) a-h: dataset metadata with provenance, bias assessment, gaps."""

    dataset_id: str
    name: str
    collection_purpose: str
    data_origin: str
    original_collection_purpose: str = ""
    preparation_operations: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    bias_assessment: BiasDetectionReport | None = None
    quality_metrics: DatasetQualityMetrics | None = None
    gaps: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class DatasetQualityMetrics:
    """Art.10(3): quality dimensions for dataset evaluation.

    Boolean flags are auto-computed from numerical scores during __post_init__:
    - is_relevant: relevance_score >= 0.7
    - is_representative: representativeness_score >= 0.7
    - is_complete: completeness_score >= 0.8
    - is_free_of_errors: error_rate <= 0.05
    """

    relevance_score: float = 0.0
    representativeness_score: float = 0.0
    completeness_score: float = 0.0
    error_rate: float = 0.0
    is_relevant: bool = False
    is_representative: bool = False
    is_complete: bool = False
    is_free_of_errors: bool = False

    def __post_init__(self) -> None:
        self.is_relevant = self.relevance_score >= 0.7
        self.is_representative = self.representativeness_score >= 0.7
        self.is_complete = self.completeness_score >= 0.8
        self.is_free_of_errors = self.error_rate <= 0.05

    @property
    def passed(self) -> bool:
        """All four quality dimensions must pass."""
        return (
            self.is_relevant
            and self.is_representative
            and self.is_complete
            and self.is_free_of_errors
        )


@dataclass
class BiasDetectionReport:
    """Art.10(2)(f)-(g): bias examination results.

    overall_risk is computed from parity_gaps:
    - "high" if any gap > 0.2
    - "medium" if any gap > 0.1
    - "low" otherwise
    """

    overall_risk: str
    parity_gaps: list[dict[str, Any]] = field(default_factory=list)
    demographic_breakdown: dict[str, dict[str, float]] = field(default_factory=dict)
    intersectional_analysis: list[dict[str, Any]] = field(default_factory=list)
    mitigation_measures: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        gaps = [g.get("gap", 0.0) for g in self.parity_gaps]
        if any(g > 0.2 for g in gaps):
            self.overall_risk = "high"
        elif any(g > 0.1 for g in gaps):
            self.overall_risk = "medium"
        else:
            self.overall_risk = "low"


@dataclass
class SpecialCategoryAssessment:
    """Art.10(5): strict conditions for special category data processing.

    compliant is True only when ALL 8 conditions are satisfied.
    """

    necessity_justified: bool = False
    cannot_use_alternative: bool = False
    reuse_limited: bool = False
    privacy_preserving: bool = False
    access_controlled: bool = False
    no_transfer: bool = False
    deletion_scheduled: bool = False
    records_kept: bool = False
    compliant: bool = False

    def __post_init__(self) -> None:
        self.compliant = (
            self.necessity_justified
            and self.cannot_use_alternative
            and self.reuse_limited
            and self.privacy_preserving
            and self.access_controlled
            and self.no_transfer
            and self.deletion_scheduled
            and self.records_kept
        )


class DataGovernanceManager:
    """Orchestrates all Art.10 data governance operations."""

    def __init__(self) -> None:
        self._datasets: dict[str, DatasetGovernanceRecord] = {}
        self._special_category_assessment: SpecialCategoryAssessment | None = None

    def register_dataset(
        self,
        name: str,
        collection_purpose: str,
        data_origin: str,
    ) -> DatasetGovernanceRecord:
        """Register a new dataset with auto-generated ID.

        Args:
            name: Human-readable dataset name.
            collection_purpose: Purpose for which data was collected.
            data_origin: Source/origin of the data.

        Returns:
            The newly created DatasetGovernanceRecord.
        """
        record = DatasetGovernanceRecord(
            dataset_id=uuid4().hex[:8],
            name=name,
            collection_purpose=collection_purpose,
            data_origin=data_origin,
        )
        self._datasets[record.dataset_id] = record
        return record

    def assess_quality(
        self,
        dataset_id: str,
        metrics: DatasetQualityMetrics,
    ) -> DatasetQualityMetrics:
        """Assess quality of a registered dataset.

        Args:
            dataset_id: ID of the dataset to assess.
            metrics: Quality metrics to record.

        Returns:
            The recorded quality metrics.

        Raises:
            KeyError: If no dataset with the given ID exists.
        """
        if dataset_id not in self._datasets:
            raise KeyError(f"Dataset not found: {dataset_id}")
        self._datasets[dataset_id].quality_metrics = metrics
        return metrics

    def run_bias_detection(
        self,
        dataset_id: str,
        parity_gaps: list[dict[str, Any]],
        demographic_data: dict[str, dict[str, float]],
    ) -> BiasDetectionReport:
        """Run bias detection on a registered dataset.

        Computes overall risk level from parity gaps and attaches
        the report to the dataset record.

        Args:
            dataset_id: ID of the dataset to examine.
            parity_gaps: List of parity gap measurements.
            demographic_data: Demographic breakdown of the dataset.

        Returns:
            The BiasDetectionReport with computed risk level.

        Raises:
            KeyError: If no dataset with the given ID exists.
        """
        if dataset_id not in self._datasets:
            raise KeyError(f"Dataset not found: {dataset_id}")

        report = BiasDetectionReport(
            overall_risk="low",
            parity_gaps=parity_gaps,
            demographic_breakdown=demographic_data,
        )
        self._datasets[dataset_id].bias_assessment = report
        return report

    def assess_special_category(
        self,
        conditions: dict[str, bool],
    ) -> SpecialCategoryAssessment:
        """Assess compliance with Art.10(5) special category conditions.

        Args:
            conditions: Dict of 8 condition names to boolean values.

        Returns:
            SpecialCategoryAssessment with compliant flag.
        """
        assessment = SpecialCategoryAssessment(
            necessity_justified=conditions.get("necessity_justified", False),
            cannot_use_alternative=conditions.get("cannot_use_alternative", False),
            reuse_limited=conditions.get("reuse_limited", False),
            privacy_preserving=conditions.get("privacy_preserving", False),
            access_controlled=conditions.get("access_controlled", False),
            no_transfer=conditions.get("no_transfer", False),
            deletion_scheduled=conditions.get("deletion_scheduled", False),
            records_kept=conditions.get("records_kept", False),
        )
        self._special_category_assessment = assessment
        return assessment

    def get_governance_summary(self) -> dict[str, Any]:
        """Generate a governance summary across all datasets.

        Returns:
            Dict with dataset count, bias risk level, and special
            category status.
        """
        bias_risk_level: str = "none"
        for ds in self._datasets.values():
            if ds.bias_assessment is not None:
                rl = ds.bias_assessment.overall_risk
                if rl == "high":
                    bias_risk_level = "high"
                elif rl == "medium" and bias_risk_level != "high":
                    bias_risk_level = "medium"
                elif rl == "low" and bias_risk_level not in ("high", "medium"):
                    bias_risk_level = "low"

        has_sca = self._special_category_assessment is not None
        sc_compliant = (
            self._special_category_assessment.compliant
            if self._special_category_assessment is not None
            else False
        )

        quality_passed_count = sum(
            1 for ds in self._datasets.values()
            if ds.quality_metrics is not None and ds.quality_metrics.passed
        )
        total_with_metrics = sum(
            1 for ds in self._datasets.values()
            if ds.quality_metrics is not None
        )

        return {
            "dataset_count": len(self._datasets),
            "bias_risk_level": bias_risk_level,
            "has_special_category_assessment": has_sca,
            "special_category_compliant": sc_compliant,
            "quality_metrics_count": total_with_metrics,
            "quality_passed_count": quality_passed_count,
        }

    def get_all_datasets(self) -> list[DatasetGovernanceRecord]:
        """Return all registered datasets.

        Returns:
            List of all DatasetGovernanceRecord objects.
        """
        return list(self._datasets.values())
