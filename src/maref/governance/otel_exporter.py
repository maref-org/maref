"""Governance decision export to OpenTelemetry (P2-A).

The exporter depends only on the OpenTelemetry *API* when available, and
accepts an injected tracer/meter for tests or custom SDK pipelines.  It
records one span per decision plus counters/histograms suitable for Grafana,
Tempo, or any OTLP-compatible backend.
"""

from __future__ import annotations

from contextlib import nullcontext
from typing import Any

from maref.governance.core_pipeline import GovernanceRequest, GovernanceResult

try:  # pragma: no cover - exercised only when the optional extra is installed
    from opentelemetry import metrics, trace

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    metrics = None
    trace = None
    _OTEL_AVAILABLE = False


class GovernanceOTelExporter:
    """Emit governance decisions, evidence checks, and policy metadata to OTel."""

    def __init__(
        self,
        tracer: Any | None = None,
        meter: Any | None = None,
        *,
        service_name: str = "maref-governance",
        service_version: str = "0.54.2-dev",
        use_global_provider: bool = True,
    ) -> None:
        self.tracer = tracer
        self.meter = meter
        if use_global_provider and _OTEL_AVAILABLE:
            if self.tracer is None:
                self.tracer = trace.get_tracer(service_name, service_version)
            if self.meter is None:
                self.meter = metrics.get_meter(service_name, service_version)

        self.decision_counter = _create_counter(
            self.meter,
            "maref.governance.decisions",
            "Governance decisions by verdict and action",
        )
        self.deny_counter = _create_counter(
            self.meter,
            "maref.governance.denials",
            "Denied governance decisions",
        )
        self.hitl_counter = _create_counter(
            self.meter,
            "maref.governance.hitl_escalations",
            "Decision escalations requiring human oversight",
        )
        self.risk_histogram = _create_histogram(
            self.meter,
            "maref.governance.risk_score",
            "Risk score of governance decisions",
        )
        self.evidence_counter = _create_counter(
            self.meter,
            "maref.governance.evidence_checks",
            "Evidence verification outcomes",
        )

    def record_decision(
        self,
        request: GovernanceRequest,
        result: GovernanceResult,
        *,
        latency_ms: int | None = None,
    ) -> None:
        """Record one governance decision as a span and metrics."""
        attributes = {
            "maref.action": request.action,
            "maref.agent_id": request.agent_id,
            "maref.tenant_id": request.tenant_id,
            "maref.role": request.role,
            "maref.verdict": result.verdict.value,
            "maref.matched_rule": result.matched_rule,
            "maref.risk_score": float(result.risk_score),
            "maref.policy_version": result.policy_version,
            "maref.policy_epoch": result.policy_epoch,
            "maref.evidence_id": result.evidence_id,
            "maref.latency_ms": int(result.latency_ms if latency_ms is None else latency_ms),
        }
        context = (
            self.tracer.start_as_current_span("maref.governance.decision")
            if self.tracer is not None
            else nullcontext(None)
        )
        with context as span:
            if span is not None:
                for key, value in attributes.items():
                    span.set_attribute(key, value)
                reason = str(result.reason or "")
                if reason:
                    span.set_attribute("maref.reason", reason[:1000])
                if result.hitl_event_id:
                    span.set_attribute("maref.hitl_event_id", result.hitl_event_id)

        metric_labels = {
            "verdict": result.verdict.value,
            "action": request.action,
        }
        _add(self.decision_counter, 1, metric_labels)
        if result.verdict.value == "DENY":
            _add(self.deny_counter, 1, metric_labels)
        if result.verdict.value == "ASK_USER":
            _add(self.hitl_counter, 1, metric_labels)
        _record(self.risk_histogram, float(result.risk_score), metric_labels)

    def record_evidence_check(
        self,
        evidence_id: str,
        valid: bool,
        *,
        reason: str = "",
        actor: str = "",
    ) -> None:
        """Record an evidence replay/validation check."""
        attributes = {
            "maref.evidence_id": evidence_id,
            "maref.evidence_valid": bool(valid),
            "maref.actor": actor,
        }
        context = (
            self.tracer.start_as_current_span("maref.governance.evidence_check")
            if self.tracer is not None
            else nullcontext(None)
        )
        with context as span:
            if span is not None:
                for key, value in attributes.items():
                    span.set_attribute(key, value)
                if reason:
                    span.set_attribute("maref.reason", reason[:1000])
        _add(self.evidence_counter, 1, {"valid": str(bool(valid)).lower()})


def _create_counter(meter: Any | None, name: str, description: str) -> Any | None:
    if meter is None:
        return None
    try:
        return meter.create_counter(name, description=description)
    except Exception:
        return None


def _create_histogram(meter: Any | None, name: str, description: str) -> Any | None:
    if meter is None:
        return None
    try:
        return meter.create_histogram(name, description=description)
    except Exception:
        return None


def _add(counter: Any | None, amount: int, attributes: dict[str, Any]) -> None:
    if counter is None:
        return
    try:
        counter.add(amount, attributes)
    except Exception:
        pass


def _record(histogram: Any | None, value: float, attributes: dict[str, Any]) -> None:
    if histogram is None:
        return
    try:
        histogram.record(value, attributes)
    except Exception:
        pass
