from __future__ import annotations

import tempfile
from pathlib import Path

from maref.governance.audit import AuditLogger
from maref.recursive.unified_audit import UnifiedAuditRecord, UnifiedAuditStore


class TestAuditLoggerEdgeCases:
    def test_read_all_no_path(self) -> None:
        logger = AuditLogger(log_path=None)
        entries = logger.read_all()
        assert entries == []

    def test_read_all_missing_file(self) -> None:
        logger = AuditLogger(log_path=Path("/nonexistent/audit.jsonl"))
        entries = logger.read_all()
        assert entries == []

    def test_read_all_corrupted_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "audit.jsonl"
            p.write_text(
                '{"id": "valid", "timestamp": 1, "event_type": "test", "actor": "sys", "action": "test", "details": "test"}\n'
                "{corrupted json\n"
            )
            logger = AuditLogger(log_path=p)
            entries = logger.read_all()
            assert len(entries) == 1

    def test_read_all_missing_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "audit.jsonl"
            p.write_text('{"id": "missing_fields"}\n')
            logger = AuditLogger(log_path=p)
            entries = logger.read_all()
            assert entries == []

    def test_log_writes_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(log_path=p)
            entry = logger.log("test", "sys", "act", "detail")
            entries = logger.read_all()
            assert len(entries) == 1
            assert entries[0].id == entry.id

    def test_log_creates_parent_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "subdir" / "audit.jsonl"
            logger = AuditLogger(log_path=p)
            logger.log("test", "sys", "act", "detail")
            assert p.exists()

    def test_log_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(log_path=p)
            entry = logger.log_decision(
                actor="sys",
                action="force_stabilize",
                reason="entropy_high",
                from_state="ACT",
                to_state="STABILIZE",
            )
            assert entry.event_type == "governance_decision"


class TestUnifiedAuditStore:
    def test_count_and_all(self) -> None:
        store = UnifiedAuditStore()
        assert store.count() == 0
        record = UnifiedAuditRecord(
            record_id="r1",
            timestamp=1.0,
            layer="meta",
            round=1,
            event_type="test",
            source_module="mod",
            target_module="mod2",
            decision="act",
            justification="because",
        )
        store.append(record)
        assert store.count() == 1
        assert len(store.all()) == 1

    def test_query_decision_chain_single(self) -> None:
        store = UnifiedAuditStore()
        r = UnifiedAuditRecord(
            record_id="r1",
            timestamp=1.0,
            layer="meta",
            round=1,
            event_type="test",
            source_module="mod",
            target_module="mod2",
            decision="act",
            justification="because",
            context_refs=[],
        )
        store.append(r)
        chain = store.query_decision_chain("r1")
        assert len(chain) == 1

    def test_query_decision_chain_with_refs(self) -> None:
        store = UnifiedAuditStore()
        r1 = UnifiedAuditRecord(
            record_id="r1",
            timestamp=1.0,
            layer="meta",
            round=1,
            event_type="t1",
            source_module="m1",
            target_module="m2",
            decision="a1",
            justification="j1",
            context_refs=["r2"],
        )
        r2 = UnifiedAuditRecord(
            record_id="r2",
            timestamp=2.0,
            layer="inner",
            round=1,
            event_type="t2",
            source_module="m2",
            target_module="m3",
            decision="a2",
            justification="j2",
            context_refs=[],
        )
        store.append(r1)
        store.append(r2)
        chain = store.query_decision_chain("r1")
        assert len(chain) >= 1

    def test_query_by_round(self) -> None:
        store = UnifiedAuditStore()
        r = UnifiedAuditRecord(
            record_id="r1",
            timestamp=1.0,
            layer="meta",
            round=5,
            event_type="t1",
            source_module="m1",
            target_module="m2",
            decision="a1",
            justification="j1",
        )
        store.append(r)
        round_5 = store.query_by_round(5)
        assert len(round_5) == 1

    def test_query_by_round_empty(self) -> None:
        store = UnifiedAuditStore()
        assert store.query_by_round(99) == []

    def test_query_by_event(self) -> None:
        store = UnifiedAuditStore()
        r = UnifiedAuditRecord(
            record_id="r1",
            timestamp=1.0,
            layer="meta",
            round=1,
            event_type="auto_evolve",
            source_module="m1",
            target_module="m2",
            decision="a1",
            justification="j1",
        )
        store.append(r)
        results = store.query_by_event("auto_evolve")
        assert len(results) == 1

    def test_stats_methods(self) -> None:
        store = UnifiedAuditStore()
        r = UnifiedAuditRecord(
            record_id="r1",
            timestamp=1.0,
            layer="meta",
            round=1,
            event_type="test",
            source_module="mod1",
            target_module="mod2",
            decision="act1",
            justification="j1",
        )
        store.append(r)
        etype_stats = store.stats_by_event_type()
        assert etype_stats.get("test", 0) >= 1
        assert store.stats_by_module().get("mod1", 0) >= 1
        assert store.stats_by_round()[1] == 1
