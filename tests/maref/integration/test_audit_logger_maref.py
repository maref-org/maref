"""Supplementary tests for maref.integration.audit_logger.

Covers edge cases, HMAC verification integrity, multi-record ops, error handling.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from maref.integration.audit_logger import AuditLogger, AuditRecord


class TestAuditRecordEdgeCases:
    def test_empty_agent_id(self) -> None:
        record = AuditRecord(
            timestamp=0.0, agent_id="", mcp_server="mcp_X",
            tool_name="t", verdict="allow", args_hash="abc",
        )
        assert record.agent_id == ""
        line = record.to_json_line()
        assert json.loads(line)["agent_id"] == ""

    def test_special_chars_in_agent_id(self) -> None:
        agent_id = "agent@#$%^&*()_+{}|:\"<>?/你好"
        record = AuditRecord(
            timestamp=0.0, agent_id=agent_id, mcp_server="mcp_X",
            tool_name="t", verdict="allow", args_hash="abc",
        )
        assert record.agent_id == agent_id
        line = record.to_json_line()
        assert json.loads(line)["agent_id"] == agent_id

    def test_very_long_strings(self) -> None:
        long_agent = "a" * 10000
        long_tool = "tool_" + "x" * 5000
        record = AuditRecord(
            timestamp=0.0, agent_id=long_agent, mcp_server="mcp_X",
            tool_name=long_tool, verdict="allow", args_hash="abc",
        )
        line = record.to_json_line()
        data = json.loads(line)
        assert len(data["agent_id"]) == 10000
        assert len(data["tool_name"]) == 5005

    def test_unicode_verdict(self) -> None:
        record = AuditRecord(
            timestamp=0.0, agent_id="a1", mcp_server="mcp_X",
            tool_name="t", verdict="允许/Допустимо/ALLOW", args_hash="abc",
        )
        line = record.to_json_line()
        data = json.loads(line)
        assert data["verdict"] == "允许/Допустимо/ALLOW"

    def test_negative_risk_score(self) -> None:
        record = AuditRecord(
            timestamp=0.0, agent_id="a1", mcp_server="mcp_X",
            tool_name="t", verdict="allow", args_hash="abc",
            risk_score=-1.0,
        )
        assert record.risk_score == -1.0

    def test_metadata_merges_into_json_line(self) -> None:
        record = AuditRecord(
            timestamp=0.0, agent_id="a1", mcp_server="mcp_X",
            tool_name="t", verdict="allow", args_hash="abc",
            metadata={"extra_key": "extra_val", "agent_id": "overwritten"},
        )
        line = record.to_json_line()
        data = json.loads(line)
        assert data["extra_key"] == "extra_val"


class TestAuditRecordRoundTrip:
    def test_from_dict_roundtrip(self) -> None:
        original = AuditRecord(
            timestamp=123.0, agent_id="a1", mcp_server="mcp_GitHub",
            tool_name="create_issue", verdict="allow", args_hash="abc123",
            risk_score=0.5, latency_ms=30.0,
            metadata={"branch": "main"},
        )
        data = json.loads(original.to_json_line())
        restored = AuditRecord.from_dict(data)
        assert restored.agent_id == original.agent_id
        assert restored.timestamp == original.timestamp
        assert restored.risk_score == original.risk_score
        assert restored.metadata == original.metadata

    def test_from_dict_missing_optional_fields(self) -> None:
        data = {
            "timestamp": 100.0, "agent_id": "a1", "mcp_server": "mcp_X",
            "tool_name": "t", "verdict": "allow", "args_hash": "abc",
        }
        record = AuditRecord.from_dict(data)
        assert record.risk_score == 0.0
        assert record.latency_ms == 0.0
        assert record.metadata == {}

    def test_from_dict_extra_fields_become_metadata(self) -> None:
        data = {
            "timestamp": 100.0, "agent_id": "a1", "mcp_server": "mcp_X",
            "tool_name": "t", "verdict": "allow", "args_hash": "abc",
            "unknown_field": "some_value",
        }
        record = AuditRecord.from_dict(data)
        assert record.metadata["unknown_field"] == "some_value"

    def test_from_dict_missing_required_fields(self) -> None:
        with pytest.raises(KeyError):
            AuditRecord.from_dict({"timestamp": 100.0, "agent_id": "a1"})


class TestAuditLoggerHMAC:
    def test_sign_with_custom_secret(self, tmp_path: Path) -> None:
        secret = b"my-custom-secret-42"
        logger = AuditLogger(log_dir=tmp_path / "audit", hmac_secret=secret)
        record = logger.log_call(
            agent_id="agent1", mcp_server="mcp_X",
            tool_name="t1", verdict="allow",
        )
        log_file = logger._current_log_file
        line = log_file.read_text().strip()
        parts = line.rsplit("\t", 1)
        assert len(parts) == 2
        expected_sig = hmac.new(
            secret,
            json.dumps({
                "timestamp": record.timestamp,
                "agent_id": record.agent_id,
                "mcp_server": record.mcp_server,
                "tool_name": record.tool_name,
                "verdict": record.verdict,
                "args_hash": record.args_hash,
            }, sort_keys=True).encode(),
            hashlib.sha256,
        ).hexdigest()
        assert hmac.compare_digest(parts[1], expected_sig)

    def test_different_secret_different_signature(self, tmp_path: Path) -> None:
        logger1 = AuditLogger(log_dir=tmp_path / "audit1", hmac_secret=b"secret-a")
        logger2 = AuditLogger(log_dir=tmp_path / "audit2", hmac_secret=b"secret-b")
        r1 = logger1.log_call(agent_id="a", mcp_server="mcp_X", tool_name="t", verdict="allow")
        r2 = logger2.log_call(agent_id="a", mcp_server="mcp_X", tool_name="t", verdict="allow")
        sig1 = logger1._sign(r1)
        sig2 = logger2._sign(r2)
        assert sig1 != sig2

    def test_signature_verification_valid(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path / "audit", hmac_secret=b"test-secret")
        logger.log_call(agent_id="a1", mcp_server="mcp_X", tool_name="t1", verdict="allow")
        result = logger.verify_integrity()
        assert result["status"] == "verified"
        assert result["valid"] == 1
        assert result["invalid"] == 0

    def test_signature_verification_tampered(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path / "audit", hmac_secret=b"test-secret")
        logger.log_call(agent_id="a1", mcp_server="mcp_X", tool_name="t1", verdict="allow")
        log_file = logger._current_log_file
        content = log_file.read_text()
        tampered = content.replace('"verdict": "allow"', '"verdict": "DENY"')
        log_file.write_text(tampered)
        result = logger.verify_integrity()
        assert result["status"] == "tampered"
        assert result["invalid"] == 1

    def test_verify_integrity_empty_file(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path / "audit")
        assert not logger._current_log_file.exists()
        result = logger.verify_integrity()
        assert result["status"] == "no_file"
        assert result["verified"] is True

    def test_signature_changes_with_content(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path / "audit", hmac_secret=b"key")
        r1 = logger.log_call(
            agent_id="a", mcp_server="mcp_X", tool_name="t", verdict="allow",
            args={"x": 1},
        )
        r2 = logger.log_call(
            agent_id="a", mcp_server="mcp_X", tool_name="t", verdict="allow",
            args={"x": 2},
        )
        sig1 = logger._sign(r1)
        sig2 = logger._sign(r2)
        assert sig1 != sig2


class TestAuditLoggerMultiRecord:
    def test_write_multiple_records(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path / "audit")
        for i in range(10):
            logger.log_call(
                agent_id=f"agent_{i}", mcp_server="mcp_X",
                tool_name="t", verdict="allow",
            )
        count = sum(1 for _ in logger._current_log_file.open() if _.strip())
        assert count == 10

    def test_read_all_records(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path / "audit")
        for i in range(5):
            logger.log_call(
                agent_id=f"a{i}", mcp_server="mcp_X",
                tool_name=f"t{i}", verdict="allow" if i % 2 == 0 else "deny",
            )
        all_records = logger.query(limit=100)
        assert len(all_records) == 5

    def test_query_limit(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path / "audit")
        for i in range(20):
            logger.log_call(
                agent_id="a1", mcp_server="mcp_X",
                tool_name="t", verdict="allow",
            )
        results = logger.query(agent_id="a1", limit=5)
        assert len(results) == 5

    def test_query_multiple_filters(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path / "audit")
        logger.log_call(agent_id="a1", mcp_server="mcp_X", tool_name="read", verdict="allow")
        logger.log_call(agent_id="a1", mcp_server="mcp_X", tool_name="write", verdict="deny")
        logger.log_call(agent_id="a2", mcp_server="mcp_X", tool_name="read", verdict="allow")
        results = logger.query(agent_id="a1", tool_name="read")
        assert len(results) == 1
        assert results[0].verdict == "allow"

    def test_get_stats(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path / "audit")
        logger.log_call(agent_id="a1", mcp_server="mcp_X", tool_name="t", verdict="ALLOW")
        logger.log_call(agent_id="a2", mcp_server="mcp_X", tool_name="t", verdict="DENY")
        logger.log_call(agent_id="a3", mcp_server="mcp_X", tool_name="t", verdict="ALLOW")
        stats = logger.get_stats(window_hours=24.0)
        assert stats["total"] == 3
        assert stats["allowed"] == 2
        assert stats["denied"] == 1


class TestAuditLoggerErrorHandling:
    def test_corrupted_json_line_skipped(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path / "audit")
        logger.log_call(agent_id="a1", mcp_server="mcp_X", tool_name="t", verdict="allow")
        log_file = logger._current_log_file
        with log_file.open("a") as f:
            f.write("not-json\tabc123\n")
        results = logger.query()
        assert len(results) == 1

    def test_missing_tab_separator_skipped(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path / "audit")
        logger.log_call(agent_id="a1", mcp_server="mcp_X", tool_name="t", verdict="allow")
        log_file = logger._current_log_file
        with log_file.open("a") as f:
            f.write('{"bad":"line"}\n')
        results = logger.query()
        assert len(results) == 1

    def test_empty_line_skipped(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path / "audit")
        logger.log_call(agent_id="a1", mcp_server="mcp_X", tool_name="t", verdict="allow")
        log_file = logger._current_log_file
        with log_file.open("a") as f:
            f.write("\n")
            f.write("   \n")
        results = logger.query()
        assert len(results) == 1

    def test_query_nonexistent_log_file(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path / "empty_audit")
        results = logger.query(agent_id="nonexistent")
        assert results == []


class TestAuditLoggerFileRotation:
    def test_rotate_when_file_exceeds_max_size(self, tmp_path: Path) -> None:
        logger = AuditLogger(
            log_dir=tmp_path / "audit",
            max_file_size_mb=0,
            hmac_secret=b"test",
        )
        logger.log_call(agent_id="a1", mcp_server="mcp_X", tool_name="t", verdict="allow")
        original_path = logger._current_log_file
        logger._rotate_if_needed()
        rotated_files = list(logger.log_dir.glob("mcp_audit_*.jsonl"))
        assert len(rotated_files) >= 1

    def test_rotation_creates_archived_file(self, tmp_path: Path) -> None:
        logger = AuditLogger(
            log_dir=tmp_path / "audit",
            max_file_size_mb=0,
            hmac_secret=b"test",
        )
        logger.log_call(agent_id="a1", mcp_server="mcp_X", tool_name="t", verdict="allow")
        logger._rotate_if_needed()
        rotated = list(logger.log_dir.glob("mcp_audit_*.jsonl"))
        assert len(rotated) >= 1
        assert rotated[0].stat().st_size > 0
        assert not logger._current_log_file.exists()

    def test_multiple_rotations(self, tmp_path: Path) -> None:
        logger = AuditLogger(
            log_dir=tmp_path / "audit",
            max_file_size_mb=0,
            hmac_secret=b"test",
        )
        for i in range(5):
            logger.log_call(
                agent_id=f"a{i}", mcp_server="mcp_X",
                tool_name="t", verdict="allow",
            )
            logger._rotate_if_needed()
        rotated = list(logger.log_dir.glob("mcp_audit_*.jsonl"))
        assert len(rotated) >= 1
        for f in rotated:
            assert f.stat().st_size > 0


class TestAuditLoggerGetStats:
    def test_get_stats_empty(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path / "audit")
        stats = logger.get_stats()
        assert stats["total"] == 0
        assert stats["allowed"] == 0
        assert stats["denied"] == 0

    def test_get_stats_time_window(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path / "audit")
        logger.log_call(agent_id="a1", mcp_server="mcp_X", tool_name="t", verdict="ALLOW")
        with patch("maref.integration.audit_logger.time") as mock_time:
            mock_time.time.return_value = time.time() + 48 * 3600
            stats = logger.get_stats(window_hours=24.0)
            assert stats["total"] == 0
