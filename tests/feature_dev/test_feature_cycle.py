from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from maref.integration.feature_dev.feature_cycle import (
    CycleSnapshot,
    FeatureDevelopmentCycle,
    _LAYER_NAMES,
)
from maref.integration.test_platform.schema import EvalStatus


class TestCycleSnapshot:
    def test_to_dict(self) -> None:
        snap = CycleSnapshot(
            cycle_number=1, topic="Test",
            layer_scores={"A": 80.0, "B": 70.0}, overall_score=75.0,
            overall_status=EvalStatus.CONDITIONAL, verdict="approved",
            feedback_injected="Good", duration_seconds=10.0,
            artifacts={"characters": [{"name": "A"}], "scripts": [{"title": "1"}],
                       "stages_covered": {"mvp"}, "requirements_covered": 5},
            go_nogo_decision="GO", budget_used=100.0, llm_used=True,
        )
        d = snap.to_dict()
        assert d["cycle_number"] == 1
        assert d["overall_score"] == 75.0
        assert d["overall_status"] == "CONDITIONAL"
        assert d["go_nogo_decision"] == "GO"
        assert d["characters"] == 1
        assert d["scripts"] == 1
        assert d["llm_used"]

    def test_to_dict_empty_artifacts(self) -> None:
        snap = CycleSnapshot(
            cycle_number=1, topic="T", layer_scores={}, overall_score=0.0,
            overall_status=EvalStatus.FAIL, verdict="fail",
            feedback_injected="", duration_seconds=0.0,
        )
        d = snap.to_dict()
        assert d["characters"] == 0
        assert d["scripts"] == 0


def _make_cycle(**attrs: Any) -> FeatureDevelopmentCycle:
    cycle = FeatureDevelopmentCycle.__new__(FeatureDevelopmentCycle)
    for k, v in attrs.items():
        setattr(cycle, k, v)
    missing = {
        "doc": None, "tasks": None, "iterations": 10, "budget_cents": 50000.0,
        "snapshots": [], "_llm": None, "_sm": None, "_eval_obs": None,
        "_qg": None, "_orch": None, "_producer": None, "_scorer": None,
        "_base_topic": "Test topic", "_budget_spent": 0.0,
        "_prev_artifacts": None, "_go_nogo_triggered": False,
        "_final_decision": "in_progress", "_llm_feedback_history": [],
    }
    for k, v in missing.items():
        if not hasattr(cycle, k):
            setattr(cycle, k, v)
    return cycle


class TestDecideStatus:
    def test_pass_above_80(self) -> None:
        cycle = _make_cycle()
        assert cycle._decide_status(85.0) == EvalStatus.PASS
        assert cycle._decide_status(80.0) == EvalStatus.PASS

    def test_conditional_between_50_and_80(self) -> None:
        cycle = _make_cycle()
        assert cycle._decide_status(65.0) == EvalStatus.CONDITIONAL
        assert cycle._decide_status(50.0) == EvalStatus.CONDITIONAL

    def test_fail_below_50(self) -> None:
        cycle = _make_cycle()
        assert cycle._decide_status(49.0) == EvalStatus.FAIL
        assert cycle._decide_status(0.0) == EvalStatus.FAIL
        assert cycle._decide_status(-10.0) == EvalStatus.FAIL


class TestEvaluateGoNoGo:
    def test_monitoring_first_two_cycles(self) -> None:
        cycle = _make_cycle()
        assert "monitoring" in cycle._evaluate_go_nogo(1, 60.0)
        assert "monitoring" in cycle._evaluate_go_nogo(2, 60.0)

    def test_go_when_above_threshold(self) -> None:
        cycle = _make_cycle()
        result = cycle._evaluate_go_nogo(4, 80.0)
        assert "GO" in result
        assert cycle._final_decision == "go"

    def test_kill_when_below_threshold_after_cycle_5(self) -> None:
        cycle = _make_cycle()
        result = cycle._evaluate_go_nogo(5, 40.0)
        assert "KILL" in result
        assert cycle._go_nogo_triggered
        assert cycle._final_decision == "kill"

    def test_continue_when_between(self) -> None:
        cycle = _make_cycle()
        result = cycle._evaluate_go_nogo(4, 60.0)
        assert "CONTINUE" in result

    def test_continue_at_exact_threshold(self) -> None:
        cycle = _make_cycle()
        result = cycle._evaluate_go_nogo(5, 50.0)
        assert "CONTINUE" in result  # exactly NOGO_THRESHOLD, not below it
        assert not cycle._go_nogo_triggered


