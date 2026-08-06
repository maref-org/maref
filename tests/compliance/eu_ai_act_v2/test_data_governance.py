"""Tests for EU AI Act data governance module (Art.10)."""

from __future__ import annotations

from maref.compliance.eu_ai_act_v2.data_governance import (
    BiasDetectionReport,
    DataGovernanceManager,
    DatasetGovernanceRecord,
    DatasetQualityMetrics,
    SpecialCategoryAssessment,
)


class TestDatasetGovernanceRecord:
    def test_construct_with_all_fields(self) -> None:
        record = DatasetGovernanceRecord(
            dataset_id="abc123",
            name="Training Data v1",
            collection_purpose="Model training",
            data_origin="Web scraping",
            original_collection_purpose="Research",
            preparation_operations=["cleaning", "labeling"],
            assumptions=["data is representative"],
            gaps=["missing edge cases"],
        )
        assert record.dataset_id == "abc123"
        assert record.name == "Training Data v1"
        assert record.collection_purpose == "Model training"
        assert record.data_origin == "Web scraping"
        assert record.original_collection_purpose == "Research"
        assert record.preparation_operations == ["cleaning", "labeling"]
        assert record.assumptions == ["data is representative"]
        assert record.gaps == ["missing edge cases"]

    def test_default_fields(self) -> None:
        record = DatasetGovernanceRecord(
            dataset_id="default-test",
            name="Test",
            collection_purpose="Test",
            data_origin="Test",
        )
        assert record.original_collection_purpose == ""
        assert record.preparation_operations == []
        assert record.assumptions == []
        assert record.bias_assessment is None
        assert record.quality_metrics is None
        assert record.gaps == []
        assert record.created_at != ""

    def test_auto_generated_dataset_id_via_manager(self) -> None:
        manager = DataGovernanceManager()
        record = manager.register_dataset(
            name="Auto-ID Test",
            collection_purpose="Validation",
            data_origin="Synthetic",
        )
        assert isinstance(record.dataset_id, str)
        assert len(record.dataset_id) == 8

    def test_unique_ids(self) -> None:
        manager = DataGovernanceManager()
        ids = set()
        for i in range(50):
            record = manager.register_dataset(
                name=f"Dataset {i}",
                collection_purpose="Testing",
                data_origin="Simulated",
            )
            ids.add(record.dataset_id)
        assert len(ids) == 50


class TestDatasetQualityMetrics:
    def test_default_values(self) -> None:
        metrics = DatasetQualityMetrics()
        assert metrics.relevance_score == 0.0
        assert metrics.representativeness_score == 0.0
        assert metrics.completeness_score == 0.0
        assert metrics.error_rate == 0.0
        assert not metrics.is_relevant
        assert not metrics.is_representative
        assert not metrics.is_complete
        assert metrics.is_free_of_errors

    def test_custom_values(self) -> None:
        metrics = DatasetQualityMetrics(
            relevance_score=0.95,
            representativeness_score=0.88,
            completeness_score=0.75,
            error_rate=0.02,
        )
        assert metrics.relevance_score == 0.95
        assert metrics.representativeness_score == 0.88
        assert metrics.completeness_score == 0.75
        assert metrics.error_rate == 0.02
        assert metrics.is_relevant
        assert metrics.is_representative
        assert not metrics.is_complete
        assert metrics.is_free_of_errors

    def test_passed_all_true(self) -> None:
        metrics = DatasetQualityMetrics(
            relevance_score=0.9,
            representativeness_score=0.8,
            completeness_score=0.9,
            error_rate=0.01,
        )
        assert metrics.passed

    def test_passed_any_false(self) -> None:
        cases = [
            DatasetQualityMetrics(
                relevance_score=0.5, representativeness_score=0.8, completeness_score=0.9,
                error_rate=0.01,
            ),
            DatasetQualityMetrics(
                relevance_score=0.9, representativeness_score=0.5, completeness_score=0.9,
                error_rate=0.01,
            ),
            DatasetQualityMetrics(
                relevance_score=0.9, representativeness_score=0.8, completeness_score=0.5,
                error_rate=0.01,
            ),
            DatasetQualityMetrics(
                relevance_score=0.9, representativeness_score=0.8, completeness_score=0.9,
                error_rate=0.1,
            ),
        ]
        for metrics in cases:
            assert not metrics.passed

    def test_passed_all_false_default(self) -> None:
        metrics = DatasetQualityMetrics()
        assert not metrics.passed


