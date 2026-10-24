"""Tests for the governance OpenTelemetry exporter (P2-A)."""

from __future__ import annotations

from maref.governance.core_pipeline import GovernanceRequest, GovernanceResult, Verdict
from maref.governance.otel_exporter import GovernanceOTelExporter


class FakeSpan:
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value


class FakeSpanContext:
    def __init__(self, span: FakeSpan) -> None:
        self.span = span

    def __enter__(self) -> FakeSpan:
        return self.span

    def __exit__(self, *args: object) -> None:
        return None


class FakeTracer:
    def __init__(self) -> None:
        self.spans: list[FakeSpan] = []

    def start_as_current_span(self, name: str) -> FakeSpanContext:
        span = FakeSpan()
        self.spans.append(span)
        return FakeSpanContext(span)


class FakeCounter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, dict[str, object]]] = []

    def add(self, amount: int, attributes: dict[str, object]) -> None:
        self.calls.append((amount, dict(attributes)))


class FakeHistogram:
    def __init__(self) -> None:
        self.calls: list[tuple[float, dict[str, object]]] = []

    def record(self, value: float, attributes: dict[str, object]) -> None:
        self.calls.append((value, dict(attributes)))


class FakeMeter:
    def __init__(self) -> None:
        self.counters: dict[str, FakeCounter] = {}
        self.histograms: dict[str, FakeHistogram] = {}

    def create_counter(self, name: str, description: str = "") -> FakeCounter:
        counter = FakeCounter()
        self.counters[name] = counter
        return counter

    def create_histogram(self, name: str, description: str = "") -> FakeHistogram:
        histogram = FakeHistogram()
        self.histograms[name] = histogram
        return histogram


def _request() -> GovernanceRequest:
    return GovernanceRequest(
        action="file.write",
        agent_id="agent-1",
        tenant_id="acme",
        role="震",
    )


def test_decision_span_and_metrics():
    tracer = FakeTracer()
    meter = FakeMeter()
    exporter = GovernanceOTelExporter(tracer=tracer, meter=meter, use_global_provider=False)
    result = GovernanceResult(
        verdict=Verdict.DENY,
        reason="blocked",
        matched_rule="org_policy:deny",
        risk_score=0.8,
        policy_version="v7",
        policy_epoch="e1",
        evidence_id="ev-1",
    )
    exporter.record_decision(_request(), result)

    assert len(tracer.spans) == 1
    attributes = tracer.spans[0].attributes
    assert attributes["maref.action"] == "file.write"
    assert attributes["maref.verdict"] == "DENY"
    assert attributes["maref.policy_version"] == "v7"
    assert attributes["maref.evidence_id"] == "ev-1"
    assert attributes["maref.reason"] == "blocked"

    decisions = meter.counters["maref.governance.decisions"]
    assert decisions.calls == [(1, {"verdict": "DENY", "action": "file.write"})]
    assert meter.counters["maref.governance.denials"].calls
    assert meter.histograms["maref.governance.risk_score"].calls[0][0] == 0.8


def test_ask_user_increments_hitl_counter():
    meter = FakeMeter()
    exporter = GovernanceOTelExporter(meter=meter, use_global_provider=False)
    exporter.record_decision(
        _request(),
        GovernanceResult(verdict=Verdict.ASK_USER, reason="needs review"),
    )
    assert meter.counters["maref.governance.hitl_escalations"].calls


def test_evidence_check_records_span_and_counter():
    tracer = FakeTracer()
    meter = FakeMeter()
    exporter = GovernanceOTelExporter(tracer=tracer, meter=meter, use_global_provider=False)
    exporter.record_evidence_check("ev-1", True, reason="fresh", actor="agent-1")
    assert tracer.spans[0].attributes["maref.evidence_valid"] is True
    assert tracer.spans[0].attributes["maref.actor"] == "agent-1"
    assert meter.counters["maref.governance.evidence_checks"].calls == [
        (1, {"valid": "true"})
    ]


def test_exporter_without_tracer_or_meter_is_safe():
    exporter = GovernanceOTelExporter(use_global_provider=False)
    exporter.record_decision(_request(), GovernanceResult(verdict=Verdict.ALLOW))
    exporter.record_evidence_check("missing", False)
