from __future__ import annotations

from maref.recursive.agent_discovery_negotiation import AgentDiscovery
from maref.recursive.agent_economy import AgentEconomy
from maref.recursive.agent_marketplace import (
    AgentMarketplace,
    CapabilityListing,
    ListingStatus,
    TrustLevel,
)


class TestCapabilityListing:
    def test_create_listing(self) -> None:
        listing = CapabilityListing(
            agent_id="agent_a",
            capability="observe",
            price=10.0,
            trust_requirement=TrustLevel.MEDIUM,
        )
        assert listing.agent_id == "agent_a"
        assert listing.capability == "observe"
        assert listing.price == 10.0
        assert listing.status == ListingStatus.ACTIVE
        assert len(listing.listing_id) > 0

    def test_listing_to_dict(self) -> None:
        listing = CapabilityListing(
            agent_id="agent_a",
            capability="graph_query",
            price=5.0,
            sla={"latency_ms": 100},
        )
        d = listing.to_dict()
        assert d["capability"] == "graph_query"
        assert d["price"] == 5.0
        assert "latency_ms" in d["sla"]


class TestAgentMarketplaceInit:
    def test_default_init(self) -> None:
        marketplace = AgentMarketplace()
        assert marketplace.get_all_listings() == []

    def test_init_with_economy(self) -> None:
        economy = AgentEconomy()
        marketplace = AgentMarketplace(economy=economy)
        assert marketplace.economy is economy


class TestAgentMarketplacePublish:
    def test_publish_listing(self) -> None:
        marketplace = AgentMarketplace()
        listing = CapabilityListing(agent_id="agent_a", capability="observe", price=10.0)
        lid = marketplace.publish(listing)
        assert len(lid) > 0
        retrieved = marketplace.get_listing(lid)
        assert retrieved is not None
        assert retrieved.capability == "observe"

    def test_publish_returns_listing_id(self) -> None:
        marketplace = AgentMarketplace()
        listing = CapabilityListing(agent_id="agent_a", capability="graph_query")
        lid = marketplace.publish(listing)
        assert lid == listing.listing_id

    def test_publish_multiple_listings(self) -> None:
        marketplace = AgentMarketplace()
        l1 = CapabilityListing(agent_id="agent_a", capability="observe", price=10.0)
        l2 = CapabilityListing(agent_id="agent_b", capability="graph_query", price=5.0)
        marketplace.publish(l1)
        marketplace.publish(l2)
        assert len(marketplace.get_all_listings()) == 2

    def test_publish_with_discovery_registers_peer(self) -> None:
        discovery = AgentDiscovery(None)  # type: ignore[arg-type]
        marketplace = AgentMarketplace(discovery=discovery)
        listing = CapabilityListing(agent_id="agent_a", capability="observe")
        marketplace.publish(listing)
        peers = discovery.find_peers_with_capability("observe")
        assert len(peers) == 1
        assert peers[0].agent_id == "agent_a"


class TestAgentMarketplaceDiscover:
    def test_discover_by_capability(self) -> None:
        marketplace = AgentMarketplace()
        marketplace.publish(CapabilityListing(agent_id="agent_a", capability="observe", price=10.0))
        marketplace.publish(CapabilityListing(agent_id="agent_b", capability="observe", price=5.0))
        marketplace.publish(
            CapabilityListing(agent_id="agent_c", capability="graph_query", price=8.0)
        )
        results = marketplace.discover("observe")
        assert len(results) == 2
        assert results[0].agent_id == "agent_b"
        assert results[1].agent_id == "agent_a"

    def test_discover_no_matches(self) -> None:
        marketplace = AgentMarketplace()
        results = marketplace.discover("nonexistent")
        assert results == []

    def test_discover_excludes_revoked(self) -> None:
        marketplace = AgentMarketplace()
        listing = CapabilityListing(agent_id="agent_a", capability="observe")
        marketplace.publish(listing)
        marketplace.revoke_listing(listing.listing_id)
        results = marketplace.discover("observe")
        assert results == []

    def test_discover_excludes_fulfilled(self) -> None:
        marketplace = AgentMarketplace()
        marketplace._economy.register_agent("agent_a", initial_balance=100.0)
        marketplace._economy.register_agent("agent_b", initial_balance=100.0)
        listing = CapabilityListing(agent_id="agent_a", capability="observe", price=10.0)
        marketplace.publish(listing)
        marketplace.negotiate("agent_b", listing.listing_id, buyer_trust=0.5)
        results = marketplace.discover("observe")
        assert results == []

    def test_discover_by_agent(self) -> None:
        marketplace = AgentMarketplace()
        marketplace.publish(CapabilityListing(agent_id="agent_a", capability="observe"))
        marketplace.publish(CapabilityListing(agent_id="agent_a", capability="monitor"))
        marketplace.publish(CapabilityListing(agent_id="agent_b", capability="collect"))
        results = marketplace.discover_by_agent("agent_a")
        assert len(results) == 2
        for r in results:
            assert r.agent_id == "agent_a"


