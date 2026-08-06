from __future__ import annotations

import json
import time

import pytest

from maref.recursive.observability import (
    GovernanceMetrics,
    RecursiveSpan,
    RecursiveTracer,
    StructuredLogger,
)
from maref.recursive.otel_dashboard import (
    MetricsDashboard,
    build_dashboard,
)


class TestRecursiveSpan:
    def test_span_creation(self) -> None:
        span = RecursiveSpan(
            span_id="span_001",
            parent_id=None,
            round_num=1,
            layer="inner",
            decision="observe",
            outcome=None,
            start_time=time.time(),
        )
        assert span.span_id == "span_001"
        assert span.parent_id is None
        assert span.round_num == 1
        assert span.layer == "inner"
        assert span.duration_ms >= 0

    def test_span_with_parent(self) -> None:
        span = RecursiveSpan(
            span_id="child",
            parent_id="parent",
            round_num=2,
            layer="outer",
            decision="analyze",
            outcome="success",
            start_time=time.time(),
        )
        assert span.parent_id == "parent"

    def test_span_finish_sets_end_time(self) -> None:
        span = RecursiveSpan("s", None, 1, "meta", "govern", None, time.time() - 1.0)
        assert span.end_time == 0.0
        span.finish()
        assert span.end_time > 0
        assert span.duration_ms >= 0

    def test_span_attributes(self) -> None:
        span = RecursiveSpan(
            "s", None, 1, "inner", "decision", "pending", time.time(), attributes={"key": "value"}
        )
        assert span.attributes["key"] == "value"

    def test_span_events(self) -> None:
        span = RecursiveSpan("s", None, 1, "inner", "d", None, time.time())
        span.events.append({"name": "event1", "timestamp": time.time()})
        assert len(span.events) == 1


class TestRecursiveTracer:
    @pytest.fixture
    def tracer(self) -> RecursiveTracer:
        return RecursiveTracer()

    def test_start_span_creates_span(self, tracer: RecursiveTracer) -> None:
        span = tracer.start_span(round_num=1, layer="inner")
        assert span.round_num == 1
        assert span.layer == "inner"
        assert tracer.span_count() == 1

    def test_start_span_auto_parent(self, tracer: RecursiveTracer) -> None:
        parent = tracer.start_span(1, "inner")
        child = tracer.start_span(1, "inner")
        assert child.parent_id == parent.span_id

    def test_start_span_explicit_parent(self, tracer: RecursiveTracer) -> None:
        child = tracer.start_span(2, "outer", parent_id="explicit_parent")
        assert child.parent_id == "explicit_parent"

    def test_end_span_finishes(self, tracer: RecursiveTracer) -> None:
        span = tracer.start_span(1, "inner")
        assert span.end_time == 0.0
        tracer.end_span(span.span_id, outcome="success")
        assert span.end_time > 0
        assert span.outcome == "success"

    def test_add_event_to_span(self, tracer: RecursiveTracer) -> None:
        span = tracer.start_span(1, "inner")
        tracer.add_event(span.span_id, "test_event", value=42)
        retrieved = tracer.get_span(span.span_id)
        assert retrieved is not None
        assert len(retrieved.events) == 1
        assert retrieved.events[0]["name"] == "test_event"

    def test_set_attribute(self, tracer: RecursiveTracer) -> None:
        span = tracer.start_span(1, "inner")
        tracer.set_attribute(span.span_id, "custom_key", "custom_value")
        retrieved = tracer.get_span(span.span_id)
        assert retrieved is not None
        assert retrieved.attributes["custom_key"] == "custom_value"

    def test_all_spans_returns_all(self, tracer: RecursiveTracer) -> None:
        tracer.start_span(1, "inner")
        tracer.start_span(2, "outer")
        tracer.start_span(3, "meta")
        assert len(tracer.all_spans()) == 3

    def test_spans_by_round(self, tracer: RecursiveTracer) -> None:
        tracer.start_span(1, "inner")
        tracer.start_span(1, "outer")
        tracer.start_span(2, "meta")
        r1 = tracer.spans_by_round(1)
        assert len(r1) == 2

    def test_spans_by_layer(self, tracer: RecursiveTracer) -> None:
        tracer.start_span(1, "inner")
        tracer.start_span(2, "inner")
        tracer.start_span(3, "meta")
        inner = tracer.spans_by_layer("inner")
        assert len(inner) == 2

    def test_span_hierarchy(self, tracer: RecursiveTracer) -> None:
        p = tracer.start_span(1, "meta")
        c = tracer.start_span(1, "inner")
        hierarchy = tracer.get_span_hierarchy()
        assert p.span_id in hierarchy
        assert c.span_id in hierarchy[p.span_id]

    def test_clear_empties_tracer(self, tracer: RecursiveTracer) -> None:
        tracer.start_span(1, "inner")
        tracer.clear()
        assert tracer.span_count() == 0
        assert len(tracer.all_spans()) == 0

    def test_get_span_returns_none_for_unknown(self, tracer: RecursiveTracer) -> None:
        assert tracer.get_span("nonexistent") is None

    def test_end_span_updates_stack(self, tracer: RecursiveTracer) -> None:
        s1 = tracer.start_span(1, "meta")
        s2 = tracer.start_span(1, "inner")
        tracer.end_span(s2.span_id)
        assert tracer._span_stack == [s1.span_id]

    def test_multi_round_spans(self, tracer: RecursiveTracer) -> None:
        for r in range(1, 11):
            tracer.start_span(r, "inner")
        assert tracer.span_count() == 10
        for r in range(1, 11):
            assert len(tracer.spans_by_round(r)) == 1


