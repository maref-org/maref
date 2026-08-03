"""v0.47 S5 — metering / billing injection hardening.

Two changes:

1. ``TaskMeteringEngine.record`` gains a ``caller_did`` source-binding
   field so every metric records *who* submitted it (backward compatible:
   optional, defaults to "").

2. ``FederatedPlanExecutor._dispatch_step`` no longer trusts the
   caller-supplied ``success`` param.  The success flag is **measured by
   the executor** from the actual dispatch outcome, so a caller cannot
   inject ``success=True`` to fabricate billable successful work.
"""

from __future__ import annotations

from maref.federation import create_default_federation
from maref.federation.gateway import FederationGateway, FederationRequest
from maref.federation.metering import TaskMetric, TaskMeteringEngine
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


def _register_agent(
    gateway: FederationGateway, organization: str, skills: list[str]
) -> str:
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


def _executor_platform():
    platform = create_default_federation(server_id="s5-test-01")
    _register_agent(platform.gateway, "Acme", ["research"])
    return platform


# ── Change 1: caller_did source binding ───────────────────────────────────


def test_record_binds_caller_did() -> None:
    engine = TaskMeteringEngine()
    metric = engine.record(
        task_id="t1", agent_did="did:1", agent_aic="aic:1",
        provider_org="P", consumer_org="C",
        duration_ms=10, token_count=1, success=True, complexity_score=0.5,
        caller_did="did:maref:caller:alice",
    )
    assert metric.caller_did == "did:maref:caller:alice"


def test_record_caller_did_defaults_to_empty() -> None:
    """Backward compatible: no caller_did → stored as ""."""
    engine = TaskMeteringEngine()
    metric = engine.record(
        task_id="t1", agent_did="did:1", agent_aic="aic:1",
        provider_org="P", consumer_org="C",
        duration_ms=10, token_count=1, success=True, complexity_score=0.5,
    )
    assert metric.caller_did == ""


def test_metric_to_dict_includes_caller_did() -> None:
    engine = TaskMeteringEngine()
    metric = engine.record(
        task_id="t1", agent_did="did:1", agent_aic="aic:1",
        provider_org="P", consumer_org="C",
        duration_ms=10, token_count=1, success=True, complexity_score=0.5,
        caller_did="did:caller:x",
    )
    d = metric.to_dict()
    assert d["caller_did"] == "did:caller:x"


def test_metric_from_dict_roundtrip_preserves_caller_did() -> None:
    m = TaskMetric(
        metric_id="m1", task_id="t1", agent_did="d", agent_aic="a",
        provider_org="P", consumer_org="C",
        duration_ms=10, token_count=1, success=True, complexity_score=0.5,
        caller_did="did:caller:y",
    )
    assert TaskMetric(**m.to_dict()).caller_did == "did:caller:y"


# ── Change 2: success is measured, not injected ───────────────────────────


def test_executor_ignores_caller_success_false_when_dispatch_succeeds() -> None:
    """A caller cannot force success=False to dodge billing credit."""
    platform = _executor_platform()
    executor = FederatedPlanExecutor(platform=platform)
    plan = Plan(
        plan_id="p1",
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
                    "success": False,  # caller attempts to under-report
                },
            ),
        ],
    )
    report = executor.execute(plan)
    dispatch = report.federation_dispatches[0]
    assert dispatch.success is True
    metric = platform.metering.iter_all_metrics()[0]
    assert metric.success is True  # executor measured success


def test_executor_ignores_caller_success_true_when_dispatch_fails() -> None:
    """A caller cannot inject success=True to fabricate billable work."""
    platform = create_default_federation(server_id="s5-test-02")
    # No agent registered → dispatch cannot succeed.
    executor = FederatedPlanExecutor(platform=platform)
    plan = Plan(
        plan_id="p2",
        steps=[
            PlanStep(
                task_id="t1",
                action=FEDERATION_DISPATCH_ACTION,
                params={
                    "required_capability": "nonexistent",
                    "consumer_org": "GammaCorp",
                    "provider_org": "Acme",
                    "token_count": 5000,
                    "complexity_score": 0.6,
                    "success": True,  # caller attempts to fabricate success
                },
            ),
        ],
    )
    report = executor.execute(plan)
    assert report.federation_dispatches[0].success is False
    # No metric recorded for a failed dispatch.
    assert platform.metering.metric_count == 0


def test_success_measured_from_dispatch_outcome() -> None:
    """Normal path: successful dispatch records a successful metric."""
    platform = _executor_platform()
    executor = FederatedPlanExecutor(platform=platform)
    plan = Plan(
        plan_id="p3",
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
    report = executor.execute(plan)
    assert report.federation_dispatches[0].success is True
    metric = platform.metering.iter_all_metrics()[0]
    assert metric.success is True
