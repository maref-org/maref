"""Tests for correlation_engine.py — CorrelationEngine, linking, tracing."""
from __future__ import annotations

import pytest

from maref.recursive.correlation_engine import (
    AuditCorrelationEntry,
    CorrelationEngine,
    CorrelationLink,
    ExperienceCorrelationEntry,
    SpanCorrelationEntry,
    TraceResult,
)


class TestCorrelationLink:
    def test_linked_entities_empty(self):
        link = CorrelationLink(link_id="l1")
        assert link.linked_entities == []

    def test_linked_entities_all(self):
        link = CorrelationLink(link_id="l1", span_id="s1", audit_id="a1", experience_id="e1")
        entities = link.linked_entities
        assert "span:s1" in entities
        assert "audit:a1" in entities
        assert "experience:e1" in entities

    def test_completeness_partial(self):
        link = CorrelationLink(link_id="l1", span_id="s1")
        assert link.completeness == pytest.approx(1.0 / 3.0)

    def test_completeness_full(self):
        link = CorrelationLink(link_id="l1", span_id="s1", audit_id="a1", experience_id="e1")
        assert link.completeness == 1.0

    def test_completeness_empty(self):
        link = CorrelationLink(link_id="l1")
        assert link.completeness == 0.0


class TestTraceResult:
    def test_summary(self):
        trace = TraceResult(
            trace_id="tr-1", root_entity="s1", root_type="span",
            hop_count=2, complete=False,
        )
        s = trace.summary
        assert s["trace_id"] == "tr-1"
        assert s["hops"] == 2
        assert s["complete"] is False

    def test_to_audit_record(self):
        trace = TraceResult(
            trace_id="tr-1", root_entity="s1", root_type="span",
            complete=True,
        )
        record = trace.to_audit_record(round_num=32)
        assert record.layer == "evolution"
        assert record.event_type == "correlation_trace"


class TestCorrelationEngine:
    def test_initial_state(self):
        engine = CorrelationEngine()
        assert engine.link_count == 0
        assert engine.span_correlation_count == 0

    def test_link_span_to_audit(self):
        engine = CorrelationEngine()
        link = engine.link_span_to_audit("s1", "a1", round_num=1)
        assert link.span_id == "s1"
        assert link.audit_id == "a1"
        assert engine.link_count == 1

    def test_link_span_to_experience(self):
        engine = CorrelationEngine()
        link = engine.link_span_to_experience("s1", "e1", round_num=1)
        assert link.span_id == "s1"
        assert link.experience_id == "e1"

    def test_link_audit_to_experience(self):
        engine = CorrelationEngine()
        link = engine.link_audit_to_experience("a1", "e1", round_num=1)
        assert link.audit_id == "a1"
        assert link.experience_id == "e1"

    def test_link_all(self):
        engine = CorrelationEngine()
        link = engine.link_all("s1", "a1", "e1", round_num=1, custom_attr="val")
        assert link.span_id == "s1"
        assert link.audit_id == "a1"
        assert link.experience_id == "e1"
        assert link.attributes.get("custom_attr") == "val"

    def test_deduplicate_links(self):
        engine = CorrelationEngine()
        link1 = engine.link_span_to_audit("s1", "a1")
        link2 = engine.link_span_to_audit("s1", "a1")
        assert link1.link_id == link2.link_id
        assert engine.link_count == 1

    def test_query_by_span(self):
        engine = CorrelationEngine()
        engine.link_span_to_audit("s1", "a1")
        engine.link_span_to_audit("s1", "a2")
        results = engine.query_by_span("s1")
        assert len(results) == 2

    def test_query_by_span_empty(self):
        engine = CorrelationEngine()
        assert engine.query_by_span("nonexistent") == []

    def test_query_by_audit(self):
        engine = CorrelationEngine()
        engine.link_span_to_audit("s1", "a1")
        engine.link_span_to_audit("s2", "a1")
        results = engine.query_by_audit("a1")
        assert len(results) == 2

    def test_query_by_experience(self):
        engine = CorrelationEngine()
        engine.link_span_to_experience("s1", "e1")
        results = engine.query_by_experience("e1")
        assert len(results) == 1

    def test_query_by_round(self):
        engine = CorrelationEngine()
        engine.link_span_to_audit("s1", "a1", round_num=5)
        results = engine.query_by_round(5)
        assert len(results) == 1
        assert engine.query_by_round(999) == []

    def test_query_full_trace_span_to_audit(self):
        engine = CorrelationEngine()
        engine.link_span_to_audit("s1", "a1", round_num=1)
        trace = engine.query_full_trace("s1", "span")
        assert trace.root_entity == "s1"
        assert "s1" in trace.span_ids
        assert "a1" in trace.audit_ids

    def test_query_full_trace_all_three(self):
        engine = CorrelationEngine()
        engine.link_all("s1", "a1", "e1", round_num=1)
        trace = engine.query_full_trace("s1", "span")
        assert trace.complete is True

    def test_get_completeness_report_empty(self):
        engine = CorrelationEngine()
        report = engine.get_completeness_report()
        assert report["total_links"] == 0

    def test_get_completeness_report(self):
        engine = CorrelationEngine()
        engine.link_all("s1", "a1", "e1")
        engine.link_span_to_audit("s2", "a2")
        report = engine.get_completeness_report()
        assert report["total_links"] == 2
        assert report["avg_completeness"] > 0
        assert report["fully_linked"] == 1

    def test_clear(self):
        engine = CorrelationEngine()
        engine.link_span_to_audit("s1", "a1")
        engine.clear()
        assert engine.link_count == 0
        assert engine.span_correlation_count == 0
