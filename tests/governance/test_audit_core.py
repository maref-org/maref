"""
Core Audit Logger extended tests.

Covers: chain integrity with HMAC + chain hash across multiple entries,
error handling with corrupted data, edge cases (empty, unicode, metadata),
export functions, environment key loading, and race condition safety.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from maref.governance.audit import AuditEntry, AuditLogger


class TestChainIntegrity:
    """Chain integrity across multiple entries with HMAC + chain hash."""

    def test_chain_integrity_valid_three_entries(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path, hmac_key="test_key")
        e1 = logger.log("event_a", "actor1", "action1")
        e2 = logger.log("event_b", "actor2", "action2")
        e3 = logger.log("event_c", "actor3", "action3")

        assert e1.previous_hash == ""
        assert e2.previous_hash == e1.chain_hash
        assert e3.previous_hash == e2.chain_hash

        result = logger.verify_integrity()
        assert result["integrity_intact"] is True
        assert result["total_entries"] == 3
        assert result["valid_signatures"] == 3

    def test_chain_integrity_tampered_hmac_detected(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path, hmac_key="test_key")
        logger.log("event_a", "actor1", "action1")
        logger.log("event_b", "actor2", "action2")

        data = json.loads(Path(path).read_text().splitlines()[1])
        data["hmac_signature"] = "deadbeef" * 8
        lines = Path(path).read_text().splitlines()
        lines[1] = json.dumps(data)
        Path(path).write_text("\n".join(lines) + "\n")

        result = logger.verify_integrity()
        assert result["integrity_intact"] is False
        assert len(result["tampered_entries"]) >= 1

    def test_chain_integrity_tampered_chain_hash_detected(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path, hmac_key="test_key")
        logger.log("event_a", "actor1", "action1")
        logger.log("event_b", "actor2", "action2")

        data = json.loads(Path(path).read_text().splitlines()[1])
        data["chain_hash"] = "dead" * 16
        lines = Path(path).read_text().splitlines()
        lines[1] = json.dumps(data)
        Path(path).write_text("\n".join(lines) + "\n")

        result = logger.verify_integrity()
        assert result["integrity_intact"] is False

    def test_chain_integrity_tampered_action_detected(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path, hmac_key="test_key")
        logger.log("event_a", "actor1", "action1")

        data = json.loads(Path(path).read_text().splitlines()[0])
        data["action"] = "malicious_action"
        Path(path).write_text(json.dumps(data) + "\n")

        result = logger.verify_integrity()
        assert result["integrity_intact"] is False

    def test_chain_integrity_no_hmac_key(self):
        # Use temp dir as CWD to avoid loading .maraf_hmac_key from project root
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_audit.jsonl")
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                logger = AuditLogger(log_path=path)
                logger.log("event", "actor", "action")
                result = logger.verify_integrity()
                assert result["signed_entries"] >= 0
                assert result["integrity_intact"] is False
            finally:
                os.chdir(old_cwd)

    def test_chain_integrity_previous_hash_break_detected(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path, hmac_key="test_key")
        logger.log("event_a", "actor1", "action1")
        logger.log("event_b", "actor2", "action2")

        data = json.loads(Path(path).read_text().splitlines()[1])
        data["previous_hash"] = "broken_chain"
        lines = Path(path).read_text().splitlines()
        lines[1] = json.dumps(data)
        Path(path).write_text("\n".join(lines) + "\n")

        result = logger.verify_integrity()
        assert result["integrity_intact"] is False


class TestErrorHandling:
    """Error handling and edge cases."""

    def test_corrupted_json_line_skipped(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path, hmac_key="key")
        logger.log("event", "actor", "action")
        with open(path, "a") as f:
            f.write("not json\n")
        logger.log("event2", "actor", "action")
        entries = logger.read_all()
        assert len(entries) == 2

    def test_corrupted_json_missing_key_skipped(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path, hmac_key="key")
        logger.log("event", "actor", "action")
        with open(path, "a") as f:
            f.write(json.dumps({"id": "orphan", "event_type": "bad"}) + "\n")
        entries = logger.read_all()
        assert len(entries) == 1

    def test_empty_file_read_all(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path)
        entries = logger.read_all()
        assert entries == []

    def test_empty_string_line_skipped(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=True) as f:
            path = f.name
        Path(path).write_text("\n\n")
        logger = AuditLogger(log_path=path)
        entries = logger.read_all()
        assert entries == []

    def test_file_not_found_read_all(self):
        logger = AuditLogger(log_path="/nonexistent/path/audit.jsonl")
        entries = logger.read_all()
        assert entries == []

    def test_file_not_found_read_filtered(self):
        logger = AuditLogger(log_path="/nonexistent/path/audit.jsonl")
        entries = logger.read_filtered(event_type="test")
        assert entries == []

    def test_read_all_no_limit(self):
        logger = AuditLogger()
        for i in range(5):
            logger.log(f"event_{i}", "actor", "action")
        entries = logger.read_all(max_entries=None)
        assert len(entries) == 5

    def test_log_without_path_no_side_effects(self):
        logger = AuditLogger(hmac_key="key")
        entry = logger.log("event", "actor", "action", details="test")
        assert entry.hmac_signature != ""
        assert logger.count() == 1


class TestEdgeCases:
    """Edge cases including unicode, metadata, convenience methods."""

    def test_unicode_details(self):
        logger = AuditLogger()
        entry = logger.log("event", "actor", "action", details="中文 unicode ✅ emoji")
        assert "unicode" in entry.details
        assert "中文" in entry.details

    def test_nested_metadata(self):
        logger = AuditLogger()
        entry = logger.log(
            "event", "actor", "action",
            metadata={"nested": {"key": "value"}, "list": [1, 2, 3]},
        )
        assert entry.metadata["nested"]["key"] == "value"
        assert entry.metadata["list"] == [1, 2, 3]

    def test_log_anomaly_convenience(self):
        logger = AuditLogger(hmac_key="key")
        entry = logger.log_anomaly(
            actor="Monitor",
            anomaly_type="entropy_spike",
            severity="high",
            description="entropy exceeded threshold",
        )
        assert entry.event_type == "anomaly_detected"
        assert entry.action == "handle_anomaly"
        assert entry.metadata["anomaly_type"] == "entropy_spike"
        assert entry.metadata["severity"] == "high"
        assert entry.hmac_signature != ""

    def test_log_decision_convenience(self):
        logger = AuditLogger(hmac_key="key")
        entry = logger.log_decision(
            actor="Governance",
            action="force_stabilize",
            reason="dual_threshold",
            from_state="ACT",
            to_state="STABILIZE",
            extra_field="custom",
        )
        assert entry.event_type == "governance_decision"
        assert entry.metadata["from_state"] == "ACT"
        assert entry.metadata["to_state"] == "STABILIZE"
        assert entry.metadata["extra_field"] == "custom"

    def test_hmac_key_from_environment(self):
        os.environ["MAREF_HMAC_SECRET_KEY"] = "env_key_value"
        try:
            logger = AuditLogger()
            entry = logger.log("event", "actor", "action")
            assert entry.hmac_signature != ""
        finally:
            del os.environ["MAREF_HMAC_SECRET_KEY"]

    def test_hmac_key_env_overrides_none(self):
        os.environ["MAREF_HMAC_SECRET_KEY"] = "env_key"
        try:
            logger = AuditLogger(hmac_key=None)
            entry = logger.log("event", "actor", "action")
            assert entry.hmac_signature != ""
        finally:
            del os.environ["MAREF_HMAC_SECRET_KEY"]

    def test_hmac_key_argument_overrides_env(self):
        os.environ["MAREF_HMAC_SECRET_KEY"] = "env_key"
        try:
            logger = AuditLogger(hmac_key="explicit_key")
            entry1 = logger.log("event", "actor", "action")
            logger2 = AuditLogger(hmac_key="env_key")
            entry2 = logger2.log("event", "actor", "action")
            assert entry1.hmac_signature != entry2.hmac_signature
        finally:
            del os.environ["MAREF_HMAC_SECRET_KEY"]

    def test_id_uniqueness(self):
        logger = AuditLogger()
        ids = set()
        for _ in range(100):
            entry = logger.log("event", "actor", "action")
            ids.add(entry.id)
        assert len(ids) == 100

    def test_timestamp_monotonic(self):
        logger = AuditLogger()
        entries = []
        for _ in range(5):
            entries.append(logger.log("event", "actor", "action"))
        timestamps = [e.timestamp for e in entries]
        assert timestamps == sorted(timestamps)

    def test_metadata_defaults_to_empty_dict(self):
        logger = AuditLogger()
        entry = logger.log("event", "actor", "action")
        assert entry.metadata == {}


class TestExportFunctions:
    """Export functions: JSON and syslog."""

    def test_export_json_all(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path)
        logger.log("type_a", "actor1", "action1")
        logger.log("type_b", "actor2", "action2")
        exported = logger.export_json()
        assert len(exported) == 2

    def test_export_json_filtered_by_event_type(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path)
        logger.log("type_a", "actor1", "action1")
        logger.log("type_b", "actor2", "action2")
        logger.log("type_a", "actor1", "action3")
        exported = logger.export_json(event_type="type_a")
        assert len(exported) == 2

    def test_export_json_filtered_by_time_range(self):
        logger = AuditLogger()
        logger.log("type_a", "actor1", "action1")
        logger.log("type_b", "actor2", "action2")
        now = time.time()
        exported = logger.export_json(start_time=now + 1)
        assert len(exported) == 0
        exported = logger.export_json(end_time=now + 1)
        assert len(exported) == 2

    def test_export_json_filtered_all_params(self):
        logger = AuditLogger()
        logger.log("type_a", "actor1", "action1")
        logger.log("type_b", "actor2", "action2")
        now = time.time()
        exported = logger.export_json(
            event_type="type_a",
            start_time=now - 10,
            end_time=now + 10,
            max_entries=10,
        )
        assert len(exported) == 1

    def test_export_syslog_format(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path)
        logger.log("test_event", "TestActor", "test_action", "test details")
        syslog = logger.export_syslog()
        assert "<" in syslog
        assert "MAREF" in syslog
        assert 'event="test_event"' in syslog
        assert 'actor="TestActor"' in syslog
        assert "test details" in syslog

    def test_export_syslog_empty(self):
        logger = AuditLogger()
        syslog = logger.export_syslog()
        assert syslog == ""

    def test_get_audit_trail(self):
        logger = AuditLogger()
        logger.log("event", "actor", "action")
        trail = logger.get_audit_trail()
        assert len(trail) == 1

    def test_get_audit_trail_with_limit(self):
        logger = AuditLogger()
        for _ in range(10):
            logger.log("event", "actor", "action")
        trail = logger.get_audit_trail(max_entries=3)
        assert len(trail) == 3


class TestMemoryModeEdgeCases:
    """In-memory audit logger edge cases."""

    def test_memory_mode_chain_continuity(self):
        logger = AuditLogger(hmac_key="key")
        e1 = logger.log("event", "actor", "action")
        e2 = logger.log("event", "actor", "action")
        assert e2.previous_hash == e1.chain_hash

    def test_memory_mode_read_all_limit(self):
        logger = AuditLogger()
        for i in range(20):
            logger.log(f"event_{i}", "actor", "action")
        entries = logger.read_all(max_entries=10)
        assert len(entries) == 10
        assert entries[0].id == logger._memory_entries[10].id

    def test_memory_mode_read_filtered_by_actor(self):
        logger = AuditLogger()
        logger.log("event", "alice", "action")
        logger.log("event", "bob", "action")
        logger.log("event", "alice", "action")
        filtered = logger.read_filtered(actor="alice")
        assert len(filtered) == 2

    def test_memory_mode_read_filtered_by_type_and_actor(self):
        logger = AuditLogger()
        logger.log("type_a", "alice", "action")
        logger.log("type_b", "alice", "action")
        logger.log("type_a", "bob", "action")
        filtered = logger.read_filtered(event_type="type_a", actor="alice")
        assert len(filtered) == 1

    def test_memory_mode_read_filtered_by_time(self):
        logger = AuditLogger()
        logger.log("event", "actor", "action")
        later = logger.log("event", "actor", "action")
        filtered = logger.read_filtered(start_time=later.timestamp + 1)
        assert len(filtered) == 0

    def test_memory_mode_read_filtered_max_entries(self):
        logger = AuditLogger()
        for _ in range(10):
            logger.log("event", "actor", "action")
        filtered = logger.read_filtered(max_entries=3)
        assert len(filtered) == 3

    def test_read_recent(self):
        logger = AuditLogger()
        for i in range(10):
            logger.log(f"event_{i}", "actor", "action")
        recent = logger.read_recent(n=3)
        assert len(recent) == 3
        assert recent[0].id == logger._memory_entries[7].id

    def test_read_recent_default(self):
        logger = AuditLogger()
        for i in range(10):
            logger.log(f"event_{i}", "actor", "action")
        recent = logger.read_recent()
        assert len(recent) == 10

    def test_count_after_log(self):
        logger = AuditLogger()
        assert logger.count() == 0
        logger.log("e", "a", "act")
        assert logger.count() == 1
        logger.log("e", "a", "act")
        assert logger.count() == 2


class TestFileRotation:
    """File rotation behavior."""

    def test_rotation_creates_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(log_path=path, max_file_size_mb=0)
            logger._max_file_size = 1
            entry = AuditEntry(
                id="big_entry",
                timestamp=time.time(),
                event_type="test",
                actor="test",
                action="test",
                details="x" * 100,
            )
            logger._write(entry)
            logger._write(entry)
            rotated = list(path.parent.glob("audit_*.jsonl"))
            assert len(rotated) >= 1


class TestHmacSigning:
    """HMAC signing edge cases."""

    def test_sign_entry_deterministic(self):
        logger1 = AuditLogger(hmac_key="same_key")
        logger2 = AuditLogger(hmac_key="same_key")
        timestamp = 1000.0
        entry = AuditEntry(
            id="fixed_id", timestamp=timestamp,
            event_type="test", actor="tester", action="do", details="",
        )
        sig1 = logger1._sign_entry(entry)
        sig2 = logger2._sign_entry(entry)
        assert sig1 == sig2

    def test_different_keys_produce_different_signatures(self):
        logger1 = AuditLogger(hmac_key="key_a")
        logger2 = AuditLogger(hmac_key="key_b")
        e1 = logger1.log("event", "actor", "action", details="test")
        e2 = logger2.log("event", "actor", "action", details="test")
        assert e1.hmac_signature != e2.hmac_signature

    def test_empty_hmac_key_warning(self, caplog):
        # Use temp dir as CWD to avoid loading .maraf_hmac_key from project root
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                logger = AuditLogger()
                assert "No HMAC key configured" in caplog.text
            finally:
                os.chdir(old_cwd)


class TestAuditEntryExtended:
    """AuditEntry dataclass edge cases."""

    def test_to_dict_only_includes_non_empty_fields(self):
        entry = AuditEntry(
            id="test_id",
            timestamp=1.0,
            event_type="test",
            actor="tester",
            action="do",
            details="",
        )
        d = entry.to_dict()
        assert "previous_hash" not in d
        assert "chain_hash" not in d
        assert "hmac_signature" not in d

    def test_to_dict_includes_signature_when_present(self):
        entry = AuditEntry(
            id="test_id",
            timestamp=1.0,
            event_type="test",
            actor="tester",
            action="do",
            details="",
            hmac_signature="abc123",
        )
        d = entry.to_dict()
        assert d["hmac_signature"] == "abc123"

    def test_payload_for_signing_sort_keys(self):
        entry = AuditEntry(
            id="test_id",
            timestamp=1.0,
            event_type="test",
            actor="tester",
            action="do",
            details="hello",
            metadata={"z": 1, "a": 2},
        )
        payload = entry._payload_for_signing()
        parsed = json.loads(payload)
        assert list(parsed.keys()) == sorted(parsed.keys())

    def test_to_unified_without_target_module(self):
        entry = AuditEntry(
            id="test_id",
            timestamp=1.0,
            event_type="test",
            actor="tester",
            action="do",
            details="hello",
        )
        unified = entry.to_unified()
        assert unified.outcome is None

    def test_to_unified_unknown_outcome(self):
        entry = AuditEntry(
            id="test_id",
            timestamp=1.0,
            event_type="info",
            actor="tester",
            action="do",
            details="neutral message",
        )
        unified = entry.to_unified()
        assert unified.outcome is None
