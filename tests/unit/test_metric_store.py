from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from maref.observability.metric_store import MetricStore, _validate_table


@pytest.fixture
def store() -> MetricStore:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    ms = MetricStore(db_path=db_path)
    yield ms
    ms.close()
    if db_path.exists():
        db_path.unlink()


class TestInit:
    def test_init_creates_tables(self, store: MetricStore) -> None:
        stats = store.get_table_stats()
        expected = {"governance_metrics", "guardrail_metrics", "cost_metrics", "telemetry_metrics"}
        assert set(stats.keys()) == expected


class TestRecordAndQuery:
    def test_record_and_query_round_trip(self, store: MetricStore) -> None:
        store.record("test_metric", 42.0, labels={"env": "test"}, agent_id="agent-1", table="telemetry_metrics")
        results = store.query("test_metric", table="telemetry_metrics")
        assert len(results) == 1
        assert results[0]["value"] == 42.0
        assert results[0]["name"] == "test_metric"
        assert results[0]["agent_id"] == "agent-1"
        assert results[0]["labels"] == {"env": "test"}

    def test_record_multiple_tables(self, store: MetricStore) -> None:
        store.record("cost", 10.0, agent_id="a1", table="cost_metrics")
        store.record("cost", 20.0, agent_id="a2", table="cost_metrics")
        store.record("cost", 30.0, agent_id="a1", table="governance_metrics")
        results_cost = store.query("cost", table="cost_metrics")
        results_gov = store.query("cost", table="governance_metrics")
        assert len(results_cost) == 2
        assert len(results_gov) == 1


class TestQueryFilters:
    def test_query_with_since(self, store: MetricStore) -> None:
        store.record("latency", 5.0, table="telemetry_metrics")
        store.record("latency", 10.0, table="telemetry_metrics")
        results = store.query("latency", since="2099-01-01T00:00:00Z", table="telemetry_metrics")
        assert len(results) == 0

    def test_query_with_agent_id(self, store: MetricStore) -> None:
        store.record("cpu", 0.5, agent_id="agent-foo", table="telemetry_metrics")
        store.record("cpu", 0.8, agent_id="agent-bar", table="telemetry_metrics")
        results = store.query("cpu", agent_id="agent-foo", table="telemetry_metrics")
        assert len(results) == 1
        assert results[0]["agent_id"] == "agent-foo"


class TestQueryAggregate:
    def test_aggregate_avg(self, store: MetricStore) -> None:
        store.record("latency", 10.0, table="telemetry_metrics")
        store.record("latency", 20.0, table="telemetry_metrics")
        store.record("latency", 30.0, table="telemetry_metrics")
        avg = store.query_aggregate("latency", operation="avg", table="telemetry_metrics")
        assert avg == 20.0

    def test_aggregate_sum(self, store: MetricStore) -> None:
        store.record("latency", 10.0, table="telemetry_metrics")
        store.record("latency", 20.0, table="telemetry_metrics")
        total = store.query_aggregate("latency", operation="sum", table="telemetry_metrics")
        assert total == 30.0

    def test_aggregate_max(self, store: MetricStore) -> None:
        store.record("latency", 10.0, table="telemetry_metrics")
        store.record("latency", 20.0, table="telemetry_metrics")
        store.record("latency", 15.0, table="telemetry_metrics")
        mx = store.query_aggregate("latency", operation="max", table="telemetry_metrics")
        assert mx == 20.0

    def test_aggregate_min(self, store: MetricStore) -> None:
        store.record("latency", 10.0, table="telemetry_metrics")
        store.record("latency", 20.0, table="telemetry_metrics")
        mn = store.query_aggregate("latency", operation="min", table="telemetry_metrics")
        assert mn == 10.0

    def test_aggregate_count(self, store: MetricStore) -> None:
        store.record("latency", 10.0, table="telemetry_metrics")
        store.record("latency", 20.0, table="telemetry_metrics")
        store.record("latency", 30.0, table="telemetry_metrics")
        cnt = store.query_aggregate("latency", operation="count", table="telemetry_metrics")
        assert cnt == 3.0

    def test_aggregate_across_tables(self, store: MetricStore) -> None:
        store.record("shared_metric", 100.0, table="governance_metrics")
        store.record("shared_metric", 200.0, table="guardrail_metrics")
        avg = store.query_aggregate("shared_metric", operation="avg")
        assert avg == 150.0

    def test_aggregate_no_results(self, store: MetricStore) -> None:
        val = store.query_aggregate("nonexistent", operation="avg", table="telemetry_metrics")
        assert val == 0.0


class TestPrune:
    def test_prune_deletes_old_entries(self, store: MetricStore) -> None:
        store.record("old_metric", 1.0, table="telemetry_metrics")
        deleted = store.prune(retention_days=-1)
        assert deleted >= 1
        results = store.query("old_metric", table="telemetry_metrics")
        assert len(results) == 0

    def test_prune_keeps_recent_entries(self, store: MetricStore) -> None:
        store.record("recent_metric", 1.0, table="telemetry_metrics")
        deleted = store.prune(retention_days=36500)
        assert deleted == 0
        results = store.query("recent_metric", table="telemetry_metrics")
        assert len(results) == 1


class TestGetTableStats:
    def test_get_table_stats(self, store: MetricStore) -> None:
        store.record("m1", 1.0, table="telemetry_metrics")
        store.record("m2", 2.0, table="cost_metrics")
        stats = store.get_table_stats()
        assert stats["telemetry_metrics"] == 1
        assert stats["cost_metrics"] == 1
        assert stats["governance_metrics"] == 0
        assert stats["guardrail_metrics"] == 0

    def test_get_table_stats_empty(self, store: MetricStore) -> None:
        stats = store.get_table_stats()
        assert all(v == 0 for v in stats.values())


class TestClose:
    def test_close(self, store: MetricStore) -> None:
        store.close()
        store.close()


class TestValidateTable:
    def test_invalid_table_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown table"):
            _validate_table("nonexistent_table")
