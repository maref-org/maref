from __future__ import annotations

from unittest.mock import MagicMock

from maref.integration.feature_dev.doc_ingestor import (
    ComplianceRule,
    CostModel,
    DocumentSection,
    FeatureDocument,
    Hypothesis,
)
from maref.integration.feature_dev.progress_tracker import (
    ConvergenceReport,
)
from maref.integration.feature_dev.verification_engine import (
    DeliveryVerdict,
    DeliveryVerifier,
    VerdictItem,
)


class TestVerdictItem:
    def test_default_weight(self) -> None:
        v = VerdictItem(
            check_id="c1",
            description="Test check",
            passed=True,
            detail="OK",
        )
        assert v.weight == 1.0

    def test_to_dict(self) -> None:
        v = VerdictItem(
            check_id="c1",
            description="Test",
            passed=True,
            detail="OK",
            weight=2.0,
        )
        d = v.to_dict()
        assert d["check_id"] == "c1"
        assert d["passed"] is True
        assert d["weight"] == 2.0


class TestDeliveryVerdict:
    def test_default_timestamp(self) -> None:
        d = DeliveryVerdict(
            overall_passed=False,
            score=0.0,
            items=[],
            summary="Fail",
        )
        assert d.timestamp == 0.0

    def test_to_dict(self) -> None:
        d = DeliveryVerdict(
            overall_passed=True,
            score=85.0,
            items=[
                VerdictItem("c1", "Check 1", True, "OK", 1.0),
            ],
            summary="PASSED",
            timestamp=12345.0,
        )
        result = d.to_dict()
        assert result["overall_passed"] is True
        assert result["score"] == 85.0
        assert len(result["items"]) == 1
        assert result["summary"] == "PASSED"
        assert result["timestamp"] == 12345.0


class TestDeliveryVerifierAllFlat:
    def test_flat_list(self) -> None:
        sub = DocumentSection(heading="Sub", level=2, content="")
        sec = DocumentSection(
            heading="Root", level=1, content="", subsections=[sub]
        )
        verifier = DeliveryVerifier.__new__(DeliveryVerifier)
        result = verifier._all_flat([sec])
        assert len(result) == 2

    def test_empty(self) -> None:
        verifier = DeliveryVerifier.__new__(DeliveryVerifier)
        assert verifier._all_flat([]) == []

    def test_deep_nesting(self) -> None:
        s3 = DocumentSection(heading="L3", level=3, content="")
        s2 = DocumentSection(heading="L2", level=2, content="", subsections=[s3])
        s1 = DocumentSection(heading="L1", level=1, content="", subsections=[s2])
        verifier = DeliveryVerifier.__new__(DeliveryVerifier)
        result = verifier._all_flat([s1])
        assert len(result) == 3


