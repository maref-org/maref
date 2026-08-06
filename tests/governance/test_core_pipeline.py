"""Tests for the unified GovernancePipeline (core_pipeline.py)."""

from __future__ import annotations

import pytest

from maref.governance.core_pipeline import (
    GovernancePipeline,
    GovernanceRequest,
    Verdict,
)


def test_pipeline_allows_safe_action():
    pipe = GovernancePipeline()
    result = pipe.govern(GovernanceRequest(action="file.read", agent_id="test"))
    assert result.verdict == Verdict.ALLOW


def test_pipeline_denies_dangerous_action_low_trust():
    pipe = GovernancePipeline()
    result = pipe.govern(
        GovernanceRequest(action="shell.exec", agent_id="test", trust_score=10)
    )
    assert result.verdict in (Verdict.DENY, Verdict.ASK_USER)


def test_pipeline_asks_user_for_dangerous_action_medium_trust():
    pipe = GovernancePipeline()
    result = pipe.govern(
        GovernanceRequest(action="shell.exec", agent_id="test", trust_score=50)
    )
    assert result.verdict == Verdict.ASK_USER


def test_pipeline_allows_dangerous_action_high_trust():
    pipe = GovernancePipeline()
    result = pipe.govern(
        GovernanceRequest(action="shell.exec", agent_id="test", trust_score=90)
    )
    assert result.verdict == Verdict.ALLOW


def test_pipeline_asks_user_for_git_push():
    pipe = GovernancePipeline()
    result = pipe.govern(
        GovernanceRequest(action="git.push", agent_id="test", trust_score=90)
    )
    assert result.verdict == Verdict.ASK_USER


def test_pipeline_asks_user_for_git_commit_low_trust():
    pipe = GovernancePipeline()
    result = pipe.govern(
        GovernanceRequest(action="git.commit", agent_id="test", trust_score=50)
    )
    assert result.verdict == Verdict.ASK_USER


def test_pipeline_allows_git_commit_high_trust():
    pipe = GovernancePipeline()
    result = pipe.govern(
        GovernanceRequest(action="git.commit", agent_id="test", trust_score=90)
    )
    assert result.verdict == Verdict.ALLOW


def test_pipeline_asks_user_for_high_recursion():
    pipe = GovernancePipeline()
    result = pipe.govern(
        GovernanceRequest(action="file.read", agent_id="test", recursion_depth=5)
    )
    assert result.verdict == Verdict.ASK_USER


def test_pipeline_denies_very_low_trust():
    pipe = GovernancePipeline()
    result = pipe.govern(
        GovernanceRequest(action="file.read", agent_id="test", trust_score=10)
    )
    assert result.verdict == Verdict.DENY


def test_pipeline_denies_permission_matrix():
    pipe = GovernancePipeline()
    result = pipe.govern(
        GovernanceRequest(action="file.write", agent_id="test", role="坎", trust_score=80)
    )
    assert result.verdict == Verdict.DENY

def test_pipeline_allows_permission_matrix():
    pipe = GovernancePipeline()
    result = pipe.govern(
        GovernanceRequest(action="file.read", agent_id="test", role="坎", trust_score=80)
    )
    assert result.verdict == Verdict.ALLOW


def test_pipeline_hitl_event_id_on_ask_user():
    pipe = GovernancePipeline()
    result = pipe.govern(
        GovernanceRequest(action="shell.exec", agent_id="test", trust_score=50)
    )
    if result.verdict == Verdict.ASK_USER:
        assert result.hitl_event_id
        assert result.hitl_tier is not None


def test_pipeline_latency_tracked():
    pipe = GovernancePipeline()
    result = pipe.govern(GovernanceRequest(action="file.read", agent_id="test"))
    assert result.latency_ms >= 0
    assert isinstance(result.latency_ms, int)


def test_pipeline_custom_policy_rule():
    """Custom policy rules override defaults by priority."""
    def block_all(req: GovernanceRequest):
        return Verdict.DENY, "All actions blocked", None

    pipe = GovernancePipeline(policy_rules=[(999, block_all)])
    result = pipe.govern(GovernanceRequest(action="file.read", agent_id="test"))
    assert result.verdict == Verdict.DENY
    assert "All actions blocked" in result.reason


def test_pipeline_audit_callback_invoked():
    audit_log = []
    def audit_cb(req, result):
        audit_log.append((req.action, result.verdict))

    pipe = GovernancePipeline(audit_callback=audit_cb)
    pipe.govern(GovernanceRequest(action="file.read", agent_id="test"))
    assert len(audit_log) >= 1
    assert audit_log[0][0] == "file.read"


def test_pipeline_trust_callback_invoked():
    trust_updates = []
    def trust_cb(tenant_id, agent_id, score, reason):
        trust_updates.append((agent_id, score, reason))

    pipe = GovernancePipeline(trust_callback=trust_cb)
    pipe.govern(GovernanceRequest(action="file.read", agent_id="tester"))
    assert len(trust_updates) >= 1
    assert trust_updates[0][0] == "tester"


def test_pipeline_multiple_requests_independent():
    pipe = GovernancePipeline()
    r1 = pipe.govern(GovernanceRequest(action="file.read", agent_id="agent1", trust_score=50))
    r2 = pipe.govern(GovernanceRequest(action="shell.exec", agent_id="agent2", trust_score=10))
    assert r1.verdict == Verdict.ALLOW
    assert r2.verdict in (Verdict.DENY, Verdict.ASK_USER)
