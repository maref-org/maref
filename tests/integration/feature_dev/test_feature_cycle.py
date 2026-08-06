from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maref.integration.feature_dev.feature_cycle import (
    CycleSnapshot,
    FeatureDevelopmentCycle,
    _LAYER_NAMES,
)
from maref.integration.feature_dev.doc_ingestor import (
    DeployStage,
    FeatureDocument,
    DocumentSection,
)
from maref.integration.feature_dev.task_generator import FeatureTask, LayerCriterion
from maref.integration.test_platform.schema import EvalStatus


class TestCycleSnapshot:
    def test_defaults(self) -> None:
        snap = CycleSnapshot(
            cycle_number=1,
            topic="Test",
            layer_scores={"SA": 80.0},
            overall_score=80.0,
            overall_status=EvalStatus.PASS,
            verdict="approved",
            feedback_injected="Good",
            duration_seconds=10.5,
        )
        assert snap.artifacts == {}
        assert snap.go_nogo_decision == ""
        assert snap.budget_used == 0.0
        assert snap.history_entries == []
        assert snap.llm_used is False

    def test_to_dict_structure(self) -> None:
        snap = CycleSnapshot(
            cycle_number=2,
            topic="Alpha",
            layer_scores={"Static Audit": 90.0},
            overall_score=90.0,
            overall_status=EvalStatus.CONDITIONAL,
            verdict="conditional_pass",
            feedback_injected="Fix MAS",
            duration_seconds=5.2,
            artifacts={
                "characters": [{"name": "A"}],
                "scripts": [{"title": "S1"}],
                "stages_covered": {"mvp"},
                "requirements_covered": 10,
            },
            go_nogo_decision="GO",
            budget_used=150.0,
            history_entries=[{"step": "research"}],
            llm_used=True,
        )
        d = snap.to_dict()
        assert d["cycle_number"] == 2
        assert d["overall_score"] == 90.0
        assert d["overall_status"] == "CONDITIONAL"
        assert d["verdict"] == "conditional_pass"
        assert d["characters"] == 1
        assert d["scripts"] == 1
        assert d["stages_covered"] == ["mvp"]
        assert d["reqs_covered"] == 10
        assert d["go_nogo_decision"] == "GO"
        assert d["budget_used"] == 150.0
        assert d["llm_used"] is True

    def test_to_dict_no_artifacts(self) -> None:
        snap = CycleSnapshot(
            cycle_number=1,
            topic="T",
            layer_scores={},
            overall_score=0.0,
            overall_status=EvalStatus.FAIL,
            verdict="fail",
            feedback_injected="",
            duration_seconds=0.0,
        )
        d = snap.to_dict()
        assert d["characters"] == 0
        assert d["scripts"] == 0
        assert d["stages_covered"] == []


