from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from maref.recursive.unified_audit import UnifiedAuditRecord, UnifiedAuditStore, make_record_id


@dataclass
class CorrelationLink:
    link_id: str
    span_id: str | None = None
    audit_id: str | None = None
    experience_id: str | None = None
    round_num: int = 0
    timestamp: float = field(default_factory=time.time)
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def linked_entities(self) -> list[str]:
        entities: list[str] = []
        if self.span_id:
            entities.append(f"span:{self.span_id}")
        if self.audit_id:
            entities.append(f"audit:{self.audit_id}")
        if self.experience_id:
            entities.append(f"experience:{self.experience_id}")
        return entities

    @property
    def completeness(self) -> float:
        score = 0.0
        if self.span_id:
            score += 1.0 / 3.0
        if self.audit_id:
            score += 1.0 / 3.0
        if self.experience_id:
            score += 1.0 / 3.0
        return score


@dataclass
class TraceResult:
    trace_id: str
    root_entity: str
    root_type: str
    path: list[tuple[str, str]] = field(default_factory=list)
    span_ids: list[str] = field(default_factory=list)
    audit_ids: list[str] = field(default_factory=list)
    experience_ids: list[str] = field(default_factory=list)
    hop_count: int = 0
    complete: bool = False

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "root": f"{self.root_type}:{self.root_entity}",
            "hops": self.hop_count,
            "spans_found": len(self.span_ids),
            "audits_found": len(self.audit_ids),
            "experiences_found": len(self.experience_ids),
            "complete": self.complete,
            "path": [f"{t}:{e}" for t, e in self.path],
        }

    def to_audit_record(self, round_num: int = 32) -> UnifiedAuditRecord:
        return UnifiedAuditRecord(
            record_id=make_record_id("trace", hash(self.trace_id) % 100000),
            timestamp=time.time(),
            layer="evolution",
            round=round_num,
            event_type="correlation_trace",
            source_module="CorrelationEngine",
            target_module=self.root_type,
            decision=self.root_entity,
            justification=f"Traced in {self.hop_count} hops, complete={self.complete}",
            outcome="success" if self.complete else "partial",
            context_refs=[self.trace_id],
        )


@dataclass
class SpanCorrelationEntry:
    span_id: str
    audit_refs: list[str] = field(default_factory=list)
    experience_refs: list[str] = field(default_factory=list)
    round_num: int = 0


@dataclass
class AuditCorrelationEntry:
    audit_id: str
    span_refs: list[str] = field(default_factory=list)
    experience_refs: list[str] = field(default_factory=list)
    round_num: int = 0


@dataclass
class ExperienceCorrelationEntry:
    experience_id: str
    span_refs: list[str] = field(default_factory=list)
    audit_refs: list[str] = field(default_factory=list)
    round_num: int = 0


