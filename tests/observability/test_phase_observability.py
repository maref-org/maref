"""Tests for Phase O: Full-Stack Observability."""

from __future__ import annotations

import pytest

from maref.observability.red_metrics import REDMetricsCollector, RequestMetric
from maref.observability.trace_context import (
    clear_trace_context,
    get_current_trace_id,
    get_trace_context,
    inject_trace_context,
    set_trace_context,
)


class TestTraceContext:
    def setup_method(self) -> None:
        clear_trace_context()

    def teardown_method(self) -> None:
        clear_trace_context()

    def test_set_and_get_trace_id(self) -> None:
        set_trace_context(trace_id="test-trace-123")
        assert get_current_trace_id() == "test-trace-123"

    def test_inject_trace_headers(self) -> None:
        set_trace_context(trace_id="trace-abc")
        headers: dict[str, str] = {}
        result = inject_trace_context(headers)
        assert result["X-Trace-ID"] == "trace-abc"

    def test_inject_trace_headers_preserves_existing(self) -> None:
        set_trace_context(trace_id="trace-xyz")
        headers = {"Content-Type": "application/json"}
        result = inject_trace_context(headers)
        assert result["Content-Type"] == "application/json"
        assert result["X-Trace-ID"] == "trace-xyz"

    def test_clear_trace_context(self) -> None:
        set_trace_context(trace_id="to-be-cleared")
        clear_trace_context()
        assert get_current_trace_id() is None

    def test_trace_context_with_kwargs(self) -> None:
        set_trace_context(trace_id="trace-123", operation="test_op")
        ctx = get_trace_context()
        assert ctx["trace_id"] == "trace-123"
        assert ctx["operation"] == "test_op"


class TestREDMetricsCollector:
    @pytest.fixture
    def collector(self) -> REDMetricsCollector:
        return REDMetricsCollector()

    def test_record_request(self, collector: REDMetricsCollector) -> None:
        collector.record_request("/api/test", "GET", 200, 50.0)
        summary = collector.get_red_summary()
        assert summary["rate"]["total_requests"] == 1

    def test_error_recording(self, collector: REDMetricsCollector) -> None:
        collector.record_request("/api/fail", "POST", 500, 100.0)
        summary = collector.get_red_summary()
        assert summary["errors"]["total_errors"] == 1
        assert "5xx_server_error" in summary["errors"]["by_category"]

    def test_client_error_recording(self, collector: REDMetricsCollector) -> None:
        collector.record_request("/api/notfound", "GET", 404, 10.0)
        summary = collector.get_red_summary()
        assert summary["errors"]["total_errors"] == 1
        assert "4xx_client_error" in summary["errors"]["by_category"]

    def test_duration_percentiles(self, collector: REDMetricsCollector) -> None:
        for i in range(100):
            collector.record_request("/api/test", "GET", 200, float(i + 1))
        percentiles = collector.get_duration_percentiles()
        assert percentiles["p50"] == 50.5
        assert percentiles["min"] == 1.0
        assert percentiles["max"] == 100.0

    def test_percentiles_by_path(self, collector: REDMetricsCollector) -> None:
        for i in range(50):
            collector.record_request("/api/fast", "GET", 200, float(i + 1))
        for i in range(50):
            collector.record_request("/api/slow", "GET", 200, float(i + 100))

        fast_p95 = collector.get_duration_percentiles("/api/fast")
        slow_p95 = collector.get_duration_percentiles("/api/slow")

        assert fast_p95["p95"] < slow_p95["p95"]

    def test_get_path_metrics(self, collector: REDMetricsCollector) -> None:
        collector.record_request("/api/a", "GET", 200, 10.0)
        collector.record_request("/api/a", "GET", 200, 20.0)
        collector.record_request("/api/b", "POST", 500, 30.0)

        path_metrics = collector.get_path_metrics()
        assert "/api/a" in path_metrics
        assert "/api/b" in path_metrics
        assert path_metrics["/api/a"]["request_count"] == 2
        assert path_metrics["/api/b"]["error_count"] == 1

    def test_reset(self, collector: REDMetricsCollector) -> None:
        collector.record_request("/api/test", "GET", 200, 10.0)
        collector.reset()
        summary = collector.get_red_summary()
        assert summary["rate"]["total_requests"] == 0

    def test_error_rate(self, collector: REDMetricsCollector) -> None:
        collector.record_request("/api/ok", "GET", 200, 10.0)
        collector.record_request("/api/fail", "GET", 500, 10.0)
        collector.record_request("/api/ok2", "GET", 200, 10.0)
        error_rate = collector.get_error_rate()
        assert 0.3 <= error_rate <= 0.34

    def test_empty_percentiles(self, collector: REDMetricsCollector) -> None:
        percentiles = collector.get_duration_percentiles()
        assert percentiles["p50"] == 0.0
        assert percentiles["p95"] == 0.0
        assert percentiles["p99"] == 0.0

    def test_max_samples_trimming(self, collector: REDMetricsCollector) -> None:
        for i in range(REDMetricsCollector.MAX_SAMPLES + 100):
            collector.record_request("/api/test", "GET", 200, float(i))
        assert len(collector._metrics) <= REDMetricsCollector.MAX_SAMPLES


class TestRequestMetric:
    def test_success_is_not_error(self) -> None:
        m = RequestMetric(path="/ok", method="GET", status_code=200, duration_ms=10.0)
        assert m.is_error is False

    def test_4xx_is_error(self) -> None:
        m = RequestMetric(path="/fail", method="GET", status_code=404, duration_ms=10.0)
        assert m.is_error is True

    def test_5xx_is_error(self) -> None:
        m = RequestMetric(path="/fail", method="POST", status_code=500, duration_ms=10.0)
        assert m.is_error is True

    def test_timestamp_is_set(self) -> None:
        m = RequestMetric(path="/test", method="GET", status_code=200, duration_ms=10.0)
        assert m.timestamp > 0
