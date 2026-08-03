"""Tests for Task Preflight 2.0 (task_preflight.py)."""

from __future__ import annotations

import pytest

from maref.governance.pipeline_registry import (
    PipelineGovernor,
    PipelineRegistration,
    QualityTier,
)
from maref.governance.task_preflight import (
    AlternativesComparedCheck,
    DecisionLoggedCheck,
    GitHistoryCheck,
    PipelineSelectionCheck,
    PreflightCheckStatus,
    ReadmeReadCheck,
    TaskPreflight,
)

# ---------------------------------------------------------------------------
# ReadmeReadCheck
# ---------------------------------------------------------------------------


class TestReadmeReadCheck:
    def test_pass_with_summary(self):
        check = ReadmeReadCheck()
        result = check.execute({
            "readme_read": True,
            "readme_summary": "Project has video_producer.py and audio_mixer.py",
        })
        assert result.status == PreflightCheckStatus.PASS
        assert "已阅读" in result.description

    def test_warn_without_summary(self):
        check = ReadmeReadCheck()
        result = check.execute({"readme_read": True})
        assert result.status == PreflightCheckStatus.WARN
        assert "缺少摘要证据" in result.description

    def test_fail_not_read(self):
        check = ReadmeReadCheck()
        result = check.execute({"readme_read": False})
        assert result.status == PreflightCheckStatus.FAIL
        assert "未阅读" in result.description

    def test_fail_default(self):
        check = ReadmeReadCheck()
        result = check.execute({})
        assert result.status == PreflightCheckStatus.FAIL


# ---------------------------------------------------------------------------
# GitHistoryCheck
# ---------------------------------------------------------------------------


class TestGitHistoryCheck:
    def test_pass_with_entries(self):
        check = GitHistoryCheck()
        result = check.execute({
            "git_log_consulted": True,
            "git_log_entries": 10,
        })
        assert result.status == PreflightCheckStatus.PASS
        assert "10 条" in result.description

    def test_pass_with_files(self):
        check = GitHistoryCheck()
        result = check.execute({
            "git_log_consulted": True,
            "git_log_entries": 3,
            "git_files_checked": ["video_producer.py", "pipeline.py"],
        })
        assert result.status == PreflightCheckStatus.PASS

    def test_warn_no_entries(self):
        check = GitHistoryCheck()
        result = check.execute({"git_log_consulted": True, "git_log_entries": 0})
        assert result.status == PreflightCheckStatus.WARN

    def test_fail(self):
        check = GitHistoryCheck()
        result = check.execute({"git_log_consulted": False})
        assert result.status == PreflightCheckStatus.FAIL
        assert "未查阅" in result.description

    def test_fail_default(self):
        check = GitHistoryCheck()
        result = check.execute({})
        assert result.status == PreflightCheckStatus.FAIL


# ---------------------------------------------------------------------------
# AlternativesComparedCheck
# ---------------------------------------------------------------------------


class TestAlternativesComparedCheck:
    def test_pass_with_rationale(self):
        check = AlternativesComparedCheck()
        result = check.execute({
            "alternatives_considered": ["produce_launch.js", "video_producer.py"],
            "alternatives_rationale": "video_producer.py is official",
        })
        assert result.status == PreflightCheckStatus.PASS
        assert "2 种方案" in result.description

    def test_warn_no_rationale(self):
        check = AlternativesComparedCheck()
        result = check.execute({
            "alternatives_considered": ["opt_a", "opt_b"],
        })
        assert result.status == PreflightCheckStatus.WARN
        assert "未记录选择理由" in result.description

    def test_fail_single_alternative(self):
        check = AlternativesComparedCheck()
        result = check.execute({
            "alternatives_considered": ["only_one"],
        })
        assert result.status == PreflightCheckStatus.FAIL
        assert "1 种方案" in result.description

    def test_fail_empty(self):
        check = AlternativesComparedCheck()
        result = check.execute({"alternatives_considered": []})
        assert result.status == PreflightCheckStatus.FAIL
        assert "未比较" in result.description

    def test_fail_default(self):
        check = AlternativesComparedCheck()
        result = check.execute({})
        assert result.status == PreflightCheckStatus.FAIL


# ---------------------------------------------------------------------------
# DecisionLoggedCheck
# ---------------------------------------------------------------------------