class CorrelationEngine:
    MAX_HOPS = 5
    MAX_TRACE_DEPTH = 10

    def __init__(self, audit_store: UnifiedAuditStore | None = None) -> None:
        self._links: dict[str, CorrelationLink] = {}
        self._span_index: dict[str, list[str]] = defaultdict(list)
        self._audit_index: dict[str, list[str]] = defaultdict(list)
        self._experience_index: dict[str, list[str]] = defaultdict(list)
        self._by_round: dict[int, list[str]] = defaultdict(list)
        self._audit_store = audit_store or UnifiedAuditStore()

        self._span_corr: dict[str, SpanCorrelationEntry] = {}
        self._audit_corr: dict[str, AuditCorrelationEntry] = {}
        self._experience_corr: dict[str, ExperienceCorrelationEntry] = {}

    def link_span_to_audit(self, span_id: str, audit_id: str,
                            round_num: int = 0, **attrs: Any) -> CorrelationLink:
        link = self._get_or_create_link(span_id=span_id, audit_id=audit_id,
                                         round_num=round_num, **attrs)
        self._index_link(link)
        self._update_correlation_entries(span_id=span_id, audit_id=audit_id, round_num=round_num)
        return link

    def link_span_to_experience(self, span_id: str, experience_id: str,
                                 round_num: int = 0, **attrs: Any) -> CorrelationLink:
        link = self._get_or_create_link(span_id=span_id, experience_id=experience_id,
                                         round_num=round_num, **attrs)
        self._index_link(link)
        self._update_correlation_entries(span_id=span_id, experience_id=experience_id,
                                          round_num=round_num)
        return link

    def link_audit_to_experience(self, audit_id: str, experience_id: str,
                                  round_num: int = 0, **attrs: Any) -> CorrelationLink:
        link = self._get_or_create_link(audit_id=audit_id, experience_id=experience_id,
                                         round_num=round_num, **attrs)
        self._index_link(link)
        self._update_correlation_entries(audit_id=audit_id, experience_id=experience_id,
                                          round_num=round_num)
        return link

    def link_all(self, span_id: str, audit_id: str, experience_id: str,
                  round_num: int = 0, **attrs: Any) -> CorrelationLink:
        link_id = f"link_{span_id}_{int(time.time() * 1000)}"
        link = CorrelationLink(
            link_id=link_id,
            span_id=span_id,
            audit_id=audit_id,
            experience_id=experience_id,
            round_num=round_num,
            timestamp=time.time(),
            attributes=dict(attrs),
        )
        self._links[link_id] = link
        self._index_link(link)
        self._update_correlation_entries(
            span_id=span_id, audit_id=audit_id, experience_id=experience_id,
            round_num=round_num,
        )
        return link

    def query_full_trace(self, entity_id: str, entity_type: str = "span") -> TraceResult:
        trace_id = f"trace_{entity_type}_{entity_id}_{int(time.time() * 1000)}"
        result = TraceResult(
            trace_id=trace_id,
            root_entity=entity_id,
            root_type=entity_type,
        )

        visited_entities: set[str] = set()
        visited_links: set[str] = set()
        queue: list[str] = [f"{entity_type}:{entity_id}"]

        while queue and result.hop_count <= self.MAX_HOPS:
            current = queue.pop(0)
            if current in visited_entities:
                continue
            visited_entities.add(current)

            prefix, eid = current.split(":", 1)

            if prefix == "span":
                result.span_ids.append(eid)
            elif prefix == "audit":
                result.audit_ids.append(eid)
            elif prefix == "experience":
                result.experience_ids.append(eid)

            adjacent = self._get_adjacent_links(eid, prefix)
            for link in adjacent:
                if link.link_id in visited_links:
                    continue
                visited_links.add(link.link_id)
                result.hop_count += 1

                for entity in link.linked_entities:
                    if entity not in visited_entities:
                        et, eid2 = entity.split(":", 1)
                        result.path.append((et, eid2))
                        queue.append(entity)

        result.complete = (
            len(result.span_ids) > 0 and
            len(result.audit_ids) > 0 and
            len(result.experience_ids) > 0 and
            result.hop_count <= self.MAX_HOPS
        )

        self._audit_store.append(result.to_audit_record())
        return result

    def query_by_span(self, span_id: str) -> list[CorrelationLink]:
        return [self._links[lid] for lid in self._span_index.get(span_id, [])
                if lid in self._links]

    def query_by_audit(self, audit_id: str) -> list[CorrelationLink]:
        return [self._links[lid] for lid in self._audit_index.get(audit_id, [])
                if lid in self._links]

    def query_by_experience(self, experience_id: str) -> list[CorrelationLink]:
        return [self._links[lid] for lid in self._experience_index.get(experience_id, [])
                if lid in self._links]

    def query_by_round(self, round_num: int) -> list[CorrelationLink]:
        return [self._links[lid] for lid in self._by_round.get(round_num, [])
                if lid in self._links]

    def get_completeness_report(self) -> dict[str, Any]:
        total = len(self._links)
        if total == 0:
            return {"total_links": 0, "avg_completeness": 0.0, "fully_linked": 0}

        avg = sum(link.completeness for link in self._links.values()) / total
        fully = sum(1 for link in self._links.values() if link.completeness >= 1.0)

        return {
            "total_links": total,
            "avg_completeness": round(avg, 4),
            "fully_linked": fully,
            "fully_linked_pct": round(fully / total * 100, 1),
            "orphan_spans": sum(
                1 for e in self._span_corr.values()
                if not e.audit_refs and not e.experience_refs
            ),
            "orphan_audits": sum(
                1 for e in self._audit_corr.values()
                if not e.span_refs and not e.experience_refs
            ),
            "orphan_experiences": sum(
                1 for e in self._experience_corr.values()
                if not e.span_refs and not e.audit_refs
            ),
        }

    def _get_or_create_link(self, **kwargs: Any) -> CorrelationLink:
        span_id = kwargs.get("span_id") or ""
        audit_id = kwargs.get("audit_id") or ""
        exp_id = kwargs.get("experience_id") or ""

        for link in self._links.values():
            if link.span_id == span_id and link.audit_id == audit_id and link.experience_id == exp_id:
                return link

        link = CorrelationLink(
            link_id=f"link_{int(time.time() * 1000)}_{abs(hash((span_id, audit_id, exp_id))) % 100000}",
            span_id=span_id or None,
            audit_id=audit_id or None,
            experience_id=exp_id or None,
            round_num=kwargs.get("round_num", 0),
            timestamp=time.time(),
            attributes={k: v for k, v in kwargs.items()
                         if k not in ("span_id", "audit_id", "experience_id", "round_num")},
        )
        self._links[link.link_id] = link
        return link

    def _index_link(self, link: CorrelationLink) -> None:
        if link.span_id:
            self._span_index[link.span_id].append(link.link_id)
        if link.audit_id:
            self._audit_index[link.audit_id].append(link.link_id)
        if link.experience_id:
            self._experience_index[link.experience_id].append(link.link_id)
        self._by_round[link.round_num].append(link.link_id)

    def _update_correlation_entries(self, **kwargs: Any) -> None:
        span_id = kwargs.get("span_id", "")
        audit_id = kwargs.get("audit_id", "")
        experience_id = kwargs.get("experience_id", "")
        round_num = kwargs.get("round_num", 0)

        if span_id:
            entry = self._span_corr.setdefault(
                span_id, SpanCorrelationEntry(span_id=span_id, round_num=round_num or 0)
            )
            if audit_id and audit_id not in entry.audit_refs:
                entry.audit_refs.append(audit_id)
            if experience_id and experience_id not in entry.experience_refs:
                entry.experience_refs.append(experience_id)

        if audit_id:
            audit_entry = self._audit_corr.setdefault(
                audit_id, AuditCorrelationEntry(audit_id=audit_id, round_num=round_num or 0)
            )
            if span_id and span_id not in audit_entry.span_refs:
                audit_entry.span_refs.append(span_id)
            if experience_id and experience_id not in audit_entry.experience_refs:
                audit_entry.experience_refs.append(experience_id)

        if experience_id:
            exp_entry = self._experience_corr.setdefault(
                experience_id,
                ExperienceCorrelationEntry(experience_id=experience_id, round_num=round_num or 0),
            )
            if span_id and span_id not in exp_entry.span_refs:
                exp_entry.span_refs.append(span_id)
            if audit_id and audit_id not in exp_entry.audit_refs:
                exp_entry.audit_refs.append(audit_id)

    def _get_adjacent_links(self, entity_id: str, entity_type: str) -> list[CorrelationLink]:
        index = {
            "span": self._span_index,
            "audit": self._audit_index,
            "experience": self._experience_index,
        }
        link_ids = index.get(entity_type, {}).get(entity_id, [])
        return [self._links[lid] for lid in link_ids if lid in self._links]

    @property
    def link_count(self) -> int:
        return len(self._links)

    @property
    def span_correlation_count(self) -> int:
        return len(self._span_corr)

    @property
    def audit_correlation_count(self) -> int:
        return len(self._audit_corr)

    @property
    def experience_correlation_count(self) -> int:
        return len(self._experience_corr)

    def clear(self) -> None:
        self._links.clear()
        self._span_index.clear()
        self._audit_index.clear()
        self._experience_index.clear()
        self._by_round.clear()
        self._span_corr.clear()
        self._audit_corr.clear()
        self._experience_corr.clear()
