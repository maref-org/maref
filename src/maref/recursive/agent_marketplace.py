from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.recursive.agent_discovery_negotiation import AgentDiscovery, AgentNegotiator
from maref.recursive.agent_economy import AgentEconomy
from maref.recursive.unified_audit import UnifiedAuditRecord, UnifiedAuditStore, make_record_id


class TrustLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ListingStatus(str, Enum):
    ACTIVE = "active"
    FULFILLED = "fulfilled"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass
class CapabilityListing:
    agent_id: str
    capability: str
    price: float = 0.0
    trust_requirement: TrustLevel = TrustLevel.LOW
    sla: dict[str, Any] = field(default_factory=dict)
    signed_card: str = ""
    listing_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: ListingStatus = ListingStatus.ACTIVE
    published_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "listing_id": self.listing_id,
            "agent_id": self.agent_id,
            "capability": self.capability,
            "price": self.price,
            "trust_requirement": self.trust_requirement.value,
            "sla": self.sla,
            "status": self.status.value,
            "published_at": self.published_at,
        }


@dataclass
class NegotiationResult:
    accepted: bool
    buyer_id: str
    seller_id: str
    listing_id: str
    agreement_id: str = ""
    final_price: float = 0.0
    refusal_reason: str = ""
    terms: dict[str, Any] = field(default_factory=dict)


