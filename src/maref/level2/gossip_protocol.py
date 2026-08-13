"""Level 2 — Gossip transport prototype (v0.49 P6).

Design source: ``docs/design/gossip-sync.md`` (TP-08 T8.5). Implements an
in-process, multi-node gossip network for propagating member state snapshots
and audit events:

- Random-k peer forwarding per hop (k defaults to 3, per design §2.2).
- Message-level deduplication on ``(kind, origin_org, generation)``.
- TTL bound on propagation (design §2.2).
- CRDT-style merge: ``state_snapshot``/``constitution_amendment`` merge by
  generation (higher wins); ``audit_event`` is append-only.
- Optional Ed25519 signing for authenticity (design §4).

This is a protocol-semantics prototype: nodes run in one process and no real
network transport is used (v0.49 plan R3 mitigation).

Usage::

    from maref.level2.gossip_protocol import GossipMessage, GossipNode

    nodes = [GossipNode(f"node-{i}", fanout=3) for i in range(8)]
    for a, b in zip(nodes, nodes[1:] + nodes[:1]):
        a.add_neighbor(b); b.add_neighbor(a)
    nodes[0].publish_audit_event("acme", {"action": "tool.call"})
    assert all(n.audit_event_count() == 1 for n in nodes)  # converged
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any


class GossipMessageKind(str, Enum):
    """Message kinds from the gossip design (§2.1)."""

    STATE_SNAPSHOT = "state_snapshot"
    AUDIT_EVENT = "audit_event"
    CONSTITUTION_AMENDMENT = "constitution_amendment"


DEFAULT_TTL = 6
DEFAULT_FANOUT = 3


@dataclass
class GossipMessage:
    """A gossip network message (design §2.1)."""

    kind: str
    payload: dict[str, Any]
    origin_org: str
    generation: int = 0
    timestamp: float = 0.0
    ttl: int = DEFAULT_TTL
    signature: str = ""
    signer: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = time.time()
        GossipMessageKind(self.kind)  # validate kind eagerly

    @property
    def message_id(self) -> tuple[str, str, str]:
        """Deduplication identity (§2.2).

        ``state_snapshot`` / ``constitution_amendment`` collapse on
        ``(kind, origin_org, generation)`` (last-writer-wins merge).

        ``audit_event`` is append-only, so generation is *not* a valid
        deduplication key — two distinct events from the same origin with the
        same generation would collapse into one (v0.49 review fix). Audit
        events deduplicate on the *payload digest*: identical re-broadcasts of
        the same event collapse, distinct events are all retained.
        """
        if self.kind == GossipMessageKind.AUDIT_EVENT.value:
            payload_digest = hashlib.sha256(
                json.dumps(self.payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            return (self.kind, self.origin_org, f"audit:{payload_digest}")
        return (self.kind, self.origin_org, str(self.generation))

    def canonical_payload(self) -> bytes:
        """Bytes signed over (excludes signature/signer)."""
        return json.dumps(
            {
                "kind": self.kind,
                "payload": self.payload,
                "origin_org": self.origin_org,
                "generation": self.generation,
                "timestamp": self.timestamp,
                "ttl": self.ttl,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "payload": self.payload,
            "origin_org": self.origin_org,
            "generation": self.generation,
            "timestamp": self.timestamp,
            "ttl": self.ttl,
            "signature": self.signature,
            "signer": self.signer,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GossipMessage:
        return cls(
            kind=data["kind"],
            payload=dict(data.get("payload", {})),
            origin_org=data["origin_org"],
            generation=int(data.get("generation", 0)),
            timestamp=float(data.get("timestamp", 0.0)),
            ttl=int(data.get("ttl", DEFAULT_TTL)),
            signature=data.get("signature", ""),
            signer=data.get("signer", ""),
        )

    def sign(self, signing_key: Any) -> GossipMessage:
        """Ed25519-sign the message; sets signature + signer fingerprint."""
        sig = signing_key.sign(self.canonical_payload())
        self.signature = sig.hex()
        self.signer = signing_key.fingerprint
        return self

    def verify(self, public_key_pem: str) -> bool:
        """Verify the Ed25519 signature against a public key."""
        if not self.signature or not public_key_pem:
            return False
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        try:
            return Ed25519KeyPair.verify(
                public_key_pem,
                bytes.fromhex(self.signature),
                self.canonical_payload(),
            )
        except Exception:
            return False


class GossipNode:
    """A single node in the gossip network.

    Args:
        node_id: Local identifier for diagnostics.
        fanout: Number of random peers to forward to per hop (k, §2.2).
        ttl: Default TTL for messages originating at this node.
        signing_key: Optional Ed25519 key pair; signs outgoing messages.
        trust_store: Optional mapping signer fingerprint → public key PEM;
            when provided, received signed messages are verified (dropped on
            failure). Messages from unknown signers are dropped.
    """

    def __init__(
        self,
        node_id: str,
        fanout: int = DEFAULT_FANOUT,
        ttl: int = DEFAULT_TTL,
        signing_key: Any | None = None,
        trust_store: dict[str, str] | None = None,
    ) -> None:
        self.node_id = node_id
        self._fanout = fanout
        self._default_ttl = ttl
        self._signing_key = signing_key
        self._trust_store = trust_store
        self._neighbors: list[GossipNode] = []
        self._seen: set[tuple[str, str, str]] = set()
        self._state_snapshots: dict[str, dict[str, Any]] = {}
        self._amendments: dict[str, dict[str, Any]] = {}
        self._audit_events: list[dict[str, Any]] = []
        self._received_count = 0

    # ── Topology ─────────────────────────────────────────────────────────

    def add_neighbor(self, peer: GossipNode) -> None:
        if peer is not self and peer not in self._neighbors:
            self._neighbors.append(peer)

    def remove_neighbor(self, peer: GossipNode) -> None:
        if peer in self._neighbors:
            self._neighbors.remove(peer)

    @property
    def neighbor_count(self) -> int:
        return len(self._neighbors)

    def _select_peers(self) -> list[GossipNode]:
        """Randomly select up to ``fanout`` distinct peers (§2.2 random-k)."""
        if self._fanout <= 0 or not self._neighbors:
            return []
        pool = list(self._neighbors)
        k = min(self._fanout, len(pool))
        return random.sample(pool, k)

    # ── Local state accessors ────────────────────────────────────────────

    def audit_event_count(self) -> int:
        return len(self._audit_events)

    def audit_events(self) -> list[dict[str, Any]]:
        return list(self._audit_events)

    def state_snapshot(self, origin_org: str) -> dict[str, Any] | None:
        return self._state_snapshots.get(origin_org)

    def amendment(self, origin_org: str) -> dict[str, Any] | None:
        return self._amendments.get(origin_org)

    @property
    def received_count(self) -> int:
        return self._received_count

    # ── Publishing ───────────────────────────────────────────────────────

    def publish_state_snapshot(
        self, origin_org: str, payload: dict[str, Any], generation: int
    ) -> None:
        """Broadcast a member-state snapshot into the network."""
        self._propagate(
            GossipMessage(
                kind=GossipMessageKind.STATE_SNAPSHOT.value,
                payload=payload,
                origin_org=origin_org,
                generation=generation,
                ttl=self._default_ttl,
            )
        )

    def publish_audit_event(
        self, origin_org: str, payload: dict[str, Any], generation: int = 0
    ) -> None:
        """Broadcast an audit event (append-only semantics).

        ``generation`` is retained for API symmetry but is **not** part of the
        audit-event deduplication identity (dedup is on the payload digest), so
        distinct events from the same origin always propagate (v0.49 review
        fix).
        """
        self._propagate(
            GossipMessage(
                kind=GossipMessageKind.AUDIT_EVENT.value,
                payload=payload,
                origin_org=origin_org,
                generation=generation,
                ttl=self._default_ttl,
            )
        )

    def publish_amendment(self, origin_org: str, payload: dict[str, Any], generation: int) -> None:
        """Broadcast a constitution amendment (generation-merged)."""
        self._propagate(
            GossipMessage(
                kind=GossipMessageKind.CONSTITUTION_AMENDMENT.value,
                payload=payload,
                origin_org=origin_org,
                generation=generation,
                ttl=self._default_ttl,
            )
        )

    # ── Propagation core ─────────────────────────────────────────────────

    def _propagate(self, message: GossipMessage, hops: int = 0) -> None:
        """Deliver + forward a message through the local fanout (§2.2)."""
        if not self._verify_authenticity(message):
            return
        if message.message_id in self._seen:
            return
        self._seen.add(message.message_id)
        self._received_count += 1
        self._merge(message)

        if hops >= message.ttl:
            return  # TTL bound reached
        for peer in self._select_peers():
            peer._propagate(message, hops + 1)

    def _verify_authenticity(self, message: GossipMessage) -> bool:
        """Verify signed messages against the trust store.

        ``trust_store=None`` → authentication disabled (unsigned protocol).
        ``trust_store={...}`` → verification enforced; messages from unknown
        signers are dropped (fail-closed).
        """
        if self._trust_store is None:
            return True
        public_key = self._trust_store.get(message.signer)
        if public_key is None:
            return False  # unknown signer → drop (fail-closed)
        return message.verify(public_key)

    def _merge(self, message: GossipMessage) -> None:
        """CRDT-style merge (§2.3): snapshots/amendments merge by generation;
        audit events are append-only."""
        if message.kind == GossipMessageKind.AUDIT_EVENT.value:
            self._audit_events.append(message.to_dict())
            return
        target = (
            self._state_snapshots
            if message.kind == GossipMessageKind.STATE_SNAPSHOT.value
            else self._amendments
        )
        current = target.get(message.origin_org)
        if current is None or message.generation >= int(current["generation"]):
            target[message.origin_org] = message.to_dict()

    # ── Diagnostics ──────────────────────────────────────────────────────

    def summary(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "neighbors": self.neighbor_count,
            "seen": len(self._seen),
            "audit_events": len(self._audit_events),
            "snapshots": len(self._state_snapshots),
            "amendments": len(self._amendments),
        }


def build_ring(n: int, fanout: int = DEFAULT_FANOUT, **kwargs: Any) -> list[GossipNode]:
    """Build a ring-topology gossip network of ``n`` nodes (convenience)."""
    nodes = [GossipNode(f"node-{i}", fanout=fanout, **kwargs) for i in range(n)]
    for i, node in enumerate(nodes):
        node.add_neighbor(nodes[(i - 1) % n])
        node.add_neighbor(nodes[(i + 1) % n])
    return nodes


__all__ = [
    "DEFAULT_FANOUT",
    "DEFAULT_TTL",
    "GossipMessage",
    "GossipMessageKind",
    "GossipNode",
    "build_ring",
]