class TestBuildTopic:
    def test_first_cycle_returns_base(self) -> None:
        cycle = _make_cycle()
        assert cycle._build_topic(1) == "Test topic"

    def test_later_cycle_focuses_low_layers(self) -> None:
        snap = MagicMock()
        snap.layer_scores = {"Static Audit": 40.0, "Reasoning Metrics": 80.0,
                             "Action Metrics": 70.0, "E2E Metrics": 90.0,
                             "MAS Dimensions": 85.0}
        cycle = _make_cycle(snapshots=[snap])
        topic = cycle._build_topic(2)
        assert "focus" in topic
        assert "Static Audit" in topic

    def test_later_cycle_all_high(self) -> None:
        snap = MagicMock()
        snap.layer_scores = {"A": 85.0, "B": 90.0}
        cycle = _make_cycle(snapshots=[snap])
        topic = cycle._build_topic(2)
        assert "iter" in topic


class TestLastScores:
    def test_empty_snapshots(self) -> None:
        cycle = _make_cycle(snapshots=[])
        scores = cycle._last_scores()
        for name in _LAYER_NAMES.values():
            assert scores[name] == 0.0

    def test_with_snapshots(self) -> None:
        snap = MagicMock()
        snap.layer_scores = {"A": 75.0, "B": 85.0}
        cycle = _make_cycle(snapshots=[snap])
        scores = cycle._last_scores()
        assert scores["A"] == 75.0
        assert scores["B"] == 85.0


class TestCompileStructuralFeedback:
    def test_all_layers_at_target(self) -> None:
        cycle = _make_cycle()
        result = cycle._compile_structural_feedback(
            {"A": 85.0, "B": 82.0}, {"characters": [], "scripts": []},
        )
        assert "All layers at target" in result

    def test_gaps_generate_suggestions(self) -> None:
        cycle = _make_cycle()
        result = cycle._compile_structural_feedback(
            {"Static Audit": 40.0, "Reasoning Metrics": 70.0},
            {"characters": [{"name": "A"}], "scripts": [{"title": "1"}]},
        )
        assert "Static Audit" in result
        assert "more characters" in result

    def test_limited_to_three_suggestions(self) -> None:
        cycle = _make_cycle()
        result = cycle._compile_structural_feedback(
            {"A": 30.0, "B": 30.0, "C": 30.0, "D": 30.0},
            {"characters": [], "scripts": []},
        )
        assert len(result.split(";")) <= 3


class TestEstimateCycleCost:
    def test_exponential_decay(self) -> None:
        cycle = _make_cycle()
        c1 = cycle._estimate_cycle_cost(1)
        c2 = cycle._estimate_cycle_cost(2)
        c3 = cycle._estimate_cycle_cost(3)
        assert c1 == 100.0
        assert c2 < c1
        assert c3 < c2

    def test_positive_always(self) -> None:
        cycle = _make_cycle()
        for i in range(1, 20):
            assert cycle._estimate_cycle_cost(i) > 0


class TestIsDeployReady:
    def test_no_snapshots(self) -> None:
        cycle = _make_cycle(snapshots=[])
        assert not cycle.is_deploy_ready

    def test_ready(self) -> None:
        snap = MagicMock()
        snap.overall_score = 85.0
        snap.verdict = "approved"
        cycle = _make_cycle(snapshots=[snap])
        assert cycle.is_deploy_ready

    def test_not_ready_low_score(self) -> None:
        snap = MagicMock()
        snap.overall_score = 70.0
        snap.verdict = "approved"
        cycle = _make_cycle(snapshots=[snap])
        assert not cycle.is_deploy_ready

    def test_not_ready_wrong_verdict(self) -> None:
        snap = MagicMock()
        snap.overall_score = 85.0
        snap.verdict = "rejected"
        cycle = _make_cycle(snapshots=[snap])
        assert not cycle.is_deploy_ready


class TestTotalElapsed:
    def test_empty(self) -> None:
        cycle = _make_cycle(snapshots=[])
        assert cycle.total_elapsed == 0.0

    def test_sum(self) -> None:
        s1 = MagicMock(duration_seconds=10.0)
        s2 = MagicMock(duration_seconds=20.0)
        cycle = _make_cycle(snapshots=[s1, s2])
        assert cycle.total_elapsed == 30.0