class TestDecisionLoggedCheck:
    def test_pass_with_location(self):
        check = DecisionLoggedCheck()
        result = check.execute({
            "decision_logged": True,
            "decision_log_location": "audit://20260716/launch-video",
        })
        assert result.status == PreflightCheckStatus.PASS
        assert "已记录" in result.description

    def test_warn_no_location(self):
        check = DecisionLoggedCheck()
        result = check.execute({"decision_logged": True})
        assert result.status == PreflightCheckStatus.WARN

    def test_fail(self):
        check = DecisionLoggedCheck()
        result = check.execute({"decision_logged": False})
        assert result.status == PreflightCheckStatus.FAIL
        assert "未被记录" in result.description

    def test_fail_default(self):
        check = DecisionLoggedCheck()
        result = check.execute({})
        assert result.status == PreflightCheckStatus.FAIL


# ---------------------------------------------------------------------------
# PipelineSelectionCheck — unit
# ---------------------------------------------------------------------------


class TestPipelineSelectionCheck:
    @pytest.fixture
    def governor(self) -> PipelineGovernor:
        g = PipelineGovernor()
        g.register(
            PipelineRegistration(
                pipeline_id="official_pipe",
                name="Official",
                entry_point="official.py",
                description="",
                quality_tier=QualityTier.OFFICIAL,
                tags=["video"],
                verified=True,
            )
        )
        g.register(
            PipelineRegistration(
                pipeline_id="exp_pipe",
                name="Experimental",
                entry_point="exp.py",
                description="",
                quality_tier=QualityTier.EXPERIMENTAL,
                tags=["video"],
            )
        )
        g.register(
            PipelineRegistration(
                pipeline_id="deprecated_pipe",
                name="Deprecated",
                entry_point="dep.py",
                description="",
                quality_tier=QualityTier.DEPRECATED,
            )
        )
        return g

    def test_fail_no_selection(self):
        check = PipelineSelectionCheck()
        result = check.execute({})
        assert result.status == PreflightCheckStatus.FAIL
        assert "未选择管线" in result.description

    def test_warn_no_governor(self):
        check = PipelineSelectionCheck()
        result = check.execute({"selected_pipeline": "something"})
        assert result.status == PreflightCheckStatus.WARN
        assert "未提供 PipelineGovernor" in result.description

    def test_official_pass(self, governor):
        check = PipelineSelectionCheck()
        result = check.execute({
            "selected_pipeline": "official_pipe",
            "pipeline_governor": governor,
        })
        assert result.status == PreflightCheckStatus.PASS

    def test_experimental_warn(self, governor):
        check = PipelineSelectionCheck()
        result = check.execute({
            "selected_pipeline": "exp_pipe",
            "pipeline_governor": governor,
        })
        assert result.status == PreflightCheckStatus.WARN
        assert "EXPERIMENTAL" in result.description

    def test_deprecated_fail(self, governor):
        check = PipelineSelectionCheck()
        result = check.execute({
            "selected_pipeline": "deprecated_pipe",
            "pipeline_governor": governor,
        })
        assert result.status == PreflightCheckStatus.FAIL
        assert "DEPRECATED" in result.description

    def test_unregistered_fail(self, governor):
        check = PipelineSelectionCheck()
        result = check.execute({
            "selected_pipeline": "unknown",
            "pipeline_governor": governor,
        })
        assert result.status == PreflightCheckStatus.FAIL
        assert "未在注册表中注册" in result.description

    def test_suggestion_on_unregistered(self, governor):
        """When a task_type is given, the check should suggest an alternative."""
        check = PipelineSelectionCheck()
        result = check.execute({
            "selected_pipeline": "unknown",
            "pipeline_governor": governor,
            "task_type": "video",
        })
        assert result.status == PreflightCheckStatus.FAIL
        # Should suggest 'official_pipe'
        details = result.details
        assert "official_pipe" in details.get("suggestions", [])


# ---------------------------------------------------------------------------
# TaskPreflight — integration
# ---------------------------------------------------------------------------


