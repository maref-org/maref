"""Tests for the governance data flywheel (P1-C)."""

from __future__ import annotations

from pathlib import Path

from maref.governance.audit import AuditEntry, AuditLogger
from maref.governance.value_flywheel import GovernanceFlywheel


def _entry(
    index: int,
    verdict: str,
    *,
    action: str = "file.read",
    timestamp: float = 1000.0,
    signed: bool = True,
) -> AuditEntry:
    return AuditEntry(
        id=f"e{index}",
        timestamp=timestamp + index,
        event_type="governance_decision",
        actor="agent-1",
        action=action,
        details=f"{verdict}: reason-{index}",
        metadata={"policy_version": "v1"},
        hmac_signature="sig" if signed else "",
    )


def test_collects_verdicts_and_coverage():
    entries = [
        _entry(0, "ALLOW"),
        _entry(1, "DENY"),
        _entry(2, "ASK_USER"),
        _entry(3, "ALLOW", signed=False),
    ]
    kpis = GovernanceFlywheel().collect(entries, since=0, now=2000)
    assert kpis.decisions == 4
    assert kpis.allow == 2
    assert kpis.deny == 1
    assert kpis.ask_user == 1
    assert kpis.deny_rate == 0.25
    assert kpis.hitl_rate == 0.25
    assert kpis.evidence_coverage == 0.75
    assert kpis.policy_versions == {"v1": 4}


def test_deny_trend_is_computed():
    entries = [
        _entry(0, "ALLOW", timestamp=100),
        _entry(1, "ALLOW", timestamp=110),
        _entry(2, "DENY", timestamp=200),
        _entry(3, "DENY", timestamp=210),
    ]
    kpis = GovernanceFlywheel().collect(entries, since=100, now=220)
    assert kpis.deny_rate_trend == 1.0


def test_feedback_is_persisted_and_summarized(tmp_path: Path):
    path = tmp_path / "feedback.jsonl"
    flywheel = GovernanceFlywheel(path)
    flywheel.record_feedback("e1", "override", reviewer="alice", score=2.0)
    flywheel.record_feedback("e2", "approve", reviewer="bob", score=4.0)
    summary = flywheel.feedback_summary()
    assert summary["count"] == 2
    assert summary["outcomes"] == {"override": 1, "approve": 1}
    assert summary["average_score"] == 3.0


def test_invalid_feedback_outcome_rejected():
    flywheel = GovernanceFlywheel()
    try:
        flywheel.record_feedback("e1", "maybe")
    except ValueError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_recommends_policy_review_and_signing():
    entries = [_entry(i, "DENY", signed=False) for i in range(10)]
    report = GovernanceFlywheel().run_cycle(entries, since=0, now=2000)
    actions = {item["action"] for item in report.recommendations}
    assert "review_deny_policy" in actions
    assert "enable_signed_audit" in actions


def test_cycle_uses_feedback_override_rate(tmp_path: Path):
    path = tmp_path / "feedback.jsonl"
    flywheel = GovernanceFlywheel(path)
    for index in range(4):
        flywheel.record_feedback(f"e{index}", "override")
    entries = [_entry(0, "ALLOW")]
    report = flywheel.run_cycle(entries, since=0, now=2000)
    actions = {item["action"] for item in report.recommendations}
    assert "tighten_false_positive_loop" in actions


def test_audit_logger_entries_can_feed_flywheel(tmp_path: Path):
    logger = AuditLogger(log_path=tmp_path / "audit.jsonl", hmac_key="test-key")
    logger.log(
        event_type="governance_decision",
        actor="agent-1",
        action="file.read",
        details="ALLOW: ok",
        metadata={"policy_version": "v1"},
    )
    kpis = GovernanceFlywheel().collect(logger.read_all(), since=0)
    assert kpis.decisions == 1
    assert kpis.allow == 1
    assert kpis.evidence_coverage == 1.0
