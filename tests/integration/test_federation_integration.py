"""Integration tests for the MAREF Federation Aggregation Platform.

Covers the end-to-end flows enabled by P0 integration:

* Factory + lifecycle — :func:`create_default_federation` returns a
  fully-wired :class:`FederatedPlatform` that all 9 submodules
  interoperate.
* Register → discover → dispatch → meter → settle — the canonical
  federation workflow, exercised through
  :class:`~maref.orchestration.federated_plan_executor.FederatedPlanExecutor`.
* Federated saga — :class:`~maref.recursive.federated_saga_orchestrator.FederatedSagaOrchestrator`
  with policy + HITL + trust assessment.
* Cross-org trust aggregation — :class:`FederatedTrustEngine` weighted
  scoring with peer reports.
* Layered policy with conflict resolution —
  :class:`FederationPolicyEngine` 4 strategies.
* Cross-org HITL with escalation — :class:`CrossOrgHITL` timeout →
  escalate → expire.
* Marketplace + metering + settlement — pricing, contribution scores,
  billing entries, and proposal lifecycle.

These tests use only in-process state — no HTTP / no real peers. The
:class:`FederatedDiscovery` is exercised with in-memory
``catalog_providers`` instead of real ADP endpoints.
"""

from __future__ import annotations

from typing import Any

import pytest

from maref.federation import (
    AgentMarketplace,
    ConflictStrategy,
    CrossOrgHITL,
    FederatedCatalog,
    FederatedDiscovery,
    FederatedPlatform,
    FederatedSettlement,
    FederatedTrustEngine,
    FederationGateway,
    FederationPolicyEngine,
    FederationRequest,
    PolicyDecision,
    Pricing,
    PricingModel,
    TaskMeteringEngine,
    create_default_federation,
)
from maref.identity.aic_adapter import AIC
from maref.orchestration.federated_plan_executor import (
    FEDERATION_DISPATCH_ACTION,
    FederatedPlanExecutor,
)
from maref.orchestration.plan_executor import Plan, PlanStep
from maref.recursive.federated_saga_orchestrator import FederatedSagaOrchestrator
from maref.recursive.saga_orchestrator import Saga, SagaStep, StepResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_acs_doc(aic: AIC, organization: str, skills: list[str]) -> dict[str, Any]:
    """Build a minimal but valid ACS document for federation registration."""
    return {
        "aic": aic.aic_string,
        "name": f"{organization}-agent",
        "description": f"Federated agent for {organization}",
        "protocolVersion": "2.00",
        "version": "1.0",
        "provider": {"organization": organization},
        "capabilities": {
            "streaming": False,
            "notification": False,
            "messageQueue": [],
        },
        "endpoints": [
            {
                "url": f"https://{organization.lower()}.example.com/api",
                "transport": "HTTP_JSON",
                "security": ["mutualTLS"],
            }
        ],
        "skills": [
            {"id": s, "name": s.title(), "description": f"{s} capability"}
            for s in skills
        ],
        "securitySchemes": {"mutualTLS": {"type": "mutualTLS"}},
    }


def _register_agent(
    gateway: FederationGateway,
    organization: str,
    skills: list[str],
) -> str:
    """Register a fresh federated agent and return its DID string."""
    aic = AIC.generate()
    doc = _make_acs_doc(aic, organization, skills)
    response = gateway.register_agent(
        FederationRequest(
            aic_string=aic.aic_string,
            acs_document=doc,
            endpoint_url=f"https://{organization.lower()}.example.com/api",
            protocol="aip",
        )
    )
    assert response.success, response.error
    return response.did_string


