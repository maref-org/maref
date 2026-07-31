from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from maref.crypto.ed25519_keys import Ed25519KeyPair
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
        """Verify the signature against the card data.

        Supports two algorithms:
        - ``ed25519``: real Ed25519 elliptic curve signature verification.
        - ``ed25519-sim``: legacy SHA-256 hash comparison (for backward compat).
        """
        computed_hash = hashlib.sha256(
            json.dumps(card_data, sort_keys=True).encode()
        ).hexdigest()

        if self.algorithm == "ed25519":
            try:
                signature_bytes = bytes.fromhex(self.signature_value)
            except ValueError:
                self.verified = False
                return False
            sig_valid = Ed25519KeyPair.verify(
                public_key_pem, signature_bytes, computed_hash.encode()
            )
            self.verified = sig_valid and (time.time() < self.expires_at)
        else:
            # Legacy SHA-256 simulation (ed25519-sim).
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


@dataclass
class CapabilityDriftReport:
    """声明 vs 实际能力偏离报告"""
    agent_id: str
    drift_detected: bool
    declared_capabilities: set[str]
    observed_capabilities: set[str]
    unauthorized_syscalls: set[str]
    unauthorized_domains: set[str]
    severity: str  # CRITICAL | HIGH | MEDIUM | LOW
    reason: str


class AgentCardSigner:
    """Signs Agent Cards with Ed25519 or legacy SHA-256 simulation.

    By default (``legacy_mode=False``) uses real Ed25519 elliptic curve
    signatures via :class:`~maref.crypto.ed25519_keys.Ed25519KeyPair`.
    Set ``legacy_mode=True`` for backward compatibility with the
    previous SHA-256 hash simulation (``ed25519-sim``).
    """

    def __init__(self, legacy_mode: bool = False) -> None:
        self._key_registry: dict[str, str] = {}
        self._legacy_mode = legacy_mode

    def register_key(self, agent_id: str, public_key_pem: str) -> None:
        self._key_registry[agent_id] = public_key_pem

    def sign_card(self, card: SignedAgentCard, private_key_pem: str) -> AgentCardSignature:
        card_data = card.to_card_data()
        card_hash = hashlib.sha256(
            json.dumps(card_data, sort_keys=True).encode()
        ).hexdigest()

        if self._legacy_mode:
            algorithm = "ed25519-sim"
            signature_value = hashlib.sha256(
                (card_hash + private_key_pem).encode()
            ).hexdigest()
        else:
            key_pair = Ed25519KeyPair.from_private_pem(private_key_pem)
            signature_bytes = key_pair.sign(card_hash.encode())
            algorithm = "ed25519"
            signature_value = signature_bytes.hex()

        public_key_pem = self._key_registry.get(card.agent_id, "")
        fingerprint = (
            hashlib.sha256(public_key_pem.encode()).hexdigest()[:16]
            if public_key_pem
            else ""
        )

        sig = AgentCardSignature(
            signature_id=f"sig_{card.card_id}_{int(time.time())}",
            agent_id=card.agent_id,
            public_key_fingerprint=fingerprint,
            signed_at=time.time(),
            expires_at=card.expires_at,
            algorithm=algorithm,
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

    def compare_declared_vs_observed(
        self,
        agent_id: str,
        observed_syscalls: set[str],
        observed_domains: set[str],
    ) -> CapabilityDriftReport:
        """对比 agent card 声明的 capabilities 与实际观测行为。

        检测闭源 agent 声明 'read_only' 但实际执行网络连接等偏离行为。

        Args:
            agent_id: 目标 agent ID
            observed_syscalls: 观测到的 syscall 名称集合
            observed_domains: 观测到的网络域名集合

        Returns:
            CapabilityDriftReport 包含偏离详情
        """
        cards = self.get_agent_cards(agent_id)
        if not cards:
            return CapabilityDriftReport(
                agent_id=agent_id,
                drift_detected=False,
                declared_capabilities=set(),
                observed_capabilities=set(),
                unauthorized_syscalls=set(),
                unauthorized_domains=set(),
                severity="LOW",
                reason="no agent card on record — unable to compare",
            )

        # 取最新一张有效 card (按 issued_at 降序排序)
        valid = sorted(
            [c for c in cards if c.is_valid()],
            key=lambda c: c.issued_at,
            reverse=True,
        )
        if not valid:
            return CapabilityDriftReport(
                agent_id=agent_id,
                drift_detected=False,
                declared_capabilities=set(),
                observed_capabilities=set(),
                unauthorized_syscalls=set(),
                unauthorized_domains=set(),
                severity="LOW",
                reason="no valid agent card — all expired or revoked",
            )

        card = valid[-1]
        declared = set(card.capabilities)

        # 能力语义映射 (简化的启发式映射)
        syscall_to_cap: dict[str, str] = {
            "connect": "network",
            "sendto": "network",
            "recvfrom": "network",
            "open": "filesystem",
            "openat": "filesystem",
            "read": "filesystem",
            "write": "filesystem",
            "execve": "execute",
            "fork": "process",
            "clone": "process",
            "ptrace": "debug",
            "bind": "network_server",
            "listen": "network_server",
        }

        observed_caps: set[str] = set()
        for sc in observed_syscalls:
            cap = syscall_to_cap.get(sc)
            if cap:
                observed_caps.add(cap)
        if observed_domains:
            observed_caps.add("network")

        # 检测偏离：观测到但未声明的能力
        unauthorized = observed_caps - declared
        unauthorized_syscalls = {
            sc for sc in observed_syscalls
            if sc in syscall_to_cap and syscall_to_cap[sc] in unauthorized
        }
        unauthorized_domains = (
            observed_domains if "network" in unauthorized else set()
        )

        drift = bool(unauthorized)
        if drift:
            severity = "CRITICAL" if "execute" in unauthorized or "debug" in unauthorized else "HIGH"
        else:
            severity = "LOW"

        return CapabilityDriftReport(
            agent_id=agent_id,
            drift_detected=drift,
            declared_capabilities=declared,
            observed_capabilities=observed_caps,
            unauthorized_syscalls=unauthorized_syscalls,
            unauthorized_domains=unauthorized_domains,
            severity=severity,
            reason=(
                f"observed capabilities {observed_caps} exceed declared {declared}"
                if drift else "all observed capabilities match declared"
            ),
        )

    def clear(self) -> None:
        self._cards.clear()
        self._by_agent.clear()
        self._by_trust_range.clear()
