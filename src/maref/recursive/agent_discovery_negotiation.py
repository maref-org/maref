from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from maref.recursive.agent_24_state_machine import Agent24StateMachine
from maref.recursive.unified_audit import UnifiedAuditRecord, UnifiedAuditStore, make_record_id


@dataclass
class CapabilityContractRef:
    capability_id: str
    version: str
    trust_required: float = 0.0
    timeout_seconds: float = 30.0


@dataclass
class DiscoveryMessage:
    source_id: str
    source_capabilities: list[str] = field(default_factory=list)
    source_contracts: list[CapabilityContractRef] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    trust_level: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class NegotiationProposal:
    source_id: str
    target_id: str
    proposal_type: str
    terms: dict[str, Any] = field(default_factory=dict)
    exchanged_contracts: list[CapabilityContractRef] = field(default_factory=list)
    counterparty_min_trust: float = 0.0
    status: str = "pending"
    timestamp: float = field(default_factory=time.time)


@dataclass
class NegotiationResult:
    accepted: bool
    agreement_id: str = ""
    refusal_reason: str = ""
    modified_terms: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentCapability:
    name: str
    level: float = 0.5
    success_rate: float = 0.5
    invocation_count: int = 0


@dataclass
class PeerAgent:
    agent_id: str
    capabilities: list[str] = field(default_factory=list)
    last_seen: float = field(default_factory=time.time)
    trust_estimate: float = 0.5
    negotiation_success_rate: float = 0.5
    active: bool = True


class AgentDiscovery:
    def __init__(self, state_machine: Agent24StateMachine) -> None:
        self._sm = state_machine
        self._peers: dict[str, PeerAgent] = {}
        self._broadcast_history: list[DiscoveryMessage] = []

    def discover(self, source_id: str, capabilities: list[str],
                 contracts: list[CapabilityContractRef] | None = None) -> DiscoveryMessage:
        msg = DiscoveryMessage(
            source_id=source_id,
            source_capabilities=capabilities,
            source_contracts=list(contracts) if contracts else [],
        )
        self._broadcast_history.append(msg)
        return msg

    def register_peer(self, peer_id: str, capabilities: list[str],
                       trust: float = 0.5) -> PeerAgent:
        peer = PeerAgent(
            agent_id=peer_id,
            capabilities=list(capabilities),
            trust_estimate=trust,
        )
        self._peers[peer_id] = peer
        return peer

    def find_peers_with_capability(self, capability: str) -> list[PeerAgent]:
        return [p for p in self._peers.values()
                if p.active and capability in p.capabilities]

    def list_active_peers(self) -> list[PeerAgent]:
        return [p for p in self._peers.values() if p.active]

    def update_trust(self, peer_id: str, delta: float) -> None:
        peer = self._peers.get(peer_id)
        if peer:
            peer.trust_estimate = max(0.0, min(1.0, peer.trust_estimate + delta))
            peer.last_seen = time.time()

    def deactivate_peer(self, peer_id: str) -> None:
        peer = self._peers.get(peer_id)
        if peer:
            peer.active = False