class AgentMarketplace:
    DEFAULT_LISTING_TTL = 3600.0
    COMMISSION_RATE = 0.05

    def __init__(
        self,
        economy: AgentEconomy | None = None,
        discovery: AgentDiscovery | None = None,
        negotiator: AgentNegotiator | None = None,
        audit_store: UnifiedAuditStore | None = None,
    ) -> None:
        self._economy = economy or AgentEconomy()
        self._discovery = discovery
        self._negotiator = negotiator or AgentNegotiator()
        self._audit_store = audit_store or UnifiedAuditStore()
        self._listings: dict[str, CapabilityListing] = {}
        self._fulfilled: dict[str, NegotiationResult] = {}

    @property
    def economy(self) -> AgentEconomy:
        return self._economy

    @property
    def discovery(self) -> AgentDiscovery | None:
        return self._discovery

    def publish(self, listing: CapabilityListing) -> str:
        self._listings[listing.listing_id] = listing
        if self._discovery is not None:
            self._discovery.register_peer(
                listing.agent_id,
                [listing.capability],
                trust=0.5,
            )
        self._audit_store.append(
            UnifiedAuditRecord(
                record_id=make_record_id("mkt", hash(listing.listing_id) % 100000),
                timestamp=time.time(),
                layer="orchestration",
                round=45,
                event_type="capability_published",
                source_module="AgentMarketplace",
                target_module=listing.agent_id,
                decision=f"publish_{listing.capability}",
                justification=f"Price={listing.price}, trust={listing.trust_requirement.value}",
                outcome="success",
                context_refs=[listing.listing_id],
            )
        )
        return listing.listing_id

    def discover(self, required_capability: str) -> list[CapabilityListing]:
        results: list[CapabilityListing] = []
        for listing in self._listings.values():
            if listing.status == ListingStatus.ACTIVE and listing.capability == required_capability:
                results.append(listing)
        results.sort(key=lambda l: l.price)
        return results

    def discover_by_agent(self, agent_id: str) -> list[CapabilityListing]:
        return [
            l
            for l in self._listings.values()
            if l.agent_id == agent_id and l.status == ListingStatus.ACTIVE
        ]

    def negotiate(
        self,
        buyer_id: str,
        listing_id: str,
        max_price: float | None = None,
        buyer_trust: float = 0.5,
    ) -> NegotiationResult:
        listing = self._listings.get(listing_id)
        if listing is None:
            return NegotiationResult(
                accepted=False,
                buyer_id=buyer_id,
                seller_id="",
                listing_id=listing_id,
                refusal_reason="Listing not found",
            )

        if listing.status != ListingStatus.ACTIVE:
            return NegotiationResult(
                accepted=False,
                buyer_id=buyer_id,
                seller_id=listing.agent_id,
                listing_id=listing_id,
                refusal_reason=f"Listing status is {listing.status.value}",
            )

        trust_map = {
            TrustLevel.LOW: 0.0,
            TrustLevel.MEDIUM: 0.3,
            TrustLevel.HIGH: 0.6,
            TrustLevel.CRITICAL: 0.8,
        }
        required_trust = trust_map.get(listing.trust_requirement, 0.0)
        if buyer_trust < required_trust:
            return NegotiationResult(
                accepted=False,
                buyer_id=buyer_id,
                seller_id=listing.agent_id,
                listing_id=listing_id,
                refusal_reason=f"Buyer trust ({buyer_trust:.2f}) below required ({required_trust})",
            )

        final_price = listing.price
        if max_price is not None and max_price < listing.price:
            return NegotiationResult(
                accepted=False,
                buyer_id=buyer_id,
                seller_id=listing.agent_id,
                listing_id=listing_id,
                refusal_reason=f"Max price ({max_price}) below listing price ({listing.price})",
            )

        if self._economy.get_wallet(buyer_id) is None:
            self._economy.register_agent(buyer_id)
        if self._economy.get_wallet(listing.agent_id) is None:
            self._economy.register_agent(listing.agent_id)

        wallet = self._economy.get_wallet(buyer_id)
        if wallet is not None and not wallet.can_spend(final_price):
            return NegotiationResult(
                accepted=False,
                buyer_id=buyer_id,
                seller_id=listing.agent_id,
                listing_id=listing_id,
                refusal_reason="Insufficient funds",
            )

        commission = final_price * self.COMMISSION_RATE
        trade = self._economy.propose_trade(
            buyer_id, listing.agent_id, listing.capability, final_price - commission
        )
        if trade is None:
            return NegotiationResult(
                accepted=False,
                buyer_id=buyer_id,
                seller_id=listing.agent_id,
                listing_id=listing_id,
                refusal_reason="Trade proposal failed",
            )

        self._economy.execute_trade(trade.trade_id)

        agreement_id = f"agr_{listing_id}_{buyer_id}_{int(time.time())}"
        result = NegotiationResult(
            accepted=True,
            buyer_id=buyer_id,
            seller_id=listing.agent_id,
            listing_id=listing_id,
            agreement_id=agreement_id,
            final_price=final_price,
            terms={
                "capability": listing.capability,
                "price": final_price,
                "commission": commission,
                "sla": listing.sla,
            },
        )
        self._fulfilled[agreement_id] = result
        listing.status = ListingStatus.FULFILLED

        self._audit_store.append(
            UnifiedAuditRecord(
                record_id=make_record_id("mkt_n", hash(agreement_id) % 100000),
                timestamp=time.time(),
                layer="orchestration",
                round=45,
                event_type="capability_negotiated",
                source_module="AgentMarketplace",
                target_module=listing.agent_id,
                decision=f"negotiate_{listing.capability}",
                justification=f"Price={final_price}, buyer={buyer_id}",
                outcome="success",
                context_refs=[agreement_id, listing_id],
            )
        )
        return result

    def revoke_listing(self, listing_id: str) -> bool:
        listing = self._listings.get(listing_id)
        if listing is None or listing.status != ListingStatus.ACTIVE:
            return False
        listing.status = ListingStatus.REVOKED
        self._audit_store.append(
            UnifiedAuditRecord(
                record_id=make_record_id("mkt_r", hash(listing_id) % 100000),
                timestamp=time.time(),
                layer="orchestration",
                round=45,
                event_type="capability_revoked",
                source_module="AgentMarketplace",
                target_module=listing.agent_id,
                decision=f"revoke_{listing.capability}",
                justification="Listing revoked",
                outcome="success",
                context_refs=[listing_id],
            )
        )
        return True

    def get_listing(self, listing_id: str) -> CapabilityListing | None:
        return self._listings.get(listing_id)

    def get_all_listings(self) -> list[CapabilityListing]:
        return list(self._listings.values())

    def get_fulfilled(self) -> list[NegotiationResult]:
        return list(self._fulfilled.values())

    def stats(self) -> dict[str, Any]:
        active = sum(1 for l in self._listings.values() if l.status == ListingStatus.ACTIVE)
        return {
            "total_listings": len(self._listings),
            "active_listings": active,
            "fulfilled": len(self._fulfilled),
            "economy_stats": self._economy.get_statistics(),
        }

    def clear(self) -> None:
        self._listings.clear()
        self._fulfilled.clear()