class TestBiasDetectionReport:
    def test_risk_low_no_gaps(self) -> None:
        report = BiasDetectionReport(
            overall_risk="low",
            parity_gaps=[],
            demographic_breakdown={},
        )
        assert report.overall_risk == "low"

    def test_risk_medium_when_gap_above_01(self) -> None:
        report = BiasDetectionReport(
            overall_risk="",
            parity_gaps=[
                {"group": "gender", "gap": 0.15},
            ],
            demographic_breakdown={},
        )
        assert report.overall_risk == "medium"

    def test_risk_high_when_gap_above_02(self) -> None:
        report = BiasDetectionReport(
            overall_risk="",
            parity_gaps=[
                {"group": "gender", "gap": 0.25},
            ],
            demographic_breakdown={},
        )
        assert report.overall_risk == "high"

    def test_default_fields(self) -> None:
        report = BiasDetectionReport(overall_risk="")
        assert report.parity_gaps == []
        assert report.demographic_breakdown == {}
        assert report.intersectional_analysis == []
        assert report.mitigation_measures == []
        assert report.overall_risk == "low"


class TestSpecialCategoryAssessment:
    def test_all_conditions_true_is_compliant(self) -> None:
        assessment = SpecialCategoryAssessment(
            necessity_justified=True,
            cannot_use_alternative=True,
            reuse_limited=True,
            privacy_preserving=True,
            access_controlled=True,
            no_transfer=True,
            deletion_scheduled=True,
            records_kept=True,
        )
        assert assessment.compliant

    def test_any_condition_false_not_compliant(self) -> None:
        fields = [
            "necessity_justified",
            "cannot_use_alternative",
            "reuse_limited",
            "privacy_preserving",
            "access_controlled",
            "no_transfer",
            "deletion_scheduled",
            "records_kept",
        ]
        for field in fields:
            kwargs: dict[str, bool] = dict.fromkeys(fields, True)  # type: ignore[arg-type]
            kwargs[field] = False
            assessment = SpecialCategoryAssessment(**kwargs)
            assert not assessment.compliant, (
                f"Expected not compliant when {field}=False"
            )

    def test_all_false_default(self) -> None:
        assessment = SpecialCategoryAssessment()
        assert not assessment.necessity_justified
        assert not assessment.cannot_use_alternative
        assert not assessment.reuse_limited
        assert not assessment.privacy_preserving
        assert not assessment.access_controlled
        assert not assessment.no_transfer
        assert not assessment.deletion_scheduled
        assert not assessment.records_kept
        assert not assessment.compliant


