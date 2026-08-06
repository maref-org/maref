"""Unit tests for AgentMarketplace."""

from __future__ import annotations

import time

from maref.federation.marketplace import (
    AgentMarketplace,
    Pricing,
    PricingModel,
)


def _make_pricing(model: PricingModel = PricingModel.PER_TASK, price: float = 1.0) -> Pricing:
    return Pricing(model=model, price=price)


class TestPricing:
    def test_is_free_for_free_model(self) -> None:
        p = Pricing(model=PricingModel.FREE)
        assert p.is_free is True

    def test_is_free_for_zero_price(self) -> None:
        p = Pricing(model=PricingModel.PER_TASK, price=0.0)
        assert p.is_free is True

    def test_is_free_false_for_priced(self) -> None:
        p = Pricing(model=PricingModel.PER_TASK, price=5.0)
        assert p.is_free is False

    def test_to_dict(self) -> None:
        p = Pricing(model=PricingModel.PER_TOKEN, price=0.001, currency="USD", free_quota=100)
        d = p.to_dict()
        assert d["model"] == "per_token"
        assert d["price"] == 0.001
        assert d["currency"] == "USD"
        assert d["free_quota"] == 100


class TestMarketplacePublish:
    def test_publish_creates_listing(self) -> None:
        market = AgentMarketplace()
        listing = market.publish(
            agent_aic="aic:1",
            agent_did="did:1",
            provider_org="OrgA",
            name="Research Agent",
            description="A research agent",
            capabilities=["research", "analysis"],
            pricing=_make_pricing(PricingModel.PER_TASK, 2.0),
        )
        assert listing.listing_id.startswith("list_")
        assert listing.name == "Research Agent"
        assert listing.version == 1
        assert listing.active is True
        assert market.get_listing(listing.listing_id) is not None

    def test_publish_updates_existing_by_aic(self) -> None:
        market = AgentMarketplace()
        market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="V1", description="v1", capabilities=["research"],
        )
        time.sleep(0.01)
        listing = market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="V2", description="v2", capabilities=["research", "analysis"],
            pricing=_make_pricing(PricingModel.PER_TASK, 5.0),
        )
        assert listing.version == 2
        assert listing.name == "V2"
        assert len(listing.capabilities) == 2
        # Only one listing (no duplicate).
        assert len(market.list_listings()) == 1

    def test_publish_updates_provider_org_and_index(self) -> None:
        """Re-publishing with a different provider_org must update both the
        listing field and the org index (regression test for silent
        inconsistency where _org_index[new_org] got the listing but
        listing.provider_org stayed as old_org)."""
        market = AgentMarketplace()
        market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="V1", description="v1", capabilities=["research"],
        )
        # Re-publish with a new provider_org.
        listing = market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgB",
            name="V2", description="v2", capabilities=["research"],
        )
        assert listing.provider_org == "OrgB"
        # Old org must no longer return this listing.
        assert market.list_listings(provider_org="OrgA") == []
        # New org must return it.
        org_b_listings = market.list_listings(provider_org="OrgB")
        assert len(org_b_listings) == 1
        assert org_b_listings[0].provider_org == "OrgB"
        # Org aggregation must reflect the change.
        assert "OrgA" not in market.list_organizations()
        assert "OrgB" in market.list_organizations()

    def test_publish_with_tags(self) -> None:
        market = AgentMarketplace()
        listing = market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="N", description="D", tags=["beta", "internal"],
        )
        assert listing.tags == ["beta", "internal"]

    def test_publish_default_pricing_is_free(self) -> None:
        market = AgentMarketplace()
        listing = market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="N", description="D",
        )
        assert listing.pricing.model == PricingModel.FREE
        assert listing.pricing.is_free is True


class TestMarketplaceUnpublish:
    def test_unpublish_soft_delete(self) -> None:
        market = AgentMarketplace()
        listing = market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="N", description="D",
        )
        assert market.unpublish(listing.listing_id) is True
        assert listing.active is False

    def test_unpublish_already_inactive_returns_false(self) -> None:
        market = AgentMarketplace()
        listing = market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="N", description="D",
        )
        market.unpublish(listing.listing_id)
        assert market.unpublish(listing.listing_id) is False

    def test_unpublish_nonexistent(self) -> None:
        market = AgentMarketplace()
        assert market.unpublish("nonexistent") is False


