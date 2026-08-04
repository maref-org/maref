"""v0.47 F3 — federated dispatch through TrustBoundary.

``FederatedPlanExecutor`` gains an optional ``boundary``.  When provided,
every federation dispatch is checked against the
:class:`TrustBoundaryManager` before the gateway is invoked — the same
gate local execution gets via ``GovernancePipeline`` (S9).  An
out-of-bounds dispatch is rejected (fail-closed) and no metric is recorded.
"""

from __future__ import annotations

from maref.federation import create_default_federation
from maref.federation.gateway import FederationGateway, FederationRequest
from maref.governance.trust_boundary import TrustBoundaryManager
from maref.identity.aic_adapter import AIC
from maref.orchestration.federated_plan_executor import (
    FEDERATION_DISPATCH_ACTION,
    FederatedPlanExecutor,
)
from maref.orchestration.plan_executor import Plan, PlanStep


def _acs_doc(aic: AIC, organization: str, skills: list[str]) -> dict[str, object]:
    return {
        "aic": aic.aic_string,
        "name": f"{organization}-agent",
        "description": f"Federated agent for {organization}",
        "protocolVersion": "2.00",
        "version": "1.0",
        "provider": {"organization": organization},
        "capabilities": {"streaming": False, "notification": False, "messageQueue": []},
        "endpoints": [
            {
                "url": f"https://{organization.lower()}.example.com/api",
                "transport": "HTTP_JSON",
                "security": ["mutualTLS"],
            }
        ],
        "skills": [{"id": s, "name": s.title(), "description": f"{s} capability"} for s in skills],
        "securitySchemes": {"mutualTLS": {"type": "mutualTLS"}},
    }


def _register_agent(gateway: FederationGateway, organization: str, skills: list[str]) -> str:
    aic = AIC.generate()
    response = gateway.register_agent(
        FederationRequest(
            aic_string=aic.aic_string,
            acs_document=_acs_doc(aic, organization, skills),
            endpoint_url=f"https://{organization.lower()}.example.com/api",
            protocol="aip",
        )
    )
    assert response.success, response.error
    return response.did_string


def _plan_with_action(action: str) -> Plan:
    return Plan(
        plan_id="f3-plan",
        steps=[
            PlanStep(
                task_id="t1",
                action=FEDERATION_DISPATCH_ACTION,
                params={
                    "required_capability": "research",
                    "consumer_org": "GammaCorp",
                    "provider_org": "Acme",
                    "token_count": 100,
                    "complexity_score": 0.5,
                },
            ),
        ],
    )


class TestFederatedDispatchBoundary:
    def test_boundary_denied_dispatch_fails_closed(self) -> None:
        """An out-of-bounds federation dispatch is rejected before the
        gateway runs; no metric is recorded."""
        platform = create_default_federation(server_id="f3-deny")
        _register_agent(platform.gateway, "Acme", ["research"])
        boundary = TrustBoundaryManager()
        executor = FederatedPlanExecutor(platform=platform, boundary=boundary)
        # "research" is a HIGH-ish action w/o scope → boundary denies.
        report = executor.execute(_plan_with_action("research"))
        dispatch = report.federation_dispatches[0]
        assert dispatch.success is False
        assert "boundary" in (dispatch.error or "").lower() or "denied" in (dispatch.error or "").lower()
        assert platform.metering.metric_count == 0

    def test_boundary_allowed_dispatch_succeeds(self) -> None:
        """A LOW-risk in-scope dispatch passes the boundary."""
        platform = create_default_federation(server_id="f3-allow")
        _register_agent(platform.gateway, "Acme", ["research"])
        # Boundary with a scope allowing the action + matching agent.
        from maref.identity.credential import AuthorizationScope

        scope = AuthorizationScope(
            subject_did="GammaCorp",
            max_risk_level="HIGH",
            allowed_actions=["federation_dispatch", "research"],
        )
        boundary = TrustBoundaryManager(scope=scope, allowed_domains={"local", "network", "filesystem", "readonly"})
        executor = FederatedPlanExecutor(platform=platform, boundary=boundary)
        report = executor.execute(_plan_with_action("research"))
        dispatch = report.federation_dispatches[0]
        assert dispatch.success is True

    def test_no_boundary_backward_compatible(self) -> None:
        """Without a boundary, dispatch behaves as before."""
        platform = create_default_federation(server_id="f3-compat")
        _register_agent(platform.gateway, "Acme", ["research"])
        executor = FederatedPlanExecutor(platform=platform)
        report = executor.execute(_plan_with_action("research"))
        assert report.federation_dispatches[0].success is True
