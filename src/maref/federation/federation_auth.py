"""Federated HTTP transport hardening (v0.47 S1/S2).

S1 — request authentication:
    :class:`FederationRequestSigner` / :class:`FederationRequestVerifier`
    provide Ed25519 request signing for the federated HTTP transport.
    A client signs ``timestamp\\nmethod\\npath\\nbody_hash`` with its private
    key; the server verifies the signature against a configured set of
    trusted peer public keys (``key_id`` → public key PEM).  Timestamps are
    checked against a configurable skew window to prevent replay.

    The scheme is deliberately additive: when no verifier is configured the
    transport keeps its historical behaviour (backward compatible), so
    existing in-process / localhost E2E stacks are unaffected.

S2 — SSRF protection:
    :func:`validate_peer_url` rejects peer URLs that resolve to loopback,
    link-local, private, reserved, multicast or unspecified addresses
    (including IPv4-mapped IPv6), unless the host is explicitly whitelisted
    through ``allowed_hosts``.
"""

from __future__ import annotations

import hashlib
import ipaddress
import socket
import time
from collections.abc import Mapping

from maref.signing.signing_key import ReportSigningKey

_AUTH_HEADER = "X-MAREF-Fed-Auth"
_BODY_HASH_HEADER = "X-MAREF-Fed-Body-Hash"
_DEFAULT_MAX_SKEW_SECONDS = 300.0

# Subnets that must never be reachable from a server-side fetch.
_BLOCKED_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
)


def _signing_payload(timestamp: int, method: str, path: str, body_bytes: bytes) -> bytes:
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    return f"{timestamp}\n{method}\n{path}\n{body_hash}".encode()


class FederationRequestSigner:
    """Signs outbound federation HTTP requests with an Ed25519 key.

    Args:
        key: The local server's :class:`ReportSigningKey`.
        key_id: Identifier the peer uses to look up the public key
            (usually the server_id / org id).
    """

    def __init__(self, key: ReportSigningKey, key_id: str) -> None:
        self._key = key
        self._key_id = key_id

    def sign(
        self,
        method: str,
        path: str,
        body_bytes: bytes,
        timestamp: int | None = None,
    ) -> dict[str, str]:
        """Return the ``X-MAREF-Fed-*`` headers for the request."""
        ts = int(time.time()) if timestamp is None else timestamp
        payload = _signing_payload(ts, method, path, body_bytes)
        signature = self._key.sign_report(payload)
        return {
            _AUTH_HEADER: f"{self._key_id}:{ts}:{signature}",
            _BODY_HASH_HEADER: hashlib.sha256(body_bytes).hexdigest(),
        }


class FederationRequestVerifier:
    """Verifies inbound federation HTTP request signatures (fail-closed).

    Args:
        public_keys: Mapping of ``key_id`` → Ed25519 public key PEM for
            every peer this server is willing to accept requests from.
        max_skew_seconds: Maximum acceptable age of the request timestamp
            (replay protection).
    """

    def __init__(
        self,
        public_keys: Mapping[str, str],
        max_skew_seconds: float = _DEFAULT_MAX_SKEW_SECONDS,
    ) -> None:
        self._public_keys = dict(public_keys)
        self._max_skew = max_skew_seconds

    @property
    def trusted_key_ids(self) -> set[str]:
        return set(self._public_keys)

    def verify(
        self,
        *,
        method: str,
        path: str,
        body_bytes: bytes,
        auth_header: str | None,
        body_hash_header: str | None = None,
        now: float | None = None,
    ) -> bool:
        """Return True only if the request carries a valid signature.

        Never raises — a malformed or unsigned request simply fails closed.
        """
        if not auth_header:
            return False
        try:
            key_id, ts_str, signature_b64 = auth_header.split(":", 2)
        except ValueError:
            return False
        public_key_pem = self._public_keys.get(key_id)
        if public_key_pem is None:
            return False
        try:
            timestamp = int(ts_str)
        except ValueError:
            return False
        current = time.time() if now is None else now
        if abs(current - timestamp) > self._max_skew:
            return False
        if body_hash_header is not None:
            if body_hash_header != hashlib.sha256(body_bytes).hexdigest():
                return False
        payload = _signing_payload(timestamp, method, path, body_bytes)
        return ReportSigningKey.verify_signature(public_key_pem, signature_b64, payload)


def _host_is_blocked(host: str, allowed_hosts: set[str]) -> bool:
    """Return True if *any* resolved address of ``host`` is blocked."""
    if host in allowed_hosts:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # Unresolvable hosts cannot be fetched — treat as safe-to-block.
        return True
    for info in infos:
        try:
            host_ip = str(info[4][0]).split("%")[0]
            address = ipaddress.ip_address(host_ip)
        except ValueError:
            return True
        if address.is_private or address.is_loopback or address.is_link_local:
            return True
        if address.is_multicast or address.is_unspecified or address.is_reserved:
            return True
        for net in _BLOCKED_NETWORKS:
            if address in net:
                return True
    return False


def validate_peer_url(peer_url: str, allowed_hosts: set[str] | None = None) -> str | None:
    """Return an error message if ``peer_url`` is unsafe, else None.

    Args:
        peer_url: The ``peer_url`` supplied to ``settlement/reconcile``.
        allowed_hosts: Optional set of hostnames/IPs explicitly permitted
            (e.g. the local loopback in single-node deployments).

    Returns:
        A human-readable rejection reason, or None when the URL is safe.
    """
    from urllib.parse import urlparse

    allowed = set(allowed_hosts or ())
    try:
        parsed = urlparse(peer_url)
    except (ValueError, TypeError):
        return "invalid peer_url"
    if parsed.scheme not in ("http", "https"):
        return f"unsupported scheme: {parsed.scheme!r}"
    host = parsed.hostname
    if not host:
        return "peer_url has no hostname"
    if _host_is_blocked(host, allowed):
        return f"peer host blocked: {host}"
    return None


__all__ = [
    "FederationRequestSigner",
    "FederationRequestVerifier",
    "validate_peer_url",
]