class TestGovernanceMetrics:
    def test_default_values(self) -> None:
        m = GovernanceMetrics()
        assert m.cb_trips_total == 0
        assert m.survival_rate == 1.0

    def test_record_cb_trip(self) -> None:
        m = GovernanceMetrics()
        m.record_cb_trip()
        assert m.cb_trips_total == 1

    def test_record_heal_success(self) -> None:
        m = GovernanceMetrics()
        m.record_heal(success=True, cycle_count=2)
        assert m.heal_attempts == 1
        assert m.heal_success_rate == 1.0
        assert m.avg_heal_cycle_count == 2.0

    def test_record_heal_failure(self) -> None:
        m = GovernanceMetrics()
        m.record_heal(success=True, cycle_count=1)
        m.record_heal(success=False, cycle_count=3)
        assert m.heal_attempts == 2
        assert m.heal_success_rate == 0.5

    def test_record_optimization(self) -> None:
        m = GovernanceMetrics()
        m.record_optimization(adopted=True)
        m.record_optimization(adopted=True)
        m.record_optimization(adopted=False)
        assert m.optimization_proposals == 3
        assert m.optimization_adoptions == 2
        assert m.adoption_rate == 2.0 / 3.0

    def test_record_chaos(self) -> None:
        m = GovernanceMetrics()
        m.record_chaos(survived=True, recovery_time_ms=100.0)
        m.record_chaos(survived=True, recovery_time_ms=200.0)
        assert m.chaos_injections_total == 2
        assert m.survival_rate == 1.0
        assert m.avg_recovery_time_ms == 150.0

    def test_to_dict_non_zero(self) -> None:
        m = GovernanceMetrics()
        m.record_cb_trip()
        m.record_heal(success=True, cycle_count=1)
        m.record_optimization(adopted=True)
        m.record_chaos(survived=True, recovery_time_ms=50.0)
        d = m.to_dict()
        assert d["cb_trips_total"] == 1
        assert d["heal_attempts"] == 1

    def test_to_dict_json_serializable(self) -> None:
        m = GovernanceMetrics()
        m.record_cb_trip()
        try:
            json.dumps(m.to_dict())
        except (TypeError, ValueError) as e:
            pytest.fail(f"Not JSON serializable: {e}")


