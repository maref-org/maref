"""Federated Discovery (ADP Client).

Implements the ACPs ADP (Agent Discovery Protocol) client: federated
agent discovery across organizational boundaries via multi-server
forwarding queries.

ADP v2.00 enables an agent to discover agents registered with other
federation servers by forwarding capability-based queries through a
chain of federation peers. Each server responds with its local catalog
and optionally forwards the query to its known peers.

Reference: AIP-ACPs-Technical-Analysis.md section 2.4 (ADP v2.00).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from maref.federation.gateway import FederatedAgent, FederationGateway

# ADP protocol version (matches ACPs v2.00).
ADP_PROTOCOL_VERSION = "2.00"

# Maximum query forwarding depth (prevents infinite loops).
DEFAULT_MAX_DEPTH = 3

# Default query timeout in seconds.
DEFAULT_QUERY_TIMEOUT = 5.0


@dataclass
class DiscoveryQuery:
    """An ADP discovery query.

    Attributes:
        capability: Optional capability/skill ID to filter by.
        aic_prefix: Optional AIC prefix (e.g. ARSP.Provider) to filter by.
        protocol: Optional wire protocol filter ("a2a", "mcp", "aip").
        max_results: Maximum number of agents to return.
        max_depth: Maximum forwarding depth.
        visited: Set of server IDs already visited (loop prevention).
        query_id: Unique query identifier for tracing.
    """

    capability: str | None = None
    aic_prefix: str | None = None
    protocol: str | None = None
    max_results: int = 50
    max_depth: int = DEFAULT_MAX_DEPTH
    visited: set[str] = field(default_factory=set)
    query_id: str = ""

    def __post_init__(self) -> None:
        if not self.query_id:
            import uuid

            self.query_id = f"adp-{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "queryId": self.query_id,
            "capability": self.capability,
            "aicPrefix": self.aic_prefix,
            "protocol": self.protocol,
            "maxResults": self.max_results,
            "maxDepth": self.max_depth,
            "visited": list(self.visited),
        }


@dataclass
class DiscoveryResult:
    """A single agent discovered via ADP.

    Attributes:
        agent: The discovered federated agent.
        source_server: The server that returned this agent.
        hop_count: Number of forwarding hops to reach this agent.
    """

    agent: FederatedAgent
    source_server: str
    hop_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "aic": self.agent.aic.aic_string,
            "did": self.agent.did.did_string,
            "name": self.agent.acs.name,
            "source_server": self.source_server,
            "hop_count": self.hop_count,
            "protocol": self.agent.protocol,
            "endpoint": self.agent.endpoint_url,
            "capabilities": [s.id for s in self.agent.acs.skills],
        }


@dataclass
class FederationPeer:
    """A peer federation server for ADP forwarding.

    Attributes:
        server_id: Unique identifier for the peer server.
        endpoint_url: The peer's ADP query endpoint URL.
        trust_score: Trust score for this peer (0.0-100.0).
        last_contact: Timestamp of last successful contact.
        healthy: Whether the peer is currently responsive.
    """

    server_id: str
    endpoint_url: str
    trust_score: float = 50.0
    last_contact: float = 0.0
    healthy: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "endpoint_url": self.endpoint_url,
            "trust_score": self.trust_score,
            "last_contact": self.last_contact,
            "healthy": self.healthy,
        }


class FederatedDiscovery:
    """ADP discovery client for cross-organization agent discovery.

    The discovery client queries the local federation gateway first,
    then forwards the query to peer federation servers. Results are
    deduplicated by AIC and sorted by trust score and hop count.

    Usage:
        discovery = FederatedDiscovery(gateway=gateway)
        discovery.add_peer("fed-server-2", "https://fed2.example.com/adp")
        results = discovery.discover(capability="research")
    """

    def __init__(
        self,
        gateway: FederationGateway,
        server_id: str = "maref-local",
        max_depth: int = DEFAULT_MAX_DEPTH,
        query_timeout: float = DEFAULT_QUERY_TIMEOUT,
    ) -> None:
        self._gateway = gateway
        self._server_id = server_id
        self._max_depth = max_depth
        self._query_timeout = query_timeout
        self._peers: dict[str, FederationPeer] = {}
        # Per-instance catalog providers for testability. Kept on the
        # instance (not module-level) so parallel tests don't leak state.
        self._catalog_providers: dict[str, Callable[[], list[FederatedAgent]]] = {}

    @property
    def server_id(self) -> str:
        return self._server_id

    @property
    def peer_count(self) -> int:
        return len(self._peers)

    def add_peer(
        self,
        server_id: str,
        endpoint_url: str,
        trust_score: float = 50.0,
    ) -> FederationPeer:
        """Register a peer federation server for forwarding.

        Args:
            server_id: Unique peer server identifier.
            endpoint_url: ADP query endpoint URL.
            trust_score: Initial trust score (0.0-100.0).

        Returns:
            The registered :class:`FederationPeer`.
        """
        peer = FederationPeer(
            server_id=server_id,
            endpoint_url=endpoint_url.rstrip("/"),
            trust_score=max(0.0, min(100.0, trust_score)),
        )
        self._peers[server_id] = peer
        return peer

    def remove_peer(self, server_id: str) -> bool:
        """Remove a peer federation server.

        Returns:
            True if the peer was found and removed, False otherwise.
        """
        return self._peers.pop(server_id, None) is not None

    def list_peers(self) -> list[FederationPeer]:
        """List all registered peer servers."""
        return list(self._peers.values())

    def discover(
        self,
        capability: str | None = None,
        aic_prefix: str | None = None,
        protocol: str | None = None,
        max_results: int = 50,
        include_remote: bool = True,
    ) -> list[DiscoveryResult]:
        """Discover federated agents matching the given filters.

        Queries the local gateway first, then forwards to peer servers
        (if ``include_remote`` is True). Results are deduplicated by AIC
        and sorted by hop count (local first) then trust score.

        Args:
            capability: Optional capability/skill ID to filter by.
            aic_prefix: Optional AIC prefix filter (e.g. "1.2.156.3088.1.2").
            protocol: Optional wire protocol filter.
            max_results: Maximum number of results to return.
            include_remote: Whether to query peer federation servers.

        Returns:
            A list of :class:`DiscoveryResult` sorted by relevance.
        """
        query = DiscoveryQuery(
            capability=capability,
            aic_prefix=aic_prefix,
            protocol=protocol,
            max_results=max_results,
            max_depth=self._max_depth,
            visited={self._server_id},
        )

        # Query local gateway first (hop 0).
        results = self._query_local(query)

        if include_remote and len(results) < max_results:
            remote_results = self._forward_to_peers(query, results)
            results.extend(remote_results)

        # Deduplicate by AIC string, keeping the lowest hop count.
        seen: dict[str, DiscoveryResult] = {}
        for result in results:
            aic_str = result.agent.aic.aic_string
            existing = seen.get(aic_str)
            if existing is None or result.hop_count < existing.hop_count:
                seen[aic_str] = result

        # Sort by hop count (local first, then remote by source server name).
        sorted_results = sorted(
            seen.values(),
            key=lambda r: (r.hop_count, r.source_server),
        )
        return sorted_results[:max_results]

    def _query_local(self, query: DiscoveryQuery) -> list[DiscoveryResult]:
        """Query the local federation gateway for matching agents."""
        agents: list[FederatedAgent] = []

        if query.capability is not None:
            agents = self._gateway.discover_by_capability(query.capability)
        else:
            agents = self._gateway.list_agents(protocol_filter=query.protocol)

        results: list[DiscoveryResult] = []
        for agent in agents:
            if not self._matches_filters(agent, query):
                continue
            results.append(
                DiscoveryResult(
                    agent=agent,
                    source_server=self._server_id,
                    hop_count=0,
                )
            )
        return results

    def _matches_filters(self, agent: FederatedAgent, query: DiscoveryQuery) -> bool:
        """Check whether an agent matches the query filters."""
        if query.protocol is not None and agent.protocol != query.protocol:
            return False
        if query.aic_prefix is not None:
            if not agent.aic.aic_string.startswith(query.aic_prefix):
                return False
        if query.capability is not None:
            if not any(s.id == query.capability for s in agent.acs.skills):
                return False
        return True

    def _forward_to_peers(
        self,
        query: DiscoveryQuery,
        local_results: list[DiscoveryResult],
    ) -> list[DiscoveryResult]:
        """Forward the query to peer federation servers.

        This is a synchronous, in-process simulation of ADP forwarding.
        In production, this would issue HTTP requests to peer ADP endpoints.
        For testability and offline operation, peers can be registered with
        a callable hook that returns their local catalog.
        """
        remote_results: list[DiscoveryResult] = []
        local_aics = {r.agent.aic.aic_string for r in local_results}

        for peer in self._peers.values():
            if not peer.healthy:
                continue
            if peer.server_id in query.visited:
                continue
            if query.max_depth <= 0:
                continue

            # Fetch peer's catalog (in production, HTTP GET to peer.endpoint_url).
            peer_catalog = self._fetch_peer_catalog(peer)
            for agent in peer_catalog:
                aic_str = agent.aic.aic_string
                if aic_str in local_aics:
                    continue
                if not self._matches_filters(agent, query):
                    continue
                remote_results.append(
                    DiscoveryResult(
                        agent=agent,
                        source_server=peer.server_id,
                        hop_count=1,
                    )
                )
                local_aics.add(aic_str)

            peer.last_contact = time.time()

        return remote_results

    def _fetch_peer_catalog(self, peer: FederationPeer) -> list[FederatedAgent]:
        """Fetch a peer's local agent catalog.

        In production this would issue an HTTP GET to
        ``{peer.endpoint_url}/.well-known/adp/catalog``. For testability,
        peers can register a catalog provider via :meth:`set_catalog_provider`.
        """
        provider = self._catalog_providers.get(peer.server_id)
        if provider is None:
            return []
        return provider()

    def set_catalog_provider(
        self,
        server_id: str,
        provider: Callable[[], list[FederatedAgent]],
    ) -> None:
        """Register a callable that returns the local catalog for a peer.

        This is primarily for testing; production deployments use HTTP.
        """
        self._catalog_providers[server_id] = provider

    def discovery_summary(self) -> dict[str, Any]:
        """Return a summary of the discovery service state."""
        healthy_peers = sum(1 for p in self._peers.values() if p.healthy)
        return {
            "server_id": self._server_id,
            "local_agent_count": self._gateway.agent_count,
            "peer_count": len(self._peers),
            "healthy_peers": healthy_peers,
            "max_depth": self._max_depth,
        }


__all__ = [
    "ADP_PROTOCOL_VERSION",
    "DEFAULT_MAX_DEPTH",
    "DEFAULT_QUERY_TIMEOUT",
    "DiscoveryQuery",
    "DiscoveryResult",
    "FederationPeer",
    "FederatedDiscovery",
]
