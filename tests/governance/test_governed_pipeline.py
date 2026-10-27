"""Tests for GovernedPipeline (governance/governed_pipeline.py)."""

from __future__ import annotations

import time

import pytest

from maref.governance.decorators import GovernanceDeniedError, get_default_pipeline, governed
from maref.governance.governed_pipeline import GovernedPipeline


@pytest.fixture(autouse=True)
def cleanup():
    """Ensure no leftover default pipeline between tests."""
    from maref.governance.decorators import set_default_pipeline

    yield
    set_default_pipeline(None)


def test_governed_pipeline_default_assembly():
    pipeline = GovernedPipeline()
    assert hasattr(pipeline, "pipeline")
    assert hasattr(pipeline, "audit")
    assert hasattr(pipeline, "hitl")
    assert hasattr(pipeline, "permission")
    assert hasattr(pipeline, "cb_pool")


def test_governed_pipeline_set_as_default():
    pipeline = GovernedPipeline()
    pipeline.set_as_default()
    # 必须注册外层装配；注册内层会绕过 kill switch 与路由证据。
    assert get_default_pipeline() is pipeline


def test_governed_pipeline_govern_allows():
    pipeline = GovernedPipeline()
    from maref.governance.core_pipeline import GovernanceRequest, Verdict

    result = pipeline.govern(GovernanceRequest(action="file.read", agent_id="test", trust_score=80))
    assert result.verdict == Verdict.ALLOW


def test_governed_pipeline_govern_denies():
    pipeline = GovernedPipeline()
    from maref.governance.core_pipeline import GovernanceRequest

    result = pipeline.govern(
        GovernanceRequest(action="shell.exec", agent_id="test", trust_score=10)
    )
    assert result.verdict.value in ("DENY", "ASK_USER")


def test_governed_pipeline_integration_with_decorator():
    """GovernedPipeline set_as_default makes @governed work end-to-end."""
    pipeline = GovernedPipeline()
    pipeline.set_as_default()

    @governed(require="file.read")
    def read_file(path):
        return "content"

    assert read_file("/tmp/test.txt") == "content"


def test_governed_decorator_respects_kill_switch(tmp_path):
    """@governed 必须命中外层 kill switch，而不能只走内层管道。"""
    from maref.governance.kill_switch import KillScope

    pipeline = GovernedPipeline(audit_path=tmp_path / "audit.jsonl", hmac_key="test-key")
    pipeline.kill_switch.engage(KillScope.AGENT, "decorated", "runaway", "test")
    pipeline.set_as_default()

    @governed(require="file.read")
    def read_file():
        return "content"

    with pytest.raises(GovernanceDeniedError):
        read_file()


def test_governed_pipeline_decorator_blocks():
    pipeline = GovernedPipeline()
    pipeline.set_as_default()
    from maref.governance.core_pipeline import GovernancePipeline, Verdict
    from maref.governance.decorators import set_default_pipeline

    # Override with deny-all pipeline for the block test
    deny_pipe = GovernancePipeline(
        policy_rules=[(999, lambda req: (Verdict.DENY, "always deny", None))]
    )
    set_default_pipeline(deny_pipe)

    @governed(require="any.action")
    def do_something():
        return "done"

    with pytest.raises(GovernanceDeniedError):
        do_something()


def test_governed_pipeline_emits_policy_version_and_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("MAREF_POLICY_VERSION", "v-test")
    monkeypatch.setenv("MAREF_POLICY_EPOCH", "epoch-1")
    pipeline = GovernedPipeline(audit_path=tmp_path / "audit.jsonl", hmac_key="test-key")
    from maref.governance.core_pipeline import GovernanceRequest

    result = pipeline.govern(GovernanceRequest(action="file.read", agent_id="test", trust_score=80))
    assert result.policy_version == "v-test"
    assert result.policy_epoch == "epoch-1"
    assert result.evidence_id
    assert pipeline.verify_evidence(result.evidence_id) is True
    assert pipeline.verify_evidence(result.evidence_id) is False


def test_governed_pipeline_rejects_expired_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("MAREF_EVIDENCE_TTL_SECONDS", "1")
    pipeline = GovernedPipeline(audit_path=tmp_path / "audit.jsonl", hmac_key="test-key")
    from maref.governance.core_pipeline import GovernanceRequest

    result = pipeline.govern(GovernanceRequest(action="file.read", agent_id="test", trust_score=80))
    assert pipeline.verify_evidence(result.evidence_id, now=time.time() + 10) is False


def test_governed_pipeline_evidence_can_be_checked_without_consuming(tmp_path):
    pipeline = GovernedPipeline(audit_path=tmp_path / "audit.jsonl", hmac_key="test-key")
    from maref.governance.core_pipeline import GovernanceRequest

    result = pipeline.govern(GovernanceRequest(action="file.read", agent_id="test", trust_score=80))
    assert pipeline.verify_evidence(result.evidence_id, consume=False) is True
    assert pipeline.verify_evidence(result.evidence_id, consume=False) is True
    assert pipeline.verify_evidence(result.evidence_id) is True
    assert pipeline.verify_evidence("missing-evidence") is False


class _RecordingExporter:
    def __init__(self) -> None:
        self.decisions = []
        self.evidence_checks = []

    def record_decision(self, request, result) -> None:
        self.decisions.append((request, result))

    def record_evidence_check(self, evidence_id, valid, reason="") -> None:
        self.evidence_checks.append((evidence_id, valid, reason))


def test_otel_exporter_receives_decision_and_evidence_check(tmp_path):
    exporter = _RecordingExporter()
    pipeline = GovernedPipeline(
        audit_path=tmp_path / "audit.jsonl",
        hmac_key="test-key",
        otel_exporter=exporter,
    )
    from maref.governance.core_pipeline import GovernanceRequest

    result = pipeline.govern(GovernanceRequest(action="file.read", agent_id="test", trust_score=80))
    assert len(exporter.decisions) == 1
    assert exporter.decisions[0][1] is result
    assert pipeline.verify_evidence(result.evidence_id) is True
    assert exporter.evidence_checks[0][1] is True


def test_evidence_consumption_survives_pipeline_restart(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    pipeline = GovernedPipeline(audit_path=audit_path, hmac_key="test-key")
    from maref.governance.core_pipeline import GovernanceRequest

    result = pipeline.govern(GovernanceRequest(action="file.read", agent_id="test", trust_score=80))
    assert pipeline.verify_evidence(result.evidence_id) is True
    assert (tmp_path / "audit.jsonl.consumed.jsonl").exists()

    restarted = GovernedPipeline(audit_path=audit_path, hmac_key="test-key")
    assert restarted.verify_evidence(result.evidence_id) is False
