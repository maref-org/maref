"""Tests for B3: outcome_quality participates in settlement (v0.51 W2-S3).

The contribution score should factor result quality (attainment / output
usability) into settlement so that results, not just effort, are priced.
The weight defaults to 0.0 for backward compatibility and is enabled per
tenant by the operator.
"""

from __future__ import annotations

from maref.federation.metering import TaskMeteringEngine


def _record_task(
    engine: TaskMeteringEngine,
    task_id: str,
    agent_did: str,
    duration_ms: float = 1000.0,
    token_count: int = 100,
    success: bool = True,
    complexity: float = 0.5,
    outcome_quality: float = 0.0,
) -> None:
    engine.record(
        task_id=task_id,
        agent_did=agent_did,
        agent_aic=f"aic_{agent_did}",
        provider_org="org-a",
        consumer_org="org-b",
        duration_ms=duration_ms,
        token_count=token_count,
        success=success,
        complexity_score=complexity,
        outcome_quality=outcome_quality,
    )


def test_metric_stores_outcome_quality() -> None:
    engine = TaskMeteringEngine()
    _record_task(engine, "t1", "agent-1", outcome_quality=0.9)
    metric = engine.get_task_metrics("t1")[0]
    assert metric.outcome_quality == 0.9


def test_outcome_quality_default_zero() -> None:
    engine = TaskMeteringEngine()
    engine.record(
        task_id="t1",
        agent_did="agent-1",
        agent_aic="aic_1",
        provider_org="org-a",
        consumer_org="org-b",
        duration_ms=1000.0,
        token_count=100,
        success=True,
        complexity_score=0.5,
    )
    assert engine.get_task_metrics("t1")[0].outcome_quality == 0.0


def test_outcome_quality_clamped_to_unit_interval() -> None:
    engine = TaskMeteringEngine()
    engine.record(
        task_id="t1",
        agent_did="agent-1",
        agent_aic="aic_1",
        provider_org="org-a",
        consumer_org="org-b",
        duration_ms=1000.0,
        token_count=100,
        success=True,
        complexity_score=0.5,
        outcome_quality=1.7,
    )
    assert engine.get_task_metrics("t1")[0].outcome_quality == 1.0


def test_outcome_quality_zero_weight_backward_compatible() -> None:
    """Default engine (weight=0) reproduces v0.50 contribution semantics."""
    engine = TaskMeteringEngine()
    _record_task(engine, "t1", "agent-good", duration_ms=2000, outcome_quality=1.0)
    _record_task(engine, "t1", "agent-bad", duration_ms=1000, outcome_quality=0.0)
    scores = engine.compute_contribution("t1")
    by_agent = {s.agent_did: s.contribution for s in scores}
    # 无 quality 权重时，贡献与 effort 成正比（duration 权重 0.3）
    assert by_agent["agent-good"] > by_agent["agent-bad"]
    assert abs(by_agent["agent-good"] + by_agent["agent-bad"] - 1.0) < 1e-6


def test_outcome_quality_weight_shifts_contribution() -> None:
    """Enabled quality weight: high-quality agent gains, low-quality loses."""
    engine = TaskMeteringEngine(outcome_quality_weight=0.3)
    # 两名 agent 消耗完全相同的 effort
    _record_task(engine, "t1", "agent-good", duration_ms=1000, token_count=100, outcome_quality=1.0)
    _record_task(engine, "t1", "agent-bad", duration_ms=1000, token_count=100, outcome_quality=0.0)
    scores = engine.compute_contribution("t1")
    by_agent = {s.agent_did: s.contribution for s in scores}
    assert by_agent["agent-good"] > by_agent["agent-bad"]
    # quality 优势应显著（0.3 权重在 effort 相同的竞争场景产生 ≥0.15 贡献差）
    assert by_agent["agent-good"] - by_agent["agent-bad"] >= 0.15


def test_contribution_factors_include_quality() -> None:
    engine = TaskMeteringEngine(outcome_quality_weight=0.3)
    _record_task(engine, "t1", "agent-1", outcome_quality=0.8)
    score = engine.compute_contribution("t1")[0]
    assert "outcome_quality" in score.factors
    assert score.factors["outcome_quality"] == 0.8