class TestMarketplaceLookup:
    def test_get_listing_by_aic(self) -> None:
        market = AgentMarketplace()
        market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="N", description="D",
        )
        listing = market.get_listing_by_aic("aic:1")
        assert listing is not None
        assert listing.name == "N"

    def test_get_listing_by_aic_missing(self) -> None:
        market = AgentMarketplace()
        assert market.get_listing_by_aic("nonexistent") is None

    def test_update_pricing(self) -> None:
        market = AgentMarketplace()
        listing = market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="N", description="D",
        )
        new_pricing = _make_pricing(PricingModel.PER_TOKEN, 0.01)
        assert market.update_pricing(listing.listing_id, new_pricing) is True
        updated = market.get_listing(listing.listing_id)
        assert updated.pricing.price == 0.01

    def test_update_pricing_nonexistent(self) -> None:
        market = AgentMarketplace()
        assert market.update_pricing("nonexistent", _make_pricing()) is False


class TestMarketplaceSearch:
    def test_search_by_capability(self) -> None:
        market = AgentMarketplace()
        market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="A", description="d", capabilities=["research"],
        )
        market.publish(
            agent_aic="aic:2", agent_did="did:2", provider_org="OrgA",
            name="B", description="d", capabilities=["translation"],
        )
        results = market.search(capability="research")
        assert len(results) == 1
        assert results[0].name == "A"

    def test_search_by_max_price(self) -> None:
        market = AgentMarketplace()
        market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="Cheap", description="d", capabilities=["research"],
            pricing=_make_pricing(PricingModel.PER_TASK, 1.0),
        )
        market.publish(
            agent_aic="aic:2", agent_did="did:2", provider_org="OrgA",
            name="Expensive", description="d", capabilities=["research"],
            pricing=_make_pricing(PricingModel.PER_TASK, 10.0),
        )
        results = market.search(capability="research", max_price=5.0)
        assert len(results) == 1
        assert results[0].name == "Cheap"

    def test_search_by_provider_org(self) -> None:
        market = AgentMarketplace()
        market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="A", description="d", capabilities=["research"],
        )
        market.publish(
            agent_aic="aic:2", agent_did="did:2", provider_org="OrgB",
            name="B", description="d", capabilities=["research"],
        )
        results = market.search(capability="research", provider_org="OrgA")
        assert len(results) == 1
        assert results[0].provider_org == "OrgA"

    def test_search_by_tags(self) -> None:
        market = AgentMarketplace()
        market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="A", description="d", capabilities=["research"],
            tags=["beta", "internal"],
        )
        market.publish(
            agent_aic="aic:2", agent_did="did:2", provider_org="OrgA",
            name="B", description="d", capabilities=["research"],
            tags=["stable"],
        )
        results = market.search(tags=["beta"])
        assert len(results) == 1
        assert results[0].name == "A"

    def test_search_excludes_inactive(self) -> None:
        market = AgentMarketplace()
        listing = market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="A", description="d", capabilities=["research"],
        )
        market.unpublish(listing.listing_id)
        results = market.search(capability="research")
        assert len(results) == 0

    def test_search_includes_inactive_when_flag_off(self) -> None:
        market = AgentMarketplace()
        listing = market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="A", description="d", capabilities=["research"],
        )
        market.unpublish(listing.listing_id)
        results = market.search(capability="research", active_only=False)
        assert len(results) == 1

    def test_search_sort_by_price_low(self) -> None:
        market = AgentMarketplace()
        market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="Expensive", description="d", capabilities=["research"],
            pricing=_make_pricing(PricingModel.PER_TASK, 10.0),
        )
        market.publish(
            agent_aic="aic:2", agent_did="did:2", provider_org="OrgA",
            name="Cheap", description="d", capabilities=["research"],
            pricing=_make_pricing(PricingModel.PER_TASK, 1.0),
        )
        results = market.search(capability="research", sort_by="price_low")
        assert results[0].name == "Cheap"
        assert results[1].name == "Expensive"

    def test_search_sort_by_newest(self) -> None:
        market = AgentMarketplace()
        market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="Old", description="d", capabilities=["research"],
        )
        time.sleep(0.02)
        market.publish(
            agent_aic="aic:2", agent_did="did:2", provider_org="OrgA",
            name="New", description="d", capabilities=["research"],
        )
        results = market.search(capability="research", sort_by="newest")
        assert results[0].name == "New"

    def test_search_limit(self) -> None:
        market = AgentMarketplace()
        for i in range(5):
            market.publish(
                agent_aic=f"aic:{i}", agent_did=f"did:{i}", provider_org="OrgA",
                name=f"Agent{i}", description="d", capabilities=["research"],
            )
        results = market.search(capability="research", limit=2)
        assert len(results) == 2


