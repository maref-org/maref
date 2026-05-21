from __future__ import annotations

from maref.recursive.signed_agent_cards import (
    AgentCardSignature,
    AgentCardSigner,
    SignedAgentCard,
    SignedAgentCardStore,
)
from maref.recursive.unified_audit import UnifiedAuditStore


class TestAgentCardSignature:
    def test_create_signature(self) -> None:
        sig = AgentCardSignature(
            signature_id="sig_1",
            agent_id="agent_1",
            public_key_fingerprint="fp_1234",
            signed_at=1000.0,
            expires_at=2000.0,
        )
        assert sig.signature_id == "sig_1"
        assert sig.agent_id == "agent_1"
        assert sig.verified is False

    def test_verify_signature(self) -> None:
        sig = AgentCardSignature(
            signature_id="sig_1",
            agent_id="agent_1",
            public_key_fingerprint="fp_1234",
            signed_at=1000.0,
            expires_at=9999999999.0,
            card_hash="abc123",
        )
        card_data = {"agent_name": "test", "version": "1.0"}
        import hashlib
        import json
        computed = hashlib.sha256(json.dumps(card_data, sort_keys=True).encode()).hexdigest()
        sig.card_hash = computed
        sig.verify("pub_key_pem", card_data)
        assert sig.verified is True


class TestSignedAgentCard:
    def test_create_card(self) -> None:
        card = SignedAgentCard(
            card_id="card_1",
            agent_id="agent_1",
            agent_name="Test Agent",
            capabilities=["search", "compute"],
            trust_score=0.8,
        )
        assert card.card_id == "card_1"
        assert card.agent_name == "Test Agent"
        assert len(card.capabilities) == 2

    def test_is_valid(self) -> None:
        card = SignedAgentCard(
            card_id="card_1",
            agent_id="agent_1",
            agent_name="Test",
        )
        assert card.is_valid() is True

    def test_expired_card(self) -> None:
        import time
        card = SignedAgentCard(
            card_id="card_1",
            agent_id="agent_1",
            agent_name="Expired",
            expires_at=time.time() - 1000,
        )
        assert card.is_valid() is False

    def test_to_card_data(self) -> None:
        card = SignedAgentCard(
            card_id="card_1",
            agent_id="agent_1",
            agent_name="Test",
            capabilities=["c1"],
        )
        data = card.to_card_data()
        assert data["card_id"] == "card_1"
        assert data["capabilities"] == ["c1"]

    def test_to_audit_record(self) -> None:
        card = SignedAgentCard(
            card_id="card_1",
            agent_id="agent_1",
            agent_name="Test",
        )
        record = card.to_audit_record(round_num=36)
        assert record.event_type == "signed_agent_card"


class TestAgentCardSigner:
    def setup_method(self) -> None:
        self.signer = AgentCardSigner()

    def test_register_key(self) -> None:
        self.signer.register_key("agent_1", "pub_key_pem_123")
        assert self.signer.has_key("agent_1")

    def test_has_key_false(self) -> None:
        assert self.signer.has_key("unknown") is False

    def test_sign_card(self) -> None:
        self.signer.register_key("agent_1", "pub_key")
        card = SignedAgentCard(
            card_id="card_1",
            agent_id="agent_1",
            agent_name="Test",
        )
        sig = self.signer.sign_card(card, "private_key")
        assert sig.agent_id == "agent_1"
        assert sig.card_hash != ""
        assert len(card.signatures) >= 1

    def test_verify_card(self) -> None:
        self.signer.register_key("agent_1", "pub_key")
        card = SignedAgentCard(
            card_id="card_1",
            agent_id="agent_1",
            agent_name="Test",
        )
        self.signer.sign_card(card, "private_key")
        assert self.signer.verify_card(card)


class TestSignedAgentCardStore:
    def setup_method(self) -> None:
        self.store = SignedAgentCardStore()

    def test_register_card(self) -> None:
        card = SignedAgentCard(
            card_id="card_1",
            agent_id="agent_1",
            agent_name="Test",
        )
        self.store.register(card)
        assert self.store.card_count == 1

    def test_get_card(self) -> None:
        card = SignedAgentCard(
            card_id="card_1",
            agent_id="agent_1",
            agent_name="Test",
        )
        self.store.register(card)
        retrieved = self.store.get_card("card_1")
        assert retrieved is not None
        assert retrieved.card_id == "card_1"

    def test_get_card_not_found(self) -> None:
        assert self.store.get_card("nonexistent") is None

    def test_get_agent_cards(self) -> None:
        card1 = SignedAgentCard(card_id="c1", agent_id="agent_1", agent_name="A1")
        card2 = SignedAgentCard(card_id="c2", agent_id="agent_1", agent_name="A2")
        self.store.register(card1)
        self.store.register(card2)
        cards = self.store.get_agent_cards("agent_1")
        assert len(cards) == 2

    def test_get_valid_cards(self) -> None:
        card = SignedAgentCard(card_id="c1", agent_id="agent_1", agent_name="Valid")
        self.store.register(card)
        valid = self.store.get_valid_cards()
        assert len(valid) >= 1

    def test_revoke_card(self) -> None:
        card = SignedAgentCard(card_id="c1", agent_id="agent_1", agent_name="Revoked")
        self.store.register(card)
        self.store.revoke_card("c1")
        retrieved = self.store.get_card("c1")
        assert retrieved is not None
        assert retrieved.is_valid() is False

    def test_valid_count(self) -> None:
        card = SignedAgentCard(card_id="c1", agent_id="agent_1", agent_name="Test")
        self.store.register(card)
        assert self.store.valid_count >= 1

    def test_custom_audit_store(self) -> None:
        audit = UnifiedAuditStore()
        store = SignedAgentCardStore(audit_store=audit)
        card = SignedAgentCard(card_id="c1", agent_id="a1", agent_name="Test")
        store.register(card)
        assert audit.count() >= 1

    def test_clear(self) -> None:
        card = SignedAgentCard(card_id="c1", agent_id="a1", agent_name="Test")
        self.store.register(card)
        self.store.clear()
        assert self.store.card_count == 0
