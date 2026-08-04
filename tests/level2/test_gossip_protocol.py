"""v0.49 P6 — Gossip transport prototype: propagation, dedup, TTL, merge, auth.

Acceptance: events propagate to all nodes in a ring; duplicates collapse;
state snapshots merge by generation (higher wins); audit events append;
TTL bounds reach; signed messages are authenticated against a trust store.
"""

from __future__ import annotations

from maref.crypto.ed25519_keys import Ed25519KeyPair
from maref.level2.gossip_protocol import (
    GossipMessage,
    GossipMessageKind,
    build_ring,
)


class TestPropagation:
    def test_audit_event_reaches_all_nodes(self) -> None:
        nodes = build_ring(8, fanout=3)
        nodes[0].publish_audit_event("did:maref:org:acme:7f3a", {"action": "tool.call"})
        for node in nodes:
            assert node.audit_event_count() == 1
            assert node.audit_events()[0]["payload"]["action"] == "tool.call"

    def test_duplicate_publish_is_deduplicated(self) -> None:
        nodes = build_ring(6, fanout=2)
        msg = GossipMessage(
            kind=GossipMessageKind.AUDIT_EVENT.value,
            payload={"action": "x"},
            origin_org="acme",
            generation=3,
            ttl=6,
        )
        nodes[0]._propagate(msg)
        nodes[0]._propagate(msg)  # same (kind, origin, generation) → dropped
        for node in nodes:
            assert node.audit_event_count() == 1

    def test_ttl_bounds_propagation(self) -> None:
        nodes = build_ring(6, fanout=2)
        # TTL=1: only the source (hop 0) and its direct fanout peers (hop 1)
        # receive the message; nothing propagates further.
        nodes[0]._propagate(
            GossipMessage(
                kind=GossipMessageKind.AUDIT_EVENT.value,
                payload={"action": "x"},
                origin_org="acme",
                generation=1,
                ttl=1,
            )
        )
        assert nodes[0].audit_event_count() == 1
        # nodes[0] neighbors in the ring: node-5 and node-1
        for idx in (1, 5):
            assert nodes[idx].audit_event_count() == 1
        # two hops away: nothing received
        for idx in (2, 3, 4):
            assert nodes[idx].audit_event_count() == 0


class TestMerge:
    def test_state_snapshot_higher_generation_wins(self) -> None:
        nodes = build_ring(6, fanout=3)
        nodes[0].publish_state_snapshot("acme", {"state": "v1"}, generation=1)
        nodes[0].publish_state_snapshot("acme", {"state": "v2"}, generation=2)
        for node in nodes:
            snap = node.state_snapshot("acme")
            assert snap is not None
            assert snap["payload"]["state"] == "v2"
            assert snap["generation"] == 2

    def test_older_generation_does_not_overwrite(self) -> None:
        nodes = build_ring(6, fanout=3)
        nodes[0].publish_state_snapshot("acme", {"state": "v2"}, generation=2)
        nodes[0].publish_state_snapshot("acme", {"state": "v1"}, generation=1)
        for node in nodes:
            snap = node.state_snapshot("acme")
            assert snap["payload"]["state"] == "v2"

    def test_audit_events_are_append_only(self) -> None:
        nodes = build_ring(5, fanout=2)
        nodes[0].publish_audit_event("acme", {"n": 1}, generation=1)
        nodes[0].publish_audit_event("acme", {"n": 2}, generation=2)
        for node in nodes:
            gens = {e["generation"] for e in node.audit_events()}
            assert gens == {1, 2}

    def test_consecutive_audit_events_with_default_generation_retained(self) -> None:
        """Review regression: distinct audit events from the same origin with
        the same (default) generation must all propagate — audit dedup is on
        the payload digest, not on generation."""
        nodes = build_ring(5, fanout=2)
        nodes[0].publish_audit_event("acme", {"n": 1})
        nodes[0].publish_audit_event("acme", {"n": 2})
        for node in nodes:
            events = node.audit_events()
            assert len(events) == 2
            assert {e["payload"]["n"] for e in events} == {1, 2}


class TestAuthenticity:
    def test_signed_message_verified(self) -> None:
        signer = Ed25519KeyPair.generate()
        nodes = build_ring(
            6,
            fanout=3,
            trust_store={signer.fingerprint: signer.public_key_pem},
        )
        msg = GossipMessage(
            kind=GossipMessageKind.AUDIT_EVENT.value,
            payload={"action": "x"},
            origin_org="acme",
            generation=1,
        ).sign(signer)
        nodes[0]._propagate(msg)
        for node in nodes:
            assert node.audit_event_count() == 1

    def test_unknown_signer_dropped(self) -> None:
        signer = Ed25519KeyPair.generate()
        nodes = build_ring(4, fanout=2, trust_store={})  # empty trust store
        msg = GossipMessage(
            kind=GossipMessageKind.AUDIT_EVENT.value,
            payload={"action": "x"},
            origin_org="acme",
            generation=1,
        ).sign(signer)
        nodes[0]._propagate(msg)
        assert nodes[0].audit_event_count() == 0

    def test_tampered_signed_message_dropped(self) -> None:
        signer = Ed25519KeyPair.generate()
        nodes = build_ring(
            5,
            fanout=2,
            trust_store={signer.fingerprint: signer.public_key_pem},
        )
        msg = GossipMessage(
            kind=GossipMessageKind.STATE_SNAPSHOT.value,
            payload={"state": "clean"},
            origin_org="acme",
            generation=1,
        ).sign(signer)
        msg.payload = {"state": "tampered"}  # tamper after signing
        nodes[0]._propagate(msg)
        assert nodes[0].state_snapshot("acme") is None

    def test_message_round_trip_serialization(self) -> None:
        signer = Ed25519KeyPair.generate()
        msg = GossipMessage(
            kind=GossipMessageKind.AUDIT_EVENT.value,
            payload={"action": "x"},
            origin_org="acme",
            generation=7,
            ttl=4,
        ).sign(signer)
        restored = GossipMessage.from_dict(msg.to_dict())
        assert restored == msg
        assert restored.verify(signer.public_key_pem) is True
