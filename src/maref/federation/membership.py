"""Node heartbeat + membership management for the MAREF agent internet (Phase 3.1).

:class:`MembershipManager` keeps the federation's membership table alive
over real HTTP by reusing :class:`~maref.federation.health_monitor.FederationHealthMonitor`
(so the Phase 2.5 cascade-breaker linkage applies to whole servers, not
just agents):

* **Heartbeat registration** — :meth:`receive_heartbeat` records a peer's
  liveness (``probe``) and auto-registers unknown peers into the local
  :class:`~maref.federation.discovery.FederatedDiscovery` table, so a new
  server is self-healing: announcing once makes it reachable from now on.
* **Heartbeat broadcast** — :meth:`announce` / :meth:`announce_to_all`
  push our liveness to one peer / all known peers over HTTP.
* **Silence detection** — :meth:`run_check` delegates to the health
  monitor; a server that stops beating is suspected (and, via the
  cascade breaker, isolated + its dependents degraded).

Heartbeats carry a ``generation`` counter so an operator can tell apart
a restarted instance from a long-lived one; the latest seen generation
per member is exposed in :meth:`members_summary`.
"""

from __future__ import annotations

import hmac
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from maref.federation.discovery import FederatedDiscovery, FederationPeer
from maref.federation.health_monitor import (
    FederationHealthMonitor,
    HealthCheckResult,
)

#: HTTP path receiving heartbeats (see federation_http.py).
HEARTBEAT_ENDPOINT_PATH = "/api/v1/federation/network/heartbeat"

DEFAULT_HEARTBEAT_INTERVAL = 30.0
DEFAULT_HEARTBEAT_TIMEOUT = 5.0


@dataclass
class HeartbeatMessage:
    """A liveness announcement from one federation server.

    Attributes:
        server_id: Sender's identifier.
        endpoint_url: Sender's base URL (used for auto-registration).
        generation: Instance generation — incremented on restart so a new
            instance can be told apart from a stale heartbeat.
        timestamp: When the heartbeat was emitted (epoch seconds).
    """

    server_id: str
    endpoint_url: str
    generation: int = 0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "endpoint_url": self.endpoint_url,
            "generation": self.generation,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HeartbeatMessage:
        return cls(
            server_id=str(data["server_id"]),
            endpoint_url=str(data["endpoint_url"]),
            generation=int(data.get("generation", 0)),
            timestamp=float(data.get("timestamp", time.time())),
        )


