"""Unit tests for TaskMeteringEngine (federation metering)."""

from __future__ import annotations

import time

from maref.federation.metering import (
    TaskMeteringEngine,
    TaskMetric,
)


class TestTaskMetric:
    def test_to_dict_roundtrip(self) -> None:
        m = TaskMetric(
            metric_id="met_1",
            task_id="task_1",
            agent_did="did:maref:federated:abc",
            agent_aic="1.2.156.3088.1.2.1.1.v1.xx",
            provider_org="OrgA",
            consumer_org="OrgB",
            duration_ms=1500.0,
            token_count=500,
            success=True,
            complexity_score=0.8,
            metadata={"key": "value"},
        )
        d = m.to_dict()
        assert d["metric_id"] == "met_1"
        assert d["provider_org"] == "OrgA"
        assert d["consumer_org"] == "OrgB"
        assert d["success"] is True
        assert d["metadata"] == {"key": "value"}


class TestTaskMeteringRecord:
    def test_record_returns_metric_with_id(self) -> None:
        engine = TaskMeteringEngine()
        metric = engine.record(
            task_id="task-1",
            agent_did="did:1",
            agent_aic="aic:1",
            provider_org="OrgA",
            consumer_org="OrgB",
            duration_ms=1000.0,
            token_count=100,
            success=True,
            complexity_score=0.5,
        )
        assert metric.metric_id.startswith("met_")
        assert metric.task_id == "task-1"
        assert engine.metric_count == 1

    def test_record_clamps_complexity_score(self) -> None:
        engine = TaskMeteringEngine()
        high = engine.record(
            task_id="t", agent_did="d", agent_aic="a",
            provider_org="P", consumer_org="C",
            duration_ms=10, token_count=1, success=True,
            complexity_score=5.0,
        )
        low = engine.record(
            task_id="t", agent_did="d", agent_aic="a",
            provider_org="P", consumer_org="C",
            duration_ms=10, token_count=1, success=True,
            complexity_score=-1.0,
        )
        assert high.complexity_score == 1.0
        assert low.complexity_score == 0.0

    def test_record_clamps_duration_and_tokens(self) -> None:
        engine = TaskMeteringEngine()
        metric = engine.record(
            task_id="t", agent_did="d", agent_aic="a",
            provider_org="P", consumer_org="C",
            duration_ms=-100, token_count=-50, success=True,
            complexity_score=0.5,
        )
        assert metric.duration_ms == 0.0
        assert metric.token_count == 0

    def test_record_indexes_by_org_both_sides(self) -> None:
        engine = TaskMeteringEngine()
        engine.record(
            task_id="t", agent_did="d", agent_aic="a",
            provider_org="OrgA", consumer_org="OrgB",
            duration_ms=10, token_count=1, success=True, complexity_score=0.5,
        )
        # Both orgs should see this metric.
        assert len(engine.get_org_metrics("OrgA")) == 1
        assert len(engine.get_org_metrics("OrgB")) == 1

    def test_record_internal_task_only_indexes_once(self) -> None:
        engine = TaskMeteringEngine()
        engine.record(
            task_id="t", agent_did="d", agent_aic="a",
            provider_org="OrgA", consumer_org="OrgA",
            duration_ms=10, token_count=1, success=True, complexity_score=0.5,
        )
        # Same org → only one index entry (no duplicate).
        assert len(engine.get_org_metrics("OrgA")) == 1


class TestTaskMeteringQuery:
    def test_get_task_metrics(self) -> None:
        engine = TaskMeteringEngine()
        for i in range(3):
            engine.record(
                task_id="shared-task", agent_did=f"did:{i}", agent_aic=f"aic:{i}",
                provider_org="P", consumer_org="C",
                duration_ms=100, token_count=10, success=True, complexity_score=0.5,
            )
        engine.record(
            task_id="other-task", agent_did="did:x", agent_aic="aic:x",
            provider_org="P", consumer_org="C",
            duration_ms=100, token_count=10, success=True, complexity_score=0.5,
        )
        assert len(engine.get_task_metrics("shared-task")) == 3
        assert len(engine.get_task_metrics("other-task")) == 1
        assert engine.get_task_metrics("nonexistent") == []

    def test_get_org_metrics_with_since_filter(self) -> None:
        engine = TaskMeteringEngine()
        before = time.time()
        time.sleep(0.02)
        engine.record(
            task_id="t1", agent_did="d", agent_aic="a",
            provider_org="P", consumer_org="C",
            duration_ms=10, token_count=1, success=True, complexity_score=0.5,
        )
        after = time.time()
        # since=before → both metrics
        assert len(engine.get_org_metrics("P", since=before)) == 1
        # since=after → no metrics
        assert len(engine.get_org_metrics("P", since=after)) == 0

    def test_get_metric_by_id(self) -> None:
        engine = TaskMeteringEngine()
        metric = engine.record(
            task_id="t", agent_did="d", agent_aic="a",
            provider_org="P", consumer_org="C",
            duration_ms=10, token_count=1, success=True, complexity_score=0.5,
        )
        found = engine.get_metric(metric.metric_id)
        assert found is not None
        assert found.task_id == "t"
        assert engine.get_metric("nonexistent") is None

    def test_task_count(self) -> None:
        engine = TaskMeteringEngine()
        engine.record(task_id="t1", agent_did="d", agent_aic="a",
                       provider_org="P", consumer_org="C",
                       duration_ms=10, token_count=1, success=True, complexity_score=0.5)
        engine.record(task_id="t1", agent_did="d2", agent_aic="a2",
                       provider_org="P", consumer_org="C",
                       duration_ms=10, token_count=1, success=True, complexity_score=0.5)
        engine.record(task_id="t2", agent_did="d3", agent_aic="a3",
                       provider_org="P", consumer_org="C",
                       duration_ms=10, token_count=1, success=True, complexity_score=0.5)
        assert engine.metric_count == 3
        assert engine.task_count == 2  # t1 and t2