# ---------------------------------------------------------------------------
# Test 1: Factory + lifecycle
# ---------------------------------------------------------------------------
class TestFederationFactory:
    """`create_default_federation` returns a fully-wired platform."""

    def test_factory_returns_all_nine_components(self) -> None:
        platform = create_default_federation(server_id="maref-test-01")
        assert isinstance(platform, FederatedPlatform)
        assert isinstance(platform.gateway, FederationGateway)
        assert isinstance(platform.discovery, FederatedDiscovery)
        assert isinstance(platform.catalog, FederatedCatalog)
        assert isinstance(platform.trust_engine, FederatedTrustEngine)
        assert isinstance(platform.policy_engine, FederationPolicyEngine)
        assert isinstance(platform.hitl, CrossOrgHITL)
        assert isinstance(platform.marketplace, AgentMarketplace)
        assert isinstance(platform.metering, TaskMeteringEngine)
        assert isinstance(platform.settlement, FederatedSettlement)

    def test_factory_initial_state_is_empty(self) -> None:
        platform = create_default_federation()
        summary = platform.platform_summary()
        assert summary["gateway"]["agent_count"] == 0
        assert summary["catalog"]["entry_count"] == 0
        assert summary["trust"]["total_peer_reports"] == 0
        assert summary["metering"]["total_metrics"] == 0
        assert summary["settlement"]["total_billing_entries"] == 0

    def test_factory_with_custom_conflict_strategy(self) -> None:
        platform = create_default_federation(
            conflict_strategy=ConflictStrategy.MOST_RESTRICTIVE,
        )
        assert (
            platform.policy_engine.conflict_strategy
            == ConflictStrategy.MOST_RESTRICTIVE
        )

    def test_factory_with_custom_trust_weight(self) -> None:
        platform = create_default_federation(local_trust_weight=0.8)
        assert platform.trust_engine.local_weight == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# Test 2: Register → discover → dispatch → meter → settle
# ---------------------------------------------------------------------------
class TestEndToEndFederationFlow:
    """The canonical federation workflow through FederatedPlanExecutor."""

    def test_register_discover_dispatch_meter_settle(self) -> None:
        platform = create_default_federation(server_id="maref-prod-01")
        # 1. Register two agents in different organizations.
        acme_did = _register_agent(
            platform.gateway, "Acme", ["research", "analysis"]
        )
        betalabs_did = _register_agent(platform.gateway, "BetaLabs", ["research"])
        assert platform.gateway.agent_count == 2

        # 2. Discover by capability.
        research_agents = platform.gateway.discover_by_capability("research")
        assert len(research_agents) == 2
        acme_agent = next(a for a in research_agents if a.did.did_string == acme_did)
        assert acme_agent.aic is not None

        # 3. Federated dispatch via FederatedPlanExecutor.
        executor = FederatedPlanExecutor(platform=platform)
        plan = Plan(
            plan_id="plan-1",
            steps=[
                PlanStep(
                    task_id="t1",
                    action=FEDERATION_DISPATCH_ACTION,
                    params={
                        "required_capability": "research",
                        "consumer_org": "GammaCorp",
                        "provider_org": "Acme",
                        "token_count": 5000,
                        "complexity_score": 0.6,
                        "success": True,
                    },
                ),
            ],
        )
        report = executor.execute(plan)
        assert report.status.value == "completed"
        assert len(report.federation_dispatches) == 1
        dispatch = report.federation_dispatches[0]
        assert dispatch.success
        assert dispatch.provider_org == "Acme"
        assert dispatch.agent_did == acme_did
        assert dispatch.confidence > 0.0

        # 4. Metering recorded the task.
        assert platform.metering.metric_count == 1
        metric = platform.metering.iter_all_metrics()[0]
        assert metric.provider_org == "Acme"
        assert metric.consumer_org == "GammaCorp"
        assert metric.token_count == 5000
        assert metric.success is True

        # 5. Settlement generated exactly one cross-org billing entry.
        assert report.billing_entries_generated == 1
        proposal = platform.settlement.generate_proposal(
            provider_org="Acme",
            consumer_org="GammaCorp",
            period_start=metric.timestamp - 1,
            period_end=metric.timestamp + 1,
        )
        assert proposal.total_amount > 0.0
        assert proposal.status.value == "proposed"
        # Accept and settle.
        assert platform.settlement.accept_proposal(proposal.proposal_id) is True
        assert platform.settlement.settle_proposal(proposal.proposal_id) is True
        settled = platform.settlement.get_proposal(proposal.proposal_id)
        assert settled.status.value == "settled"

        # 6. Trust assessment was performed for the dispatched agent.
        assert acme_did in report.trust_assessments
        score = platform.trust_engine.get_score(acme_did)
        assert score is not None
        assert score.effective_score >= 0.0

    def test_remote_fallback_when_local_trust_below_threshold(self) -> None:
        """When local trust is below the threshold and no remote peer has a catalog, dispatch fails cleanly."""
        platform = create_default_federation(server_id="maref-prod-01")
        # Register one local agent with the "research" capability.
        # Its trust score is 0.0 (no history), which is below the
        # 99.0 threshold we set below.
        _register_agent(platform.gateway, "Acme", ["research"])
        # Add a peer, but without a catalog provider — so remote
        # discovery returns no agents.
        platform.discovery.add_peer(
            server_id="peer-1",
            endpoint_url="https://peer-1.example.com",
            trust_score=95.0,
        )
        executor = FederatedPlanExecutor(platform=platform, trust_fallback_threshold=99.0)
        plan = Plan(
            plan_id="plan-2",
            steps=[
                PlanStep(
                    task_id="t1",
                    action=FEDERATION_DISPATCH_ACTION,
                    params={
                        "required_capability": "research",
                        "consumer_org": "GammaCorp",
                        "provider_org": "",  # any org
                        "token_count": 100,
                        "complexity_score": 0.5,
                        "success": True,
                        "use_remote": True,
                    },
                ),
            ],
        )
        report = executor.execute(plan)
        assert len(report.federation_dispatches) == 1
        dispatch = report.federation_dispatches[0]
        # The local agent was found but its trust (0.0) is below 99.0.
        # use_remote=True triggers a remote lookup, but the peer has no
        # catalog provider → _find_remote_agent returns None, overwriting
        # the local agent. Dispatch fails with "No agent found".
        assert dispatch.task_id == "t1"
        assert dispatch.success is False
        assert "No agent found" in dispatch.error


