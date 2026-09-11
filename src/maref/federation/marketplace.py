"""MAREF Agent Marketplace

A federation-level marketplace where agent providers publish capability
offerings with pricing, and consumers can search, compare, and review
agents.

Builds on :mod:`maref.federation.catalog` for the directory foundation
and :mod:`maref.federation.trust` for trust-aware search ranking.

References:
    - Plan §7 Phase 3: AgentMarketplace ``marketplace.py``
    - Plan §6.1: 收入模型 (发现服务费 + 结算抽成)
    - Depends on: :mod:`maref.federation.catalog`, :mod:`maref.federation.trust`
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PricingModel(str, Enum):
    """How an agent offering is priced."""

    FREE = "free"
    PER_TASK = "per_task"
    PER_TOKEN = "per_token"
    PER_HOUR = "per_hour"
    SUBSCRIPTION = "subscription"


@dataclass(frozen=True)
class Pricing:
    """Pricing configuration for a marketplace listing.

    ``price`` is in abstract settlement units (consistent with
    :mod:`maref.federation.settlement`).  ``free_quota`` is the number
    of free invocations per billing period (0 = no free tier).
    """

    model: PricingModel
    price: float = 0.0
    currency: str = "MAREF"
    free_quota: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model.value,
            "price": round(self.price, 4),
            "currency": self.currency,
            "free_quota": self.free_quota,
            "metadata": dict(self.metadata),
        }

    @property
    def is_free(self) -> bool:
        return self.model == PricingModel.FREE or self.price == 0.0


@dataclass
class MarketplaceListing:
    """A published agent offering in the marketplace."""

    listing_id: str
    agent_aic: str
    agent_did: str
    provider_org: str
    name: str
    description: str
    capabilities: list[str] = field(default_factory=list)
    pricing: Pricing = field(default_factory=lambda: Pricing(model=PricingModel.FREE))
    terms: str = ""
    published_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    active: bool = True
    version: int = 1
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "listing_id": self.listing_id,
            "agent_aic": self.agent_aic,
            "agent_did": self.agent_did,
            "provider_org": self.provider_org,
            "name": self.name,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "pricing": self.pricing.to_dict(),
            "terms": self.terms,
            "published_at": self.published_at,
            "updated_at": self.updated_at,
            "active": self.active,
            "version": self.version,
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class AgentReview:
    """A consumer's review of a marketplace listing."""

    review_id: str
    listing_id: str
    reviewer_org: str
    rating: int  # 1-5
    comment: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "listing_id": self.listing_id,
            "reviewer_org": self.reviewer_org,
            "rating": self.rating,
            "comment": self.comment,
            "timestamp": self.timestamp,
        }


def _validate_rating(rating: int) -> int:
    """Clamp rating to the valid 1-5 range."""
    return max(1, min(5, rating))


