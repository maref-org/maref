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
from typing import Any, Protocol

import httpx

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


class DiscoveryTransport(Protocol):
    """Abstract transport for fetching peer agent catalogs.

    Implementations include:
    - :class:`InProcessTransport`: in-process callbacks (testing/offline).
    - :class:`HTTPDiscoveryTransport`: real HTTP via ``httpx`` (production).
    """

    def fetch_catalog(self, peer: FederationPeer, query: DiscoveryQuery) -> list[FederatedAgent]:
        """Fetch the agent catalog from a peer federation server."""
        ...


class InProcessTransport:
    """In-process transport using registered catalog providers.

    This is the default transport, primarily used for testing and
    offline operation. Peers register callable providers via
    :meth:`set_catalog_provider`.
    """

    def __init__(self) -> None:
        self._providers: dict[str, Callable[[], list[FederatedAgent]]] = {}

    def set_catalog_provider(
        self,
        server_id: str,
        provider: Callable[[], list[FederatedAgent]],
    ) -> None:
        """Register a callable that returns the local catalog for a peer."""
        self._providers[server_id] = provider

    def fetch_catalog(self, peer: FederationPeer, query: DiscoveryQuery) -> list[FederatedAgent]:
        provider = self._providers.get(peer.server_id)
        if provider is None:
            return []
        return provider()


