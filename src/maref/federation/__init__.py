"""MAREF Federation Aggregation Layer.

Provides the federation gateway that allows external ACPs/A2A/MCP agents
to attach to the MAREF governance framework, plus identity translation,
capability discovery, and protocol adaptation.

The 9 submodules form a complete federation aggregation platform::

    +-------------------------------------------------------------+
    |              FederatedPlatform (create_default)              |
    +-------------------------------------------------------------+
    |  Gateway  →  Identity (AIC↔DID) + ACS Parser + Dispatcher   |
    |  Discovery → ADP v2.00 forward to peer catalogs             |
    |  Catalog  → Inverted index + subscriptions                  |
    |  Trust    → Local 0.6 + Federated 0.4 (weighted, decay)     |
    |  Policy   → 3 layers, 4 conflict strategies                 |
    |  HITL     → Cross-org approval + escalation                 |
    |  Marketplace → Pricing + reviews + discovery                 |
    |  Metering → Per-task metrics + contribution scores          |
    |  Settlement → Billing + proposals + ledger                  |
    +-------------------------------------------------------------+

Public entry points:

- :func:`create_default_federation` — factory wiring all 9 modules.
- :class:`FederationGateway` — unified entry point for external agents.

Modules:
- :mod:`gateway`: FederationGateway — unified entry point for external agents.
- :mod:`discovery`: FederatedDiscovery — ADP v2.00 cross-org discovery.
- :mod:`catalog`: FederatedCatalog — searchable agent directory.
- :mod:`trust`: FederatedTrustEngine — cross-org trust propagation.
- :mod:`policy`: FederationPolicyEngine — layered policy with conflict strategies.
- :mod:`hitl`: CrossOrgHITL — cross-organization human approval.
- :mod:`marketplace`: AgentMarketplace — agent capability marketplace.
- :mod:`metering`: TaskMeteringEngine — per-task metrics + contribution.
- :mod:`settlement`: FederatedSettlement — cross-org billing + settlement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from maref.federation.bootstrap import (
    BootstrapClient,
    BootstrapSeed,
    parse_srv_seeds,
)
from maref.federation.cascade_breaker import (
    CascadeStatus,
    CascadeTrip,
    FederationCascadeBreaker,
)
from maref.federation.catalog import FederatedCatalog
from maref.federation.discovery import FederatedDiscovery
from maref.federation.gateway import (
    FederatedAgent,
    FederationGateway,
    FederationGatewayError,
    FederationRequest,
    FederationResponse,
)
from maref.federation.health_monitor import FederationHealthMonitor
from maref.federation.hitl import (
    CrossOrgApprovalRequest,
    CrossOrgApprovalStatus,
    CrossOrgHITL,
)
from maref.federation.jurisdiction_router import (
    CrossJurisdictionResult,
    JurisdictionConfig,
    JurisdictionConflictStrategy,
    JurisdictionEvaluation,
    JurisdictionPolicyRouter,
)
from maref.federation.marketplace import (
    AgentMarketplace,
    AgentReview,
    MarketplaceListing,
    Pricing,
    PricingModel,
)
from maref.federation.membership import (
    HeartbeatMessage,
    MembershipManager,
)
from maref.federation.metering import (
    ContributionScore,
    TaskMeteringEngine,
    TaskMetric,
)
from maref.federation.policy import (
    ConflictStrategy,
    FederationPolicyEngine,
    PolicyDecision,
    PolicyEvaluationResult,
    PolicyRule,
    PolicyScope,
)
from maref.federation.policy_subscriber import (
    FederatedPolicySubscriber,
    PolicyChangeType,
    PolicyPushEvent,
    PolicySubscription,
    SubscriptionStatus,
)
from maref.federation.settlement import (
    BillingEntry,
    FederatedSettlement,
    LedgerEntry,
    SettlementProposal,
    SettlementStatus,
    billing_charge_key,
    billing_fingerprint,
    merkle_root,
)
from maref.federation.settlement_reconciler import (
    SettlementReconciler,
    SettlementReconciliationReport,
)
from maref.federation.trigram_sync import (
    AgentTrigramProof,
    TrigramStateSnapshot,
    TrigramStateSynchronizer,
)
from maref.federation.trust import (
    FederatedTrustEngine,
    FederatedTrustScore,
    PeerTrustReport,
)
from maref.federation.trust_hardening import (
    AnomalyRecord,
    SourceReputation,
    SybilTrustGuard,
    byzantine_robust_aggregate,
)


@dataclass
class FederatedPlatform:
    """A wired-up federation aggregation platform.

    Contains all 9 federation components with consistent cross-references.
    Use :func:`create_default_federation` to construct one with sensible
    defaults; advanced users can build one manually by passing shared
    instances (e.g. a custom :class:`FederationGateway` into the
    :class:`FederatedDiscovery`).

    Attributes:
        gateway: The :class:`FederationGateway` (entry point).
        discovery: The :class:`FederatedDiscovery` (ADP v2.00 client).
        catalog: The :class:`FederatedCatalog` (searchable directory).
        trust_engine: The :class:`FederatedTrustEngine` (cross-org trust).
        policy_engine: The :class:`FederationPolicyEngine` (layered policy).
        hitl: The :class:`CrossOrgHITL` (cross-org approval).
        marketplace: The :class:`AgentMarketplace` (pricing + reviews).
        metering: The :class:`TaskMeteringEngine` (per-task metrics).
        settlement: The :class:`FederatedSettlement` (cross-org billing).
    """

    gateway: FederationGateway
    discovery: FederatedDiscovery
    catalog: FederatedCatalog
    trust_engine: FederatedTrustEngine
    policy_engine: FederationPolicyEngine
    hitl: CrossOrgHITL
    marketplace: AgentMarketplace
    metering: TaskMeteringEngine
    settlement: FederatedSettlement
    # v0.48 W3: federated consensus (F2 membership-bound voting).
    consensus: Any | None = None

    def platform_summary(self) -> dict[str, Any]:
        """Return a snapshot of the entire platform's state.

        Used by the GUI dashboard and by ``maref-lite`` health checks.
        """
        return {
            "gateway": self.gateway.gateway_summary(),
            "discovery": self.discovery.discovery_summary(),
            "catalog": self.catalog.catalog_summary(),
            "trust": self.trust_engine.federated_summary(),
            "policy": self.policy_engine.policy_summary(),
            "hitl": self.hitl.hitl_summary(),
            "marketplace": self.marketplace.marketplace_summary(),
            "metering": self.metering.metering_summary(),
            "settlement": self.settlement.settlement_summary(),
        }


def create_default_federation(
    *,
    server_id: str = "maref-local",
    conflict_strategy: ConflictStrategy = ConflictStrategy.FEDERATION_WINS,
    local_trust_weight: float = 0.6,
    audit_logger: Any | None = None,
    dispatcher: Any | None = None,
    did_registry: Any | None = None,
    trusted_peer_public_keys: dict[str, str] | None = None,
    consensus_membership: Any | None = None,
    consensus_quorum_size: int | None = None,
) -> FederatedPlatform:
    """Create a fully-wired :class:`FederatedPlatform` with sensible defaults.

    Wires up the 9 federation submodules with consistent cross-references:

    * :class:`FederationGateway` ← identity adapter + ACS parser + dispatcher
    * :class:`FederatedDiscovery` ← gateway (for local queries)
    * :class:`FederatedCatalog` ← (no cross-refs, independent)
    * :class:`FederatedTrustEngine` ← wraps a fresh local :class:`TrustEngineV2`
    * :class:`FederationPolicyEngine` ← (independent)
    * :class:`CrossOrgHITL` ← (independent)
    * :class:`AgentMarketplace` ← (independent)
    * :class:`TaskMeteringEngine` ← (independent)
    * :class:`FederatedSettlement` ← metering (for billing source)

    Args:
        server_id: Identifier for this federation server (used by
            :class:`FederatedDiscovery` for ADP forwarding).
        conflict_strategy: Conflict resolution strategy for the
            :class:`FederationPolicyEngine` (default
            :attr:`ConflictStrategy.FEDERATION_WINS`).
        local_trust_weight: Local sovereignty weight ``alpha`` for the
            :class:`FederatedTrustEngine` (default 0.6).
        audit_logger: Optional :class:`~maref.governance.audit.AuditLogger`
            to attach to the gateway. If provided, all registration and
            dispatch events are recorded with HMAC signing.
        dispatcher: Optional :class:`~maref.orchestration.dispatcher.AgentDispatcher`
            to attach to the gateway. Defaults to a fresh
            :class:`~maref.orchestration.dispatcher.AgentDispatcher`.
        did_registry: Optional :class:`~maref.identity.did_registry.DIDRegistry`
            to attach to the gateway. Defaults to a fresh
            :class:`~maref.identity.did_registry.DIDRegistry`.

    Returns:
        A :class:`FederatedPlatform` with all components wired.

    Example:
        >>> platform = create_default_federation(server_id="maref-prod-01")
        >>> from maref.identity.aic_adapter import AIC
        >>> aic = AIC.generate()
        >>> request = FederationRequest(
        ...     aic_string=aic.aic_string,
        ...     acs_document={"aic": aic.aic_string, "name": "agent-1",
        ...                   "provider": {"organization": "Acme"},
        ...                   "skills": [{"id": "research", "name": "Research",
        ...                              "description": "research"}]},
        ...     endpoint_url="https://acme.example.com/api",
        ...     protocol="aip",
        ... )
        >>> resp = platform.gateway.register_agent(request)
        >>> assert resp.success
        >>> platform.gateway.agent_count
        1
    """
    # Lazy imports: avoid forcing the caller to import the broader
    # orchestration / identity / recursive stack just to build a
    # federation platform.
    from maref.identity.aic_adapter import AICIdentityAdapter
    from maref.identity.did_registry import DIDRegistry
    from maref.integration.acs_parser import ACSParser
    from maref.orchestration.dispatcher import AgentDispatcher
    from maref.recursive.trust_engine_v2 import TrustEngineV2

    # 1. Identity + ACS + Dispatcher (injected or fresh).
    identity_adapter = AICIdentityAdapter()
    acs_parser = ACSParser()
    if dispatcher is None:
        dispatcher = AgentDispatcher()
    if did_registry is None:
        did_registry = DIDRegistry()

    # 2. Gateway: the entry point that ties identity / capability /
    #    dispatch / audit together.
    gateway = FederationGateway(
        identity_adapter=identity_adapter,
        acs_parser=acs_parser,
        dispatcher=dispatcher,
        did_registry=did_registry,
        audit_logger=audit_logger,
    )

    # 3. Discovery: queries the gateway locally, then forwards to peers.
    discovery = FederatedDiscovery(
        gateway=gateway,
        server_id=server_id,
    )

    # 4. Catalog: independent inverted index of federated agents.
    catalog = FederatedCatalog()

    # 5. Trust: wraps a fresh local TrustEngineV2 with cross-org aggregation.
    local_trust = TrustEngineV2()
    trust_engine = FederatedTrustEngine(
        local_engine=local_trust,
        local_weight=local_trust_weight,
        trusted_peer_public_keys=trusted_peer_public_keys,
    )

    # 6. Policy: layered engine with the requested conflict strategy.
    policy_engine = FederationPolicyEngine(conflict_strategy=conflict_strategy)

    # 7. HITL: cross-org human-in-the-loop approval.
    hitl = CrossOrgHITL()

    # 8. Marketplace: agent listings + reviews (independent).
    marketplace = AgentMarketplace()

    # 9. Metering: per-task metrics (independent).
    metering = TaskMeteringEngine()

    # 10. Settlement: wraps metering for cross-org billing.
    settlement = FederatedSettlement(metering=metering)

    # 11. Consensus (v0.48 W3): F2 membership-bound voting, when wired.
    from maref.governance.federated_consensus import FederatedConsensus

    member_count = (
        len(consensus_membership.members_summary())
        if consensus_membership is not None
        and hasattr(consensus_membership, "members_summary")
        else 3
    )
    quorum_size = consensus_quorum_size or max(2, member_count // 2 + 1)
    consensus = FederatedConsensus(
        member_count=member_count,
        quorum_size=quorum_size,
        membership=consensus_membership,
    )

    return FederatedPlatform(
        gateway=gateway,
        discovery=discovery,
        catalog=catalog,
        trust_engine=trust_engine,
        policy_engine=policy_engine,
        hitl=hitl,
        marketplace=marketplace,
        metering=metering,
        settlement=settlement,
        consensus=consensus,
    )


__all__ = [
    # Factory + container
    "FederatedPlatform",
    "create_default_federation",
    # Gateway
    "FederatedAgent",
    "FederationGateway",
    "FederationGatewayError",
    "FederationRequest",
    "FederationResponse",
    # Bootstrap (3.1)
    "BootstrapClient",
    "BootstrapSeed",
    "parse_srv_seeds",
    # Cascade breaker (2.4)
    "FederationCascadeBreaker",
    "CascadeStatus",
    "CascadeTrip",
    # Discovery
    "FederatedDiscovery",
    # Catalog
    "FederatedCatalog",
    # Health monitor (2.5 / 3.1 membership)
    "FederationHealthMonitor",
    # Membership (3.1)
    "MembershipManager",
    "HeartbeatMessage",
    # Trust
    "FederatedTrustEngine",
    "FederatedTrustScore",
    "PeerTrustReport",
    # Policy
    "FederationPolicyEngine",
    "PolicyRule",
    "PolicyDecision",
    "PolicyScope",
    "PolicyEvaluationResult",
    "ConflictStrategy",
    # HITL
    "CrossOrgHITL",
    "CrossOrgApprovalRequest",
    "CrossOrgApprovalStatus",
    # Marketplace
    "AgentMarketplace",
    "MarketplaceListing",
    "AgentReview",
    "Pricing",
    "PricingModel",
    # Metering
    "TaskMeteringEngine",
    "TaskMetric",
    "ContributionScore",
    # Settlement
    "FederatedSettlement",
    "BillingEntry",
    "SettlementProposal",
    "SettlementStatus",
    "LedgerEntry",
    # Settlement reconciliation (3.2)
    "SettlementReconciler",
    "SettlementReconciliationReport",
    "billing_charge_key",
    "billing_fingerprint",
    "merkle_root",
    # Trust hardening (3.3)
    "SybilTrustGuard",
    "SourceReputation",
    "AnomalyRecord",
    "byzantine_robust_aggregate",
    # Trigram Sync (F1)
    "TrigramStateSnapshot",
    "TrigramStateSynchronizer",
    "AgentTrigramProof",
    # Jurisdiction Router (F2)
    "JurisdictionPolicyRouter",
    "JurisdictionConfig",
    "JurisdictionConflictStrategy",
    "JurisdictionEvaluation",
    "CrossJurisdictionResult",
    # Policy Subscriber (F3)
    "FederatedPolicySubscriber",
    "PolicySubscription",
    "PolicyPushEvent",
    "PolicyChangeType",
    "SubscriptionStatus",
]