class TestDataGovernanceManager:
    def test_instantiate_standalone(self) -> None:
        manager = DataGovernanceManager()
        assert isinstance(manager, DataGovernanceManager)

    def test_register_dataset_returns_record(self) -> None:
        manager = DataGovernanceManager()
        record = manager.register_dataset(
            name="Test Dataset",
            collection_purpose="Training",
            data_origin="Web",
        )
        assert isinstance(record, DatasetGovernanceRecord)
        assert record.name == "Test Dataset"
        assert record.collection_purpose == "Training"
        assert record.data_origin == "Web"
        assert record.dataset_id != ""

    def test_register_dataset_adds_to_internal_store(self) -> None:
        manager = DataGovernanceManager()
        record = manager.register_dataset(
            name="Store Check",
            collection_purpose="Validation",
            data_origin="Synthetic",
        )
        datasets = manager.get_all_datasets()
        assert record.dataset_id in [d.dataset_id for d in datasets]

    def test_assess_quality_returns_metrics(self) -> None:
        manager = DataGovernanceManager()
        record = manager.register_dataset(
            name="Quality Test",
            collection_purpose="Training",
            data_origin="Manual",
        )
        metrics = DatasetQualityMetrics(
            relevance_score=0.9,
            representativeness_score=0.85,
            completeness_score=0.95,
            error_rate=0.01,
        )
        result = manager.assess_quality(record.dataset_id, metrics)
        assert result.relevance_score == 0.9
        assert result.passed
        assert record.quality_metrics is not None
        assert record.quality_metrics.passed

    def test_assess_quality_updates_dataset_record(self) -> None:
        manager = DataGovernanceManager()
        record = manager.register_dataset(
            name="Quality Update",
            collection_purpose="Training",
            data_origin="Manual",
        )
        metrics = DatasetQualityMetrics(
            relevance_score=0.7,
            representativeness_score=0.6,
            completeness_score=0.5,
            error_rate=0.1,
        )
        manager.assess_quality(record.dataset_id, metrics)
        assert record.quality_metrics is not None
        assert not record.quality_metrics.passed
        assert record.quality_metrics.relevance_score == 0.7

    def test_assess_quality_missing_dataset_raises(self) -> None:
        manager = DataGovernanceManager()
        metrics = DatasetQualityMetrics()
        try:
            manager.assess_quality("nonexistent", metrics)
            raise AssertionError("Expected KeyError")
        except KeyError:
            pass

    def test_run_bias_detection_returns_report(self) -> None:
        manager = DataGovernanceManager()
        record = manager.register_dataset(
            name="Bias Test",
            collection_purpose="Training",
            data_origin="Survey",
        )
        report = manager.run_bias_detection(
            dataset_id=record.dataset_id,
            parity_gaps=[
                {"group": "gender", "gap": 0.05},
            ],
            demographic_data={
                "gender": {"male": 0.5, "female": 0.5},
            },
        )
        assert isinstance(report, BiasDetectionReport)
        assert report.overall_risk in ("low", "medium", "high")
        assert len(report.parity_gaps) == 1
        assert len(report.demographic_breakdown) == 1

    def test_run_bias_detection_computes_overall_risk(self) -> None:
        manager = DataGovernanceManager()
        record = manager.register_dataset(
            name="Bias Risk Compute",
            collection_purpose="Training",
            data_origin="Survey",
        )

        low = manager.run_bias_detection(
            dataset_id=record.dataset_id,
            parity_gaps=[{"group": "age", "gap": 0.05}],
            demographic_data={},
        )
        assert low.overall_risk == "low"

        medium = manager.run_bias_detection(
            dataset_id=record.dataset_id,
            parity_gaps=[{"group": "age", "gap": 0.15}],
            demographic_data={},
        )
        assert medium.overall_risk == "medium"

        high = manager.run_bias_detection(
            dataset_id=record.dataset_id,
            parity_gaps=[{"group": "age", "gap": 0.25}],
            demographic_data={},
        )
        assert high.overall_risk == "high"

    def test_run_bias_detection_attaches_to_dataset(self) -> None:
        manager = DataGovernanceManager()
        record = manager.register_dataset(
            name="Bias Attach",
            collection_purpose="Training",
            data_origin="Sensor",
        )
        manager.run_bias_detection(
            dataset_id=record.dataset_id,
            parity_gaps=[{"group": "gender", "gap": 0.15}],
            demographic_data={},
        )
        datasets = manager.get_all_datasets()
        target = next(d for d in datasets if d.dataset_id == record.dataset_id)
        assert target.bias_assessment is not None
        assert target.bias_assessment.overall_risk == "medium"

    def test_run_bias_detection_missing_dataset_raises(self) -> None:
        manager = DataGovernanceManager()
        try:
            manager.run_bias_detection(
                dataset_id="nonexistent",
                parity_gaps=[],
                demographic_data={},
            )
            raise AssertionError("Expected KeyError")
        except KeyError:
            pass

    def test_assess_special_category_all_true(self) -> None:
        manager = DataGovernanceManager()
        assessment = manager.assess_special_category({
            "necessity_justified": True,
            "cannot_use_alternative": True,
            "reuse_limited": True,
            "privacy_preserving": True,
            "access_controlled": True,
            "no_transfer": True,
            "deletion_scheduled": True,
            "records_kept": True,
        })
        assert assessment.compliant

    def test_assess_special_category_partial(self) -> None:
        manager = DataGovernanceManager()
        assessment = manager.assess_special_category({
            "necessity_justified": True,
            "cannot_use_alternative": False,
            "reuse_limited": True,
            "privacy_preserving": True,
            "access_controlled": True,
            "no_transfer": True,
            "deletion_scheduled": True,
            "records_kept": True,
        })
        assert not assessment.compliant
        assert assessment.necessity_justified
        assert not assessment.cannot_use_alternative

    def test_assess_special_category_empty_conditions(self) -> None:
        manager = DataGovernanceManager()
        assessment = manager.assess_special_category({})
        assert not assessment.compliant
        assert not assessment.necessity_justified

    def test_get_all_datasets_empty(self) -> None:
        manager = DataGovernanceManager()
        assert manager.get_all_datasets() == []

    def test_get_all_datasets_returns_all(self) -> None:
        manager = DataGovernanceManager()
        manager.register_dataset(name="A", collection_purpose="P1", data_origin="O1")
        manager.register_dataset(name="B", collection_purpose="P2", data_origin="O2")
        manager.register_dataset(name="C", collection_purpose="P3", data_origin="O3")
        datasets = manager.get_all_datasets()
        assert len(datasets) == 3
        names = [d.name for d in datasets]
        assert "A" in names
        assert "B" in names
        assert "C" in names

    def test_governance_summary_empty(self) -> None:
        manager = DataGovernanceManager()
        summary = manager.get_governance_summary()
        assert summary["dataset_count"] == 0
        assert summary["bias_risk_level"] == "none"
        assert not summary["has_special_category_assessment"]

    def test_governance_summary_with_datasets(self) -> None:
        manager = DataGovernanceManager()
        manager.register_dataset(
            name="Dataset 1",
            collection_purpose="Training",
            data_origin="Web",
        )
        summary = manager.get_governance_summary()
        assert summary["dataset_count"] == 1

    def test_governance_summary_bias_risk_level(self) -> None:
        manager = DataGovernanceManager()
        record = manager.register_dataset(
            name="Biased Dataset",
            collection_purpose="Training",
            data_origin="Sensor",
        )
        manager.run_bias_detection(
            dataset_id=record.dataset_id,
            parity_gaps=[{"group": "age", "gap": 0.25}],
            demographic_data={},
        )
        summary = manager.get_governance_summary()
        assert summary["bias_risk_level"] == "high"

    def test_governance_summary_bias_risk_low(self) -> None:
        manager = DataGovernanceManager()
        record = manager.register_dataset(
            name="Fair Dataset",
            collection_purpose="Training",
            data_origin="Survey",
        )
        manager.run_bias_detection(
            dataset_id=record.dataset_id,
            parity_gaps=[{"group": "age", "gap": 0.03}],
            demographic_data={},
        )
        summary = manager.get_governance_summary()
        assert summary["bias_risk_level"] == "low"

    def test_governance_summary_bias_risk_medium(self) -> None:
        manager = DataGovernanceManager()
        record = manager.register_dataset(
            name="Medium Bias",
            collection_purpose="Training",
            data_origin="Survey",
        )
        manager.run_bias_detection(
            dataset_id=record.dataset_id,
            parity_gaps=[{"group": "age", "gap": 0.15}],
            demographic_data={},
        )
        summary = manager.get_governance_summary()
        assert summary["bias_risk_level"] == "medium"

    def test_governance_summary_special_category_with_assessment(self) -> None:
        manager = DataGovernanceManager()
        manager.assess_special_category({
            "necessity_justified": True,
            "cannot_use_alternative": True,
            "reuse_limited": True,
            "privacy_preserving": True,
            "access_controlled": True,
            "no_transfer": True,
            "deletion_scheduled": True,
            "records_kept": True,
        })
        summary = manager.get_governance_summary()
        assert summary["has_special_category_assessment"]
        assert summary["special_category_compliant"]

    def test_governance_summary_special_category_not_compliant(self) -> None:
        manager = DataGovernanceManager()
        manager.assess_special_category({
            "necessity_justified": True,
            "cannot_use_alternative": False,
            "reuse_limited": False,
            "privacy_preserving": False,
            "access_controlled": False,
            "no_transfer": False,
            "deletion_scheduled": False,
            "records_kept": False,
        })
        summary = manager.get_governance_summary()
        assert summary["has_special_category_assessment"]
        assert not summary["special_category_compliant"]

    def test_get_governance_summary_returns_dict(self) -> None:
        manager = DataGovernanceManager()
        summary = manager.get_governance_summary()
        assert isinstance(summary, dict)