# ---------------------------------------------------------------------------
# Test 3: Federated saga with policy + HITL + trust
# ---------------------------------------------------------------------------
class TestFederatedSagaFlow:
    """FederatedSagaOrchestrator end-to-end."""

    def test_saga_no_policy_succeeds(self) -> None:
        platform = create_default_federation()
        orch = FederatedSagaOrchestrator(platform)

        def step_a(ctx: dict[str, Any]) -> StepResult:
            return StepResult(step_id="a", success=True, data={"v": 1})

        def step_b(ctx: dict[str, Any]) -> StepResult:
            return StepResult(step_id="b", success=True, data={"v": 2})

        saga = Saga(
            saga_id="s1",
            steps=[
                SagaStep(step_id="a", description="action:noop", execute_fn=step_a),
                SagaStep(step_id="b", description="action:noop", execute_fn=step_b),
            ],
        )
        result = orch.execute(
            saga,
            initial_context={"requesting_org": "Acme", "reviewing_org": "Acme"},
        )
        assert result.is_success
        assert result.steps_executed == 2
        assert all(d.decision.value == "allow" for d in result.policy_decisions)

    def test_saga_fails_fast_on_deny(self) -> None:
        platform = create_default_federation()
        orch = FederatedSagaOrchestrator(platform)
        orch.policy_engine.add_federation_rule(
            rule_id="r1",
            action="action:noop",
            decision=PolicyDecision.DENY,
        )

        def step_a(ctx: dict[str, Any]) -> StepResult:
            return StepResult(step_id="a", success=True)

        saga = Saga(
            saga_id="s1",
            steps=[
                SagaStep(step_id="a", description="action:noop", execute_fn=step_a),
            ],
        )
        result = orch.execute(
            saga,
            initial_context={"requesting_org": "Acme", "reviewing_org": "Acme"},
        )
        assert not result.is_success
        assert "Policy denied" in result.error

    def test_saga_defer_cross_org_creates_hitl_request(self) -> None:
        platform = create_default_federation()
        orch = FederatedSagaOrchestrator(
            platform, default_timeout_seconds=0.05, hitl_poll_interval=0.01
        )
        orch.policy_engine.add_federation_rule(
            rule_id="r1",
            action="action:cross_org",
            decision=PolicyDecision.DEFER,
        )

        def step_a(ctx: dict[str, Any]) -> StepResult:
            return StepResult(step_id="a", success=True)

        saga = Saga(
            saga_id="s1",
            steps=[
                SagaStep(step_id="a", description="action:cross_org", execute_fn=step_a),
            ],
        )
        result = orch.execute(
            saga,
            initial_context={
                "requesting_org": "Acme",
                "reviewing_org": "BetaLabs",
            },
        )
        # With fail-closed semantics, the saga is denied because no
        # human approves within the 0.05s timeout → EXPIRED.
        assert not result.is_success
        assert any(d.hitl_request_id for d in result.policy_decisions)
        hitl_request_id = result.policy_decisions[0].hitl_request_id
        assert hitl_request_id != "auto"  # not auto-approved
        # Use the public API instead of accessing private _requests.
        assert platform.hitl.get_request(hitl_request_id) is not None
        assert result.policy_decisions[0].hitl_status == "expired"

    def test_saga_intra_org_defer_auto_approved(self) -> None:
        platform = create_default_federation()
        orch = FederatedSagaOrchestrator(platform, auto_approve_intra_org=True)
        orch.policy_engine.add_federation_rule(
            rule_id="r1",
            action="action:noop",
            decision=PolicyDecision.DEFER,
        )

        def step_a(ctx: dict[str, Any]) -> StepResult:
            return StepResult(step_id="a", success=True)

        saga = Saga(
            saga_id="s1",
            steps=[
                SagaStep(step_id="a", description="action:noop", execute_fn=step_a),
            ],
        )
        result = orch.execute(
            saga,
            initial_context={"requesting_org": "Acme", "reviewing_org": "Acme"},
        )
        assert result.is_success
        assert result.policy_decisions[0].hitl_request_id == "auto"


