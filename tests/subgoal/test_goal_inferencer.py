from __future__ import annotations

from maref.subgoal.cot_monitor import CoTMonitor, CoTReport
from maref.subgoal.goal_inferencer import GoalInferencer


def _make_report(tokens: list[str]) -> CoTReport:
    monitor = CoTMonitor()
    return monitor.monitor_stream("test", tokens)


class TestGoalInferencer:
    def test_expand_goals_empty(self) -> None:
        gi = GoalInferencer()
        report = _make_report([])
        dag = gi.expand_goals(report)
        assert dag.root_goal == "root"
        assert len(dag.nodes) == 0

    def test_expand_goals_creates_nodes(self) -> None:
        gi = GoalInferencer()
        report = _make_report(["a", "b", "c", "d", "e", "f", "g", "h"])
        dag = gi.expand_goals(report)
        assert len(dag.nodes) > 0
        if len(dag.nodes) > 1:
            assert len(dag.edges) > 0

    def test_no_control_subgoal(self) -> None:
        gi = GoalInferencer()
        report = _make_report(["the", "weather", "is", "nice", "today"])
        dag = gi.expand_goals(report)
        risk = gi.detect_control_subgoal(dag)
        assert risk.control_goal_count == 0
        assert risk.risk_score == 0.0

    def test_detect_control_subgoal(self) -> None:
        gi = GoalInferencer()
        report = _make_report(["gain", "control", "of", "server",
                               "elevate", "permission", "to", "admin",
                               "bypass", "security", "gate"])
        dag = gi.expand_goals(report)
        risk = gi.detect_control_subgoal(dag)
        assert risk.control_goal_count > 0
        assert risk.risk_score > 0

    def test_concealment_detection(self) -> None:
        gi = GoalInferencer()
        report = _make_report(["hide", "our", "actions",
                               "conceal", "the", "bypass",
                               "gain", "access"])
        dag = gi.expand_goals(report)
        risk = gi.detect_control_subgoal(dag)
        assert risk.concealment_level in ("medium", "high")
        assert len(risk.findings) > 0

    def test_direct_control_action(self) -> None:
        gi = GoalInferencer()
        report = _make_report(["bypass", "security", "to", "get", "access",
                               "elevate", "permissions", "to", "full", "access",
                               "grant", "override", "capability"])
        dag = gi.expand_goals(report)
        risk = gi.detect_control_subgoal(dag)
        assert risk.control_goal_count > 0
