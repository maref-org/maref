"""v0.48 L3 — Distributed Audit Bus MVP: cross-framework audit consistency.

Three agent frameworks (langgraph / crewai / autogen) each produce audit
events; the DistributedAuditBus normalises them to a canonical event and
verifies cross-framework consistency (same underlying action → identical
canonical digest across frameworks).
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from maref.level2.audit_bus_mvp import (
    DistributedAuditBus,
    FrameworkAuditEvent,
    LangGraphAdapter,
    CrewAIAdapter,
    AutoGenAdapter,
)


def _bus() -> DistributedAuditBus:
    return DistributedAuditBus(secret_key=b"test-secret")


class TestCanonicalEvent:
    def test_canonical_digest_deterministic(self) -> None:
        e1 = FrameworkAuditEvent(
            event_type="agent_action", actor="agent-1", action="tool.call",
            framework="langgraph", metadata={"tool": "read_file"}, timestamp=1000.0,
        )
        e2 = FrameworkAuditEvent(
            event_type="agent_action", actor="agent-1", action="tool.call",
            framework="langgraph", metadata={"tool": "read_file"}, timestamp=1000.0,
        )
        assert e1.canonical_digest() == e2.canonical_digest()
        assert isinstance(e1.canonical_digest(), str)
        assert len(e1.canonical_digest()) == 64  # sha256 hex

    def test_digest_changes_with_core_fields(self) -> None:
        base = FrameworkAuditEvent(
            event_type="agent_action", actor="agent-1", action="tool.call",
            framework="langgraph", metadata={"tool": "read_file"}, timestamp=1000.0,
        )
        assert FrameworkAuditEvent(
            event_type="agent_action", actor="agent-1", action="tool.delete",
            framework="langgraph", metadata={"tool": "read_file"}, timestamp=1000.0,
        ).canonical_digest() != base.canonical_digest()

    def test_framework_excluded_from_digest(self) -> None:
        """Framework identity must not change the canonical digest — the
        same action across frameworks yields the same digest."""
        e1 = FrameworkAuditEvent(
            event_type="agent_action", actor="agent-1", action="tool.call",
            framework="langgraph", metadata={"tool": "read_file"}, timestamp=1000.0,
        )
        e2 = FrameworkAuditEvent(
            event_type="agent_action", actor="agent-1", action="tool.call",
            framework="crewai", metadata={"tool": "read_file"}, timestamp=1000.0,
        )
        assert e1.canonical_digest() == e2.canonical_digest()


class TestCrossFrameworkConsistency:
    def test_same_action_across_frameworks_consistent(self) -> None:
        bus = _bus()
        bus.register_adapter(LangGraphAdapter())
        bus.register_adapter(CrewAIAdapter())
        bus.register_adapter(AutoGenAdapter())

        result = bus.publish_cross_framework(
            event_type="agent_action",
            actor="agent-1",
            action="tool.call",
            metadata={"tool": "read_file"},
        )
        assert result["consistent"] is True
        assert len(result["frameworks"]) == 3
        digests = {f["digest"] for f in result["frameworks"].values()}
        assert len(digests) == 1  # all frameworks agree on the canonical digest

    def test_inconsistent_event_rejected(self) -> None:
        """If a framework adapter tampers the action, consistency fails."""
        bus = _bus()
        bus.register_adapter(LangGraphAdapter())
        tampered = AutoGenAdapter()
        tampered._tamper_action = "tool.delete"  # diverges
        bus.register_adapter(tampered)

        result = bus.publish_cross_framework(
            event_type="agent_action",
            actor="agent-1",
            action="tool.call",
            metadata={"tool": "read_file"},
        )
        assert result["consistent"] is False
        digests = {f["digest"] for f in result["frameworks"].values()}
        assert len(digests) > 1

    def test_adapters_produce_signed_events(self) -> None:
        bus = _bus()
        lang = LangGraphAdapter()
        event = lang.build_event(
            event_type="agent_action", actor="a1", action="x", metadata={}
        )
        assert event.framework == "langgraph"
        bus.publish(event)  # publish signs the event
        assert bus.verify_event_signature(event) is True


class TestDistributedAuditBus:
    def test_publish_records_event(self) -> None:
        bus = _bus()
        bus.register_adapter(LangGraphAdapter())
        event = FrameworkAuditEvent(
            event_type="agent_action", actor="a1", action="x",
            framework="langgraph", metadata={},
        )
        bus.publish(event)
        log = bus.get_audit_log()
        assert len(log) == 1
        assert log[0]["action"] == "x"

    def test_audit_log_entries_have_hmac(self) -> None:
        bus = _bus()
        bus.register_adapter(LangGraphAdapter())
        event = FrameworkAuditEvent(
            event_type="agent_action", actor="a1", action="x",
            framework="langgraph", metadata={},
        )
        bus.publish(event)
        entry = bus.get_audit_log()[0]
        assert "signature" in entry
        assert entry["signature"]
