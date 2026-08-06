from __future__ import annotations

from maref.orchestration.protocols import (
    AgentTaskResult,
    RiskPoint,
    SelfCheckResult,
    TaskResultStatus,
)
from maref.orchestration.state_merge_controller import (
    Conflict,
    MergeResult,
    StateMergeController,
)
from maref.orchestration.task_graph import TaskGraph, TaskNode, TaskStatus


def _make_result(
    task_id: str,
    status: TaskResultStatus = TaskResultStatus.COMPLETED,
    quality: float = 1.0,
    passed: bool = True,
    risks: list | None = None,
    next_steps: list[str] | None = None,
) -> AgentTaskResult:
    return AgentTaskResult(
        task_id=task_id,
        status=status,
        summary=f"Task {task_id}",
        self_check=SelfCheckResult(passed=passed, quality_score=quality),
        risks=risks or [],
        next_steps=next_steps or [],
    )


class TestStateMergeController:
    def test_merge_no_conflicts(self) -> None:
        ctrl = StateMergeController()
        results = [
            _make_result("t1"),
            _make_result("t2"),
        ]
        mr = ctrl.merge(results)
        assert mr.merged is True
        assert mr.conflicts == []
        assert mr.needs_rework is False
        assert mr.needs_human_review is False
        assert mr.quality_score == 1.0

    def test_merge_failed_task_triggers_rework(self) -> None:
        ctrl = StateMergeController()
        results = [
            _make_result("t1", status=TaskResultStatus.FAILED),
            _make_result("t2"),
        ]
        mr = ctrl.merge(results)
        assert mr.merged is False
        assert mr.needs_rework is True
        assert "t1" in mr.rework_tasks
        assert len(mr.conflicts) == 1
        assert mr.conflicts[0].severity == "high"

    def test_merge_low_quality_alone_no_rework(self) -> None:
        ctrl = StateMergeController(quality_threshold=0.6)
        results = [
            _make_result("t1", quality=0.4),
            _make_result("t2", quality=1.0),
        ]
        mr = ctrl.merge(results)
        assert mr.needs_rework is False
        assert mr.quality_score == 0.7

    def test_merge_high_risk_triggers_rework(self) -> None:
        ctrl = StateMergeController()
        results = [
            _make_result("t1", risks=[RiskPoint(description="Data loss", severity="high")]),
            _make_result("t2"),
        ]
        mr = ctrl.merge(results)
        assert mr.needs_rework is True
        assert "t1" in mr.rework_tasks

    def test_merge_critical_risk_triggers_human_review(self) -> None:
        ctrl = StateMergeController()
        results = [
            _make_result("t1", risks=[RiskPoint(description="Breach", severity="critical")]),
        ]
        mr = ctrl.merge(results)
        assert mr.needs_human_review is True

    def test_merge_self_check_failed_with_bad_quality(self) -> None:
        ctrl = StateMergeController(quality_threshold=0.6)
        results = [
            _make_result("t1", passed=False, quality=0.5),
        ]
        mr = ctrl.merge(results)
        assert mr.needs_rework is True

    def test_merge_self_check_failed_but_quality_ok(self) -> None:
        ctrl = StateMergeController(quality_threshold=0.6)
        results = [
            _make_result("t1", passed=False, quality=0.8),
        ]
        mr = ctrl.merge(results)
        assert mr.merged is False
        assert mr.needs_rework is False
        route = ctrl.decide_route(mr, None)
        assert route == "rework"

    def test_cross_conflict_duplicate_task_id(self) -> None:
        ctrl = StateMergeController()
        results = [
            _make_result("t1"),
            _make_result("t1"),
        ]
        mr = ctrl.merge(results)
        dup = [c for c in mr.conflicts if "duplicate" in c.description.lower()]
        assert len(dup) == 1
        assert dup[0].severity == "high"

    def test_cross_conflict_divergent_next_steps_low_severity(self) -> None:
        ctrl = StateMergeController()
        results = [
            _make_result("t1", next_steps=["write tests"]),
            _make_result("t2", next_steps=["deploy"]),
        ]
        mr = ctrl.merge(results)
        div = [c for c in mr.conflicts if "divergent" in c.description.lower()]
        assert len(div) == 1
        assert div[0].severity == "low"

    def test_cross_conflict_no_false_positive_when_both_empty(self) -> None:
        ctrl = StateMergeController()
        results = [
            _make_result("t1", next_steps=[]),
            _make_result("t2", next_steps=[]),
        ]
        mr = ctrl.merge(results)
        div = [c for c in mr.conflicts if "divergent" in c.description.lower()]
        assert len(div) == 0

    def test_cross_conflict_no_false_positive_when_shared(self) -> None:
        ctrl = StateMergeController()
        results = [
            _make_result("t1", next_steps=["write tests", "deploy"]),
            _make_result("t2", next_steps=["write tests"]),
        ]
        mr = ctrl.merge(results)
        div = [c for c in mr.conflicts if "divergent" in c.description.lower()]
        assert len(div) == 0

    def test_decide_route_continue(self) -> None:
        ctrl = StateMergeController()
        mr = MergeResult(merged=True)
        assert ctrl.decide_route(mr, None) == "continue"

    def test_decide_route_rework(self) -> None:
        ctrl = StateMergeController()
        mr = MergeResult(merged=False, needs_rework=True, rework_tasks=["t1"])
        assert ctrl.decide_route(mr, None) == "rework"

    def test_decide_route_human_review(self) -> None:
        ctrl = StateMergeController()
        mr = MergeResult(merged=True, needs_human_review=True)
        assert ctrl.decide_route(mr, None) == "human_review"

    def test_quality_score_average(self) -> None:
        ctrl = StateMergeController()
        results = [
            _make_result("t1", quality=0.8),
            _make_result("t2", quality=0.6),
        ]
        mr = ctrl.merge(results)
        assert mr.quality_score == 0.7

    def test_merge_empty_results(self) -> None:
        ctrl = StateMergeController()
        mr = ctrl.merge([])
        assert mr.merged is True
        assert mr.quality_score == 0.0