# ---------------------------------------------------------------------------
# Test 4: Trust aggregation
# ---------------------------------------------------------------------------
class TestFederatedTrustAggregation:
    """FederatedTrustEngine weighted scoring with peer reports."""

    def test_effective_score_combines_local_and_federated(self) -> None:
        platform = create_default_federation(local_trust_weight=0.5)
        agent_did = "did:maref:federated:abc123"
        # Inject a local trust score via the inner engine.
        platform.trust_engine.local_engine.register_agent(agent_did)
        platform.trust_engine.local_engine.record_task(
            agent_did, "task-1", success=True, quality=80.0, latency_ms=100.0
        )
        # assess() computes the score; get_score() retrieves it.
        platform.trust_engine.local_engine.assess(agent_did)
        # Submit a federated report.
        from maref.federation.trust import PeerTrustReport

        report = PeerTrustReport(
            agent_id=agent_did,
            source_server="peer-1",
            trust_score=60.0,
            confidence=1.0,
        )
        platform.trust_engine.submit_peer_report(report)
        score = platform.trust_engine.assess(agent_did)
        # local_weight=0.5 → effective = 0.5*local + 0.5*federated
        local = platform.trust_engine.local_engine.get_score(agent_did).overall_trust
        assert score.local_score == pytest.approx(local)
        assert score.federated_score == pytest.approx(60.0)
        expected = 0.5 * local + 0.5 * 60.0
        assert score.effective_score == pytest.approx(expected, abs=0.5)

    def test_no_reports_falls_back_to_local(self) -> None:
        platform = create_default_federation()
        agent_did = "did:maref:federated:xyz789"
        platform.trust_engine.local_engine.register_agent(agent_did)
        platform.trust_engine.local_engine.record_task(
            agent_did, "task-1", success=True, quality=70.0, latency_ms=50.0
        )
        # assess() computes the score before get_score() can return it.
        platform.trust_engine.local_engine.assess(agent_did)
        score = platform.trust_engine.assess(agent_did)
        assert score.local_score is not None
        assert score.federated_score is None
        # No peer reports → effective = local.
        assert score.effective_score == pytest.approx(score.local_score)


