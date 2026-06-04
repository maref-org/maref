"""Phase 6 测试：遥测与进化对接 — HarnessTelemetryCollector + EvolutionDataFeed。"""

from __future__ import annotations

from unittest.mock import MagicMock

from maref.execution.telemetry.collector import HarnessTelemetryCollector, TelemetryEvent
from maref.execution.telemetry.evolution_feed import EvolutionDataFeed
from maref.observation.probes import ProbeSeverity


# ── HarnessTelemetryCollector ───────────────────────────────────────────────

class TestHarnessTelemetryCollector:
    def test_record_event(self) -> None:
        c = HarnessTelemetryCollector()
        c.record_event(harness_id="h1", lifecycle_stage="run", latency_ms=10.0)
        assert c.event_count == 1

    def test_record_via_event_object(self) -> None:
        c = HarnessTelemetryCollector()
        c.record(TelemetryEvent(harness_id="h2", lifecycle_stage="start"))
        assert c.event_count == 1

    def test_report_empty(self) -> None:
        c = HarnessTelemetryCollector()
        r = c.report()
        assert r.total_events == 0

    def test_report_summary(self) -> None:
        c = HarnessTelemetryCollector()
        c.record_event(harness_id="h1", lifecycle_stage="start", tool_calls=5, token_count=100)
        c.record_event(harness_id="h1", lifecycle_stage="step", tool_calls=3, token_count=50)
        c.record_event(harness_id="h1", lifecycle_stage="stop", latency_ms=20.0)
        r = c.report()
        assert r.total_events == 3
        assert r.total_tool_calls == 8
        assert r.total_token_count == 150
        assert r.total_duration_ms == 20.0

    def test_report_error_count(self) -> None:
        c = HarnessTelemetryCollector()
        c.record_event(harness_id="h1", lifecycle_stage="start")
        c.record_event(harness_id="h1", lifecycle_stage="fail", error="crash")
        c.record_event(harness_id="h1", lifecycle_stage="stop", error="timeout")
        r = c.report()
        assert r.error_count == 2

    def test_report_stage_summary(self) -> None:
        c = HarnessTelemetryCollector()
        c.record_event(lifecycle_stage="start")
        c.record_event(lifecycle_stage="step")
        c.record_event(lifecycle_stage="step")
        c.record_event(lifecycle_stage="stop")
        r = c.report()
        assert r.stage_summary == {"start": 1, "step": 2, "stop": 1}

    def test_report_harness_summary(self) -> None:
        c = HarnessTelemetryCollector()
        c.record_event(harness_id="h1")
        c.record_event(harness_id="h1")
        c.record_event(harness_id="h2")
        r = c.report()
        assert r.harness_summary == {"h1": 2, "h2": 1}

    def test_clear(self) -> None:
        c = HarnessTelemetryCollector()
        c.record_event(harness_id="h1")
        c.clear()
        assert c.event_count == 0

    def test_report_events_list(self) -> None:
        c = HarnessTelemetryCollector()
        c.record_event(harness_id="h1", lifecycle_stage="start")
        r = c.report()
        assert len(r.events) == 1
        assert r.events[0]["harness_id"] == "h1"
        assert r.events[0]["lifecycle_stage"] == "start"


# ── EvolutionDataFeed ──────────────────────────────────────────────────────

class TestEvolutionDataFeed:
    def test_to_readings(self) -> None:
        c = HarnessTelemetryCollector()
        c.record_event(harness_id="h1", lifecycle_stage="start", tool_calls=5)
        c.record_event(harness_id="h1", lifecycle_stage="stop", error="err")
        feed = EvolutionDataFeed()
        readings = feed.to_readings(c.report())
        assert len(readings) >= 5  # 5 base metrics + stage entries
        probe_names = [r.probe_name for r in readings]
        assert "harness.total_events" in probe_names
        assert "harness.total_tool_calls" in probe_names
        assert "harness.error_count" in probe_names
        assert "harness.stage.start" in probe_names
        assert "harness.stage.stop" in probe_names

    def test_error_count_warning_severity(self) -> None:
        c = HarnessTelemetryCollector()
        c.record_event(error="fail")
        feed = EvolutionDataFeed()
        readings = feed.to_readings(c.report())
        for r in readings:
            if r.probe_name == "harness.error_count":
                assert r.severity == ProbeSeverity.WARNING
                break

    def test_no_errors_info_severity(self) -> None:
        c = HarnessTelemetryCollector()
        c.record_event(lifecycle_stage="start")
        feed = EvolutionDataFeed()
        readings = feed.to_readings(c.report())
        for r in readings:
            if r.probe_name == "harness.error_count":
                assert r.severity == ProbeSeverity.NORMAL
                break

    def test_feed_writes_to_observer(self) -> None:
        c = HarnessTelemetryCollector()
        c.record_event(harness_id="h1", lifecycle_stage="run")
        observer = MagicMock()
        observer.probe_readings = []
        feed = EvolutionDataFeed()
        readings = feed.feed(c.report(), observer)
        assert len(readings) > 0
        assert len(observer.probe_readings) > 0