class TestStructuredLogger:
    @pytest.fixture
    def logger(self) -> StructuredLogger:
        return StructuredLogger()

    def test_log_entry(self, logger: StructuredLogger) -> None:
        logger.log("INFO", "test message", component="governance")
        assert logger.count() == 1

    def test_by_level(self, logger: StructuredLogger) -> None:
        logger.log("INFO", "msg1")
        logger.log("ERROR", "msg2")
        logger.log("INFO", "msg3")
        assert len(logger.by_level("INFO")) == 2
        assert len(logger.by_level("ERROR")) == 1

    def test_clear(self, logger: StructuredLogger) -> None:
        logger.log("INFO", "msg")
        logger.clear()
        assert logger.count() == 0

    def test_to_json(self, logger: StructuredLogger) -> None:
        logger.log("INFO", "test", key="val")
        json_str = logger.to_json()
        parsed = json.loads(json_str)
        assert len(parsed) == 1


class TestMetricsDashboard:
    def test_dashboard_creation(self) -> None:
        dash = MetricsDashboard(
            timestamp=time.time(),
            metrics={"cb_trips_total": 5, "survival_rate": 0.8},
            health_status="DEGRADED",
        )
        assert dash.health_status == "DEGRADED"

    def test_dashboard_to_dict(self) -> None:
        dash = MetricsDashboard(time.time(), {}, "HEALTHY")
        d = dash.to_dict()
        assert "timestamp" in d
        assert "metrics" in d
        assert "health_status" in d

    def test_dashboard_to_json(self) -> None:
        dash = MetricsDashboard(time.time(), {"cb_trips_total": 1}, "HEALTHY")
        json_str = dash.to_json()
        parsed = json.loads(json_str)
        assert parsed["health_status"] == "HEALTHY"

    def test_build_dashboard(self) -> None:
        dash = build_dashboard({"cb_trips_total": 3}, status="WARNING")
        assert dash.health_status == "WARNING"
        assert dash.metrics["cb_trips_total"] == 3

    def test_dashboard_empty_metrics(self) -> None:
        dash = MetricsDashboard(time.time(), {}, "HEALTHY")
        d = dash.to_dict()
        assert d["metrics"]["cb_trips_total"] == 0
        assert d["metrics"]["survival_rate"] == 1.0


class TestObservabilityE2E:
    def test_full_span_lifecycle(self) -> None:
        tracer = RecursiveTracer()
        span = tracer.start_span(round_num=1, layer="inner", decision="observe")
        tracer.add_event(span.span_id, "probe_started")
        tracer.set_attribute(span.span_id, "module", "governance")
        tracer.end_span(span.span_id, outcome="success")

        retrieved = tracer.get_span(span.span_id)
        assert retrieved is not None
        assert retrieved.outcome == "success"
        assert retrieved.end_time > 0
        assert len(retrieved.events) == 1

    def test_nested_spans_hierarchy(self) -> None:
        tracer = RecursiveTracer()
        meta = tracer.start_span(5, "meta", decision="wrap")
        inner = tracer.start_span(5, "inner", decision="govern")
        outer = tracer.start_span(5, "outer", decision="monitor")

        hierarchy = tracer.get_span_hierarchy()
        assert meta.span_id in hierarchy
        children_of_meta = hierarchy[meta.span_id]
        assert inner.span_id in children_of_meta
        assert inner.span_id in hierarchy
        children_of_inner = hierarchy[inner.span_id]
        assert outer.span_id in children_of_inner

    def test_metrics_dashboard_pipeline(self) -> None:
        metrics = GovernanceMetrics()
        metrics.record_cb_trip()
        metrics.record_heal(success=True, cycle_count=2)
        metrics.record_optimization(adopted=True)

        dash = build_dashboard(metrics.to_dict())
        assert dash.health_status == "HEALTHY"
        assert dash.metrics["cb_trips_total"] == 1

    def test_structured_log_governance(self) -> None:
        logger = StructuredLogger()
        logger.log("INFO", "governance cycle started", round=1)
        logger.log("WARN", "entropy spike detected", round=1, entropy=4.5)
        logger.log("INFO", "force stabilize applied", round=2)

        assert logger.count() == 3
        assert len(logger.by_level("WARN")) == 1
