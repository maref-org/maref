"""v0.47 F4 — AgentDNS SQLite persistence + restart recovery."""

from __future__ import annotations

from pathlib import Path

from maref.identity.agent_dns import AgentDNS
from maref.identity.did_registry import AgentDID, DIDRegistry
from maref.governance.state_machine import GovernanceStateMachine


def _dns(db_path: Path | None = None, did_registry: DIDRegistry | None = None) -> AgentDNS:
    reg = did_registry or DIDRegistry()
    dns = AgentDNS(did_registry=reg, db_path=db_path)
    return dns


def _register_card(dns: AgentDNS) -> AgentDID:
    did = AgentDID(namespace="default", agent_short_id="abc12345")
    dns._did_registry.register(did, GovernanceStateMachine())
    dns.register(
        did,
        name="helper",
        description="test agent",
        skills=[{"id": "code", "name": "Coding"}],
        endpoints=["https://helper.example.com/api"],
    )
    return did


class TestAgentDNSPersistence:
    def test_register_then_reload_recovers(self, tmp_path: Path) -> None:
        db = tmp_path / "dns.db"
        dns = _dns(db_path=db)
        did = _register_card(dns)

        reloaded = _dns(db_path=db)
        card = reloaded.resolve(did)
        assert card is not None
        assert card.name == "helper"
        assert card.skills == [{"id": "code", "name": "Coding"}]

    def test_no_db_path_in_memory(self) -> None:
        dns = _dns()
        did = _register_card(dns)
        assert dns.resolve(did) is not None

    def test_unregister_removes_from_disk(self, tmp_path: Path) -> None:
        db = tmp_path / "dns.db"
        dns = _dns(db_path=db)
        did = _register_card(dns)
        dns.unregister(did)

        reloaded = _dns(db_path=db)
        assert reloaded.resolve(did) is None
