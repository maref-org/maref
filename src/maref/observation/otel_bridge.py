from __future__ import annotations

import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from maref.governance.audit import AuditLogger
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState

_OTEL_AVAILABLE = False
try:
    from opentelemetry import metrics, trace  # noqa: F401
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _OTEL_AVAILABLE = True
except ImportError:
    pass


@dataclass
class MAREFFMetric:
    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class OpenTelemetryBridge:
    """MAREF → OpenTelemetry bridge with Prometheus + Grafana support.

    Records state transitions as OTel spans, governance decisions as metrics,
    and exports both Prometheus text format and OTLP to collectors.
    """

    def __init__(
        self, state_machine: GovernanceStateMachine, audit_logger: AuditLogger
    ) -> None:
        self._sm = state_machine
        self._audit = audit_logger
        self._metrics: list[MAREFFMetric] = []
        self._lock = threading.Lock()
        self._span_counter = 0
        self._transitions: list[dict[str, Any]] = []

        # Circuit breaker metrics
        self._cb_trip_count = 0
        self._cb_recovery_count = 0
        self._halt_count = 0
        self._last_entropy_value = 0.0

        # OTel SDK initialization (if available)
        self._tracer: Any = None
        self._meter: Any = None
        self._cb_counter: Any = None
        self._transition_counter: Any = None
        self._entropy_gauge: Any = None
        if _OTEL_AVAILABLE:
            self._init_otel_sdk()

    def _init_otel_sdk(self) -> None:
        """Initialize OTel SDK with Prometheus metric exporter and OTLP trace exporter."""
        try:
            otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
            if otlp_endpoint:
                metric_exporter = OTLPMetricExporter(endpoint=f"{otlp_endpoint}/v1/metrics")
                metric_reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=15_000)
                mp = MeterProvider(metric_readers=[metric_reader])
                metrics.set_meter_provider(mp)

                span_exporter = OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")
                tp = TracerProvider()
                tp.add_span_processor(BatchSpanProcessor(span_exporter))
                trace.set_tracer_provider(tp)

            self._meter = metrics.get_meter("maref.governance", "0.17.0")
            self._tracer = trace.get_tracer("maref.governance", "0.17.0")

            self._cb_counter = self._meter.create_counter(
                "maref.circuit_breaker.trips",
                description="CircuitBreaker activation count",
            )
            self._transition_counter = self._meter.create_counter(
                "maref.state_transitions",
                description="Governance state transition count",
            )
            self._entropy_gauge = self._meter.create_gauge(
                "maref.entropy.current",
                description="Current system entropy level",
            )
        except Exception:
            pass

    # ── State transition recording (Aligned with OTel trace Span) ────

    def record_state_transition(
        self, from_state: GovernanceState, to_state: GovernanceState, reason: str = ""
    ) -> int:
        with self._lock:
            self._span_counter += 1
            span_id = self._span_counter
            self._transitions.append(
                {
                    "span_id": span_id,
                    "from_state": from_state.name,
                    "to_state": to_state.name,
                    "reason": reason,
                    "timestamp": time.time(),
                }
            )
            self._metrics.append(
                MAREFFMetric(
                    name="maref_state_transition_total",
                    value=1.0,
                    labels={"from_state": from_state.name, "to_state": to_state.name},
                )
            )

            if to_state == GovernanceState.HALT:
                self._halt_count += 1

            # OTel trace span
            if self._tracer is not None:
                with self._tracer.start_as_current_span("maref.state_transition") as span:
                    span.set_attribute("maref.state.from", from_state.name)
                    span.set_attribute("maref.state.to", to_state.name)
                    span.set_attribute("maref.state.reason", reason)
                    span.set_attribute("maref.transition_id", span_id)

            if self._transition_counter is not None:
                self._transition_counter.add(
                    1,
                    {"from_state": from_state.name, "to_state": to_state.name},
                )
            return span_id

    def record_governance_metric(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        with self._lock:
            self._metrics.append(MAREFFMetric(name=name, value=value, labels=labels or {}))

    # ── CircuitBreaker metrics ────────────────────────────────────────

    def record_circuit_breaker_trip(self, agent_id: str = "") -> None:
        with self._lock:
            self._cb_trip_count += 1
            self._metrics.append(
                MAREFFMetric(
                    name="maref_circuit_breaker_trips_total",
                    value=1.0,
                    labels={"agent_id": agent_id},
                )
            )
            if self._cb_counter is not None:
                self._cb_counter.add(1, {"agent_id": agent_id})

    def record_circuit_breaker_recovery(self, agent_id: str = "") -> None:
        with self._lock:
            self._cb_recovery_count += 1
            self._metrics.append(
                MAREFFMetric(
                    name="maref_circuit_breaker_recoveries_total",
                    value=1.0,
                    labels={"agent_id": agent_id},
                )
            )

    def set_entropy(self, value: float, level: str = "normal") -> None:
        with self._lock:
            self._last_entropy_value = value
            self._metrics.append(
                MAREFFMetric(
                    name="maref_entropy_current",
                    value=value,
                    labels={"level": level},
                )
            )
            if self._entropy_gauge is not None:
                self._entropy_gauge.set(value, {"level": level})

    # ── OTLP export helpers ──────────────────────────────────────────

    def collect_metrics(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "name": m.name,
                    "value": m.value,
                    "labels": m.labels,
                    "timestamp": m.timestamp,
                }
                for m in self._metrics
            ]

    def get_prometheus_text(self) -> str:
        with self._lock:
            grouped: dict[str, list[MAREFFMetric]] = defaultdict(list)
            for m in self._metrics:
                grouped[m.name].append(m)
            lines: list[str] = []
            for name, metrics_list in grouped.items():
                for m in metrics_list:
                    label_str = ",".join(f'{k}="{v}"' for k, v in m.labels.items())
                    label_part = f"{{{label_str}}}" if label_str else ""
                    lines.append(f"maref_{name}{label_part} {m.value} {int(m.timestamp)}")

            lines.append(f"maref_state_transitions_total {len(self._transitions)}")
            lines.append(f"maref_spans_total {self._span_counter}")
            lines.append(f"maref_circuit_breaker_trips_total {self._cb_trip_count}")
            lines.append(f"maref_circuit_breaker_recoveries_total {self._cb_recovery_count}")
            lines.append(f"maref_halt_total {self._halt_count}")
            lines.append(f"maref_entropy_current {self._last_entropy_value}")
            return "\n".join(lines)

    def verify_all_transitions_have_spans(self) -> bool:
        with self._lock:
            audit_entries = self._audit.read_all()
            transition_entries = [
                e for e in audit_entries if e.event_type == "state_transition"
            ]
            return len(transition_entries) <= self._span_counter

    @property
    def span_count(self) -> int:
        return self._span_counter

    @property
    def cb_trip_count(self) -> int:
        return self._cb_trip_count

    @property
    def halt_count(self) -> int:
        return self._halt_count

    @property
    def otel_available(self) -> bool:
        return _OTEL_AVAILABLE


