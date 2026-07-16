"""Federated Agent Catalog.

A searchable directory of federated agents indexed by AIC, DID,
capability, protocol, and organization. Supports:

- **Publication**: agents publish their ACS document to the catalog.
- **Subscription**: clients subscribe to capability updates.
- **Query**: multi-criteria search (capability, protocol, organization, tier).
- **Indexing**: inverted indices for fast capability-based lookup.

The catalog is the local counterpart to :class:`FederatedDiscovery`:
it stores the agents registered with this federation server, and the
discovery client queries it (locally) and forwards queries to peer
catalogs (remotely).

Reference: AIP-ACPs-Technical-Analysis.md section 4.6 (Agent Catalog).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from maref.federation.gateway import FederatedAgent


@dataclass
class CatalogEntry:
    """A single entry in the federated agent catalog.

    Attributes:
        agent: The federated agent.
        published_at: When the entry was published to this catalog.
        updated_at: When the entry was last updated.
        version: Catalog entry version (incremented on each update).
        tags: Optional tags for additional indexing.
    """

    agent: FederatedAgent
    published_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    version: int = 1
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "aic": self.agent.aic.aic_string,
            "did": self.agent.did.did_string,
            "name": self.agent.acs.name,
            "organization": (
                self.agent.acs.provider.organization
                if self.agent.acs.provider
                else ""
            ),
            "protocol": self.agent.protocol,
            "endpoint": self.agent.endpoint_url,
            "capabilities": [s.id for s in self.agent.acs.skills],
            "tags": list(self.tags),
            "published_at": self.published_at,
            "updated_at": self.updated_at,
            "version": self.version,
        }


@dataclass
class CatalogSubscription:
    """A subscription to catalog updates.

    Attributes:
        subscription_id: Unique subscription identifier.
        capability_filter: Optional capability to filter on.
        callback: Called when a matching entry is published or updated.
        created_at: Subscription creation timestamp.
        active: Whether the subscription is active.
    """

    subscription_id: str
    callback: Callable[[CatalogEntry], None] = field(repr=False)
    capability_filter: str | None = None
    created_at: float = field(default_factory=time.time)
    active: bool = True

    def matches(self, entry: CatalogEntry) -> bool:
        """Check whether an entry matches this subscription."""
        if not self.active:
            return False
        if self.capability_filter is None:
            return True
        return any(
            s.id == self.capability_filter for s in entry.agent.acs.skills
        )


class FederatedCatalog:
    """Searchable directory of federated agents.

    Maintains entries indexed by AIC, DID, capability, protocol, and
    organization for fast multi-criteria queries.

    Usage:
        catalog = FederatedCatalog()
        catalog.publish(agent)
        results = catalog.query(capability="research", protocol="aip")
    """

    def __init__(self) -> None:
        # Primary storage: AIC string → CatalogEntry.
        self._entries: dict[str, CatalogEntry] = {}
        # Secondary indices for fast lookup.
        self._did_to_aic: dict[str, str] = {}
        self._capability_index: dict[str, set[str]] = {}  # capability → {aic}
        self._protocol_index: dict[str, set[str]] = {}  # protocol → {aic}
        self._org_index: dict[str, set[str]] = {}  # organization → {aic}
        self._subscriptions: dict[str, CatalogSubscription] = {}
        self._sub_counter: int = 0

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def subscription_count(self) -> int:
        return sum(1 for s in self._subscriptions.values() if s.active)

    def publish(
        self,
        agent: FederatedAgent,
        tags: list[str] | None = None,
    ) -> CatalogEntry:
        """Publish or update an agent's entry in the catalog.

        If an entry with the same AIC already exists, it is updated
        (version incremented, ``updated_at`` refreshed) and subscribers
        are notified.

        Args:
            agent: The federated agent to publish.
            tags: Optional tags for additional indexing.

        Returns:
            The published :class:`CatalogEntry`.
        """
        aic_str = agent.aic.aic_string
        existing = self._entries.get(aic_str)

        if existing is not None:
            # Update existing entry.
            self._remove_from_indices(existing)
            existing.agent = agent
            existing.updated_at = time.time()
            existing.version += 1
            if tags is not None:
                existing.tags = list(tags)
            entry = existing
        else:
            entry = CatalogEntry(
                agent=agent,
                tags=list(tags) if tags else [],
            )
            self._entries[aic_str] = entry

        # Update indices.
        self._add_to_indices(entry)
        # Notify subscribers.
        self._notify_subscribers(entry)

        return entry

    def unpublish(self, aic_string: str) -> bool:
        """Remove an agent's entry from the catalog.

        Returns:
            True if the entry was found and removed, False otherwise.
        """
        entry = self._entries.pop(aic_string, None)
        if entry is None:
            return False
        self._remove_from_indices(entry)
        self._did_to_aic.pop(entry.agent.did.did_string, None)
        return True

    def get_by_aic(self, aic_string: str) -> CatalogEntry | None:
        """Look up a catalog entry by AIC string."""
        return self._entries.get(aic_string)

    def get_by_did(self, did_string: str) -> CatalogEntry | None:
        """Look up a catalog entry by DID string."""
        aic_str = self._did_to_aic.get(did_string)
        if aic_str is None:
            return None
        return self._entries.get(aic_str)

    def query(
        self,
        capability: str | None = None,
        protocol: str | None = None,
        organization: str | None = None,
        tag: str | None = None,
        limit: int = 100,
    ) -> list[CatalogEntry]:
        """Query the catalog with multiple optional filters.

        All filters are AND-combined. Entries matching all provided
        filters are returned, sorted by ``updated_at`` (most recent first).

        Args:
            capability: Optional capability/skill ID.
            protocol: Optional wire protocol.
            organization: Optional provider organization.
            tag: Optional tag.
            limit: Maximum number of results.

        Returns:
            A list of matching :class:`CatalogEntry` instances.
        """
        # Start with all AICs, then intersect with each filter's index.
        candidate_aics: set[str] | None = None

        if capability is not None:
            caps = self._capability_index.get(capability, set())
            candidate_aics = caps.copy() if candidate_aics is None else candidate_aics & caps
        if protocol is not None:
            protos = self._protocol_index.get(protocol, set())
            candidate_aics = protos.copy() if candidate_aics is None else candidate_aics & protos
        if organization is not None:
            orgs = self._org_index.get(organization, set())
            candidate_aics = orgs.copy() if candidate_aics is None else candidate_aics & orgs

        if candidate_aics is None:
            # No filters — all entries.
            candidate_aics = set(self._entries.keys())

        results: list[CatalogEntry] = []
        for aic_str in candidate_aics:
            entry = self._entries.get(aic_str)
            if entry is None:
                continue
            if tag is not None and tag not in entry.tags:
                continue
            results.append(entry)

        # Sort by updated_at descending.
        results.sort(key=lambda e: e.updated_at, reverse=True)
        return results[:limit]

    def list_capabilities(self) -> list[str]:
        """Return all unique capability IDs in the catalog."""
        return sorted(self._capability_index.keys())

    def list_organizations(self) -> list[str]:
        """Return all unique provider organizations in the catalog."""
        return sorted(self._org_index.keys())

    def list_protocols(self) -> list[str]:
        """Return all unique wire protocols in the catalog."""
        return sorted(self._protocol_index.keys())

    def subscribe(
        self,
        callback: Callable[[CatalogEntry], None],
        capability_filter: str | None = None,
    ) -> str:
        """Subscribe to catalog updates.

        The callback is invoked whenever a matching entry is published
        or updated.

        Args:
            callback: Called with the updated :class:`CatalogEntry`.
            capability_filter: Optional capability to filter on.

        Returns:
            The subscription ID (use :meth:`unsubscribe` to remove).
        """
        self._sub_counter += 1
        sub_id = f"sub-{self._sub_counter:06d}"
        sub = CatalogSubscription(
            subscription_id=sub_id,
            capability_filter=capability_filter,
            callback=callback,
        )
        self._subscriptions[sub_id] = sub
        return sub_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """Remove a subscription.

        Returns:
            True if the subscription was found and removed;
            False if not found (already removed or never existed).
        """
        sub = self._subscriptions.pop(subscription_id, None)
        if sub is None:
            return False
        # Mark inactive in case the caller retains a reference to the object.
        sub.active = False
        return True

    def _notify_subscribers(self, entry: CatalogEntry) -> None:
        """Notify all matching subscriptions of an entry update."""
        for sub in self._subscriptions.values():
            if sub.matches(entry):
                try:
                    sub.callback(entry)
                except Exception:
                    # Swallow subscriber errors to protect the catalog.
                    pass

    def _add_to_indices(self, entry: CatalogEntry) -> None:
        """Add an entry to all secondary indices."""
        aic_str = entry.agent.aic.aic_string
        self._did_to_aic[entry.agent.did.did_string] = aic_str

        for skill in entry.agent.acs.skills:
            self._capability_index.setdefault(skill.id, set()).add(aic_str)

        proto = entry.agent.protocol
        self._protocol_index.setdefault(proto, set()).add(aic_str)

        org = (
            entry.agent.acs.provider.organization
            if entry.agent.acs.provider
            else ""
        )
        if org:
            self._org_index.setdefault(org, set()).add(aic_str)

    def _remove_from_indices(self, entry: CatalogEntry) -> None:
        """Remove an entry from all secondary indices."""
        aic_str = entry.agent.aic.aic_string

        for skill in entry.agent.acs.skills:
            caps = self._capability_index.get(skill.id)
            if caps is not None:
                caps.discard(aic_str)
                if not caps:
                    del self._capability_index[skill.id]

        proto = entry.agent.protocol
        protos = self._protocol_index.get(proto)
        if protos is not None:
            protos.discard(aic_str)
            if not protos:
                del self._protocol_index[proto]

        org = (
            entry.agent.acs.provider.organization
            if entry.agent.acs.provider
            else ""
        )
        if org:
            orgs = self._org_index.get(org)
            if orgs is not None:
                orgs.discard(aic_str)
                if not orgs:
                    del self._org_index[org]

    def catalog_summary(self) -> dict[str, Any]:
        """Return a summary of the catalog state."""
        return {
            "entry_count": len(self._entries),
            "capability_count": len(self._capability_index),
            "protocol_count": len(self._protocol_index),
            "organization_count": len(self._org_index),
            "active_subscriptions": self.subscription_count,
        }


__all__ = [
    "CatalogEntry",
    "CatalogSubscription",
    "FederatedCatalog",
]
