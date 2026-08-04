"""v0.47 F4 — DIDRegistry SQLite persistence + restart recovery."""

from __future__ import annotations

from pathlib import Path

from maref.identity.did_registry import AgentDID, DIDRegistry
from maref.governance.state_machine import GovernanceStateMachine


def _registry(db_path: Path | None = None) -> DIDRegistry:
    return DIDRegistry(db_path=db_path)


class TestDIDRegistryPersistence:
    def test_register_then_reload_recovers(self, tmp_path: Path) -> None:
        db = tmp_path / "did.db"
        reg = _registry(db)
        did = AgentDID(namespace="default", agent_short_id="abc12345")
        reg.register(did, GovernanceStateMachine())
        reg.revoke(did, reason="test")

        reloaded = _registry(db)
        record = reloaded.resolve(did)
        assert record is not None
        assert record.status == "revoked"
        assert record.revocation_entry["reason"] == "test"

    def test_state_machine_restored(self, tmp_path: Path) -> None:
        db = tmp_path / "did.db"
        reg = _registry(db)
        did = AgentDID(namespace="default", agent_short_id="abc12345")
        sm = GovernanceStateMachine()
        sm.transition(sm.current_state, "init-test")
        reg.register(did, sm)

        reloaded = _registry(db)
        record = reloaded.resolve(did)
        assert record is not None
        assert record.state_machine.current_state == sm.current_state

    def test_no_db_path_in_memory(self) -> None:
        reg = _registry()
        did = AgentDID(namespace="default", agent_short_id="abc12345")
        reg.register(did, GovernanceStateMachine())
        assert reg.agent_count() == 1

    def test_persist_writes_through_after_mutation(self, tmp_path: Path) -> None:
        db = tmp_path / "did.db"
        reg = _registry(db)
        did = AgentDID(namespace="default", agent_short_id="abc12345")
        reg.register(did, GovernanceStateMachine())
        reg.deactivate(did, reason="gone")

        reloaded = _registry(db)
        assert reloaded.resolve(did).status == "deactivated"