class TestTaskMeteringContribution:
    def test_single_agent_contribution_is_one(self) -> None:
        engine = TaskMeteringEngine()
        engine.record(
            task_id="solo", agent_did="did:1", agent_aic="aic:1",
            provider_org="P", consumer_org="C",
            duration_ms=1000, token_count=100, success=True, complexity_score=0.8,
        )
        scores = engine.compute_contribution("solo")
        assert len(scores) == 1
        assert abs(scores[0].contribution - 1.0) < 0.001

    def test_multi_agent_contributions_sum_to_one(self) -> None:
        engine = TaskMeteringEngine()
        for i in range(3):
            engine.record(
                task_id="multi", agent_did=f"did:{i}", agent_aic=f"aic:{i}",
                provider_org="P", consumer_org="C",
                duration_ms=1000 * (i + 1),
                token_count=100 * (i + 1),
                success=True,
                complexity_score=0.5 + i * 0.1,
            )
        scores = engine.compute_contribution("multi")
        assert len(scores) == 3
        total = sum(s.contribution for s in scores)
        assert abs(total - 1.0) < 0.001

    def test_contribution_sorted_descending(self) -> None:
        engine = TaskMeteringEngine()
        # Agent A does more work than Agent B.
        engine.record(
            task_id="sort", agent_did="did:A", agent_aic="aic:A",
            provider_org="P", consumer_org="C",
            duration_ms=5000, token_count=500, success=True, complexity_score=0.9,
        )
        engine.record(
            task_id="sort", agent_did="did:B", agent_aic="aic:B",
            provider_org="P", consumer_org="C",
            duration_ms=500, token_count=50, success=True, complexity_score=0.3,
        )
        scores = engine.compute_contribution("sort")
        assert scores[0].agent_did == "did:A"
        assert scores[1].agent_did == "did:B"
        assert scores[0].contribution > scores[1].contribution

    def test_contribution_empty_task(self) -> None:
        engine = TaskMeteringEngine()
        assert engine.compute_contribution("nonexistent") == []

    def test_contribution_factors_recorded(self) -> None:
        engine = TaskMeteringEngine()
        engine.record(
            task_id="t", agent_did="d", agent_aic="a",
            provider_org="P", consumer_org="C",
            duration_ms=1000, token_count=100, success=True, complexity_score=0.7,
        )
        scores = engine.compute_contribution("t")
        assert "duration" in scores[0].factors
        assert "tokens" in scores[0].factors
        assert "complexity" in scores[0].factors
        assert "success" in scores[0].factors


class TestTaskMeteringUsageSummary:
    def test_usage_summary_separates_provider_and_consumer(self) -> None:
        engine = TaskMeteringEngine()
        engine.record(
            task_id="t1", agent_did="d1", agent_aic="a1",
            provider_org="OrgA", consumer_org="OrgB",
            duration_ms=1000, token_count=100, success=True, complexity_score=0.5,
        )
        engine.record(
            task_id="t2", agent_did="d2", agent_aic="a2",
            provider_org="OrgC", consumer_org="OrgA",
            duration_ms=500, token_count=50, success=False, complexity_score=0.3,
        )
        now = time.time()
        summary = engine.generate_usage_summary("OrgA", now - 10, now + 10)
        assert summary["org"] == "OrgA"
        assert summary["as_provider"]["count"] == 1
        assert summary["as_provider"]["success_rate"] == 1.0
        assert summary["as_consumer"]["count"] == 1
        assert summary["as_consumer"]["success_rate"] == 0.0

    def test_usage_summary_period_filter(self) -> None:
        engine = TaskMeteringEngine()
        old = time.time() - 1000
        # We can't set timestamp directly in record(), so record now and
        # query a period that excludes it.
        engine.record(
            task_id="t", agent_did="d", agent_aic="a",
            provider_org="P", consumer_org="C",
            duration_ms=10, token_count=1, success=True, complexity_score=0.5,
        )
        # Period in the far past → no metrics.
        summary = engine.generate_usage_summary("P", old - 100, old - 50)
        assert summary["as_provider"]["count"] == 0
        assert summary["as_consumer"]["count"] == 0

    def test_usage_summary_empty_org(self) -> None:
        engine = TaskMeteringEngine()
        now = time.time()
        summary = engine.generate_usage_summary("NonexistentOrg", now - 10, now + 10)
        assert summary["as_provider"]["count"] == 0
        assert summary["as_consumer"]["count"] == 0


class TestTaskMeteringSummary:
    def test_metering_summary(self) -> None:
        engine = TaskMeteringEngine()
        engine.record(
            task_id="t1", agent_did="d1", agent_aic="a1",
            provider_org="OrgA", consumer_org="OrgB",
            duration_ms=10, token_count=1, success=True, complexity_score=0.5,
        )
        engine.record(
            task_id="t2", agent_did="d2", agent_aic="a2",
            provider_org="OrgB", consumer_org="OrgC",
            duration_ms=10, token_count=1, success=True, complexity_score=0.5,
        )
        summary = engine.metering_summary()
        assert summary["total_metrics"] == 2
        assert summary["total_tasks"] == 2
        assert summary["total_orgs"] == 3  # OrgA, OrgB, OrgC
        assert set(summary["orgs"]) == {"OrgA", "OrgB", "OrgC"}
