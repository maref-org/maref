"""Unit tests for FederatedDiscovery (ADP discovery client)."""

from __future__ import annotations

from maref.federation.discovery import (
    ADP_PROTOCOL_VERSION,
    DEFAULT_MAX_DEPTH,
    DEFAULT_QUERY_TIMEOUT,
    DiscoveryQuery,
    FederatedDiscovery,
    FederationPeer,
)
from maref.federation.gateway import FederatedAgent, FederationGateway
from maref.identity.aic_adapter import AIC
from maref.identity.did_registry import AgentDID
from maref.integration.acs_parser import AgentCapabilitySpec, AgentSkill


def _make_standalone_agent(
    skills: list[str] | None = None,
    organization: str = "RemoteOrg",
    protocol: str = "aip",
) -> FederatedAgent:
    """Build a FederatedAgent without registering it on any gateway.

    Used to simulate agents returned by a remote peer's catalog.
    """
    aic = AIC.generate()
    did = AgentDID.generate()
    acs = AgentCapabilitySpec(
        aic=aic.aic_string,
        name="standalone-agent",
        description="standalone",
        skills=[
            AgentSkill(id=s, name=s.title(), description=f"{s} capability") for s in (skills or [])
        ],
    )
    return FederatedAgent(
        did=did,
        aic=aic,
        acs=acs,
        endpoint_url="https://standalone.example.com/api",
        protocol=protocol,
        registered_at=0.0,
    )


class TestDiscoveryQuery:
    def test_auto_generates_query_id(self) -> None:
        q = DiscoveryQuery()
        assert q.query_id.startswith("adp-")
        assert len(q.query_id) == len("adp-") + 12

    def test_explicit_query_id_preserved(self) -> None:
        q = DiscoveryQuery(query_id="custom-001")
        assert q.query_id == "custom-001"

    def test_to_dict_serializes_visited(self) -> None:
        q = DiscoveryQuery(visited={"srv-1", "srv-2"})
        d = q.to_dict()
        assert isinstance(d["visited"], list)
        assert set(d["visited"]) == {"srv-1", "srv-2"}


class TestFederationPeer:
    def test_to_dict_roundtrip(self) -> None:
        peer = FederationPeer(server_id="s1", endpoint_url="https://x/", trust_score=80.0)
        d = peer.to_dict()
        assert d["server_id"] == "s1"
        assert d["endpoint_url"] == "https://x/"
        assert d["trust_score"] == 80.0


class TestFederatedDiscoveryPeers:
    def test_add_peer_normalizes_trailing_slash(self, fed_gateway: FederationGateway) -> None:
        disc = FederatedDiscovery(gateway=fed_gateway)
        peer = disc.add_peer("srv-2", "https://fed2.example.com/adp/")
        assert peer.endpoint_url == "https://fed2.example.com/adp"
        assert peer.trust_score == 50.0

    def test_add_peer_clamps_trust_score(self, fed_gateway: FederationGateway) -> None:
        disc = FederatedDiscovery(gateway=fed_gateway)
        high = disc.add_peer("h", "https://h", trust_score=200.0)
        low = disc.add_peer("l", "https://l", trust_score=-10.0)
        assert high.trust_score == 100.0
        assert low.trust_score == 0.0

    def test_remove_peer(self, fed_gateway: FederationGateway) -> None:
        disc = FederatedDiscovery(gateway=fed_gateway)
        disc.add_peer("srv-1", "https://srv1")
        assert disc.peer_count == 1
        assert disc.remove_peer("srv-1") is True
        assert disc.peer_count == 0
        assert disc.remove_peer("srv-1") is False

    def test_list_peers(self, fed_gateway: FederationGateway) -> None:
        disc = FederatedDiscovery(gateway=fed_gateway)
        disc.add_peer("a", "https://a")
        disc.add_peer("b", "https://b")
        ids = {p.server_id for p in disc.list_peers()}
        assert ids == {"a", "b"}


class TestFederatedDiscoveryLocal:
    def test_discover_local_by_capability(
        self, fed_gateway: FederationGateway, make_federated_agent
    ) -> None:
        agent = make_federated_agent(skills=["research", "analysis"])
        # An unrelated agent that does not match.
        make_federated_agent(skills=["translation"])

        disc = FederatedDiscovery(gateway=fed_gateway)
        results = disc.discover(capability="research", include_remote=False)
        assert len(results) == 1
        assert results[0].agent.aic.aic_string == agent.aic.aic_string
        assert results[0].hop_count == 0
        assert results[0].source_server == disc.server_id

    def test_discover_local_by_protocol(
        self, fed_gateway: FederationGateway, make_federated_agent
    ) -> None:
        make_federated_agent(skills=["research"], protocol="aip")
        make_federated_agent(skills=["research"], protocol="a2a")

        disc = FederatedDiscovery(gateway=fed_gateway)
        aip_results = disc.discover(protocol="aip", include_remote=False)
        assert len(aip_results) == 1
        assert aip_results[0].agent.protocol == "aip"

        a2a_results = disc.discover(protocol="a2a", include_remote=False)
        assert len(a2a_results) == 1
        assert a2a_results[0].agent.protocol == "a2a"

    def test_discover_local_by_aic_prefix(
        self, fed_gateway: FederationGateway, make_federated_agent
    ) -> None:
        agent = make_federated_agent(skills=["research"])
        # The AIC OID root is "1.2.156.3088"; use the first OID segment as a
        # prefix filter (the agent's AIC starts with it).
        prefix = agent.aic.aic_string.split(".")[0]
        disc = FederatedDiscovery(gateway=fed_gateway)
        results = disc.discover(aic_prefix=prefix, include_remote=False)
        assert any(r.agent.aic.aic_string == agent.aic.aic_string for r in results)

    def test_discover_local_no_filters_returns_all(
        self, fed_gateway: FederationGateway, make_federated_agent
    ) -> None:
        make_federated_agent(skills=["research"])
        make_federated_agent(skills=["analysis"])
        disc = FederatedDiscovery(gateway=fed_gateway)
        results = disc.discover(include_remote=False)
        assert len(results) == 2
        assert all(r.hop_count == 0 for r in results)

    def test_discover_respects_max_results(
        self, fed_gateway: FederationGateway, make_federated_agent
    ) -> None:
        for _ in range(5):
            make_federated_agent(skills=["research"])
        disc = FederatedDiscovery(gateway=fed_gateway)
        results = disc.discover(capability="research", max_results=2, include_remote=False)
        assert len(results) == 2


