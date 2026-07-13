from __future__ import annotations

from maref.orchestration.protocols import (
    AgentTaskResult,
    RiskPoint,
    SelfCheckResult,
    TaskResultStatus,
)


class TestSelfCheckResult:
    def test_defaults(self) -> None:
        sc = SelfCheckResult()
        assert sc.passed is True
        assert sc.quality_score == 1.0
        assert sc.coverage == 1.0
        assert sc.issues == []


class TestRiskPoint:
    def test_defaults(self) -> None:
        rp = RiskPoint()
        assert rp.description == ""
        assert rp.severity == "low"
        assert rp.mitigation == ""


class TestAgentTaskResult:
    def test_acceptable_when_completed_and_passed(self) -> None:
        r = AgentTaskResult(
            task_id="t1",
            status=TaskResultStatus.COMPLETED,
            self_check=SelfCheckResult(passed=True, quality_score=0.8),
        )
        assert r.is_acceptable is True

    def test_not_acceptable_when_failed(self) -> None:
        r = AgentTaskResult(
            task_id="t1",
            status=TaskResultStatus.FAILED,
            self_check=SelfCheckResult(passed=True),
        )
        assert r.is_acceptable is False

    def test_not_acceptable_when_low_quality(self) -> None:
        r = AgentTaskResult(
            task_id="t1",
            status=TaskResultStatus.COMPLETED,
            self_check=SelfCheckResult(passed=True, quality_score=0.3),
        )
        assert r.is_acceptable is False

    def test_not_acceptable_when_self_check_failed(self) -> None:
        r = AgentTaskResult(
            task_id="t1",
            status=TaskResultStatus.COMPLETED,
            self_check=SelfCheckResult(passed=False),
        )
        assert r.is_acceptable is False

    def test_needs_human_review_with_high_risk(self) -> None:
        r = AgentTaskResult(
            task_id="t1",
            risks=[RiskPoint(description="Data loss", severity="high")],
        )
        assert r.needs_human_review is True

    def test_needs_human_review_with_critical_risk(self) -> None:
        r = AgentTaskResult(
            task_id="t1",
            risks=[RiskPoint(description="Security breach", severity="critical")],
        )
        assert r.needs_human_review is True

    def test_needs_human_review_with_needs_rework(self) -> None:
        r = AgentTaskResult(
            task_id="t1",
            status=TaskResultStatus.NEEDS_REWORK,
        )
        assert r.needs_human_review is True

    def test_no_human_review_when_low_risk(self) -> None:
        r = AgentTaskResult(
            task_id="t1",
            risks=[RiskPoint(description="Minor issue", severity="low")],
        )
        assert r.needs_human_review is False

    def test_to_dict(self) -> None:
        r = AgentTaskResult(
            task_id="t1",
            status=TaskResultStatus.COMPLETED,
            summary="Done",
            self_check=SelfCheckResult(passed=True, coverage=0.9),
            risks=[RiskPoint(description="Minor", severity="low", mitigation="Ignore")],
            next_steps=["deploy"],
        )
        d = r.to_dict()
        assert d["task_id"] == "t1"
        assert d["status"] == "completed"
        assert d["summary"] == "Done"
        assert d["self_check"]["passed"] is True
        assert d["self_check"]["coverage"] == 0.9
        assert len(d["risks"]) == 1
        assert d["risks"][0]["description"] == "Minor"
        assert d["risks"][0]["mitigation"] == "Ignore"
        assert d["next_steps"] == ["deploy"]