# ---------------------------------------------------------------------------
# Test 5: Policy with conflict resolution
# ---------------------------------------------------------------------------
class TestFederationPolicyConflictResolution:
    """FederationPolicyEngine layered rules with conflict strategies."""

    def test_federation_wins_default(self) -> None:
        engine = FederationPolicyEngine(
            conflict_strategy=ConflictStrategy.FEDERATION_WINS
        )
        engine.add_federation_rule("fed-deny", "x", PolicyDecision.DENY)
        engine.add_local_rule("local-allow", "x", PolicyDecision.ALLOW)
        result = engine.evaluate("x")
        assert result.decision.value == "deny"
        assert result.conflict_detected is True

    def test_most_restrictive_picks_deny(self) -> None:
        engine = FederationPolicyEngine(
            conflict_strategy=ConflictStrategy.MOST_RESTRICTIVE
        )
        engine.add_federation_rule("fed-allow", "x", PolicyDecision.ALLOW)
        engine.add_local_rule("local-deny", "x", PolicyDecision.DENY)
        result = engine.evaluate("x")
        assert result.decision.value == "deny"
        assert result.conflict_detected is True

    def test_no_rules_allow_by_default(self) -> None:
        engine = FederationPolicyEngine()
        result = engine.evaluate("unknown-action")
        assert result.decision.value == "allow"


# ---------------------------------------------------------------------------
# Test 6: Cross-org HITL with escalation
# ---------------------------------------------------------------------------
class TestCrossOrgHITLEscalation:
    """CrossOrgHITL timeout → escalate → expire."""

    def test_intra_org_auto_approved(self) -> None:
        hitl = CrossOrgHITL()
        req = hitl.request_approval(
            action="x",
            description="",
            requesting_org="Acme",
            reviewing_org="Acme",
            agent_did="did:1",
            task_id="t1",
        )
        assert req.status.value == "approved"
        assert req.reviewer == "auto"

    def test_timeout_escalates_then_expires(self) -> None:
        import time

        hitl = CrossOrgHITL()
        # Create with a 0-second timeout so it expires immediately.
        req = hitl.request_approval(
            action="x",
            description="",
            requesting_org="Acme",
            reviewing_org="BetaLabs",
            agent_did="did:1",
            task_id="t1",
            timeout_seconds=0.01,
            escalation_org="Compliance",
        )
        # No escalation: req remains PENDING until process_timeouts is called.
        time.sleep(0.02)
        affected = hitl.process_timeouts()
        assert req.request_id in affected
        # After escalation, the request status should be ESCALATED.
        refreshed = hitl.get_request(req.request_id)
        assert refreshed is not None
        assert refreshed.status.value in ("escalated", "expired")
        if refreshed.status.value == "escalated":
            time.sleep(0.02)
            hitl.process_timeouts()
            refreshed = hitl.get_request(req.request_id)
            assert refreshed.status.value == "expired"

    def test_pending_count_by_org(self) -> None:
        hitl = CrossOrgHITL()
        for i in range(3):
            hitl.request_approval(
                action="x",
                description="",
                requesting_org="Acme",
                reviewing_org=f"Org{i}",
                agent_did=f"did:{i}",
                task_id=f"t{i}",
            )
        # Auto-approved (intra-org for Acme) + 3 pending.
        summary = hitl.hitl_summary()
        assert summary["total_requests"] == 3
        assert summary["pending_count"] == 3