class TestMarketplaceReviews:
    def test_add_review(self) -> None:
        market = AgentMarketplace()
        listing = market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="N", description="D",
        )
        review = market.add_review(listing.listing_id, "OrgB", 5, "Great agent!")
        assert review is not None
        assert review.rating == 5
        assert review.comment == "Great agent!"

    def test_add_review_clamps_rating(self) -> None:
        market = AgentMarketplace()
        listing = market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="N", description="D",
        )
        high = market.add_review(listing.listing_id, "OrgB", 10)
        low = market.add_review(listing.listing_id, "OrgC", -1)
        assert high.rating == 5
        assert low.rating == 1

    def test_add_review_nonexistent_listing(self) -> None:
        market = AgentMarketplace()
        assert market.add_review("nonexistent", "OrgB", 5) is None

    def test_get_reviews_newest_first(self) -> None:
        market = AgentMarketplace()
        listing = market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="N", description="D",
        )
        market.add_review(listing.listing_id, "OrgB", 5, "first")
        time.sleep(0.02)
        market.add_review(listing.listing_id, "OrgC", 3, "second")
        reviews = market.get_reviews(listing.listing_id)
        assert len(reviews) == 2
        assert reviews[0].comment == "second"  # newest first

    def test_get_average_rating(self) -> None:
        market = AgentMarketplace()
        listing = market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="N", description="D",
        )
        market.add_review(listing.listing_id, "OrgB", 4)
        market.add_review(listing.listing_id, "OrgC", 5)
        market.add_review(listing.listing_id, "OrgD", 3)
        avg = market.get_average_rating(listing.listing_id)
        assert abs(avg - 4.0) < 0.01

    def test_get_average_rating_no_reviews(self) -> None:
        market = AgentMarketplace()
        listing = market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="N", description="D",
        )
        assert market.get_average_rating(listing.listing_id) == 0.0

    def test_get_review_count(self) -> None:
        market = AgentMarketplace()
        listing = market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="N", description="D",
        )
        market.add_review(listing.listing_id, "OrgB", 5)
        market.add_review(listing.listing_id, "OrgC", 3)
        assert market.get_review_count(listing.listing_id) == 2

    def test_search_sort_by_rating(self) -> None:
        market = AgentMarketplace()
        low = market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="LowRated", description="d", capabilities=["research"],
        )
        high = market.publish(
            agent_aic="aic:2", agent_did="did:2", provider_org="OrgA",
            name="HighRated", description="d", capabilities=["research"],
        )
        market.add_review(low.listing_id, "OrgB", 2)
        market.add_review(high.listing_id, "OrgC", 5)
        results = market.search(capability="research", sort_by="rating")
        assert results[0].name == "HighRated"
        assert results[1].name == "LowRated"


class TestMarketplaceAggregations:
    def test_list_capabilities(self) -> None:
        market = AgentMarketplace()
        market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="A", description="d", capabilities=["research", "analysis"],
        )
        market.publish(
            agent_aic="aic:2", agent_did="did:2", provider_org="OrgA",
            name="B", description="d", capabilities=["translation"],
        )
        caps = market.list_capabilities()
        assert caps == ["analysis", "research", "translation"]

    def test_list_capabilities_excludes_inactive(self) -> None:
        market = AgentMarketplace()
        listing = market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="A", description="d", capabilities=["research"],
        )
        market.unpublish(listing.listing_id)
        assert "research" not in market.list_capabilities()

    def test_list_organizations(self) -> None:
        market = AgentMarketplace()
        market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgB",
            name="A", description="d", capabilities=["research"],
        )
        market.publish(
            agent_aic="aic:2", agent_did="did:2", provider_org="OrgA",
            name="B", description="d", capabilities=["research"],
        )
        orgs = market.list_organizations()
        assert orgs == ["OrgA", "OrgB"]


class TestMarketplaceSummary:
    def test_marketplace_summary(self) -> None:
        market = AgentMarketplace()
        market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="Free", description="d", capabilities=["research"],
        )
        market.publish(
            agent_aic="aic:2", agent_did="did:2", provider_org="OrgA",
            name="Paid", description="d", capabilities=["analysis"],
            pricing=_make_pricing(PricingModel.PER_TASK, 5.0),
        )
        summary = market.marketplace_summary()
        assert summary["total_listings"] == 2
        assert summary["active_listings"] == 2
        assert summary["free_listings"] == 1
        assert summary["priced_listings"] == 1
        assert summary["average_price"] == 5.0
        assert summary["total_capabilities"] == 2
        assert summary["total_organizations"] == 1

    def test_list_listings_by_org(self) -> None:
        market = AgentMarketplace()
        market.publish(
            agent_aic="aic:1", agent_did="did:1", provider_org="OrgA",
            name="A", description="d",
        )
        market.publish(
            agent_aic="aic:2", agent_did="did:2", provider_org="OrgB",
            name="B", description="d",
        )
        assert len(market.list_listings(provider_org="OrgA")) == 1
        assert len(market.list_listings(provider_org="OrgB")) == 1
        assert len(market.list_listings()) == 2