class TestFederatedDiscoveryRemote:
    def test_discover_forwards_to_healthy_peer(
        self, fed_gateway: FederationGateway, make_federated_agent
    ) -> None:
        local_agent = make_federated_agent(skills=["research"])
        remote_agent = _make_standalone_agent(skills=["research"])

        disc = FederatedDiscovery(gateway=fed_gateway)
        disc.add_peer("remote-srv", "https://remote-srv/adp")
        disc.set_catalog_provider("remote-srv", lambda: [remote_agent])

        results = disc.discover(capability="research", include_remote=True)
        aics = {r.agent.aic.aic_string for r in results}
        assert local_agent.aic.aic_string in aics
        assert remote_agent.aic.aic_string in aics
        # Local result has hop 0, remote has hop 1.
        hops = {r.agent.aic.aic_string: r.hop_count for r in results}
        assert hops[local_agent.aic.aic_string] == 0
        assert hops[remote_agent.aic.aic_string] == 1

    def test_discover_deduplicates_by_aic(
        self, fed_gateway: FederationGateway, make_federated_agent
    ) -> None:
        local_agent = make_federated_agent(skills=["research"])
        disc = FederatedDiscovery(gateway=fed_gateway)
        disc.add_peer("peer", "https://peer/adp")
        # Peer catalog returns the SAME agent (same AIC) — should dedupe.
        disc.set_catalog_provider("peer", lambda: [local_agent])

        results = disc.discover(capability="research", include_remote=True)
        matching = [r for r in results if r.agent.aic.aic_string == local_agent.aic.aic_string]
        assert len(matching) == 1
        # Local (hop 0) wins over remote (hop 1).
        assert matching[0].hop_count == 0

    def test_discover_skips_unhealthy_peer(
        self, fed_gateway: FederationGateway, make_federated_agent
    ) -> None:
        make_federated_agent(skills=["research"])
        disc = FederatedDiscovery(gateway=fed_gateway)
        peer = disc.add_peer("dead-peer", "https://dead/adp")
        peer.healthy = False
        # Provider would return an agent if called, but peer is unhealthy.
        remote_agent = _make_standalone_agent(skills=["research"])
        disc.set_catalog_provider("dead-peer", lambda: [remote_agent])

        results = disc.discover(capability="research", include_remote=True)
        # Only the local agent; unhealthy peer contributes nothing.
        assert len(results) == 1
        assert results[0].hop_count == 0

    def test_discover_remote_only_when_local_below_max(
        self, fed_gateway: FederationGateway, make_federated_agent
    ) -> None:
        # Register 2 local agents with the target capability.
        local1 = make_federated_agent(skills=["research"])
        make_federated_agent(skills=["research"])
        remote_agent = _make_standalone_agent(skills=["research"])

        disc = FederatedDiscovery(gateway=fed_gateway)
        disc.add_peer("peer", "https://peer/adp")
        disc.set_catalog_provider("peer", lambda: [remote_agent])

        # max_results=2 with 2 local matches: remote forwarding should be
        # skipped because len(local_results) >= max_results.
        results = disc.discover(capability="research", max_results=2, include_remote=True)
        aics = {r.agent.aic.aic_string for r in results}
        assert remote_agent.aic.aic_string not in aics
        assert local1.aic.aic_string in aics

    def test_discover_remote_filtered_by_capability(
        self, fed_gateway: FederationGateway, make_federated_agent
    ) -> None:
        make_federated_agent(skills=["research"])
        # Remote agent with a DIFFERENT capability should be filtered out.
        remote_agent = _make_standalone_agent(skills=["translation"])

        disc = FederatedDiscovery(gateway=fed_gateway)
        disc.add_peer("peer", "https://peer/adp")
        disc.set_catalog_provider("peer", lambda: [remote_agent])

        results = disc.discover(capability="research", include_remote=True)
        aics = {r.agent.aic.aic_string for r in results}
        assert remote_agent.aic.aic_string not in aics


class TestFederatedDiscoverySummary:
    def test_discovery_summary(
        self, fed_gateway: FederationGateway, make_federated_agent
    ) -> None:
        make_federated_agent(skills=["research"])
        disc = FederatedDiscovery(gateway=fed_gateway)
        disc.add_peer("p1", "https://p1")
        disc.add_peer("p2", "https://p2")
        summary = disc.discovery_summary()
        assert summary["server_id"] == disc.server_id
        assert summary["local_agent_count"] == 1
        assert summary["peer_count"] == 2
        assert summary["healthy_peers"] == 2
        assert summary["max_depth"] == DEFAULT_MAX_DEPTH

    def test_constants(self) -> None:
        assert ADP_PROTOCOL_VERSION == "2.00"
        assert DEFAULT_QUERY_TIMEOUT == 5.0
        assert DEFAULT_MAX_DEPTH == 3