class TestFeatureDevelopmentCycleProperties:
    def test_is_deploy_ready_empty_snapshots(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        task = FeatureTask(
            task_id="t1", title="T1", description="D", deploy_stage=DeployStage.MVP,
            source_section="S",
        )
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.doc = doc
        cycle.tasks = [task]
        cycle.snapshots = []
        assert cycle.is_deploy_ready is False

    def test_is_deploy_ready_true(self) -> None:
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.snapshots = [
            CycleSnapshot(
                cycle_number=1,
                topic="T",
                layer_scores={"SA": 90.0},
                overall_score=85.0,
                overall_status=EvalStatus.PASS,
                verdict="approved",
                feedback_injected="",
                duration_seconds=1.0,
            ),
        ]
        assert cycle.is_deploy_ready is True

    def test_is_deploy_ready_low_score(self) -> None:
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.snapshots = [
            CycleSnapshot(
                cycle_number=1,
                topic="T",
                layer_scores={"SA": 50.0},
                overall_score=55.0,
                overall_status=EvalStatus.CONDITIONAL,
                verdict="pending",
                feedback_injected="",
                duration_seconds=1.0,
            ),
        ]
        assert cycle.is_deploy_ready is False

    def test_is_deploy_ready_wrong_verdict(self) -> None:
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.snapshots = [
            CycleSnapshot(
                cycle_number=1,
                topic="T",
                layer_scores={"SA": 90.0},
                overall_score=85.0,
                overall_status=EvalStatus.PASS,
                verdict="rejected",
                feedback_injected="",
                duration_seconds=1.0,
            ),
        ]
        assert cycle.is_deploy_ready is False

    def test_total_elapsed(self) -> None:
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.snapshots = [
            CycleSnapshot(
                cycle_number=1, topic="T", layer_scores={}, overall_score=0.0,
                overall_status=EvalStatus.FAIL, verdict="", feedback_injected="",
                duration_seconds=10.0,
            ),
            CycleSnapshot(
                cycle_number=2, topic="T", layer_scores={}, overall_score=0.0,
                overall_status=EvalStatus.FAIL, verdict="", feedback_injected="",
                duration_seconds=20.0,
            ),
        ]
        assert cycle.total_elapsed == 30.0

    def test_total_elapsed_empty(self) -> None:
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.snapshots = []
        assert cycle.total_elapsed == 0.0


class TestCompileStructuralFeedback:
    def test_all_at_target(self) -> None:
        scores = {
            "Static Audit": 85.0,
            "Reasoning Metrics": 80.0,
            "Action Metrics": 82.0,
            "E2E Metrics": 88.0,
            "MAS Dimensions": 90.0,
        }
        doc = FeatureDocument(title="T", raw_path="t.md")
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.doc = doc
        feedback = cycle._compile_structural_feedback(scores, {"characters": [], "scripts": []})
        assert feedback == "All layers at target."

    def test_low_static_audit(self) -> None:
        scores = {
            "Static Audit": 40.0,
            "Reasoning Metrics": 85.0,
            "Action Metrics": 85.0,
            "E2E Metrics": 85.0,
            "MAS Dimensions": 85.0,
        }
        doc = FeatureDocument(title="T", raw_path="t.md")
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.doc = doc
        feedback = cycle._compile_structural_feedback(scores, {"characters": [], "scripts": []})
        assert "Static Audit" in feedback
        assert "need more characters" in feedback

    def test_low_mas(self) -> None:
        scores = {
            "Static Audit": 85.0,
            "Reasoning Metrics": 85.0,
            "Action Metrics": 85.0,
            "E2E Metrics": 85.0,
            "MAS Dimensions": 30.0,
        }
        doc = FeatureDocument(title="T", raw_path="t.md")
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.doc = doc
        feedback = cycle._compile_structural_feedback(scores, {"characters": [], "scripts": []})
        assert "MAS=" in feedback
        assert "crossover" in feedback

    def test_multiple_low_layers_truncated_to_3(self) -> None:
        scores = {
            "Static Audit": 40.0,
            "Reasoning Metrics": 45.0,
            "Action Metrics": 50.0,
            "E2E Metrics": 55.0,
            "MAS Dimensions": 60.0,
        }
        doc = FeatureDocument(title="T", raw_path="t.md")
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.doc = doc
        feedback = cycle._compile_structural_feedback(scores, {"characters": [], "scripts": []})
        assert feedback.count("=") <= 3

    def test_small_gap_skipped(self) -> None:
        scores = {
            "Static Audit": 78.0,  # gap=2, <=5, should be skipped
            "Reasoning Metrics": 85.0,
            "Action Metrics": 85.0,
            "E2E Metrics": 85.0,
            "MAS Dimensions": 85.0,
        }
        doc = FeatureDocument(title="T", raw_path="t.md")
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.doc = doc
        feedback = cycle._compile_structural_feedback(scores, {"characters": [], "scripts": []})
        assert feedback == "All layers at target."


class TestDecideStatus:
    def test_pass_at_80(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.doc = doc
        assert cycle._decide_status(80.0) == EvalStatus.PASS
        assert cycle._decide_status(95.0) == EvalStatus.PASS

    def test_conditional_between_50_and_80(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.doc = doc
        assert cycle._decide_status(50.0) == EvalStatus.CONDITIONAL
        assert cycle._decide_status(79.9) == EvalStatus.CONDITIONAL

    def test_fail_below_50(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.doc = doc
        assert cycle._decide_status(0.0) == EvalStatus.FAIL
        assert cycle._decide_status(49.9) == EvalStatus.FAIL


class TestEvaluateGoNoGo:
    def test_monitoring_first_two_cycles(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.doc = doc
        assert cycle._evaluate_go_nogo(1, 0.0) == "monitoring"
        assert cycle._evaluate_go_nogo(2, 100.0) == "monitoring"

    def test_go_when_score_high(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.doc = doc
        cycle._final_decision = "in_progress"
        result = cycle._evaluate_go_nogo(5, 80.0)
        assert "GO" in result
        assert cycle._final_decision == "go"

    def test_kill_when_low_and_late_cycle(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.doc = doc
        cycle._go_nogo_triggered = False
        cycle._final_decision = "in_progress"
        result = cycle._evaluate_go_nogo(5, 30.0)
        assert "KILL" in result
        assert cycle._go_nogo_triggered is True

    def test_continue_when_not_go_or_kill(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.doc = doc
        result = cycle._evaluate_go_nogo(4, 60.0)
        assert "CONTINUE" in result


class TestBuildTopic:
    def test_first_cycle(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.doc = doc
        cycle._base_topic = "Research: T"
        topic = cycle._build_topic(1)
        assert topic == "Research: T"

    def test_subsequent_with_low_scores(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.doc = doc
        cycle._base_topic = "Research: T"
        cycle.snapshots = [
            MagicMock(spec=CycleSnapshot, layer_scores={
                "Static Audit": 40.0,
                "Reasoning Metrics": 70.0,
                "Action Metrics": 80.0,
                "E2E Metrics": 85.0,
                "MAS Dimensions": 90.0,
            }),
        ]
        topic = cycle._build_topic(2)
        assert "focus" in topic
        assert "Static Audit" in topic

    def test_subsequent_all_high(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.doc = doc
        cycle._base_topic = "Research: T"
        cycle.snapshots = [
            MagicMock(spec=CycleSnapshot, layer_scores={
                "Static Audit": 85.0,
                "Reasoning Metrics": 90.0,
                "Action Metrics": 95.0,
                "E2E Metrics": 88.0,
                "MAS Dimensions": 92.0,
            }),
        ]
        topic = cycle._build_topic(2)
        assert "(iter" in topic
        assert "focus" not in topic


class TestLastScores:
    def test_no_snapshots_returns_zeros(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.doc = doc
        cycle.snapshots = []
        scores = cycle._last_scores()
        for name in _LAYER_NAMES.values():
            assert scores[name] == 0.0

    def test_returns_last_snapshot(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.doc = doc
        cycle.snapshots = [
            MagicMock(spec=CycleSnapshot, layer_scores={"SA": 50.0}),
            MagicMock(spec=CycleSnapshot, layer_scores={"SA": 80.0}),
        ]
        scores = cycle._last_scores()
        assert scores["SA"] == 80.0


class TestEstimateCycleCost:
    def test_decaying_cost(self) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
        cycle.doc = doc
        assert cycle._estimate_cycle_cost(1) == 100.0
        assert cycle._estimate_cycle_cost(2) == 85.0
        assert cycle._estimate_cycle_cost(3) == pytest.approx(72.25)


class TestFeatureDevelopmentCycleFull:
    @patch("maref.integration.feature_dev.feature_cycle.LlmClient")
    @patch("maref.integration.feature_dev.feature_cycle.GovernanceStateMachine")
    @patch("maref.integration.feature_dev.feature_cycle.MASEvalObserver")
    @patch("maref.integration.feature_dev.feature_cycle.EvolutionQualityGate")
    @patch("maref.integration.feature_dev.feature_cycle.PERCVResearchOrchestrator")
    def test_constructor(
        self,
        mock_orch: MagicMock,
        mock_qg: MagicMock,
        mock_eval: MagicMock,
        mock_sm: MagicMock,
        mock_llm: MagicMock,
    ) -> None:
        doc = FeatureDocument(title="T", raw_path="t.md")
        task = FeatureTask(
            task_id="t1", title="T1", description="D", deploy_stage=DeployStage.MVP,
            source_section="S",
        )
        cycle = FeatureDevelopmentCycle(doc=doc, tasks=[task], iterations=5, budget_cents=10000.0)
        assert cycle.doc.title == "T"
        assert cycle.iterations == 5
        assert cycle.budget_cents == 10000.0
        assert cycle.snapshots == []
