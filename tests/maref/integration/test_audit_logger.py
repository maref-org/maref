"""Smoke tests for maref.integration.audit_logger."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from maref.integration.audit_logger import AuditLogger, AuditRecord


class TestAuditRecord:
    def test_init_default(self) -> None:
        record = AuditRecord(
            timestamp=100.0, agent_id="a1", mcp_server="mcp_GitHub",
            tool_name="create_issue", verdict="allow", args_hash="abc123",
        )
        assert record.agent_id == "a1"
        assert record.verdict == "allow"
        assert record.risk_score == 0.0
        assert record.metadata == {}

    def test_init_custom(self) -> None:
        record = AuditRecord(
            timestamp=200.0, agent_id="a2", mcp_server="mcp_Filesystem",
            tool_name="write_file", verdict="deny", args_hash="def456",
            risk_score=0.8, latency_ms=50.0, metadata={"reason": "high_risk"},
        )
        assert record.risk_score == 0.8
        assert record.metadata["reason"] == "high_risk"

    def test_to_json_line(self) -> None:
        record = AuditRecord(
            timestamp=100.0, agent_id="a1", mcp_server="mcp_GitHub",
            tool_name="create_issue", verdict="allow", args_hash="abc123",
        )
        line = record.to_json_line()
        data = json.loads(line)
        assert data["agent_id"] == "a1"
        assert data["verdict"] == "allow"

    def test_from_dict(self) -> None:
        data = {
            "timestamp": 100.0, "agent_id": "a1", "mcp_server": "mcp_GitHub",
            "tool_name": "create_issue", "verdict": "allow", "args_hash": "abc123",
            "risk_score": 0.5, "latency_ms": 30.0,
        }
        record = AuditRecord.from_dict(data)
        assert record.agent_id == "a1"
        assert record.risk_score == 0.5


class TestAuditLogger:
    def test_init_default(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path / "audit")
        assert logger is not None
        assert logger.log_dir == tmp_path / "audit"
        assert logger.log_dir.exists()

    def test_log_call(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path / "audit")
        record = logger.log_call(
            agent_id="test_agent",
            mcp_server="mcp_GitHub",
            tool_name="create_issue",
            verdict="allow",
            args={"title": "Test"},
            risk_score=0.3,
        )
        assert record.agent_id == "test_agent"
        assert record.verdict == "allow"
        assert record.args_hash is not None
        log_file = logger.log_dir / "mcp_audit.jsonl"
        assert log_file.exists()
        content = log_file.read_text()
        assert "test_agent" in content

    def test_query_empty(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path / "audit")
        results = logger.query(agent_id="nonexistent")
        assert results == []

    def test_query_with_data(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path / "audit")
        logger.log_call(agent_id="agent1", mcp_server="mcp_X", tool_name="t1", verdict="allow")
        logger.log_call(agent_id="agent2", mcp_server="mcp_Y", tool_name="t2", verdict="deny")
        results = logger.query(agent_id="agent1")
        assert len(results) == 1
        assert results[0].agent_id == "agent1"
