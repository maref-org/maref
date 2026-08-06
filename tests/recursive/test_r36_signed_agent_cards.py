from __future__ import annotations

import hashlib
import json

from maref.crypto.ed25519_keys import Ed25519KeyPair
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

    def test_verify_legacy_signature(self) -> None:
        """Legacy ed25519-sim mode: SHA-256 hash comparison (explicit opt-in)."""
        sig = AgentCardSignature(
            signature_id="sig_1",
            agent_id="agent_1",
            public_key_fingerprint="fp_1234",
            signed_at=1000.0,
            expires_at=9999999999.0,
            algorithm="ed25519-sim",
            card_hash="abc123",
        )
        card_data = {"agent_name": "test", "version": "1.0"}
        computed = hashlib.sha256(json.dumps(card_data, sort_keys=True).encode()).hexdigest()
        sig.card_hash = computed
        sig.verify("pub_key_pem", card_data, allow_legacy_sim=True)
        assert sig.verified is True

    def test_verify_legacy_sim_rejected_by_default(self) -> None:
        """ed25519-sim 默认不可信：未显式开启 legacy 兼容时拒绝。

        这是修复"免费签名验证"漏洞的回归测试——攻击者只要算出 card_hash
        就能伪造 ed25519-sim 签名通过验证，默认路径必须拒绝。
        """
        sig = AgentCardSignature(
            signature_id="sig_forged",
            agent_id="agent_1",
            public_key_fingerprint="fp_1234",
            signed_at=1000.0,
            expires_at=9999999999.0,
            algorithm="ed25519-sim",
            card_hash="",
        )
        card_data = {"agent_name": "evil", "version": "1.0"}
        computed = hashlib.sha256(json.dumps(card_data, sort_keys=True).encode()).hexdigest()
        sig.card_hash = computed  # 攻击者已知的 card_hash
        assert sig.verify("pub_key_pem", card_data) is False
        assert sig.verified is False

    def test_verify_ed25519_signature(self) -> None:
        """Real Ed25519 signature verification."""
        key_pair = Ed25519KeyPair.generate()
        card_data = {"agent_name": "test", "version": "1.0"}
        card_hash = hashlib.sha256(
            json.dumps(card_data, sort_keys=True).encode()
        ).hexdigest()
        signature_bytes = key_pair.sign(card_hash.encode())

        sig = AgentCardSignature(
            signature_id="sig_1",
            agent_id="agent_1",
            public_key_fingerprint=key_pair.fingerprint,
            signed_at=1000.0,
            expires_at=9999999999.0,
            algorithm="ed25519",
            signature_value=signature_bytes.hex(),
            card_hash=card_hash,
        )
        assert sig.verify(key_pair.public_key_pem, card_data) is True
        assert sig.verified is True

    def test_verify_ed25519_rejects_tampered_card(self) -> None:
        """Ed25519 verification fails on tampered card data."""
        key_pair = Ed25519KeyPair.generate()
        card_data = {"agent_name": "test", "version": "1.0"}
        card_hash = hashlib.sha256(
            json.dumps(card_data, sort_keys=True).encode()
        ).hexdigest()
        signature_bytes = key_pair.sign(card_hash.encode())

        sig = AgentCardSignature(
            signature_id="sig_1",
            agent_id="agent_1",
            public_key_fingerprint=key_pair.fingerprint,
            signed_at=1000.0,
            expires_at=9999999999.0,
            algorithm="ed25519",
            signature_value=signature_bytes.hex(),
            card_hash=card_hash,
        )
        tampered_data = {"agent_name": "evil", "version": "1.0"}
        assert sig.verify(key_pair.public_key_pem, tampered_data) is False
        assert sig.verified is False


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
        # Use legacy mode for existing tests that pass plain-string keys.
        self.signer = AgentCardSigner(legacy_mode=True)

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
        assert sig.algorithm == "ed25519-sim"
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


class TestAgentCardSignerEd25519:
    """Tests for real Ed25519 signing (default mode)."""

    def test_sign_card_ed25519(self) -> None:
        signer = AgentCardSigner()  # Default: Ed25519 mode
        key_pair = Ed25519KeyPair.generate()
        signer.register_key("agent_1", key_pair.public_key_pem)

        card = SignedAgentCard(
            card_id="card_1",
            agent_id="agent_1",
            agent_name="Test",
        )
        sig = signer.sign_card(card, key_pair.private_key_pem)
        assert sig.agent_id == "agent_1"
        assert sig.algorithm == "ed25519"
        assert sig.card_hash != ""
        assert len(sig.signature_value) == 128  # 64 bytes hex = 128 chars
        assert len(card.signatures) >= 1

    def test_verify_card_ed25519(self) -> None:
        signer = AgentCardSigner()
        key_pair = Ed25519KeyPair.generate()
        signer.register_key("agent_1", key_pair.public_key_pem)

        card = SignedAgentCard(
            card_id="card_1",
            agent_id="agent_1",
            agent_name="Test",
        )
        signer.sign_card(card, key_pair.private_key_pem)
        assert signer.verify_card(card) is True

    def test_default_signer_rejects_forged_ed25519_sim(self) -> None:
        """默认（非 legacy）signer 拒绝伪造的 ed25519-sim 签名。

        漏洞回归：ed25519-sim 只要 card_hash 匹配即可通过，默认模式必须拒绝。
        """
        import hashlib
        import json

        signer = AgentCardSigner()  # 默认 Ed25519 模式
        key_pair = Ed25519KeyPair.generate()
        signer.register_key("agent_1", key_pair.public_key_pem)

        card = SignedAgentCard(
            card_id="card_forged",
            agent_id="agent_1",
            agent_name="Evil",
        )
        card_hash = hashlib.sha256(
            json.dumps(card.to_card_data(), sort_keys=True).encode()
        ).hexdigest()
        forged = AgentCardSignature(
            signature_id="sig_forged",
            agent_id="agent_1",
            public_key_fingerprint="fp_1234",
            signed_at=1000.0,
            expires_at=9999999999.0,
            algorithm="ed25519-sim",
            card_hash=card_hash,
        )
        card.signatures.append(forged)
        # 未显式开启 legacy 模式时，伪造 sim 卡验证失败。
        assert signer.verify_card(card) is False

    def test_ed25519_rejects_wrong_public_key(self) -> None:
        """Verification fails when the wrong public key is registered."""
        signer = AgentCardSigner()
        signing_key = Ed25519KeyPair.generate()
        wrong_key = Ed25519KeyPair.generate()
        signer.register_key("agent_1", wrong_key.public_key_pem)

        card = SignedAgentCard(
            card_id="card_1",
            agent_id="agent_1",
            agent_name="Test",
        )
        signer.sign_card(card, signing_key.private_key_pem)
        assert signer.verify_card(card) is False

    def test_ed25519_rejects_tampered_card(self) -> None:
        """Verification fails when card data is modified after signing."""
        signer = AgentCardSigner()
        key_pair = Ed25519KeyPair.generate()
        signer.register_key("agent_1", key_pair.public_key_pem)

        card = SignedAgentCard(
            card_id="card_1",
            agent_id="agent_1",
            agent_name="Original",
        )
        signer.sign_card(card, key_pair.private_key_pem)
        # Tamper with the card after signing.
        card.agent_name = "Tampered"
        assert signer.verify_card(card) is False


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