class AgentMarketplace:
    """Agent capability marketplace with pricing and reviews.

    The marketplace is a thin layer over the existing
    :class:`~maref.federation.catalog.FederatedCatalog` — it adds
    pricing, search-by-price, and review/rating aggregation.
    Listings are keyed by ``listing_id`` and indexed by AIC for
    deduplication.
    """

    def __init__(self) -> None:
        self._listings: dict[str, MarketplaceListing] = {}
        self._aic_to_listing: dict[str, str] = {}  # agent_aic -> listing_id
        self._reviews: dict[str, list[AgentReview]] = {}  # listing_id -> reviews
        self._capability_index: dict[str, set[str]] = {}  # capability -> {listing_id}
        self._org_index: dict[str, set[str]] = {}  # provider_org -> {listing_id}
        # Cached average rating per listing. Invalidated on add_review.
        self._rating_cache: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Listing management
    # ------------------------------------------------------------------

    def publish(
        self,
        agent_aic: str,
        agent_did: str,
        provider_org: str,
        name: str,
        description: str,
        capabilities: list[str] | None = None,
        pricing: Pricing | None = None,
        terms: str = "",
        tags: list[str] | None = None,
    ) -> MarketplaceListing:
        """Publish a new listing or update an existing one (by AIC).

        If a listing already exists for ``agent_aic``, it is updated
        (version incremented) rather than duplicated.
        """
        existing_id = self._aic_to_listing.get(agent_aic)
        now = time.time()

        if existing_id is not None:
            listing = self._listings[existing_id]
            # Remove old capability index entries.
            for cap in listing.capabilities:
                self._capability_index.get(cap, set()).discard(existing_id)
            # Remove old org index entry if provider_org is changing.
            old_org = listing.provider_org
            if old_org != provider_org:
                self._org_index.get(old_org, set()).discard(existing_id)
            # Update in place.
            listing.name = name
            listing.description = description
            listing.provider_org = provider_org
            listing.capabilities = list(capabilities or [])
            listing.pricing = pricing or Pricing(model=PricingModel.FREE)
            listing.terms = terms
            listing.tags = list(tags or [])
            listing.updated_at = now
            listing.version += 1
            listing.active = True
        else:
            listing = MarketplaceListing(
                listing_id=f"list_{uuid.uuid4().hex}",
                agent_aic=agent_aic,
                agent_did=agent_did,
                provider_org=provider_org,
                name=name,
                description=description,
                capabilities=list(capabilities or []),
                pricing=pricing or Pricing(model=PricingModel.FREE),
                terms=terms,
                tags=list(tags or []),
            )
            self._listings[listing.listing_id] = listing
            self._aic_to_listing[agent_aic] = listing.listing_id

        # Rebuild capability index.
        for cap in listing.capabilities:
            self._capability_index.setdefault(cap, set()).add(listing.listing_id)
        # Org index.
        self._org_index.setdefault(provider_org, set()).add(listing.listing_id)

        return listing

    def unpublish(self, listing_id: str) -> bool:
        """Deactivate a listing (soft delete).

        Returns True if the listing was found and active.
        """
        listing = self._listings.get(listing_id)
        if listing is None or not listing.active:
            return False
        listing.active = False
        listing.updated_at = time.time()
        return True

    def get_listing(self, listing_id: str) -> MarketplaceListing | None:
        return self._listings.get(listing_id)

    def get_listing_by_aic(self, agent_aic: str) -> MarketplaceListing | None:
        listing_id = self._aic_to_listing.get(agent_aic)
        if listing_id is None:
            return None
        return self._listings.get(listing_id)

    def update_pricing(self, listing_id: str, pricing: Pricing) -> bool:
        """Update the pricing of an existing listing."""
        listing = self._listings.get(listing_id)
        if listing is None:
            return False
        listing.pricing = pricing
        listing.updated_at = time.time()
        return True

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        capability: str | None = None,
        max_price: float | None = None,
        provider_org: str | None = None,
        tags: list[str] | None = None,
        active_only: bool = True,
        sort_by: str = "rating",
        limit: int | None = None,
    ) -> list[MarketplaceListing]:
        """Search listings by multiple criteria (AND-combined).

        ``sort_by`` can be ``"rating"`` (default), ``"price_low"``,
        ``"price_high"``, or ``"newest"``.
        """
        # Start with all listings (or filter by capability via index).
        if capability is not None:
            ids = self._capability_index.get(capability, set())
            candidates = [self._listings[i] for i in ids]
        else:
            candidates = list(self._listings.values())

        results: list[MarketplaceListing] = []
        for listing in candidates:
            if active_only and not listing.active:
                continue
            if provider_org is not None and listing.provider_org != provider_org:
                continue
            if max_price is not None and not listing.pricing.is_free:
                if listing.pricing.price > max_price:
                    continue
            if tags is not None:
                if not all(t in listing.tags for t in tags):
                    continue
            results.append(listing)

        # Sort.
        if sort_by == "price_low":
            results.sort(key=lambda l: l.pricing.price if not l.pricing.is_free else 0.0)
        elif sort_by == "price_high":
            results.sort(key=lambda l: -(l.pricing.price if not l.pricing.is_free else 0.0))
        elif sort_by == "newest":
            results.sort(key=lambda l: -l.published_at)
        else:  # "rating" — highest rating first, tie-break by review count.
            results.sort(
                key=lambda l: (
                    -self.get_average_rating(l.listing_id),
                    -len(self._reviews.get(l.listing_id, [])),
                )
            )

        if limit is not None:
            results = results[:limit]
        return results

    def list_listings(
        self, provider_org: str | None = None, active_only: bool = True
    ) -> list[MarketplaceListing]:
        """List all listings, optionally filtered by provider org."""
        if provider_org is not None:
            ids = self._org_index.get(provider_org, set())
            listings = [self._listings[i] for i in ids]
        else:
            listings = list(self._listings.values())
        if active_only:
            listings = [l for l in listings if l.active]
        return sorted(listings, key=lambda l: -l.published_at)

    # ------------------------------------------------------------------
    # Reviews
    # ------------------------------------------------------------------

    def add_review(
        self,
        listing_id: str,
        reviewer_org: str,
        rating: int,
        comment: str = "",
    ) -> AgentReview | None:
        """Add a review to a listing.  Returns None if listing not found."""
        if listing_id not in self._listings:
            return None
        review = AgentReview(
            review_id=f"rev_{uuid.uuid4().hex}",
            listing_id=listing_id,
            reviewer_org=reviewer_org,
            rating=_validate_rating(rating),
            comment=comment,
        )
        self._reviews.setdefault(listing_id, []).append(review)
        # Invalidate the cached average rating for this listing.
        self._rating_cache.pop(listing_id, None)
        return review

    def get_reviews(self, listing_id: str) -> list[AgentReview]:
        """Return all reviews for a listing, newest first."""
        reviews = self._reviews.get(listing_id, [])
        return sorted(reviews, key=lambda r: -r.timestamp)

    def get_average_rating(self, listing_id: str) -> float:
        """Return the average rating (0.0 if no reviews).

        Uses a cache that is invalidated whenever a review is added, so
        repeated calls (e.g. during ``search(sort_by="rating")``) do not
        recompute the average over the review list each time.
        """
        cached = self._rating_cache.get(listing_id)
        if cached is not None:
            return cached
        reviews = self._reviews.get(listing_id, [])
        if not reviews:
            return 0.0
        avg = sum(r.rating for r in reviews) / len(reviews)
        self._rating_cache[listing_id] = avg
        return avg

    def get_review_count(self, listing_id: str) -> int:
        return len(self._reviews.get(listing_id, []))

    # ------------------------------------------------------------------
    # Aggregations
    # ------------------------------------------------------------------

    def list_capabilities(self) -> list[str]:
        """Return all distinct capabilities across active listings, sorted."""
        caps = {
            cap
            for cap, ids in self._capability_index.items()
            if any(self._listings[i].active for i in ids)
        }
        return sorted(caps)

    def list_organizations(self) -> list[str]:
        """Return all distinct provider orgs with active listings, sorted."""
        orgs = {
            org
            for org, ids in self._org_index.items()
            if any(self._listings[i].active for i in ids)
        }
        return sorted(orgs)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def marketplace_summary(self) -> dict[str, Any]:
        """Return a global summary of the marketplace state."""
        active = [l for l in self._listings.values() if l.active]
        total_reviews = sum(len(revs) for revs in self._reviews.values())
        avg_price = 0.0
        priced = [l for l in active if not l.pricing.is_free]
        if priced:
            avg_price = sum(l.pricing.price for l in priced) / len(priced)

        return {
            "total_listings": len(self._listings),
            "active_listings": len(active),
            "total_reviews": total_reviews,
            "total_capabilities": len(self.list_capabilities()),
            "total_organizations": len(self.list_organizations()),
            "average_price": round(avg_price, 4),
            "priced_listings": len(priced),
            "free_listings": len(active) - len(priced),
        }