# ---------------------------------------------------------------------------
# Test 7: Marketplace + metering + settlement
# ---------------------------------------------------------------------------
class TestMarketplaceMeteringSettlement:
    """Marketplace pricing + metering contribution + settlement ledger."""

    def test_marketplace_publish_and_search(self) -> None:
        platform = create_default_federation()
        listing = platform.marketplace.publish(
            agent_aic="1.2.156.3088.1.1.1.aaaa.1.bbbb",
            agent_did="did:maref:federated:1",
            provider_org="Acme",
            name="Research Pro",
            description="Premium research agent",
            capabilities=["research"],
            pricing=Pricing(model=PricingModel.PER_TOKEN, price=0.001),
        )
        assert listing.listing_id.startswith("list_")
        results = platform.marketplace.search(capability="research", max_price=0.01)
        assert len(results) == 1
        assert results[0].listing_id == listing.listing_id

    def test_marketplace_review_and_rating(self) -> None:
        platform = create_default_federation()
        listing = platform.marketplace.publish(
            agent_aic="1.2.156.3088.1.1.1.aaaa.1.bbbb",
            agent_did="did:maref:federated:1",
            provider_org="Acme",
            name="X",
            description="Y",
            capabilities=["research"],
        )
        platform.marketplace.add_review(
            listing.listing_id, reviewer_org="GammaCorp", rating=5, comment="Great"
        )
        platform.marketplace.add_review(
            listing.listing_id, reviewer_org="DeltaCorp", rating=4, comment="Good"
        )
        avg = platform.marketplace.get_average_rating(listing.listing_id)
        assert avg == pytest.approx(4.5)
        assert platform.marketplace.get_review_count(listing.listing_id) == 2

    def test_metering_contribution_score(self) -> None:
        platform = create_default_federation()
        # Two agents contribute to the same task.
        platform.metering.record(
            task_id="t1",
            agent_did="did:1",
            agent_aic="1.2.156.3088.1.1.1.aaaa.1.bbbb",
            provider_org="Acme",
            consumer_org="Beta",
            duration_ms=1000.0,
            token_count=100,
            success=True,
            complexity_score=0.5,
        )
        platform.metering.record(
            task_id="t1",
            agent_did="did:2",
            agent_aic="1.2.156.3088.1.1.1.aaaa.1.cccc",
            provider_org="Acme",
            consumer_org="Beta",
            duration_ms=2000.0,
            token_count=200,
            success=True,
            complexity_score=0.7,
        )
        scores = platform.metering.compute_contribution("t1")
        assert len(scores) == 2
        # The second agent has higher duration + complexity → higher contribution.
        assert scores[0].agent_did == "did:2"
        assert scores[0].contribution > scores[1].contribution
        # Contributions sum to ~1.0.
        total = sum(s.contribution for s in scores)
        assert total == pytest.approx(1.0, abs=0.001)

    def test_settlement_billing_and_ledger(self) -> None:
        platform = create_default_federation()
        # Generate a cross-org metric, then bill it.
        platform.metering.record(
            task_id="t1",
            agent_did="did:1",
            agent_aic="1.2.156.3088.1.1.1.aaaa.1.bbbb",
            provider_org="Acme",
            consumer_org="Beta",
            duration_ms=500.0,
            token_count=1000,
            success=True,
            complexity_score=0.3,
        )
        entries = platform.settlement.generate_billing_from_metering()
        assert len(entries) == 1
        entry = entries[0]
        assert entry.provider_org == "Acme"
        assert entry.consumer_org == "Beta"
        assert entry.amount > 0.0
        # Ledger: Beta owes Acme.
        balance = platform.settlement.get_balance("Acme", "Beta")
        assert balance == pytest.approx(entry.amount)
        # Internal tasks (same org) are skipped by record_billing,
        # so calling generate_billing_from_metering again returns 0
        # new entries (the internal metric does not produce an entry).
        platform.metering.record(
            task_id="t2",
            agent_did="did:2",
            agent_aic="1.2.156.3088.1.1.1.aaaa.1.cccc",
            provider_org="Acme",
            consumer_org="Acme",
            duration_ms=100.0,
            token_count=10,
            success=True,
            complexity_score=0.1,
        )
        entries2 = platform.settlement.generate_billing_from_metering()
        # Internal task was skipped → 0 new billing entries.
        assert len(entries2) == 0
        # Ledger still has the original cross-org balance.
        assert platform.settlement.get_balance("Acme", "Beta") == pytest.approx(
            entry.amount
        )
