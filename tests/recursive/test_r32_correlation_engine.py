from __future__ import annotations

from maref.recursive.correlation_engine import (
    AuditCorrelationEntry,
    CorrelationEngine,
    CorrelationLink,
    ExperienceCorrelationEntry,
    SpanCorrelationEntry,
    TraceResult,
)


class TestCorrelationLink:
    def test_create_link(self) -> None:
        link = CorrelationLink(
            link_id="link_1",
            span_id="span_1",
            audit_id="audit_1",
        )
        assert link.link_id == "link_1"
        assert link.span_id == "span_1"
        assert link.audit_id == "audit_1"
        assert link.experience_id is None

    def test_linked_entities(self) -> None:
        link = CorrelationLink(
            link_id="link_1",
            span_id="span_1",
            audit_id="audit_1",
            experience_id="exp_1",
        )
        entities = link.linked_entities
        assert "span:span_1" in entities
        assert "audit:audit_1" in entities
        assert "experience:exp_1" in entities

    def test_full_completeness(self) -> None:
        link = CorrelationLink(
            link_id="link_1",
            span_id="s1",
            audit_id="a1",
            experience_id="e1",
        )
        assert link.completeness == 1.0

    def test_partial_completeness(self) -> None:
        link = CorrelationLink(
            link_id="link_1",
            span_id="s1",
        )
        assert link.completeness == 1.0 / 3.0

    def test_two_thirds_completeness(self) -> None:
        link = CorrelationLink(
            link_id="link_1",
            span_id="s1",
            audit_id="a1",
        )
        assert link.completeness == 2.0 / 3.0


class TestSpanCorrelationEntry:
    def test_create(self) -> None:
        entry = SpanCorrelationEntry(span_id="s1", round_num=32)
        assert entry.span_id == "s1"
        assert entry.audit_refs == []
        assert entry.experience_refs == []

    def test_with_refs(self) -> None:
        entry = SpanCorrelationEntry(
            span_id="s1",
            audit_refs=["a1", "a2"],
            experience_refs=["e1"],
        )
        assert len(entry.audit_refs) == 2
        assert len(entry.experience_refs) == 1


class TestAuditCorrelationEntry:
    def test_create(self) -> None:
        entry = AuditCorrelationEntry(audit_id="a1")
        assert entry.audit_id == "a1"
        assert entry.span_refs == []


class TestExperienceCorrelationEntry:
    def test_create(self) -> None:
        entry = ExperienceCorrelationEntry(experience_id="e1")
        assert entry.experience_id == "e1"