class TestDataGovernanceEdgeCases:
    def test_no_bias_assessment_returns_none(self) -> None:
        manager = DataGovernanceManager()
        record = manager.register_dataset(
            name="No Bias",
            collection_purpose="Training",
            data_origin="Web",
        )
        assert record.bias_assessment is None

    def test_empty_datasets_list_empty_summary(self) -> None:
        manager = DataGovernanceManager()
        assert manager.get_all_datasets() == []
        summary = manager.get_governance_summary()
        assert summary["dataset_count"] == 0

    def test_multiple_datasets_different_bias_levels(self) -> None:
        manager = DataGovernanceManager()

        r1 = manager.register_dataset(name="D1", collection_purpose="T", data_origin="S")
        manager.run_bias_detection(r1.dataset_id, [{"group": "a", "gap": 0.25}], {})

        r2 = manager.register_dataset(name="D2", collection_purpose="T", data_origin="S")
        manager.run_bias_detection(r2.dataset_id, [{"group": "a", "gap": 0.15}], {})

        r3 = manager.register_dataset(name="D3", collection_purpose="T", data_origin="S")
        manager.run_bias_detection(r3.dataset_id, [{"group": "a", "gap": 0.05}], {})

        summary = manager.get_governance_summary()
        assert summary["dataset_count"] == 3
        assert summary["bias_risk_level"] == "high"

    def test_assess_quality_only_updates_target(self) -> None:
        manager = DataGovernanceManager()
        r1 = manager.register_dataset(name="D1", collection_purpose="T", data_origin="O")
        r2 = manager.register_dataset(name="D2", collection_purpose="T", data_origin="O")

        m1 = DatasetQualityMetrics(relevance_score=0.9, representativeness_score=0.9, completeness_score=0.9, error_rate=0.01)
        m2 = DatasetQualityMetrics(relevance_score=0.3, representativeness_score=0.3, completeness_score=0.3, error_rate=0.3)

        manager.assess_quality(r1.dataset_id, m1)
        manager.assess_quality(r2.dataset_id, m2)

        datasets = {d.dataset_id: d for d in manager.get_all_datasets()}
        assert datasets[r1.dataset_id].quality_metrics is not None
        assert datasets[r1.dataset_id].quality_metrics.passed
        assert datasets[r2.dataset_id].quality_metrics is not None
        assert not datasets[r2.dataset_id].quality_metrics.passed
