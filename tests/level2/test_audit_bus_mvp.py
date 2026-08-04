"""v0.48 L3 — Distributed Audit Bus MVP: cross-framework audit consistency.

Three agent frameworks (langgraph / crewai / autogen) each produce audit
events; the DistributedAuditBus normalises them to a canonical event and
verifies cross-framework consistency (same underlying action → identical
canonical digest across frameworks).
"""

from __future__ import annotations

from enum import Enum

from maref.level2.audit_bus_mvp import (
    AutoGenAdapter,
    CrewAIAdapter,
    DistributedAuditBus,
    FrameworkAuditEvent,
    LangGraphAdapter,
    normalise_metadata,
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


class TestMetadataNormalisation:
    """v0.49 P1 — metadata normalisation (type + key-order invariance)."""

    class _Severity(Enum):
        HIGH = "high"

    def test_type_variants_yield_same_digest(self) -> None:
        """tuple/set/Enum variants of equivalent metadata collapse to one."""
        base = FrameworkAuditEvent(
            event_type="agent_action", actor="a1", action="tool.call",
            framework="langgraph", metadata={"tool": "read_file", "tags": ["a", "b"]},
            timestamp=1000.0,
        )
        variant = FrameworkAuditEvent(
            event_type="agent_action", actor="a1", action="tool.call",
            framework="langgraph",
            metadata={"tool": "read_file", "tags": ("a", "b")},
            timestamp=1000.0,
        )
        assert base.canonical_digest() == variant.canonical_digest()

    def test_set_and_enum_metadata_normalised(self) -> None:
        base = FrameworkAuditEvent(
            event_type="agent_action", actor="a1", action="x",
            framework="langgraph",
            metadata={"severity": self._Severity.HIGH, "flags": {"b", "a"}},
            timestamp=1000.0,
        )
        variant = FrameworkAuditEvent(
            event_type="agent_action", actor="a1", action="x",
            framework="langgraph",
            metadata={"severity": "high", "flags": ["a", "b"]},
            timestamp=1000.0,
        )
        assert base.canonical_digest() == variant.canonical_digest()

    def test_key_order_invariance(self) -> None:
        e1 = FrameworkAuditEvent(
            event_type="agent_action", actor="a1", action="x",
            framework="langgraph",
            metadata={"a": 1, "b": 2}, timestamp=1000.0,
        )
        e2 = FrameworkAuditEvent(
            event_type="agent_action", actor="a1", action="x",
            framework="langgraph",
            metadata={"b": 2, "a": 1}, timestamp=1000.0,
        )
        assert e1.canonical_digest() == e2.canonical_digest()

    def test_normalise_metadata_is_idempotent(self) -> None:
        raw = {"b": [1, (2, 3)], "a": {"z": {1, 2}}}
        once = normalise_metadata(raw)
        assert normalise_metadata(once) == once

    def test_framework_noise_keys_stripped_for_consistency(self) -> None:
        """Framework-runtime keys (run/task ids) must not break cross-framework
        digest consistency for the same underlying action."""
        bus = _bus()
        bus.register_adapter(LangGraphAdapter())
        bus.register_adapter(CrewAIAdapter())
        bus.register_adapter(AutoGenAdapter())

        result = bus.publish_cross_framework(
            event_type="agent_action",
            actor="agent-1",
            action="tool.call",
            metadata={
                "tool": "read_file",
                # framework-runtime noise that used to diverge digests
                "tool_call_id": "call-1",
                "task_id": "task-9",
                "conversation_id": "conv-7",
            },
        )
        assert result["consistent"] is True
        assert len({f["digest"] for f in result["frameworks"].values()}) == 1


class TestSignatureAttribution:
    """v0.49 P2 — signatures bound to framework identity."""

    def test_signature_bound_to_framework(self) -> None:
        bus = _bus()
        lang = FrameworkAuditEvent(
            event_type="agent_action", actor="a1", action="tool.call",
            framework="langgraph", metadata={"tool": "read_file"}, timestamp=1000.0,
        )
        bus.publish(lang)
        assert lang.signature_scheme == "v2"
        assert bus.verify_event_signature(lang, framework="langgraph") is True

    def test_cross_framework_signature_reuse_rejected(self) -> None:
        """A langgraph signature copied onto a crewai event must fail."""
        bus = _bus()
        bus.register_adapter(LangGraphAdapter())
        bus.register_adapter(CrewAIAdapter())

        # Same canonical content in both frameworks.
        lang = LangGraphAdapter().build_event(
            "agent_action", "a1", "tool.call", {"tool": "read_file"}
        )
        lang.timestamp = 1000.0
        bus.publish(lang)

        crew = CrewAIAdapter().build_event(
            "agent_action", "a1", "tool.call", {"tool": "read_file"}
        )
        crew.timestamp = 1000.0
        crew.signature = lang.signature  # cross-framework replay
        crew.signature_scheme = "v2"

        assert bus.verify_event_signature(crew, framework="crewai") is False

    def test_legacy_v1_signature_still_verifies(self) -> None:
        """Backward compatibility: canonical-only (v0.48) signatures remain valid."""
        bus = _bus()
        event = FrameworkAuditEvent(
            event_type="agent_action", actor="a1", action="x",
            framework="langgraph", metadata={}, timestamp=1000.0,
        )
        event.signature_scheme = "v1"
        event.signature = event.sign_legacy(b"test-secret")
        assert bus.verify_event_signature(event) is True

    def test_verify_against_other_framework_rejected(self) -> None:
        """Explicit framework claim mismatch is rejected under v2."""
        bus = _bus()
        event = FrameworkAuditEvent(
            event_type="agent_action", actor="a1", action="x",
            framework="langgraph", metadata={}, timestamp=1000.0,
        )
        bus.publish(event)
        assert bus.verify_event_signature(event, framework="crewai") is False

    def test_v2_event_not_bypassed_by_legacy_v1_signature(self) -> None:
        """Review regression: a canonical-only (v1) signature must NOT verify a
        v2 event, even for identical canonical content — the v1 fallback is only
        honoured for events explicitly marked ``signature_scheme == "v1"``."""
        bus = _bus()
        event = FrameworkAuditEvent(
            event_type="agent_action", actor="a1", action="x",
            framework="langgraph", metadata={}, timestamp=1000.0,
        )
        event.signature_scheme = "v1"
        event.signature = event.sign_legacy(b"test-secret")

        v2_event = FrameworkAuditEvent(
            event_type="agent_action", actor="a1", action="x",
            framework="crewai", metadata={}, timestamp=1000.0,
        )
        v2_event.signature_scheme = "v2"
        v2_event.signature = event.signature  # v1 signature attached to v2 event

        assert bus.verify_event_signature(v2_event) is False

    def test_v1_signature_not_accepted_across_frameworks_under_v2(self) -> None:
        """Review regression: cross-framework replay of a v1 signature onto an
        event that claims v2 must fail."""
        bus = _bus()
        source = FrameworkAuditEvent(
            event_type="agent_action", actor="a1", action="x",
            framework="langgraph", metadata={}, timestamp=1000.0,
        )
        source.signature_scheme = "v1"
        source.signature = source.sign_legacy(b"test-secret")

        forged = FrameworkAuditEvent(
            event_type="agent_action", actor="a1", action="x",
            framework="crewai", metadata={}, timestamp=1000.0,
        )
        forged.signature_scheme = "v2"
        forged.signature = source.signature

        assert bus.verify_event_signature(forged, framework="crewai") is False
