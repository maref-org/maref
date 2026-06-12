"""
AuditLogger 独立测试

覆盖审计问题 P17：HMAC 签名验证、条目不可变性、文件轮转、to_unified 转换。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from maref.governance.audit import AuditEntry, AuditLogger


class TestAuditEntry:
    def test_entry_is_frozen(self) -> None:
        entry = AuditEntry(
            id="audit_000001",
            timestamp=0.0,
            event_type="test",
            actor="test",
            action="test",
            details="",
        )
        with pytest.raises(AttributeError):
            entry.event_type = "modified"

    def test_entry_to_dict(self) -> None:
        entry = AuditEntry(
            id="audit_000001",
            timestamp=1234567890.0,
            event_type="governance_decision",
            actor="GovernanceOverlay",
            action="force_stabilize",
            details="test",
            metadata={"key": "value"},
        )
        d = entry.to_dict()
        assert d["id"] == "audit_000001"
        assert d["event_type"] == "governance_decision"
        assert "hmac_signature" not in d

    def test_entry_to_dict_with_signature(self) -> None:
        entry = AuditEntry(
            id="audit_000001",
            timestamp=0.0,
            event_type="test",
            actor="test",
            action="test",
            details="",
            hmac_signature="abc123",
        )
        d = entry.to_dict()
        assert d["hmac_signature"] == "abc123"

    def test_payload_for_signing_stable(self) -> None:
        entry1 = AuditEntry(
            id="audit_000001",
            timestamp=0.0,
            event_type="test",
            actor="test",
            action="test",
            details="",
            metadata={"b": 2, "a": 1},
        )
        entry2 = AuditEntry(
            id="audit_000001",
            timestamp=0.0,
            event_type="test",
            actor="test",
            action="test",
            details="",
            metadata={"a": 1, "b": 2},
        )
        assert entry1._payload_for_signing() == entry2._payload_for_signing()


class TestAuditLoggerHMAC:
    def test_sign_entry_with_key(self) -> None:
        logger = AuditLogger(hmac_key="secret_key")
        entry = logger.log("test", "actor", "action")
        assert entry.hmac_signature != ""
        assert len(entry.hmac_signature) == 64  # SHA-256 hex

    def test_sign_entry_without_key(self) -> None:
        logger = AuditLogger()
        entry = logger.log("test", "actor", "action")
        assert entry.hmac_signature == ""

    def test_verify_integrity_valid(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path, hmac_key="secret")
        logger.log("test", "actor", "action")
        result = logger.verify_integrity()
        assert result["integrity_intact"] is True
        assert result["valid_signatures"] == 1
        assert result["tampered_entries"] == []

    def test_verify_integrity_tampered(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path, hmac_key="secret")
        logger.log("test", "actor", "action")
        # Tamper with the file
        with open(path, "r") as f:
            line = f.read()
        data = json.loads(line)
        data["action"] = "tampered_action"
        with open(path, "w") as f:
            f.write(json.dumps(data) + "\n")
        result = logger.verify_integrity()
        assert result["integrity_intact"] is False
        assert len(result["tampered_entries"]) == 1


class TestAuditLoggerFileOperations:
    def test_log_to_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        logger = AuditLogger(log_path=path)
        entry = logger.log("test_event", "TestActor", "test_action", "details")
        assert path.exists()
        entries = logger.read_all()
        assert len(entries) == 1
        assert entries[0].event_type == "test_event"

    def test_log_to_memory(self) -> None:
        logger = AuditLogger()
        logger.log("test", "actor", "action")
        entries = logger.read_all()
        assert len(entries) == 1

    def test_read_filtered(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path)
        logger.log("type_a", "actor1", "action")
        logger.log("type_b", "actor2", "action")
        logger.log("type_a", "actor1", "action")
        filtered = logger.read_filtered(event_type="type_a", actor="actor1")
        assert len(filtered) == 2

    def test_file_rotation(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        logger = AuditLogger(log_path=path, max_file_size_mb=0)
        logger.log("test", "actor", "action")
        # Force rotation by writing a large entry
        logger._max_file_size = 1  # 1 byte
        logger.log("test2", "actor", "action")
        assert any(path.parent.glob(f"{path.stem}_*{path.suffix}"))

    def test_read_all_limit(self) -> None:
        logger = AuditLogger()
        for i in range(10):
            logger.log(f"event_{i}", "actor", "action")
        entries = logger.read_all(max_entries=5)
        assert len(entries) == 5

    def test_count(self) -> None:
        logger = AuditLogger()
        assert logger.count() == 0
        logger.log("test", "actor", "action")
        assert logger.count() == 1


class TestAuditLoggerUnified:
    def test_to_unified(self) -> None:
        entry = AuditEntry(
            id="audit_000001",
            timestamp=0.0,
            event_type="governance_decision",
            actor="GovernanceOverlay",
            action="force_stabilize",
            details="recovery success",
            metadata={"target_module": "meta_governance"},
        )
        unified = entry.to_unified(layer="governance", round_num=1)
        assert unified.record_id == "audit_000001"
        assert unified.layer == "governance"
        assert unified.round == 1
        assert unified.outcome == "success"

    def test_to_unified_failure(self) -> None:
        entry = AuditEntry(
            id="audit_000001",
            timestamp=0.0,
            event_type="circuit_breaker_trip",
            actor="CircuitBreaker",
            action="trip",
            details="failure detected",
        )
        unified = entry.to_unified()
        assert unified.outcome == "failure"

    def test_export_syslog(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path)
        logger.log("test", "actor", "action", "details")
        syslog = logger.export_syslog()
        assert "MAREF" in syslog
        assert "actor=\"actor\"" in syslog

    def test_export_json(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path)
        logger.log("test", "actor", "action")
        exported = logger.export_json()
        assert len(exported) == 1
        assert exported[0]["event_type"] == "test"


class TestAuditLoggerAnomalyDecision:
    def test_log_anomaly(self) -> None:
        logger = AuditLogger()
        entry = logger.log_anomaly(
            actor="Detector",
            anomaly_type="cpu_spike",
            severity="high",
            description="cpu usage spike",
        )
        assert entry.event_type == "anomaly_detected"
        assert entry.actor == "Detector"
        assert entry.action == "handle_anomaly"

    def test_log_anomaly_no_description(self) -> None:
        logger = AuditLogger()
        entry = logger.log_anomaly(
            actor="Detector",
            anomaly_type="memory_leak",
            severity="medium",
        )
        assert entry.event_type == "anomaly_detected"
        assert entry.metadata["anomaly_type"] == "memory_leak"
        assert entry.metadata["severity"] == "medium"

    def test_log_decision(self) -> None:
        logger = AuditLogger()
        entry = logger.log_decision(
            actor="Governor",
            action="approve_transfer",
            reason="risk acceptable",
            from_state="evaluate",
            to_state="act",
        )
        assert entry.event_type == "governance_decision"
        assert entry.actor == "Governor"
        assert entry.action == "approve_transfer"
        assert entry.metadata["from_state"] == "evaluate"
        assert entry.metadata["to_state"] == "act"


class TestAuditLoggerReadRecent:
    def test_read_recent(self) -> None:
        logger = AuditLogger()
        for i in range(10):
            logger.log(f"event_{i}", "actor", "action")
        recent = logger.read_recent(n=3)
        assert len(recent) == 3

    def test_read_recent_all(self) -> None:
        logger = AuditLogger()
        logger.log("test", "actor", "action")
        recent = logger.read_recent()
        assert len(recent) == 1

    def test_read_recent_empty(self) -> None:
        logger = AuditLogger()
        assert logger.read_recent(n=5) == []

    def test_get_audit_trail(self) -> None:
        logger = AuditLogger()
        logger.log("type_a", "actor", "action_1")
        logger.log("type_b", "actor", "action_2")
        trail = logger.get_audit_trail(max_entries=1)
        assert len(trail) == 1
        assert trail[0].action == "action_2"


class TestAuditLoggerCornerCases:
    def test_to_unified_neutral_outcome(self) -> None:
        entry = AuditEntry(
            id="audit_000001",
            timestamp=0.0,
            event_type="state_transition",
            actor="FSM",
            action="enter_observe",
            details="info",
        )
        unified = entry.to_unified()
        assert unified.outcome is None

    def test_verify_integrity_with_unsigned_entries(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path, hmac_key="secret")
        logger.log("signed_1", "actor", "action")
        # Manually append an unsigned entry
        unsigned = AuditEntry(
            id="unsigned_001",
            timestamp=1.0,
            event_type="unsigned",
            actor="actor",
            action="action",
            details="",
        )
        with open(path, "a") as f:
            f.write(json.dumps(unsigned.to_dict()) + "\n")
        result = logger.verify_integrity()
        assert result["valid_signatures"] == 1
        assert len(result["tampered_entries"]) == 0

    def test_read_all_no_limit_warning(self) -> None:
        logger = AuditLogger()
        logger.log("test", "actor", "action")
        entries = logger.read_all()  # max_entries=None
        assert len(entries) == 1

    def test_read_all_file_not_found(self) -> None:
        path = Path(tempfile.mktemp(suffix=".jsonl"))
        logger = AuditLogger(log_path=path)
        assert logger.read_all() == []

    def test_read_filtered_file_not_found(self) -> None:
        path = Path(tempfile.mktemp(suffix=".jsonl"))
        logger = AuditLogger(log_path=path)
        assert logger.read_filtered(event_type="test") == []

    def test_read_filtered_in_memory(self) -> None:
        logger = AuditLogger()
        logger.log("type_a", "actor1", "action", "detail_a")
        logger.log("type_b", "actor2", "action", "detail_b")
        logger.log("type_a", "actor2", "action", "detail_c")
        mem_filtered = logger.read_filtered(event_type="type_a")
        assert len(mem_filtered) == 2
        mem_filtered2 = logger.read_filtered(actor="actor2")
        assert len(mem_filtered2) == 2
        mem_filtered3 = logger.read_filtered(event_type="type_a", actor="actor2")
        assert len(mem_filtered3) == 1

    def test_read_filtered_in_memory_limit(self) -> None:
        logger = AuditLogger()
        for i in range(10):
            logger.log("type_a", "actor", "action")
        filtered = logger.read_filtered(max_entries=3)
        assert len(filtered) == 3

    def test_file_corruption_handling(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path)
        logger.log("good", "actor", "action")
        # Write corrupted line
        with open(path, "a") as f:
            f.write("not-json\n")
        entries = logger.read_all()
        assert len(entries) == 1
        assert entries[0].event_type == "good"

    def test_read_all_from_file_with_limit(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path)
        for i in range(10):
            logger.log(f"event_{i}", "actor", "action")
        entries = logger.read_all(max_entries=3)
        assert len(entries) == 3