class TestAgentMarketplaceNegotiate:
    def test_negotiate_success(self) -> None:
        marketplace = AgentMarketplace()
        marketplace._economy.register_agent("buyer", initial_balance=100.0)
        marketplace._economy.register_agent("seller", initial_balance=100.0)
        listing = CapabilityListing(agent_id="seller", capability="observe", price=10.0)
        marketplace.publish(listing)
        result = marketplace.negotiate("buyer", listing.listing_id, buyer_trust=0.5)
        assert result.accepted is True
        assert result.final_price == 10.0
        assert len(result.agreement_id) > 0

    def test_negotiate_listing_not_found(self) -> None:
        marketplace = AgentMarketplace()
        result = marketplace.negotiate("buyer", "nonexistent")
        assert result.accepted is False
        assert "not found" in result.refusal_reason.lower()

    def test_negotiate_insufficient_trust(self) -> None:
        marketplace = AgentMarketplace()
        listing = CapabilityListing(
            agent_id="seller",
            capability="observe",
            trust_requirement=TrustLevel.HIGH,
        )
        marketplace.publish(listing)
        result = marketplace.negotiate("buyer", listing.listing_id, buyer_trust=0.2)
        assert result.accepted is False
        assert "trust" in result.refusal_reason.lower()

    def test_negotiate_insufficient_funds(self) -> None:
        marketplace = AgentMarketplace()
        marketplace._economy.register_agent("buyer", initial_balance=5.0)
        marketplace._economy.register_agent("seller", initial_balance=100.0)
        listing = CapabilityListing(agent_id="seller", capability="observe", price=10.0)
        marketplace.publish(listing)
        result = marketplace.negotiate("buyer", listing.listing_id, buyer_trust=0.5)
        assert result.accepted is False
        assert "funds" in result.refusal_reason.lower()

    def test_negotiate_max_price_below_listing(self) -> None:
        marketplace = AgentMarketplace()
        marketplace._economy.register_agent("buyer", initial_balance=100.0)
        listing = CapabilityListing(agent_id="seller", capability="observe", price=10.0)
        marketplace.publish(listing)
        result = marketplace.negotiate("buyer", listing.listing_id, max_price=3.0, buyer_trust=0.5)
        assert result.accepted is False
        assert "price" in result.refusal_reason.lower()

    def test_negotiate_auto_registers_agents(self) -> None:
        marketplace = AgentMarketplace()
        listing = CapabilityListing(agent_id="new_seller", capability="observe", price=5.0)
        marketplace.publish(listing)
        result = marketplace.negotiate("new_buyer", listing.listing_id, buyer_trust=0.5)
        assert result.accepted is True

    def test_negotiate_marks_listing_as_fulfilled(self) -> None:
        marketplace = AgentMarketplace()
        marketplace._economy.register_agent("buyer", initial_balance=100.0)
        marketplace._economy.register_agent("seller", initial_balance=100.0)
        listing = CapabilityListing(agent_id="seller", capability="observe")
        marketplace.publish(listing)
        marketplace.negotiate("buyer", listing.listing_id, buyer_trust=0.5)
        retrieved = marketplace.get_listing(listing.listing_id)
        assert retrieved is not None
        assert retrieved.status == ListingStatus.FULFILLED

    def test_cannot_negotiate_already_fulfilled(self) -> None:
        marketplace = AgentMarketplace()
        marketplace._economy.register_agent("buyer", initial_balance=100.0)
        marketplace._economy.register_agent("seller", initial_balance=100.0)
        listing = CapabilityListing(agent_id="seller", capability="observe")
        marketplace.publish(listing)
        marketplace.negotiate("buyer", listing.listing_id, buyer_trust=0.5)
        result = marketplace.negotiate("buyer", listing.listing_id, buyer_trust=0.5)
        assert result.accepted is False


class TestAgentMarketplaceRevoke:
    def test_revoke_active_listing(self) -> None:
        marketplace = AgentMarketplace()
        listing = CapabilityListing(agent_id="agent_a", capability="observe")
        marketplace.publish(listing)
        assert marketplace.revoke_listing(listing.listing_id) is True
        assert listing.status == ListingStatus.REVOKED

    def test_revoke_unknown_listing(self) -> None:
        marketplace = AgentMarketplace()
        assert marketplace.revoke_listing("nonexistent") is False

    def test_revoke_fulfilled_listing(self) -> None:
        marketplace = AgentMarketplace()
        marketplace._economy.register_agent("buyer", initial_balance=100.0)
        marketplace._economy.register_agent("seller", initial_balance=100.0)
        listing = CapabilityListing(agent_id="seller", capability="observe")
        marketplace.publish(listing)
        marketplace.negotiate("buyer", listing.listing_id, buyer_trust=0.5)
        assert marketplace.revoke_listing(listing.listing_id) is False


class TestAgentMarketplaceStats:
    def test_stats_empty(self) -> None:
        marketplace = AgentMarketplace()
        st = marketplace.stats()
        assert st["total_listings"] == 0
        assert st["active_listings"] == 0

    def test_stats_with_listings(self) -> None:
        marketplace = AgentMarketplace()
        marketplace.publish(CapabilityListing(agent_id="agent_a", capability="observe"))
        marketplace.publish(CapabilityListing(agent_id="agent_b", capability="graph_query"))
        st = marketplace.stats()
        assert st["total_listings"] == 2
        assert st["active_listings"] == 2

    def test_clear_resets(self) -> None:
        marketplace = AgentMarketplace()
        marketplace.publish(CapabilityListing(agent_id="agent_a", capability="observe"))
        marketplace.clear()
        assert marketplace.get_all_listings() == []
        assert marketplace.get_fulfilled() == []


class TestTrustLevel:
    def test_all_levels(self) -> None:
        levels = list(TrustLevel)
        assert TrustLevel.LOW in levels
        assert TrustLevel.MEDIUM in levels
        assert TrustLevel.HIGH in levels
        assert TrustLevel.CRITICAL in levels