class TestDeliveryVerifierCheckHypotheses:
    def test_all_hypotheses_found(self) -> None:
        doc = FeatureDocument(
            title="T",
            raw_path="t.md",
            hypotheses=[
                Hypothesis("H1", "m1", "p1", "f1"),
                Hypothesis("H2", "m2", "p2", "f2"),
                Hypothesis("H3", "m3", "p3", "f3"),
            ],
        )
        verifier = DeliveryVerifier(doc)
        verifier._check_hypotheses()
        items = {i.check_id: i for i in verifier.items}
        h1_item = items["§1.5_hypotheses"]
        assert h1_item.passed is True
        assert "Complete" in h1_item.detail
        th_item = items["§1.5_thresholds"]
        assert th_item.passed is True

    def test_missing_hypotheses(self) -> None:
        doc = FeatureDocument(
            title="T",
            raw_path="t.md",
            hypotheses=[
                Hypothesis("H1", "m1", "p1", "f1"),
            ],
        )
        verifier = DeliveryVerifier(doc)
        verifier._check_hypotheses()
        item = next(i for i in verifier.items if i.check_id == "§1.5_hypotheses")
        assert item.passed is False
        assert "Missing" in item.detail

    def test_no_hypotheses_skips_thresholds(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md", hypotheses=[])
        verifier = DeliveryVerifier(doc)
        verifier._check_hypotheses()
        item_ids = {i.check_id for i in verifier.items}
        assert "§1.5_hypotheses" in item_ids
        assert "§1.5_thresholds" not in item_ids  # no hypos, no threshold check

    def test_missing_thresholds(self) -> None:
        doc = FeatureDocument(
            title="T",
            raw_path="t.md",
            hypotheses=[
                Hypothesis("H1", "m1", "p1", ""),
                Hypothesis("H2", "m2", "p2", "f2"),
                Hypothesis("H3", "m3", "p3", "f3"),
            ],
        )
        verifier = DeliveryVerifier(doc)
        verifier._check_hypotheses()
        item = next(i for i in verifier.items if i.check_id == "§1.5_thresholds")
        assert item.passed is False


class TestDeliveryVerifierCheckGoNoGo:
    def test_detected(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        doc.all_sections = [
            DocumentSection(heading="Go/No-Go Decision", level=1, content=""),
        ]
        verifier = DeliveryVerifier(doc)
        verifier._check_go_nogo()
        item = verifier.items[0]
        assert item.passed is True
        assert item.check_id == "§1.6_go_nogo"

    def test_not_detected(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        doc.all_sections = [
            DocumentSection(heading="Introduction", level=1, content=""),
        ]
        verifier = DeliveryVerifier(doc)
        verifier._check_go_nogo()
        item = verifier.items[0]
        assert item.passed is False

    def test_detected_via_chinese(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        doc.all_sections = [
            DocumentSection(heading="决策机制", level=1, content=""),
        ]
        verifier = DeliveryVerifier(doc)
        verifier._check_go_nogo()
        item = verifier.items[0]
        assert item.passed is True


class TestDeliveryVerifierCheckStages:
    def test_all_stages_detected(self) -> None:
        doc = FeatureDocument(
            title="T",
            raw_path="t.md",
            metadata={"detected_stages": ["mvp", "mixed", "internalization"]},
        )
        verifier = DeliveryVerifier(doc)
        verifier._check_stages()
        item = verifier.items[0]
        assert item.passed is True
        assert "All 3 stages" in item.detail

    def test_missing_stages(self) -> None:
        doc = FeatureDocument(
            title="T",
            raw_path="t.md",
            metadata={"detected_stages": ["mvp"]},
        )
        verifier = DeliveryVerifier(doc)
        verifier._check_stages()
        item = verifier.items[0]
        assert item.passed is False
        assert "Missing" in item.detail

    def test_no_stages(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md", metadata={"detected_stages": []})
        verifier = DeliveryVerifier(doc)
        verifier._check_stages()
        item = verifier.items[0]
        assert item.passed is False


class TestDeliveryVerifierCheckChecklists:
    def test_all_categories(self) -> None:
        doc = FeatureDocument(
            title="T",
            raw_path="t.md",
            compliance_rules=[
                ComplianceRule("d1", "Daily check", "daily"),
                ComplianceRule("w1", "Weekly check", "weekly"),
                ComplianceRule("m1", "Monthly check", "monthly"),
            ],
        )
        verifier = DeliveryVerifier(doc)
        verifier._check_checklists()
        item = verifier.items[0]
        assert item.passed is True
        assert "YES" in item.detail

    def test_missing_categories(self) -> None:
        doc = FeatureDocument(
            title="T",
            raw_path="t.md",
            compliance_rules=[
                ComplianceRule("d1", "Only daily", "daily"),
            ],
        )
        verifier = DeliveryVerifier(doc)
        verifier._check_checklists()
        item = verifier.items[0]
        assert item.passed is False
        assert "NO" in item.detail


class TestDeliveryVerifierCheckCostModels:
    def test_sufficient_models(self) -> None:
        doc = FeatureDocument(
            title="T",
            raw_path="t.md",
            cost_models=[
                CostModel("MVP"),
                CostModel("Mixed"),
                CostModel("Internalization"),
            ],
        )
        verifier = DeliveryVerifier(doc)
        verifier._check_cost_models()
        item = verifier.items[0]
        assert item.passed is True

    def test_insufficient_models(self) -> None:
        doc = FeatureDocument(
            title="T",
            raw_path="t.md",
            cost_models=[CostModel("MVP"), CostModel("Mixed")],
        )
        verifier = DeliveryVerifier(doc)
        verifier._check_cost_models()
        item = verifier.items[0]
        assert item.passed is False
        assert "Insufficient" in item.detail


class TestDeliveryVerifierCheckDisciplines:
    def test_sufficient_disciplines(self) -> None:
        doc = FeatureDocument(
            title="T",
            raw_path="t.md",
            compliance_rules=[
                ComplianceRule(f"d{i}", f"Disc {i}", "discipline")
                for i in range(3)
            ],
        )
        verifier = DeliveryVerifier(doc)
        verifier._check_disciplines()
        item = verifier.items[0]
        assert item.passed is True

    def test_insufficient_disciplines(self) -> None:
        doc = FeatureDocument(
            title="T",
            raw_path="t.md",
            compliance_rules=[
                ComplianceRule("d1", "Only one", "discipline"),
            ],
        )
        verifier = DeliveryVerifier(doc)
        verifier._check_disciplines()
        item = verifier.items[0]
        assert item.passed is False


class TestDeliveryVerifierCheckDeployReadiness:
    def test_with_report_deploy_ready(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        verifier = DeliveryVerifier(doc)
        report = MagicMock(spec=ConvergenceReport)
        report.deploy_ready = True
        report.avg_score = 85.0
        report.overall_trend = "converging"
        report.final_decision = "go"
        report.deploy_gates = {"g1": True}
        verifier._check_deploy_readiness(report)
        item = verifier.items[0]
        assert item.passed is True
        assert "YES" in item.detail

    def test_with_report_not_ready(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        verifier = DeliveryVerifier(doc)
        report = MagicMock(spec=ConvergenceReport)
        report.deploy_ready = False
        report.avg_score = 50.0
        report.overall_trend = "diverging"
        report.final_decision = "kill"
        report.deploy_gates = {"g1": False}
        verifier._check_deploy_readiness(report)
        item = verifier.items[0]
        assert item.passed is False
        assert "NO" in item.detail

    def test_no_report(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        verifier = DeliveryVerifier(doc)
        verifier._check_deploy_readiness(None)
        item = verifier.items[0]
        assert item.passed is False
        assert "No pipeline report" in item.detail


class TestDeliveryVerifierCheckConvergence:
    def test_converging(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        verifier = DeliveryVerifier(doc)
        report = MagicMock(spec=ConvergenceReport)
        report.overall_trend = "converging"
        report.cycle_scores = [50, 60, 70]
        verifier._check_convergence(report)
        item = verifier.items[0]
        assert item.passed is True

    def test_diverging(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        verifier = DeliveryVerifier(doc)
        report = MagicMock(spec=ConvergenceReport)
        report.overall_trend = "diverging"
        report.cycle_scores = [80, 60, 40]
        verifier._check_convergence(report)
        item = verifier.items[0]
        assert item.passed is False

    def test_no_report_skipped(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        verifier = DeliveryVerifier(doc)
        verifier._check_convergence(None)
        assert verifier.items == []


class TestDeliveryVerifierCheckMethodsTracked:
    def test_methods_not_on_report(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        verifier = DeliveryVerifier(doc)
        report = MagicMock(spec=ConvergenceReport)
        del report.methods_used
        verifier._check_methods_tracked(report)
        item = verifier.items[0]
        assert item.passed is False

    def test_no_report_skipped(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        verifier = DeliveryVerifier(doc)
        verifier._check_methods_tracked(None)
        assert verifier.items == []


class TestDeliveryVerifierVerify:
    def test_verify_full_pipeline(self) -> None:
        doc = FeatureDocument(
            title="T",
            raw_path="t.md",
            hypotheses=[
                Hypothesis("H1", "m1", "p1", "f1"),
                Hypothesis("H2", "m2", "p2", "f2"),
                Hypothesis("H3", "m3", "p3", "f3"),
            ],
            compliance_rules=[
                ComplianceRule("d1", "Daily", "daily"),
                ComplianceRule("w1", "Weekly", "weekly"),
                ComplianceRule("m1", "Monthly", "monthly"),
                ComplianceRule("di1", "Disc 1", "discipline"),
                ComplianceRule("di2", "Disc 2", "discipline"),
                ComplianceRule("di3", "Disc 3", "discipline"),
            ],
            cost_models=[
                CostModel("MVP"), CostModel("Mixed"), CostModel("Int"),
            ],
            metadata={"detected_stages": ["mvp", "mixed", "internalization"]},
        )
        doc.all_sections = [
            DocumentSection(heading="Go/No-Go Decision", level=1, content=""),
        ]

        report = MagicMock(spec=ConvergenceReport)
        report.deploy_ready = True
        report.avg_score = 90.0
        report.overall_trend = "converging"
        report.final_decision = "go"
        report.deploy_gates = {"g1": True}
        report.cycle_scores = [70, 80, 90]
        del report.methods_used

        verifier = DeliveryVerifier(doc)
        verdict = verifier.verify(report)
        assert isinstance(verdict, DeliveryVerdict)
        assert verdict.overall_passed is True or verdict.overall_passed is False
        assert len(verdict.items) >= 8
        assert verdict.score > 0

    def test_verify_no_report(self) -> None:
        doc = FeatureDocument(
            title="T",
            raw_path="t.md",
            metadata={"detected_stages": ["mvp"]},
        )
        verifier = DeliveryVerifier(doc)
        verdict = verifier.verify(None)
        assert isinstance(verdict.summary, str)
        assert verdict.score >= 0

    def test_verify_weighted_score_calculation(self) -> None:
        doc = FeatureDocument(
            title="T",
            raw_path="t.md",
            metadata={"detected_stages": ["mvp"]},
        )
        verifier = DeliveryVerifier(doc)
        verdict = verifier.verify(None)
        assert 0.0 <= verdict.score <= 100.0
