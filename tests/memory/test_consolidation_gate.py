"""Tests for ConsolidationGate — four-question admission control."""

import pytest

from maref.memory.consolidation_gate import ConsolidationGate, GateDecision
from maref.memory.memory_manager import (
    ConfidenceLabel,
    MemoryRecord,
    SourceAnnotation,
)


class TestConsolidationGate:
    def test_pass_clean_record(self):
        gate = ConsolidationGate()
        record = MemoryRecord(
            content={"key": "value"},
            confidence=ConfidenceLabel.HIGH,
            source=SourceAnnotation.HUMAN,
        )
        result = gate.evaluate(record)
        assert result.decision == GateDecision.PASS

    def test_reject_empty_content(self):
        gate = ConsolidationGate()
        record = MemoryRecord(content={})
        result = gate.evaluate(record)
        assert result.decision == GateDecision.REJECT
        assert "empty" in result.reason.lower()

    def test_flag_duplicate_content(self):
        gate = ConsolidationGate()
        existing = [
            MemoryRecord(memory_id="m1", content={"text": "hello world"})
        ]
        record = MemoryRecord(content={"text": "hello world"})
        result = gate.evaluate(record, existing)
        assert result.decision == GateDecision.FLAG
        assert "duplicate" in result.reason

    def test_reject_conflict_with_certain(self):
        gate = ConsolidationGate()
        existing = [
            MemoryRecord(
                memory_id="m1",
                content={"price": 100},
                confidence=ConfidenceLabel.CERTAIN,
            )
        ]
        record = MemoryRecord(
            content={"price": 200},
            confidence=ConfidenceLabel.HIGH,
        )
        result = gate.evaluate(record, existing)
        assert result.decision == GateDecision.REJECT
        assert "conflict" in result.reason

    def test_flag_high_confidence_from_low_source(self):
        gate = ConsolidationGate()
        record = MemoryRecord(
            content={"key": "val"},
            confidence=ConfidenceLabel.CERTAIN,
            source=SourceAnnotation.AGENT_INFERENCE,
        )
        result = gate.evaluate(record)
        assert result.decision == GateDecision.FLAG
        assert "confidence" in result.reason

    def test_low_confidence_skips_conflict_check(self):
        gate = ConsolidationGate()
        existing = [
            MemoryRecord(
                memory_id="m1",
                content={"key": "original"},
                confidence=ConfidenceLabel.CERTAIN,
            )
        ]
        record = MemoryRecord(
            content={"key": "different"},
            confidence=ConfidenceLabel.LOW,
        )
        result = gate.evaluate(record, existing)
        assert result.decision == GateDecision.PASS

    def test_all_checks_in_result(self):
        gate = ConsolidationGate()
        record = MemoryRecord(content={"key": "val"})
        result = gate.evaluate(record)
        assert "dedup" in result.checks
        assert "conflict" in result.checks
        assert "source" in result.checks
        assert "validation" in result.checks
