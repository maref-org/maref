"""EvolutionDataFeed — 把 Harness 遥测适配为 SelfObserver 的 ProbeReading 格式。"""

from __future__ import annotations

from typing import Any

from maref.execution.telemetry.collector import TelemetryReport
from maref.observation.probes import ProbeReading, ProbeSeverity


class EvolutionDataFeed:
    """把 Harness 遥测数据适配为 recursive/self_observer.py 的观察输入格式。"""

    def to_readings(self, report: TelemetryReport) -> list[ProbeReading]:
        readings: list[ProbeReading] = []

        readings.append(ProbeReading(
            probe_name="harness.total_events",
            severity=ProbeSeverity.NORMAL,
            value=float(report.total_events),
            threshold=0,
            context={"source": "harness_telemetry", "description": "Total harness telemetry events recorded"},
        ))

        readings.append(ProbeReading(
            probe_name="harness.total_duration_ms",
            severity=ProbeSeverity.NORMAL,
            value=report.total_duration_ms,
            threshold=0,
            context={"source": "harness_telemetry"},
        ))

        readings.append(ProbeReading(
            probe_name="harness.total_tool_calls",
            severity=ProbeSeverity.NORMAL,
            value=float(report.total_tool_calls),
            threshold=0,
            context={"source": "harness_telemetry"},
        ))

        readings.append(ProbeReading(
            probe_name="harness.total_token_count",
            severity=ProbeSeverity.NORMAL,
            value=float(report.total_token_count),
            threshold=0,
            context={"source": "harness_telemetry"},
        ))

        readings.append(ProbeReading(
            probe_name="harness.error_count",
            severity=ProbeSeverity.WARNING if report.error_count > 0 else ProbeSeverity.NORMAL,
            value=float(report.error_count),
            threshold=0,
            context={"source": "harness_telemetry"},
        ))

        for stage, count in report.stage_summary.items():
            readings.append(ProbeReading(
                probe_name=f"harness.stage.{stage}",
                severity=ProbeSeverity.NORMAL,
                value=float(count),
                threshold=0,
                context={"stage": stage, "source": "harness_telemetry"},
            ))

        return readings

    def feed(self, report: TelemetryReport, observer: Any) -> list[Any]:
        readings = self.to_readings(report)
        for reading in readings:
            try:
                observer.probe_readings.append(reading)
            except AttributeError:
                pass
        return readings