class TestTaskPreflight:
    """Integration tests for the full TaskPreflight orchestrator."""

    @pytest.fixture
    def governor(self) -> PipelineGovernor:
        g = PipelineGovernor()
        g.register(
            PipelineRegistration(
                pipeline_id="video_producer",
                name="Official Video Pipeline",
                entry_point="python pipeline.py produce-video",
                description="PIL 逐帧绘制",
                quality_tier=QualityTier.OFFICIAL,
                tags=["video"],
                git_status="committed",
                verified=True,
            )
        )
        return g

    def test_default_checks(self):
        """TaskPreflight should have 6 default checks."""
        preflight = TaskPreflight()
        assert len(preflight.checks) == 6
        names = [c.name for c in preflight.checks]
        assert "readme_read" in names
        assert "pipeline_selection" in names
        assert "git_history" in names
        assert "alternatives_compared" in names
        assert "decision_logged" in names
        assert "risk_authorization" in names

    def test_custom_checks(self):
        """Can provide custom check list."""
        preflight = TaskPreflight(checks=[ReadmeReadCheck()])
        assert len(preflight.checks) == 1

    def test_all_pass(self, governor):
        """Full context with all checks passed → PreflightResult.passed=True."""
        preflight = TaskPreflight()
        result = preflight.execute({
            "agent_id": "agent-01",
            "task_description": "Generate launch video",
            "readme_read": True,
            "readme_summary": "Project has video_producer.py pipeline",
            "selected_pipeline": "video_producer",
            "pipeline_governor": governor,
            "git_log_consulted": True,
            "git_log_entries": 5,
            "git_files_checked": ["video_producer.py"],
            "alternatives_considered": ["produce_launch.js", "video_producer.py"],
            "alternatives_rationale": "video_producer.py is the official pipeline",
            "decision_logged": True,
            "decision_log_location": "audit://test/launch-video",
        })
        assert result.passed is True
        assert len(result.checks) == 6
        assert len(result.failed_checks) == 0
        assert len(result.warn_checks) == 0
        assert result.agent_id == "agent-01"

    def test_audit_scenario_fail(self):
        """Recreating the audit finding: agent using produce_launch without checks."""
        preflight = TaskPreflight()
        result = preflight.execute({
            "agent_id": "rogue-agent",
            "task_description": "Generate launch video",
            # No readme read
            "readme_read": False,
            # Selected unregistered experimental pipeline
            "selected_pipeline": "produce_launch.js",
            # No git history checked
            "git_log_consulted": False,
            # Only one alternative considered
            "alternatives_considered": ["produce_launch.js"],
            # No decision logged
            "decision_logged": False,
        })
        assert result.passed is False
        # Should fail readme, pipeline (with warn if no governor), git, alternatives, decision
        assert len(result.failed_checks) >= 3

    def test_partial_pass_with_warnings(self, governor):
        """Some checks pass, some warn, none fail → passed."""
        preflight = TaskPreflight()
        result = preflight.execute({
            "agent_id": "cautious-agent",
            "task_description": "Generate audio mix",
            "readme_read": True,
            "readme_summary": "Has audio mixer",
            "selected_pipeline": "video_producer",
            "pipeline_governor": governor,
            "git_log_consulted": True,
            "git_log_entries": 0,  # WARN
            "alternatives_considered": ["opt_a", "opt_b"],
            # No rationale → WARN
            "decision_logged": True,
            "decision_log_location": "audit://test/audio-mix",
        })
        assert result.passed is True
        assert len(result.warn_checks) >= 1

    def test_summary_format(self, governor):
        """summary property should produce readable output."""
        preflight = TaskPreflight()
        result = preflight.execute({
            "agent_id": "test",
            "task_description": "test",
            "readme_read": True,
            "readme_summary": "summary",
            "selected_pipeline": "video_producer",
            "pipeline_governor": governor,
            "git_log_consulted": True,
            "git_log_entries": 3,
            "alternatives_considered": ["a", "b"],
            "alternatives_rationale": "b is better",
            "decision_logged": True,
            "decision_log_location": "audit://test",
        })
        summary = result.summary
        assert "PASS" in summary or "FAIL" in summary
        assert "6" in summary  # total count

    def test_to_dict(self, governor):
        result = TaskPreflight().execute({
            "agent_id": "test",
            "task_description": "test",
            "readme_read": True,
            "readme_summary": "s",
            "selected_pipeline": "video_producer",
            "pipeline_governor": governor,
            "git_log_consulted": True,
            "git_log_entries": 1,
            "alternatives_considered": ["a", "b"],
            "alternatives_rationale": "b",
            "decision_logged": True,
            "decision_log_location": "audit://test",
        })
        d = result.to_dict()
        assert d["passed"] is True
        assert len(d["checks"]) == 6
        assert d["agent_id"] == "test"
        assert d["task_description"] == "test"


# ---------------------------------------------------------------------------
# RiskAuthorizationCheck（方案 D 决策分级授权）
# ---------------------------------------------------------------------------


