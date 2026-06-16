from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from maref.recursive.unified_audit import UnifiedAuditRecord, UnifiedAuditStore, make_record_id


@dataclass
class AgentCardSignature:
    signature_id: str
    agent_id: str
    public_key_fingerprint: str
    signed_at: float
    expires_at: float
    algorithm: str = "ed25519"
    signature_value: str = ""
    card_hash: str = ""
    verified: bool = False

    def verify(self, public_key_pem: str, card_data: dict[str, Any]) -> bool:
        computed_hash = hashlib.sha256(json.dumps(card_data, sort_keys=True).encode()).hexdigest()
        match = computed_hash == self.card_hash
        self.verified = match and (time.time() < self.expires_at)
        return self.verified


@dataclass
class SignedAgentCard:
    card_id: str
    agent_id: str
    agent_name: str
    capabilities: list[str] = field(default_factory=list)
    endpoints: list[str] = field(default_factory=list)
    trust_score: float = 0.0
    version: str = "1.0.0"
    signatures: list[AgentCardSignature] = field(default_factory=list)
    issued_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 86400 * 30)
    did_reference: str = ""

    def to_card_data(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "capabilities": self.capabilities,
            "endpoints": self.endpoints,
            "trust_score": self.trust_score,
            "version": self.version,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "did_reference": self.did_reference,
        }

    def is_valid(self) -> bool:
        return time.time() < self.expires_at and all(s.verified for s in self.signatures)

    def to_audit_record(self, round_num: int = 36) -> UnifiedAuditRecord:
        return UnifiedAuditRecord(
            record_id=make_record_id("sac", hash(self.card_id) % 100000),
            timestamp=time.time(),
            layer="evolution",
            round=round_num,
            event_type="signed_agent_card",
            source_module="SignedAgentCards",
            target_module=self.agent_id,
            decision=f"card_{'valid' if self.is_valid() else 'invalid'}",
            justification=f"Capabilities: {len(self.capabilities)}, Trust: {self.trust_score}",
            outcome="success" if self.is_valid() else "failure",
            context_refs=[self.card_id],
        )


class AgentCardSigner:
    def __init__(self) -> None:
        self._key_registry: dict[str, str] = {}

    def register_key(self, agent_id: str, public_key_pem: str) -> None:
        self._key_registry[agent_id] = public_key_pem

    def sign_card(self, card: SignedAgentCard, private_key_pem: str) -> AgentCardSignature:
        card_data = card.to_card_data()
        card_hash = hashlib.sha256(json.dumps(card_data, sort_keys=True).encode()).hexdigest()

        object.__setattr__(card, "card_hash", card_hash)

        signature_value = hashlib.sha256((card_hash + private_key_pem).encode()).hexdigest()

        sig = AgentCardSignature(
            signature_id=f"sig_{card.card_id}_{int(time.time())}",
            agent_id=card.agent_id,
            public_key_fingerprint=hashlib.sha256(
                (self._key_registry.get(card.agent_id, "")).encode()
            ).hexdigest()[:16],
            signed_at=time.time(),
            expires_at=card.expires_at,
            algorithm="ed25519-sim",
            signature_value=signature_value,
            card_hash=card_hash,
        )
        card.signatures.append(sig)
        return sig

    def verify_card(self, card: SignedAgentCard) -> bool:
        public_key = self._key_registry.get(card.agent_id, "")
        if not public_key:
            return False

        for sig in card.signatures:
            card_data = card.to_card_data()
            sig.verify(public_key, card_data)
        return card.is_valid()

    def has_key(self, agent_id: str) -> bool:
        return agent_id in self._key_registry


class SignedAgentCardStore:
    def __init__(self, audit_store: UnifiedAuditStore | None = None) -> None:
        self._cards: dict[str, SignedAgentCard] = {}
        self._by_agent: dict[str, list[str]] = {}
        self._by_trust_range: dict[str, list[str]] = {}
        self._audit_store = audit_store or UnifiedAuditStore()

    def register(self, card: SignedAgentCard) -> None:
        self._cards[card.card_id] = card
        self._by_agent.setdefault(card.agent_id, []).append(card.card_id)

        if card.trust_score >= 0.9:
            bucket = "high"
        elif card.trust_score >= 0.7:
            bucket = "medium"
        else:
            bucket = "low"
        self._by_trust_range.setdefault(bucket, []).append(card.card_id)

        self._audit_store.append(card.to_audit_record())

    def get_card(self, card_id: str) -> SignedAgentCard | None:
        return self._cards.get(card_id)

    def get_agent_cards(self, agent_id: str) -> list[SignedAgentCard]:
        card_ids = self._by_agent.get(agent_id, [])
        return [self._cards[cid] for cid in card_ids if cid in self._cards]

    def get_valid_cards(self) -> list[SignedAgentCard]:
        return [c for c in self._cards.values() if c.is_valid()]

    def get_by_trust_range(self, bucket: str) -> list[SignedAgentCard]:
        card_ids = self._by_trust_range.get(bucket, [])
        return [self._cards[cid] for cid in card_ids if cid in self._cards]

    def revoke_card(self, card_id: str) -> None:
        card = self._cards.get(card_id)
        if card:
            card.expires_at = time.time() - 1.0
            self._audit_store.append(
                UnifiedAuditRecord(
                    record_id=make_record_id("revoke", hash(card_id) % 100000),
                    timestamp=time.time(),
                    layer="evolution",
                    round=36,
                    event_type="agent_card_revoked",
                    source_module="SignedAgentCards",
                    target_module=card.agent_id,
                    decision="revoke",
                    justification=f"Card {card_id} manually revoked",
                    outcome="success",
                    context_refs=[card_id],
                )
            )

    @property
    def card_count(self) -> int:
        return len(self._cards)

    @property
    def valid_count(self) -> int:
        return len(self.get_valid_cards())

    def clear(self) -> None:
        self._cards.clear()
        self._by_agent.clear()
        self._by_trust_range.clear()