class MembershipManager:
    """Manage federation membership via HTTP heartbeats + health tracking.

    Args:
        server_id: Identifier of this server.
        endpoint_url: Base URL this server is reachable at (announced
            to peers in every heartbeat).
        health_monitor: The :class:`FederationHealthMonitor` tracking
            member liveness (silence → suspicion → cascade linkage).
        discovery: Optional :class:`FederatedDiscovery` — unknown peers
            announcing themselves are auto-registered here.
        timeout: Per-request HTTP timeout in seconds.
        generation: Instance generation of this server.
    """

    def __init__(
        self,
        server_id: str,
        endpoint_url: str,
        health_monitor: FederationHealthMonitor,
        discovery: FederatedDiscovery | None = None,
        timeout: float = DEFAULT_HEARTBEAT_TIMEOUT,
        generation: int = 0,
        allowed_heartbeat_servers: set[str] | None = None,
        heartbeat_token: str | None = None,
        audit_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._server_id = server_id
        self._endpoint_url = endpoint_url.rstrip("/")
        self._health_monitor = health_monitor
        self._discovery = discovery
        self._timeout = timeout
        self._generation = generation
        # Latest seen instance generation per member server id.
        self._generations: dict[str, int] = {}
        # v0.50 W2-S1 (F12): optional identity enforcement.
        # When configured, unknown server ids are rejected instead of
        # auto-registered, and a shared heartbeat token is required.
        self._allowed_heartbeat_servers: set[str] | None = (
            set(allowed_heartbeat_servers) if allowed_heartbeat_servers else None
        )
        self._heartbeat_token: str | None = heartbeat_token
        self._audit_sink: Callable[[dict[str, Any]], None] | None = audit_sink

    def set_audit_sink(self, sink: Callable[[dict[str, Any]], None]) -> None:
        """Install an audit callback for heartbeat auth events."""
        self._audit_sink = sink

    def _emit_audit(self, record: dict[str, Any]) -> None:
        if self._audit_sink is not None:
            try:
                self._audit_sink(record)
            except Exception:
                pass

    def _heartbeat_authorized(self, message: HeartbeatMessage, token: str | None) -> bool:
        """Enforce heartbeat identity: whitelist + optional shared token.

        Returns True when the heartbeat is authorized. Emits an
        ``unauthorized_heartbeat`` audit record on rejection and an
        ``unsecured_heartbeat`` warning when no enforcement is configured.
        """
        if (
            self._allowed_heartbeat_servers is not None
            and message.server_id not in self._allowed_heartbeat_servers
        ):
            self._emit_audit(
                {
                    "event_type": "unauthorized_heartbeat",
                    "server_id": message.server_id,
                    "endpoint_url": message.endpoint_url,
                    "reason": "server_id_not_in_whitelist",
                    "timestamp": time.time(),
                }
            )
            return False

        if self._heartbeat_token is not None:
            if token is None or not hmac.compare_digest(self._heartbeat_token, token):
                self._emit_audit(
                    {
                        "event_type": "unauthorized_heartbeat",
                        "server_id": message.server_id,
                        "reason": "invalid_heartbeat_token",
                        "timestamp": time.time(),
                    }
                )
                return False

        if self._allowed_heartbeat_servers is None and self._heartbeat_token is None:
            self._emit_audit(
                {
                    "event_type": "unsecured_heartbeat",
                    "server_id": message.server_id,
                    "reason": "no_heartbeat_auth_configured",
                    "timestamp": time.time(),
                }
            )
        return True

    @property
    def server_id(self) -> str:
        return self._server_id

    @property
    def member_count(self) -> int:
        """Number of tracked members (including ourselves when probed)."""
        return len(self._health_monitor.member_snapshots())

    def receive_heartbeat(self, message: HeartbeatMessage, token: str | None = None) -> bool:
        """Record a peer's heartbeat; auto-register unknown peers.

        A heartbeat from our own server id is ignored (echo loop
        protection). The peer's liveness is refreshed via ``probe`` and,
        when a :class:`FederatedDiscovery` is attached, an unknown peer is
        added to the peer table so future queries can reach it.

        v0.50 W2-S1 (F12): heartbeat identity is enforced when configured —
        unknown server ids are rejected instead of auto-registered, and a
        shared ``heartbeat_token`` is required when set.

        Returns:
            True if the heartbeat was accepted, False if ignored (self-echo)
            or rejected by identity enforcement.
        """
        if message.server_id == self._server_id:
            return False
        if not self._heartbeat_authorized(message, token):
            return False
        self._generations[message.server_id] = max(
            self._generations.get(message.server_id, 0), message.generation
        )
        self._health_monitor.probe(message.server_id)
        if self._discovery is not None:
            known = {p.server_id for p in self._discovery.list_peers()}
            if message.server_id not in known:
                self._discovery.add_peer(message.server_id, message.endpoint_url)
        return True

    def announce(self, peer: FederationPeer) -> bool:
        """Send our heartbeat to one peer over HTTP.

        Updates the peer's ``last_contact`` / ``healthy`` flags so the
        discovery layer skips unresponsive peers.

        Returns:
            True if the peer accepted the heartbeat, False on any error.
        """
        message = HeartbeatMessage(
            server_id=self._server_id,
            endpoint_url=self._endpoint_url,
            generation=self._generation,
        )
        url = f"{peer.endpoint_url.rstrip('/')}{HEARTBEAT_ENDPOINT_PATH}"
        headers = {}
        if self._heartbeat_token is not None:
            headers["X-MAREF-HB-Token"] = self._heartbeat_token
        try:
            response = httpx.post(
                url, json=message.to_dict(), headers=headers, timeout=self._timeout
            )
            response.raise_for_status()
            peer.last_contact = time.time()
            peer.healthy = True
            return True
        except httpx.HTTPError:
            peer.healthy = False
            return False

    def announce_to_all(self) -> dict[str, bool]:
        """Broadcast heartbeats to every known peer.

        Returns:
            A mapping ``{peer_server_id: accepted}``.
        """
        peers = self._discovery.list_peers() if self._discovery is not None else []
        return {p.server_id: self.announce(p) for p in peers}

    def run_check(self) -> HealthCheckResult:
        """Run the silence check over all tracked members (→ cascade linkage)."""
        return self._health_monitor.check()

    def members_summary(self) -> dict[str, dict[str, Any]]:
        """Return the membership table: member id → health snapshot + generation."""
        summary: dict[str, dict[str, Any]] = {}
        for member_id, snapshot in self._health_monitor.member_snapshots().items():
            snapshot["generation"] = self._generations.get(member_id, 0)
            summary[member_id] = snapshot
        return summary

    def health_summary(self) -> dict[str, Any]:
        """Aggregate health counters for observability endpoints."""
        base = self._health_monitor.summary()
        return {
            "server_id": self._server_id,
            "member_count": self.member_count,
            "active": base["active"],
            "suspected": base["suspected"],
            "silent": base["silent"],
        }


__all__ = [
    "DEFAULT_HEARTBEAT_INTERVAL",
    "DEFAULT_HEARTBEAT_TIMEOUT",
    "HEARTBEAT_ENDPOINT_PATH",
    "HeartbeatMessage",
    "MembershipManager",
]