class TestCorrelationEngine:
    def setup_method(self) -> None:
        self.engine = CorrelationEngine()

    def test_empty_engine(self) -> None:
        assert self.engine.link_count == 0
        report = self.engine.get_completeness_report()
        assert report["total_links"] == 0

    def test_link_span_to_audit(self) -> None:
        link = self.engine.link_span_to_audit("span_1", "audit_1", round_num=32)
        assert link.span_id == "span_1"
        assert link.audit_id == "audit_1"
        assert self.engine.link_count == 1

    def test_link_span_to_experience(self) -> None:
        link = self.engine.link_span_to_experience("span_2", "exp_2", round_num=32)
        assert link.span_id == "span_2"
        assert link.experience_id == "exp_2"

    def test_link_audit_to_experience(self) -> None:
        link = self.engine.link_audit_to_experience("audit_3", "exp_3", round_num=32)
        assert link.audit_id == "audit_3"
        assert link.experience_id == "exp_3"

    def test_link_all_three(self) -> None:
        link = self.engine.link_all("span_a", "audit_b", "exp_c", round_num=32)
        assert link.span_id == "span_a"
        assert link.audit_id == "audit_b"
        assert link.experience_id == "exp_c"
        assert link.completeness == 1.0

    def test_query_full_trace_from_span(self) -> None:
        self.engine.link_all("span_1", "audit_1", "exp_1", round_num=32)
        trace = self.engine.query_full_trace("span_1", "span")
        assert trace.root_entity == "span_1"
        assert trace.root_type == "span"
        assert trace.complete is True
        assert len(trace.span_ids) >= 1
        assert len(trace.audit_ids) >= 1
        assert len(trace.experience_ids) >= 1

    def test_query_full_trace_from_audit(self) -> None:
        self.engine.link_all("span_2", "audit_2", "exp_2", round_num=32)
        trace = self.engine.query_full_trace("audit_2", "audit")
        assert trace.root_type == "audit"
        assert len(trace.audit_ids) >= 1

    def test_query_full_trace_from_experience(self) -> None:
        self.engine.link_all("span_3", "audit_3", "exp_3", round_num=32)
        trace = self.engine.query_full_trace("exp_3", "experience")
        assert trace.root_type == "experience"
        assert len(trace.experience_ids) >= 1

    def test_trace_hop_count(self) -> None:
        self.engine.link_span_to_audit("s1", "a1", round_num=32)
        self.engine.link_audit_to_experience("a1", "e1", round_num=32)
        trace = self.engine.query_full_trace("s1", "span")
        assert trace.hop_count <= CorrelationEngine.MAX_HOPS

    def test_trace_summary(self) -> None:
        self.engine.link_all("s_trace", "a_trace", "e_trace", round_num=32)
        trace = self.engine.query_full_trace("s_trace", "span")
        summary = trace.summary
        assert summary["root"] == "span:s_trace"
        assert summary["spans_found"] >= 1

    def test_query_by_span(self) -> None:
        self.engine.link_span_to_audit("span_q", "audit_q", round_num=32)
        links = self.engine.query_by_span("span_q")
        assert len(links) >= 1
        assert links[0].span_id == "span_q"

    def test_query_by_audit(self) -> None:
        self.engine.link_span_to_audit("span_q2", "audit_q2", round_num=32)
        links = self.engine.query_by_audit("audit_q2")
        assert len(links) >= 1

    def test_query_by_experience(self) -> None:
        self.engine.link_span_to_experience("span_q3", "exp_q3", round_num=32)
        links = self.engine.query_by_experience("exp_q3")
        assert len(links) >= 1

    def test_query_by_round(self) -> None:
        self.engine.link_span_to_audit("s_r", "a_r", round_num=32)
        links = self.engine.query_by_round(32)
        assert len(links) >= 1
        empty = self.engine.query_by_round(99)
        assert empty == []

    def test_completeness_report(self) -> None:
        self.engine.link_all("s1", "a1", "e1", round_num=32)
        self.engine.link_span_to_audit("s2", "a2", round_num=32)
        report = self.engine.get_completeness_report()
        assert report["total_links"] >= 2
        assert report["fully_linked"] >= 1

    def test_clear_resets_all(self) -> None:
        self.engine.link_all("s1", "a1", "e1", round_num=32)
        self.engine.clear()
        assert self.engine.link_count == 0
        assert self.engine.span_correlation_count == 0

    def test_same_spans_dedup(self) -> None:
        self.engine.link_span_to_audit("same_span", "a1", round_num=32)
        self.engine.link_span_to_audit("same_span", "a2", round_num=32)
        links = self.engine.query_by_span("same_span")
        assert len(links) == 2

    def test_trace_result_to_audit(self) -> None:
        result = TraceResult(
            trace_id="test_trace",
            root_entity="span_1",
            root_type="span",
            complete=True,
        )
        record = result.to_audit_record(round_num=32)
        assert record.event_type == "correlation_trace"
        assert record.source_module == "CorrelationEngine"

    def test_span_correlation_entry(self) -> None:
        self.engine.link_span_to_audit("span_sc", "audit_sc", round_num=32)
        assert self.engine.span_correlation_count >= 1

    def test_audit_correlation_entry(self) -> None:
        self.engine.link_span_to_audit("span_ac", "audit_ac", round_num=32)
        assert self.engine.audit_correlation_count >= 1

    def test_experience_correlation_entry(self) -> None:
        self.engine.link_span_to_experience("span_ec", "exp_ec", round_num=32)
        assert self.engine.experience_correlation_count >= 1

    def test_orphan_detection(self) -> None:
        self.engine.link_span_to_audit("span_o1", "audit_o1", round_num=32)
        report = self.engine.get_completeness_report()
        assert "orphan_spans" in report
        assert "orphan_audits" in report
        assert "orphan_experiences" in report

    def test_multiple_links_same_entities(self) -> None:
        self.engine.link_all("s1", "a1", "e1", round_num=32)
        count_before = self.engine.link_count
        self.engine.link_all("s1", "a1", "e1", round_num=33)
        assert self.engine.link_count >= count_before
