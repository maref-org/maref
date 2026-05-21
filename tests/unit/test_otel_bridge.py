from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from maref.governance.audit import AuditLogger
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState
from maref.observation.otel_bridge import (
    OpenTelemetryBridge,
    create_grafana_dashboard,
)


@pytest.fixture
def audit_path() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        return Path(f.name)


@pytest.fixture
def audit_logger(audit_path: Path) -> AuditLogger:
    return AuditLogger(audit_path)


@pytest.fixture
def sm() -> GovernanceStateMachine:
    return GovernanceStateMachine()


@pytest.fixture
def bridge(sm: GovernanceStateMachine, audit_logger: AuditLogger) -> OpenTelemetryBridge:
    return OpenTelemetryBridge(sm, audit_logger)


class TestStateTransitionRecording:
    def test_record_transition_returns_span_id(self, bridge: OpenTelemetryBridge) -> None:
        span_id = bridge.record_state_transition(
            GovernanceState.INIT, GovernanceState.ANALYZE, "Test transition"
        )
        assert span_id > 0

    def test_multiple_transitions_increment_span_counter(self, bridge: OpenTelemetryBridge) -> None:
        bridge.record_state_transition(GovernanceState.INIT, GovernanceState.OBSERVE, "")
        bridge.record_state_transition(GovernanceState.OBSERVE, GovernanceState.ANALYZE, "")
        assert bridge.span_count == 2

    def test_transition_produces_metric(self, bridge: OpenTelemetryBridge) -> None:
        bridge.record_state_transition(GovernanceState.INIT, GovernanceState.ACT, "")
        metrics = bridge.collect_metrics()
        assert len(metrics) >= 1
        found = False
        for m in metrics:
            if m["name"] == "maref_state_transition_total":
                found = True
                break
        assert found


class TestPrometheusFormat:
    def test_prometheus_text_contains_maref_prefix(self, bridge: OpenTelemetryBridge) -> None:
        bridge.record_state_transition(GovernanceState.INIT, GovernanceState.ACT, "")
        text = bridge.get_prometheus_text()
        assert "maref_" in text

    def test_prometheus_text_has_spans_total(self, bridge: OpenTelemetryBridge) -> None:
        bridge.record_state_transition(GovernanceState.INIT, GovernanceState.ACT, "")
        text = bridge.get_prometheus_text()
        assert "maref_spans_total" in text

    def test_prometheus_text_is_parseable(self, bridge: OpenTelemetryBridge) -> None:
        bridge.record_state_transition(GovernanceState.INIT, GovernanceState.ACT, "")
        text = bridge.get_prometheus_text()
        lines = text.split("\n")
        for line in lines:
            if not line:
                continue
            parts = line.split(" ")
            assert len(parts) >= 2


class TestAllTransitionsHaveSpans:
    def test_verify_all_transitions(self, bridge: OpenTelemetryBridge) -> None:
        bridge.record_state_transition(GovernanceState.INIT, GovernanceState.ACT, "")
        assert bridge.verify_all_transitions_have_spans() is True


class TestGovernanceMetric:
    def test_record_custom_metric(self, bridge: OpenTelemetryBridge) -> None:
        bridge.record_governance_metric(
            "trust_score", 0.85, {"agent_did": "did:maref:test:1234"}
        )
        metrics = bridge.collect_metrics()
        trust_metrics = [m for m in metrics if m["name"] == "trust_score"]
        assert len(trust_metrics) >= 1
        assert trust_metrics[0]["value"] == 0.85


class TestConcurrency:
    def test_concurrent_recording(self, bridge: OpenTelemetryBridge) -> None:
        import concurrent.futures

        def record_one(i: int) -> int:
            return bridge.record_state_transition(
                GovernanceState.INIT, GovernanceState.ACT, f"Concurrent {i}"
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(record_one, i) for i in range(50)]
            results = [f.result() for f in futures]

        assert len(results) == 50
        assert len(set(results)) == 50
        assert bridge.span_count == 50


class TestGrafanaDashboard:
    def test_dashboard_has_required_panels(self) -> None:
        dashboard = create_grafana_dashboard()
        assert dashboard["title"] == "MAREF Governance"
        assert len(dashboard["panels"]) >= 6

    def test_dashboard_states_panel(self) -> None:
        dashboard = create_grafana_dashboard()
        panels = dashboard["panels"]
        types = [p["type"] for p in panels]
        assert "stat" in types
        assert "piechart" in types

    def test_dashboard_templating(self) -> None:
        dashboard = create_grafana_dashboard()
        assert "templating" in dashboard


class TestCollectPerformance:
    def test_collect_with_many_metrics(self, bridge: OpenTelemetryBridge) -> None:
        for _ in range(100):
            bridge.record_state_transition(GovernanceState.INIT, GovernanceState.ACT, "")
        metrics = bridge.collect_metrics()
        assert len(metrics) >= 100