def create_grafana_dashboard(title: str = "MAREF Governance") -> dict[str, Any]:
    """Generate a Grafana dashboard JSON for MAREF metrics."""
    return {
        "title": title,
        "uid": "maref-governance",
        "panels": [
            {
                "id": 1,
                "title": "State Transitions (24h)",
                "type": "stat",
                "gridPos": {"x": 0, "y": 0, "w": 8, "h": 4},
                "targets": [
                    {
                        "expr": "sum(rate(maref_state_transition_total[24h]))",
                        "legendFormat": "Transitions/s",
                    }
                ],
            },
            {
                "id": 2,
                "title": "Governance State Distribution",
                "type": "piechart",
                "gridPos": {"x": 8, "y": 0, "w": 8, "h": 8},
                "targets": [
                    {
                        "expr": "sum by (to_state) (maref_state_transition_total)",
                        "legendFormat": "{{to_state}}",
                    }
                ],
            },
            {
                "id": 3,
                "title": "CircuitBreaker Trips",
                "type": "timeseries",
                "gridPos": {"x": 16, "y": 0, "w": 8, "h": 4},
                "targets": [
                    {
                        "expr": "rate(maref_circuit_breaker_trips_total[5m])",
                        "legendFormat": "Trips/s",
                    }
                ],
            },
            {
                "id": 4,
                "title": "System Entropy",
                "type": "gauge",
                "gridPos": {"x": 0, "y": 4, "w": 8, "h": 4},
                "fieldConfig": {
                    "defaults": {
                        "thresholds": {
                            "steps": [
                                {"color": "green", "value": 0},
                                {"color": "yellow", "value": 3},
                                {"color": "orange", "value": 5},
                                {"color": "red", "value": 7},
                            ]
                        }
                    }
                },
                "targets": [
                    {
                        "expr": "maref_entropy_current",
                        "legendFormat": "Entropy",
                    }
                ],
            },
            {
                "id": 5,
                "title": "HALT Events",
                "type": "stat",
                "gridPos": {"x": 16, "y": 4, "w": 8, "h": 4},
                "targets": [
                    {
                        "expr": "maref_halt_total",
                        "legendFormat": "HALTs",
                    }
                ],
            },
            {
                "id": 6,
                "title": "Spans Created",
                "type": "timeseries",
                "gridPos": {"x": 0, "y": 8, "w": 24, "h": 6},
                "targets": [
                    {
                        "expr": "maref_spans_total",
                        "legendFormat": "Spans",
                    }
                ],
            },
        ],
        "templating": {
            "list": [
                {
                    "name": "agent",
                    "type": "query",
                    "query": "maref_agent_info",
                    "regex": 'name="([^"]+)"',
                }
            ]
        },
    }
