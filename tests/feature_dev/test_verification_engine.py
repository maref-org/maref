from __future__ import annotations

from maref.integration.feature_dev.doc_ingestor import (
    ComplianceRule,
    DeployStage,
    DocumentSection,
    FeatureDocument,
    Hypothesis,
)
from maref.integration.feature_dev.progress_tracker import (
    ConvergenceReport,
    LayerTrend,
)
from maref.integration.feature_dev.verification_engine import (
    DeliveryVerdict,
    DeliveryVerifier,
    VerdictItem,
)


class TestDeliveryVerifier:
    def _make_doc(self, **overrides: dict) -> FeatureDocument:
        go_sec = DocumentSection(heading="Go Decision", level=2, content="")
        base = FeatureDocument(
            title="Test",
            raw_path="/tmp/t.md",
            all_sections=[go_sec],
            stages={DeployStage.MVP: [go_sec]},
            hypotheses=[
                Hypothesis(name="H1", method="A/B", pass_threshold=">80%", fail_criterion="<50%"),
                Hypothesis(name="H2", method="B/C", pass_threshold=">70%", fail_criterion="<40%"),
                Hypothesis(name="H3", method="C/D", pass_threshold=">60%", fail_criterion="<30%"),
            ],
            compliance_rules=[
                ComplianceRule(rule_id="c1", description="R1", category="daily", is_automated=True),
                ComplianceRule(rule_id="c2", description="R2", category="weekly", is_automated=True),
                ComplianceRule(rule_id="c3", description="R3", category="monthly", is_automated=True),
                ComplianceRule(rule_id="d1", description="D1", category="discipline"),
                ComplianceRule(rule_id="d2", description="D2", category="discipline"),
                ComplianceRule(rule_id="d3", description="D3", category="discipline"),
            ],
            cost_models=[
                CostModel_wrap(stage="S1"),
                CostModel_wrap(stage="S2"),
                CostModel_wrap(stage="S3"),
            ],
            metadata={"detected_stages": ["mvp", "mixed", "internalization"]},
        )
        base.__dict__.update(overrides)
        return base

    def _make_report(self, **overrides) -> ConvergenceReport:
        lt = LayerTrend("A", [80.0], "converging", 0.0)
        params = dict(
            feature_name="T", total_cycles=1, total_duration_seconds=10.0,
            overall_trend="converging", layer_trends=[lt],
            deploy_ready=True, deploy_gates={"g1": True}, recommendations=[],
            cycle_scores=[80.0], final_decision="GO", budget_spent=100.0,
        )
        params.update(overrides)
        return ConvergenceReport(**params)

    def test_check_hypotheses_all_present(self) -> None:
        doc = self._make_doc()
        v = DeliveryVerifier(doc)
        v._check_hypotheses()
        items = {i.check_id: i for i in v.items}
        assert items["§1.5_hypotheses"].passed
        assert items["§1.5_thresholds"].passed

    def test_check_hypotheses_missing(self) -> None:
        doc = self._make_doc()
        doc.hypotheses = []
        v = DeliveryVerifier(doc)
        v._check_hypotheses()
        items = {i.check_id: i for i in v.items}
        assert not items["§1.5_hypotheses"].passed

    def test_check_go_nogo_found(self) -> None:
        doc = self._make_doc()
        v = DeliveryVerifier(doc)
        v._check_go_nogo()
        assert v.items[-1].passed

    def test_check_go_nogo_missing(self) -> None:
        doc = self._make_doc()
        doc.all_sections = []
        doc.stages = {}
        v = DeliveryVerifier(doc)
        v._check_go_nogo()
        assert not v.items[-1].passed

    def test_check_stages_all_present(self) -> None:
        doc = self._make_doc()
        v = DeliveryVerifier(doc)
        v._check_stages()
        assert v.items[-1].passed

    def test_check_stages_missing(self) -> None:
        doc = self._make_doc()
        doc.metadata["detected_stages"] = ["mvp"]
        v = DeliveryVerifier(doc)
        v._check_stages()
        assert not v.items[-1].passed

    def test_check_checklists_all_categories(self) -> None:
        doc = self._make_doc()
        v = DeliveryVerifier(doc)
        v._check_checklists()
        assert v.items[-1].passed

    def test_check_checklists_missing_category(self) -> None:
        doc = self._make_doc()
        doc.compliance_rules = [ComplianceRule(rule_id="c1", description="R", category="daily")]
        v = DeliveryVerifier(doc)
        v._check_checklists()
        assert not v.items[-1].passed

    def test_check_cost_models_sufficient(self) -> None:
        doc = self._make_doc()
        v = DeliveryVerifier(doc)
        v._check_cost_models()
        assert v.items[-1].passed

    def test_check_cost_models_insufficient(self) -> None:
        doc = self._make_doc()
        doc.cost_models = []
        v = DeliveryVerifier(doc)
        v._check_cost_models()
        assert not v.items[-1].passed

    def test_check_disciplines_sufficient(self) -> None:
        doc = self._make_doc()
        v = DeliveryVerifier(doc)
        v._check_disciplines()
        assert v.items[-1].passed

    def test_check_disciplines_insufficient(self) -> None:
        doc = self._make_doc()
        doc.compliance_rules = [
            ComplianceRule(rule_id="d1", description="D", category="daily"),
        ]
        v = DeliveryVerifier(doc)
        v._check_disciplines()
        assert not v.items[-1].passed

    def test_check_deploy_readiness_with_report(self) -> None:
        doc = self._make_doc()
        v = DeliveryVerifier(doc)
        report = self._make_report()
        v._check_deploy_readiness(report)
        assert v.items[-1].passed

    def test_check_deploy_readiness_no_report(self) -> None:
        doc = self._make_doc()
        v = DeliveryVerifier(doc)
        v._check_deploy_readiness(None)
        assert not v.items[-1].passed

    def test_check_convergence_passing(self) -> None:
        doc = self._make_doc()
        v = DeliveryVerifier(doc)
        v._check_convergence(self._make_report())
        assert v.items[-1].passed

    def test_check_convergence_failing(self) -> None:
        doc = self._make_doc()
        v = DeliveryVerifier(doc)
        report = self._make_report(overall_trend="diverging")
        v._check_convergence(report)
        assert not v.items[-1].passed

    def test_check_methods_tracked_without_field(self) -> None:
        doc = self._make_doc()
        v = DeliveryVerifier(doc)
        v._check_methods_tracked(self._make_report())
        assert not v.items[-1].passed  # no methods_used attr = not passed

    def test_check_methods_tracked_with_field(self) -> None:
        doc = self._make_doc()
        v = DeliveryVerifier(doc)
        report = self._make_report()
        report.methods_used = [Hypothesis(name="H1", method="A", pass_threshold="P", fail_criterion="F"),
                               Hypothesis(name="H2", method="B", pass_threshold="P", fail_criterion="F"),
                               Hypothesis(name="H3", method="C", pass_threshold="P", fail_criterion="F")]
        v._check_methods_tracked(report)
        assert v.items[-1].passed

    def test_verify_full_pipeline(self) -> None:
        doc = self._make_doc()
        v = DeliveryVerifier(doc)
        result = v.verify(self._make_report())
        assert isinstance(result, DeliveryVerdict)
        assert len(result.items) > 0
        assert result.score > 0

    def test_verify_without_report(self) -> None:
        doc = self._make_doc()
        v = DeliveryVerifier(doc)
        result = v.verify(report=None)
        assert isinstance(result, DeliveryVerdict)


def CostModel_wrap(stage: str, **kw):
    from maref.integration.feature_dev.doc_ingestor import CostModel
    return CostModel(stage=stage, items={"A": 100.0}, total=100.0, **kw)


class TestVerdictItem:
    def test_to_dict(self) -> None:
        vi = VerdictItem(check_id="c1", description="desc", passed=True, detail="ok", weight=2.0)
        d = vi.to_dict()
        assert d["check_id"] == "c1"
        assert d["passed"]

    def test_default_weight(self) -> None:
        vi = VerdictItem(check_id="c2", description="d", passed=False, detail="fail")
        assert vi.weight == 1.0


class TestDeliveryVerdict:
    def test_to_dict(self) -> None:
        vi = VerdictItem("c1", "d", True, "ok")
        dv = DeliveryVerdict(overall_passed=True, score=85.0, items=[vi], summary="Pass")
        d = dv.to_dict()
        assert d["overall_passed"]
        assert d["score"] == 85.0
