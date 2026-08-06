"""v0.49 P4 — Persistent audit store: SQLite persistence + replay + integrity.

Verifies that audit events survive process restarts (persistence), can be
filtered, and that stored signatures verify (incl. tamper detection and
cross-framework replay rejection).
"""

from __future__ import annotations

from maref.level2.audit_bus_mvp import (
    AutoGenAdapter,
    CrewAIAdapter,
    DistributedAuditBus,
    LangGraphAdapter,
)
from maref.level2.audit_store import PersistentAuditStore


def _filled_store(tmp_path) -> PersistentAuditStore:
    store = PersistentAuditStore(tmp_path / "audit.db")
    bus = DistributedAuditBus(secret_key=b"secret", store=store)
    bus.register_adapter(LangGraphAdapter())
    bus.register_adapter(CrewAIAdapter())
    bus.register_adapter(AutoGenAdapter())
    bus.publish_cross_framework(
        event_type="agent_action",
        actor="agent-1",
        action="tool.call",
        metadata={"tool": "read_file"},
    )
    bus.publish_cross_framework(
        event_type="agent_action",
        actor="agent-2",
        action="tool.call",
        metadata={"tool": "write_file"},
    )
    return store


class TestPersistence:
    def test_events_persisted_and_survive_restart(self, tmp_path) -> None:
        store = _filled_store(tmp_path)
        assert store.count() == 6  # 3 frameworks × 2 actions

        # Simulate a process restart: reopen the same DB file.
        reopened = PersistentAuditStore(tmp_path / "audit.db")
        assert reopened.count() == 6
        events = reopened.replay()
        assert len(events) == 6
        actors = {e.actor for e in events}
        assert actors == {"agent-1", "agent-2"}
        frameworks = {e.framework for e in events}
        assert frameworks == {"langgraph", "crewai", "autogen"}

    def test_query_filters(self, tmp_path) -> None:
        store = _filled_store(tmp_path)
        by_actor = store.query(actor="agent-1")
        assert len(by_actor) == 3
        by_fw = store.query(framework="langgraph")
        assert len(by_fw) == 2
        by_type = store.query(event_type="agent_action")
        assert len(by_type) == 6

    def test_replayed_events_round_trip_metadata(self, tmp_path) -> None:
        store = _filled_store(tmp_path)
        events = store.replay()
        lang = next(e for e in events if e.framework == "langgraph")
        assert lang.metadata == {"tool": "read_file"}
        assert lang.action == "tool.call"


class TestIntegrity:
    def test_all_signatures_verify(self, tmp_path) -> None:
        store = _filled_store(tmp_path)
        report = store.verify_integrity(b"secret")
        assert report["valid"] == 6
        assert report["invalid"] == 0

    def test_wrong_key_fails(self, tmp_path) -> None:
        store = _filled_store(tmp_path)
        report = store.verify_integrity(b"wrong-key")
        assert report["invalid"] == 6

    def test_tampered_event_detected(self, tmp_path) -> None:
        store = _filled_store(tmp_path)
        # Tamper: rewrite an event's action in the DB (append-only integrity).
        store._db.execute(
            "UPDATE audit_events SET action='tool.delete' WHERE actor='agent-1' "
            "AND framework='langgraph'"
        )
        report = store.verify_integrity(b"secret")
        assert report["invalid"] == 1
        assert report["first_invalid_id"] is not None

    def test_cross_framework_signature_replay_detected(self, tmp_path) -> None:
        """A langgraph signature copied onto a crewai row fails verification."""
        store = PersistentAuditStore(tmp_path / "audit.db")
        bus = DistributedAuditBus(secret_key=b"secret", store=store)

        lang = LangGraphAdapter().build_event(
            "agent_action", "agent-1", "tool.call", {"tool": "read_file"}
        )
        lang.timestamp = 1700000000.0
        bus.publish(lang)

        # Replay the langgraph signature onto a crewai event (stored raw, so
        # the replayed signature is what gets persisted and verified).
        crew = CrewAIAdapter().build_event(
            "agent_action", "agent-1", "tool.call", {"tool": "read_file"}
        )
        crew.timestamp = 1700000000.0
        crew.signature = lang.signature
        crew.signature_scheme = "v2"
        store.append(crew)

        report = store.verify_integrity(b"secret")
        assert report["valid"] == 1  # langgraph ok
        assert report["invalid"] == 1  # crewai replayed signature rejected
