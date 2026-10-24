"""Tests for audit entry id width and legacy id compatibility (P0)."""

from __future__ import annotations

import time

from maref.governance.audit import AuditEntry, AuditLogger


def test_new_entry_ids_are_wide_and_unique(tmp_path):
    audit = AuditLogger(log_path=tmp_path / "audit.jsonl", hmac_key=b"test-key")
    ids = [
        audit.log(event_type="evidence_test", actor="agent-1", action="test").id
        for _ in range(5)
    ]

    assert len(set(ids)) == 5
    for entry_id in ids:
        assert len(entry_id) == 32
        assert set(entry_id) <= set("0123456789abcdef")


def test_legacy_eight_char_id_still_resolves(tmp_path):
    audit = AuditLogger(log_path=tmp_path / "audit.jsonl", hmac_key=b"test-key")
    legacy = AuditEntry(
        id="deadbeef",
        timestamp=time.time(),
        event_type="governance_decision",
        actor="agent-1",
        action="file.read",
        details="ALLOW: legacy",
    )

    written = audit._write(legacy)

    assert written.id == "deadbeef"
    assert audit.find_by_id("deadbeef") is not None
    assert audit.verify_entry_integrity("deadbeef")


def test_new_id_survives_restart(tmp_path):
    path = tmp_path / "audit.jsonl"
    first = AuditLogger(log_path=path, hmac_key=b"test-key")
    entry = first.log(event_type="evidence_test", actor="agent-1", action="test")

    second = AuditLogger(log_path=path, hmac_key=b"test-key")

    assert second.find_by_id(entry.id) is not None
    assert second.verify_entry_integrity(entry.id)
