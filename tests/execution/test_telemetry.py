from __future__ import annotations

from maref.execution.telemetry import (
    EvolutionDataFeed,
    HarnessTelemetryCollector,
    TelemetryEvent,
    TelemetryReport,
)


class TestTelemetryEvent:
    def test_values(self) -> None:
        assert TelemetryEvent.STEP_STARTED.value == "step_started"
        assert TelemetryEvent.STEP_COMPLETED.value == "step_completed"
        assert TelemetryEvent.STEP_FAILED.value == "step_failed"
        assert TelemetryEvent.RUN_STARTED.value == "run_started"
        assert TelemetryEvent.RUN_COMPLETED.value == "run_completed"
        assert TelemetryEvent.RUN_FAILED.value == "run_failed"
        assert len(TelemetryEvent) == 6


class TestHarnessTelemetryCollector:
    def test_default_state(self) -> None:
        c = HarnessTelemetryCollector()
        report = c.report("test-run")
        assert isinstance(report, TelemetryReport)
        assert report.run_id == "test-run"
        assert report.events == []

    def test_record_event(self) -> None:
        c = HarnessTelemetryCollector()
        c.record(TelemetryEvent.STEP_STARTED, {"step": 1})
        c.record(TelemetryEvent.STEP_COMPLETED, {"step": 1})
        report = c.report("run-1")
        assert len(report.events) == 2
        assert report.events[0]["event"] == "step_started"

    def test_report_summary(self) -> None:
        c = HarnessTelemetryCollector()
        c.record(TelemetryEvent.RUN_STARTED)
        c.record(TelemetryEvent.RUN_COMPLETED)
        report = c.report("run-1")
        assert report.summary["count"] == 2


class TestEvolutionDataFeed:
    def test_default_state(self) -> None:
        f = EvolutionDataFeed()
        assert f.pull() == []

    def test_push_and_pull(self) -> None:
        f = EvolutionDataFeed()
        f.push({"event": "A"})
        f.push({"event": "B"})
        data = f.pull(limit=10)
        assert len(data) == 2
        assert data[-1]["event"] == "B"

    def test_pull_limit(self) -> None:
        f = EvolutionDataFeed()
        for i in range(10):
            f.push({"index": i})
        data = f.pull(limit=3)
        assert len(data) == 3
        assert data[-1]["index"] == 9
