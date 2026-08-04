"""Tests for ValueTrackingEngine (v0.51 W2-S2 / B2).

Covers value capture, aggregation by agent/team/org scope, and HMAC-signed
audit linkage.
"""

from __future__ import annotations

import os

import pytest

from maref.value.metrics import ValueMetric, ValueMetricType
from maref.value.tracking import ValueRecord, ValueTrackingEngine


@pytest.fixture(autouse=True)
def _hmac_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAREF_VALUE_HMAC_KEY", "test-value-key")


def _record(agent: str = "agent-a", team: str = "team-1", org: str = "org-x") -> ValueRecord:
    return ValueRecord(
        task_id="task-1",
        agent_id=agent,
        team_id=team,
        org_id=org,
        metrics=(
            ValueMetric(
                metric_type=ValueMetricType.HOURS_SAVED,
                baseline=100.0,
                current=150.0,
                unit="hours",
            ),
        ),
    )


def test_capture_and_count() -> None:
    engine = ValueTrackingEngine()
    engine.capture(_record())
    assert engine.count() == 1


def test_aggregate_by_agent() -> None:
    engine = ValueTrackingEngine()
    engine.capture(_record(agent="agent-a"))
    engine.capture(_record(agent="agent-b"))
    engine.capture(_record(agent="agent-a"))
    agg = engine.aggregate(scope="agent", scope_id="agent-a")
    assert agg["record_count"] == 2
    assert agg["totals"]["hours_saved"]["delta"] == 100.0


def test_aggregate_by_team() -> None:
    engine = ValueTrackingEngine()
    engine.capture(_record(agent="a1", team="team-1"))
    engine.capture(_record(agent="a2", team="team-1"))
    engine.capture(_record(agent="a3", team="team-2"))
    agg = engine.aggregate(scope="team", scope_id="team-1")
    assert agg["record_count"] == 2


def test_aggregate_by_org() -> None:
    engine = ValueTrackingEngine()
    engine.capture(_record(agent="a1", org="org-x"))
    engine.capture(_record(agent="a2", org="org-y"))
    agg = engine.aggregate(scope="org", scope_id="org-x")
    assert agg["record_count"] == 1


def test_aggregate_totals_multiple_metric_types() -> None:
    engine = ValueTrackingEngine()
    rec = ValueRecord(
        task_id="t1",
        agent_id="agent-a",
        team_id="team-1",
        org_id="org-x",
        metrics=(
            ValueMetric(metric_type=ValueMetricType.HOURS_SAVED, current=10.0),
            ValueMetric(metric_type=ValueMetricType.CYCLE_TIME, current=5.0),
        ),
    )
    engine.capture(rec)
    agg = engine.aggregate(scope="org", scope_id="org-x")
    assert agg["totals"]["hours_saved"]["delta"] == 10.0
    assert agg["totals"]["cycle_time"]["delta"] == 5.0


def test_records_have_hmac_signature() -> None:
    engine = ValueTrackingEngine()
    engine.capture(_record())
    stored = engine.records()[0]
    assert stored.signature
    assert len(stored.signature) == 64  # sha256 hex


def test_missing_hmac_key_fails_closed() -> None:
    os.environ.pop("MAREF_VALUE_HMAC_KEY", None)
    engine = ValueTrackingEngine()
    with pytest.raises(ValueError):
        engine.capture(_record())


def test_record_serialization() -> None:
    engine = ValueTrackingEngine()
    engine.capture(_record())
    d = engine.records()[0].to_dict()
    assert d["task_id"] == "task-1"
    assert d["agent_id"] == "agent-a"
    assert d["metrics"][0]["metric_type"] == "hours_saved"