class HTTPDiscoveryTransport:
    """HTTP transport for fetching peer catalogs via ADP protocol.

    Fetches peer catalogs via HTTP GET to
    ``{peer.endpoint_url}/.well-known/adp/catalog``.

    Uses ``httpx`` for HTTP requests with configurable timeout and
    retries. On any error (network, parse, etc.), returns an empty
    list rather than raising.
    """

    def __init__(
        self,
        timeout: float = DEFAULT_QUERY_TIMEOUT,
        max_retries: int = 2,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries

    def fetch_catalog(self, peer: FederationPeer, query: DiscoveryQuery) -> list[FederatedAgent]:
        """Fetch a peer's agent catalog via HTTP (single-layer view).

        Returns agents this peer knows about — its local catalog plus any
        catalog it forwarded from its own peers — without hop/source
        metadata. See :meth:`fetch_catalog_with_sources` for the
        multi-hop view used by :class:`FederatedDiscovery`.

        Returns an empty list on any error (network, parse, etc.).
        """
        return [agent for agent, _, _ in self.fetch_catalog_with_sources(peer, query)]

    def fetch_catalog_with_sources(
        self, peer: FederationPeer, query: DiscoveryQuery
    ) -> list[tuple[FederatedAgent, str, int]]:
        """Fetch a peer's catalog over HTTP, including multi-hop forwards.

        The request carries the query's ``visited`` set and ``max_depth``
        so the peer can forward the query onward (Phase 3.1 distributed
        catalog). The peer's response is a tree of ``{server_id, _hop,
        agents, forwarded}`` nodes; this method flattens it into a list
        of ``(agent, source_server, hop_count)`` tuples, where
        ``hop_count`` is measured from the caller (local=1, one forward
        away=2, ...).

        Returns an empty list on any error (network, parse, etc.).
        """
        url = f"{peer.endpoint_url.rstrip('/')}/.well-known/adp/catalog"
        params: dict[str, Any] = {
            "capability": query.capability,
            "aicPrefix": query.aic_prefix,
            "protocol": query.protocol,
            "maxResults": query.max_results,
        }
        params = {k: v for k, v in params.items() if v is not None}
        if query.visited:
            params["visited"] = ",".join(sorted(query.visited))
        if query.max_depth:
            params["maxDepth"] = query.max_depth

        for attempt in range(self._max_retries + 1):
            try:
                response = httpx.get(url, params=params, timeout=self._timeout)
                response.raise_for_status()
                data = response.json()
                return self._parse_catalog_response_with_sources(data)
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                if attempt < self._max_retries:
                    continue
                return []
        return []

    def _parse_catalog_response(self, data: Any) -> list[FederatedAgent]:
        """Parse a JSON catalog response into FederatedAgent list.

        Expected format::

            {"agents": [{"aic": "...", "did": "...", "name": "...", ...}]}

        Returns an empty list on any parse error.
        """
        if not isinstance(data, dict):
            return []
        return self._parse_agent_list(data.get("agents", []))

    def _parse_catalog_response_with_sources(
        self, data: Any
    ) -> list[tuple[FederatedAgent, str, int]]:
        """Flatten a multi-hop catalog response tree into (agent, source, hop)."""
        results: list[tuple[FederatedAgent, str, int]] = []
        if isinstance(data, dict):
            self._collect_agents(data, results, default_hop=1)
        return results

    def _collect_agents(
        self,
        node: dict[str, Any],
        out: list[tuple[FederatedAgent, str, int]],
        default_hop: int,
    ) -> None:
        """Recursively flatten one ``{server_id, _hop, agents, forwarded}`` node."""
        server_id = node.get("server_id", "")
        try:
            hop = int(node.get("_hop", default_hop))
        except (TypeError, ValueError):
            hop = default_hop
        for agent in self._parse_agent_list(node.get("agents", [])):
            out.append((agent, server_id, hop))
        for child in node.get("forwarded", []):
            if isinstance(child, dict):
                self._collect_agents(child, out, default_hop)

    def _parse_agent_list(self, items: Any) -> list[FederatedAgent]:
        """Parse a JSON ``agents`` list into :class:`FederatedAgent` objects."""
        from maref.identity.aic_adapter import AIC
        from maref.identity.did_registry import AgentDID
        from maref.integration.acs_parser import AgentCapabilitySpec, AgentSkill

        if not isinstance(items, list):
            return []

        result: list[FederatedAgent] = []
        for item in items:
            try:
                if not isinstance(item, dict):
                    continue
                aic = AIC.parse(item["aic"])
                did = AgentDID.parse(item["did"])
                skills_data = item.get("capabilities", [])
                acs = AgentCapabilitySpec(
                    aic=item["aic"],
                    name=item.get("name", "unknown"),
                    description=item.get("description", ""),
                    skills=[
                        AgentSkill(id=s, name=s, description="")
                        for s in skills_data
                        if isinstance(s, str)
                    ],
                )
                agent = FederatedAgent(
                    did=did,
                    aic=aic,
                    acs=acs,
                    endpoint_url=item.get("endpoint", ""),
                    protocol=item.get("protocol", "aip"),
                    registered_at=float(item.get("registered_at", 0.0)),
                )
                result.append(agent)
            except (KeyError, ValueError, TypeError):
                continue

        return result


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
        transport: DiscoveryTransport | None = None,
    ) -> None:
        self._gateway = gateway
        self._server_id = server_id
        self._max_depth = max_depth
        self._query_timeout = query_timeout
        self._peers: dict[str, FederationPeer] = {}
        # Transport for fetching peer catalogs. Defaults to in-process
        # for testability; use HTTPDiscoveryTransport for production.
        self._transport: DiscoveryTransport = transport or InProcessTransport()

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

        Uses the configured :class:`DiscoveryTransport` to fetch each
        peer's catalog. The default :class:`InProcessTransport` uses
        registered callbacks; :class:`HTTPDiscoveryTransport` issues
        real HTTP requests to peer ADP endpoints.
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

            # Fetch peer's catalog via the configured transport.
            # Multi-hop transports return (agent, source_server, hop_count);
            # single-hop transports fall back to peer.id / hop 1.
            fetched = self._fetch_peer_catalog(peer, query)
            for agent, source, hop in fetched:
                aic_str = agent.aic.aic_string
                if aic_str in local_aics:
                    continue
                if not self._matches_filters(agent, query):
                    continue
                remote_results.append(
                    DiscoveryResult(
                        agent=agent,
                        source_server=source,
                        hop_count=hop,
                    )
                )
                local_aics.add(aic_str)

            peer.last_contact = time.time()

        return remote_results

    def _fetch_peer_catalog(
        self, peer: FederationPeer, query: DiscoveryQuery
    ) -> list[tuple[FederatedAgent, str, int]]:
        """Fetch a peer's agent catalog via the configured transport.

        Returns a list of ``(agent, source_server, hop_count)`` tuples.
        :class:`HTTPDiscoveryTransport` natively provides source/hop
        metadata (multi-hop forwarding); other transports are wrapped to
        attribute every agent to the peer at hop 1.
        """
        fetch_sources = getattr(self._transport, "fetch_catalog_with_sources", None)
        if callable(fetch_sources):
            return fetch_sources(peer, query)
        return [(agent, peer.server_id, 1) for agent in self._transport.fetch_catalog(peer, query)]

    def set_catalog_provider(
        self,
        server_id: str,
        provider: Callable[[], list[FederatedAgent]],
    ) -> None:
        """Register a callable that returns the local catalog for a peer.

        This is a backward-compatibility wrapper for
        :meth:`InProcessTransport.set_catalog_provider`. Only works
        when the transport is an :class:`InProcessTransport`.

        For production, pass an :class:`HTTPDiscoveryTransport` to
        :class:`FederatedDiscovery` instead.
        """
        if isinstance(self._transport, InProcessTransport):
            self._transport.set_catalog_provider(server_id, provider)

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
    "DiscoveryTransport",
    "FederatedDiscovery",
    "FederationPeer",
    "HTTPDiscoveryTransport",
    "InProcessTransport",
]
