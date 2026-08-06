"""Bootstrap protocol for the MAREF agent internet (Phase 3.1).

A server joins the federation network by contacting one or more *seed*
nodes — known entry points that answer ``GET /api/v1/federation/network/peers``
with the peers they already know. :class:`BootstrapClient` merges every
seed (and the peers each seed reports) into the local
:class:`~maref.federation.discovery.FederatedDiscovery` peer table, with
deduplication and loop protection (never re-adds an existing peer or
itself).

Seeds may be discovered out-of-band — a static config file, an
environment variable, or DNS SRV records. :func:`parse_srv_seeds` turns
DNS SRV lookup results into :class:`BootstrapSeed` entries; production
deployments can resolve SRV records via ``dnspython`` (or any resolver)
and pass the records in, keeping MAREF itself dependency-free.

Typical join sequence (see :class:`~maref.federation.membership.MembershipManager`):
``bootstrap()`` to learn the network, then a heartbeat broadcast so every
learned peer records us as a member (heartbeats also auto-register unknown
peers, self-healing the membership table).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from maref.federation.discovery import FederatedDiscovery, FederationPeer

DEFAULT_BOOTSTRAP_TIMEOUT = 5.0

#: HTTP path exposing a server's known peers (see federation_http.py).
PEERS_ENDPOINT_PATH = "/api/v1/federation/network/peers"


@dataclass(frozen=True)
class BootstrapSeed:
    """A known entry point into the federation network.

    Attributes:
        server_id: Identifier of the seed server.
        endpoint_url: Base URL of the seed server (e.g. ``http://10.0.0.1:9000``).
    """

    server_id: str
    endpoint_url: str


def parse_srv_seeds(
    records: list[dict[str, Any]],
    *,
    scheme: str = "http",
    default_port: int = 8000,
) -> list[BootstrapSeed]:
    """Convert DNS SRV lookup records into :class:`BootstrapSeed` entries.

    Each record mirrors what a SRV query returns for ``_maref._tcp``::

        {"target": "node1.example.com", "port": 9100, "priority": 10}

    ``target`` is a hostname (trailing dot stripped); the seed id is
    derived as ``seed:<target>:<port>``.

    Args:
        records: SRV result records (``target``/``port`` keys required).
        scheme: URL scheme to prefix the endpoint with (default ``http``).
        default_port: Port used when a record omits ``port``.

    Returns:
        A list of :class:`BootstrapSeed` entries (empty if no valid records).
    """
    seeds: list[BootstrapSeed] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        target = str(record.get("target", "")).rstrip(".")
        if not target:
            continue
        try:
            port = int(record.get("port", default_port))
        except (TypeError, ValueError):
            port = default_port
        seeds.append(
            BootstrapSeed(
                server_id=f"seed:{target}:{port}",
                endpoint_url=f"{scheme}://{target}:{port}",
            )
        )
    return seeds


class BootstrapClient:
    """Join a federation network via seed nodes.

    Args:
        discovery: The local :class:`FederatedDiscovery` to populate.
        seeds: Seed nodes to contact.
        timeout: Per-request HTTP timeout in seconds.
    """

    def __init__(
        self,
        discovery: FederatedDiscovery,
        seeds: list[BootstrapSeed],
        timeout: float = DEFAULT_BOOTSTRAP_TIMEOUT,
    ) -> None:
        self._discovery = discovery
        self._seeds = list(seeds)
        self._timeout = timeout

    def bootstrap(self) -> list[FederationPeer]:
        """Contact all seeds and merge discovered peers into the network.

        Each seed itself is added as a peer, along with every peer the
        seed reports knowing. Existing peers and this server itself are
        never re-added (deduplication + loop protection).

        Returns:
            The list of peers newly added by this bootstrap run.
        """
        known = {p.server_id for p in self._discovery.list_peers()}
        newly: dict[str, FederationPeer] = {}

        for seed in self._seeds:
            candidates = [self._seed_as_peer(seed)]
            candidates.extend(self._fetch_peer_list(seed))
            for peer in candidates:
                if peer.server_id == self._discovery.server_id:
                    continue
                if peer.server_id in known:
                    continue
                known.add(peer.server_id)
                self._discovery.add_peer(peer.server_id, peer.endpoint_url, peer.trust_score)
                newly[peer.server_id] = peer

        return list(newly.values())

    def _seed_as_peer(self, seed: BootstrapSeed) -> FederationPeer:
        """View a seed as a :class:`FederationPeer`."""
        return FederationPeer(
            server_id=seed.server_id,
            endpoint_url=seed.endpoint_url.rstrip("/"),
        )

    def _fetch_peer_list(self, seed: BootstrapSeed) -> list[FederationPeer]:
        """Fetch the peer list a seed knows about (empty list on error)."""
        url = f"{seed.endpoint_url.rstrip('/')}{PEERS_ENDPOINT_PATH}"
        try:
            response = httpx.get(url, timeout=self._timeout)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError):
            return []
        if not isinstance(data, dict):
            return []

        peers: list[FederationPeer] = []
        for item in data.get("peers", []):
            if not isinstance(item, dict):
                continue
            try:
                peers.append(
                    FederationPeer(
                        server_id=str(item["server_id"]),
                        endpoint_url=str(item["endpoint_url"]).rstrip("/"),
                        trust_score=float(item.get("trust_score", 50.0)),
                        healthy=bool(item.get("healthy", True)),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return peers


__all__ = [
    "BootstrapClient",
    "BootstrapSeed",
    "DEFAULT_BOOTSTRAP_TIMEOUT",
    "PEERS_ENDPOINT_PATH",
    "parse_srv_seeds",
]
