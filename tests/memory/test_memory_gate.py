"""Tests for MemoryManager.write_with_gate integration."""

import pytest

from maref.memory.memory_manager import (
    ConfidenceLabel,
    MemoryManager,
    MemoryRecord,
    SourceAnnotation,
)


class TestMemoryWriteWithGate:
    def test_write_with_gate_passes(self):
        mm = MemoryManager(enable_gate=True)
        record = mm.create_record(
            content={"key": "val"},
            confidence=ConfidenceLabel.CERTAIN,
            source=SourceAnnotation.HUMAN,
        )
        stored = mm.write_with_gate(record)
        assert stored.memory_id == record.memory_id
        assert len(mm.semantic) == 1

    def test_write_with_gate_raises_on_reject(self):
        mm = MemoryManager(enable_gate=True)
        # First write a certain record
        record = mm.create_record(content={"price": 100})
        record.confidence = ConfidenceLabel.CERTAIN
        mm.write_with_gate(record)

        # Second write with conflicting data should be rejected
        conflict = mm.create_record(content={"price": 200})
        conflict.confidence = ConfidenceLabel.CERTAIN
        with pytest.raises(ValueError, match="rejected"):
            mm.write_with_gate(conflict)

    def test_write_with_gate_flag_does_not_raise(self):
        mm = MemoryManager(enable_gate=True)
        # Flagged records (e.g. near-duplicate) should still be written
        record = mm.create_record(content={"text": "hello world"})
        record.confidence = ConfidenceLabel.HIGH
        record.source = SourceAnnotation.HUMAN
        mm.write_with_gate(record)
        duplicate = mm.create_record(content={"text": "hello world"})
        duplicate.source = SourceAnnotation.HUMAN
        # Duplicate flag should not raise — it's advisory
        stored = mm.write_with_gate(duplicate)
        assert stored is not None

    def test_write_with_gate_disabled(self):
        mm = MemoryManager(enable_gate=False)
        record = mm.create_record(content={"key": "val"})
        stored = mm.write_with_gate(record)
        assert stored.memory_id == record.memory_id