class TestRiskAuthorizationCheck:
    def test_low_risk_auto_approve(self) -> None:
        preflight = TaskPreflight()
        result = preflight.execute({
            "agent_id": "agent",
            "task_description": "read",
            "action": "file.read",
        })
        check = next(c for c in result.checks if c.check_name == "risk_authorization")
        assert check.status == PreflightCheckStatus.PASS
        assert check.details["risk_level"] == "LOW"
        assert check.details["authorized"] is True

    def test_high_risk_without_scope_fails(self) -> None:
        preflight = TaskPreflight()
        result = preflight.execute({
            "agent_id": "agent",
            "task_description": "transfer",
            "action": "payment:transfer",
        })
        check = next(c for c in result.checks if c.check_name == "risk_authorization")
        assert check.status == PreflightCheckStatus.FAIL
        assert check.details["risk_level"] == "IRREVERSIBLE"
        assert check.details["action_required"] == "HITL"

    def test_irreversible_out_of_scope_blocked(self) -> None:
        preflight = TaskPreflight()
        result = preflight.execute({
            "agent_id": "agent",
            "task_description": "transfer",
            "action": "payment:transfer",
            "authorization_scope": {
                "subject_did": "did:maref:agent",
                "max_risk_level": "MEDIUM",
            },
        })
        check = next(c for c in result.checks if c.check_name == "risk_authorization")
        assert check.status == PreflightCheckStatus.FAIL
        assert check.details["action_required"] == "HITL"
        assert check.details["max_risk_level"] == "MEDIUM"

    def test_in_scope_high_risk_approved(self) -> None:
        from maref.identity.credential import AuthorizationScope

        scope = AuthorizationScope.issue(
            subject_did="did:maref:agent",
            max_risk_level="HIGH",
            allowed_actions=["network:medical_record"],
        )
        preflight = TaskPreflight()
        result = preflight.execute({
            "agent_id": "agent",
            "task_description": "access record",
            "action": "network:medical_record",
            "authorization_scope": scope,
        })
        check = next(c for c in result.checks if c.check_name == "risk_authorization")
        assert check.status == PreflightCheckStatus.PASS
        assert check.details["risk_level"] == "HIGH"
        assert check.details["authorized"] is True

    def test_expired_scope_fails(self) -> None:
        from maref.identity.credential import AuthorizationScope

        scope = AuthorizationScope.issue(
            subject_did="did:maref:agent",
            max_risk_level="HIGH",
            ttl_seconds=1,
        )
        scope.valid_until = 0.0
        preflight = TaskPreflight()
        result = preflight.execute({
            "agent_id": "agent",
            "task_description": "deploy",
            "action": "deploy:app",
            "authorization_scope": scope,
        })
        check = next(c for c in result.checks if c.check_name == "risk_authorization")
        assert check.status == PreflightCheckStatus.FAIL
        assert check.details["action_required"] == "HITL"

    def test_string_valid_until_fails_closed(self) -> None:
        """外部 dict 传入字符串时间戳时，过期判定应类型安全（fail-closed）。"""
        preflight = TaskPreflight()
        result = preflight.execute({
            "agent_id": "agent",
            "task_description": "deploy",
            "action": "deploy:app",
            "authorization_scope": {
                "subject_did": "did:maref:agent",
                "max_risk_level": "HIGH",
                "valid_until": "2020-01-01T00:00:00Z",  # 已过期的字符串时间戳
            },
        })
        check = next(c for c in result.checks if c.check_name == "risk_authorization")
        assert check.status == PreflightCheckStatus.FAIL
        assert check.details["action_required"] == "HITL"


class TestRiskClassifier:
    def test_low_read(self) -> None:
        from maref.governance.risk_classifier import RiskLevel, classify_action

        assert classify_action("file.read").risk_level == RiskLevel.LOW

    def test_medium_write(self) -> None:
        from maref.governance.risk_classifier import RiskLevel, classify_action

        assert classify_action("file.write").risk_level == RiskLevel.MEDIUM

    def test_irreversible_prefix(self) -> None:
        from maref.governance.risk_classifier import RiskLevel, classify_action

        assert classify_action("revoke:credential").risk_level == RiskLevel.IRREVERSIBLE

    def test_high_sensitive_term(self) -> None:
        from maref.governance.risk_classifier import RiskLevel, classify_action

        assert classify_action("network:medical_record").risk_level == RiskLevel.HIGH

    def test_high_production_scope(self) -> None:
        from maref.governance.risk_classifier import RiskLevel, classify_action, risk_exceeds

        assert classify_action("file.write", {"impact_scope": "production"}).risk_level == RiskLevel.HIGH
        assert risk_exceeds(RiskLevel.HIGH, RiskLevel.MEDIUM) is True
        assert risk_exceeds(RiskLevel.MEDIUM, RiskLevel.HIGH) is False