class AgentNegotiator:
    MIN_TRUST_FOR_NEGOTIATION = 0.3
    MAX_COUNTER_OFFERS = 3

    def __init__(self, audit_store: UnifiedAuditStore | None = None) -> None:
        self._proposals: list[NegotiationProposal] = []
        self._results: dict[str, NegotiationResult] = {}
        self._audit_store = audit_store or UnifiedAuditStore()

    def propose(self, source_id: str, target_id: str,
                 proposal_type: str, terms: dict[str, Any],
                 trust_level: float = 0.5,
                 contracts: list[CapabilityContractRef] | None = None) -> NegotiationProposal:
        proposal = NegotiationProposal(
            source_id=source_id,
            target_id=target_id,
            proposal_type=proposal_type,
            terms=dict(terms),
            counterparty_min_trust=trust_level,
            exchanged_contracts=list(contracts) if contracts else [],
        )
        self._proposals.append(proposal)
        return proposal

    def evaluate(self, proposal: NegotiationProposal,
                  counterparty_trust: float) -> NegotiationResult:
        if counterparty_trust < self.MIN_TRUST_FOR_NEGOTIATION:
            return NegotiationResult(
                accepted=False,
                refusal_reason=f"Trust ({counterparty_trust:.2f}) below minimum",
            )

        if proposal.counterparty_min_trust > 0 and \
                counterparty_trust < proposal.counterparty_min_trust:
            return NegotiationResult(
                accepted=False,
                refusal_reason=f"Trust does not meet counterparty minimum {proposal.counterparty_min_trust}",
            )

        agreement_id = f"agreement_{proposal.source_id}_{proposal.target_id}_{int(time.time())}"
        result = NegotiationResult(
            accepted=True,
            agreement_id=agreement_id,
            modified_terms=dict(proposal.terms),
        )
        self._results[agreement_id] = result

        self._audit_store.append(UnifiedAuditRecord(
            record_id=make_record_id("negot", hash(agreement_id) % 100000),
            timestamp=time.time(),
            layer="evolution",
            round=44,
            event_type="negotiation_accepted",
            source_module="AgentNegotiator",
            target_module=proposal.target_id,
            decision=f"accept_{proposal.proposal_type}",
            justification=f"Agreement {agreement_id}, trust={counterparty_trust:.2f}",
            outcome="success",
            context_refs=[agreement_id],
        ))

        return result

    def get_result(self, agreement_id: str) -> NegotiationResult | None:
        return self._results.get(agreement_id)

    def negotiation_history(self) -> list[NegotiationProposal]:
        return list(self._proposals)

    def negotiation_stats(self) -> dict[str, Any]:
        accepted = sum(1 for r in self._results.values() if r.accepted)
        total = len(self._results)
        return {
            "total_negotiations": len(self._proposals),
            "accepted": accepted,
            "rejected": total - accepted,
            "acceptance_rate": round(accepted / max(total, 1) * 100, 1),
        }


class TrustEstablishment:
    def __init__(self, audit_store: UnifiedAuditStore | None = None) -> None:
        self._trust_entries: dict[str, dict[str, float]] = {}
        self._audit_store = audit_store or UnifiedAuditStore()

    def establish_trust(self, source_id: str, target_id: str,
                         initial_trust: float) -> float:
        self._trust_entries.setdefault(source_id, {})[target_id] = initial_trust
        return initial_trust

    def update_trust(self, source_id: str, target_id: str, delta: float,
                      successful_interaction: bool = True) -> float:
        entries = self._trust_entries.setdefault(source_id, {})
        current = entries.get(target_id, 0.3)
        new_value = current + delta if successful_interaction else max(0.0, current - abs(delta))
        new_value = max(0.0, min(1.0, new_value))
        entries[target_id] = new_value

        self._audit_store.append(UnifiedAuditRecord(
            record_id=make_record_id("trust_build", hash((source_id, target_id)) % 100000),
            timestamp=time.time(),
            layer="evolution",
            round=44,
            event_type="trust_establishment",
            source_module="TrustEstablishment",
            target_module=target_id,
            decision=f"trust_{current:.2f}_to_{new_value:.2f}",
            justification=f"Delta={delta:.2f}, success={successful_interaction}",
            outcome="success",
            context_refs=[source_id, target_id],
        ))
        return new_value

    def get_trust(self, source_id: str, target_id: str) -> float:
        return self._trust_entries.get(source_id, {}).get(target_id, 0.0)

    def trust_network(self, source_id: str) -> dict[str, float]:
        return dict(self._trust_entries.get(source_id, {}))

    def mutual_trust(self, agent_a: str, agent_b: str) -> tuple[float, float]:
        a_trusts_b = self.get_trust(agent_a, agent_b)
        b_trusts_a = self.get_trust(agent_b, agent_a)
        return a_trusts_b, b_trusts_a

    @property
    def agent_count(self) -> int:
        return len(self._trust_entries)
