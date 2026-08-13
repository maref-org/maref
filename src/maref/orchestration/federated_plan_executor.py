"""Federated Plan Executor.

Adapter that extends :class:`~maref.orchestration.plan_executor.PlanExecutor`
with cross-organization dispatch, automatic task metering, and federated
trust assessment. When a step's action is registered as a federation
dispatch (``"federation_dispatch"``), the executor routes it through the
:mod:`maref.federation` platform instead of the local
:class:`~maref.orchestration.dispatcher.AgentDispatcher`.

Design goals
------------
1. **Zero regression for existing callers** — wraps (not inherits)
   :class:`PlanExecutor` so the standard ``Plan``/``PlanStep`` API is
   preserved.
2. **Explicit federation boundary** — only steps whose ``action`` is
   ``"federation_dispatch"`` are routed cross-organizationally. This
   keeps the audit trail unambiguous.
3. **Automatic metering** — every federation-dispatched step records a
   :class:`~maref.federation.metering.TaskMetric` so cross-org
   billing is generated without caller intervention.
4. **Trust-aware fallback** — if the local trust score is below the
   configured threshold, the executor can fall back to a federated
   peer with higher trust.

Usage
-----
>>> from maref.federation import create_default_federation
>>> from maref.orchestration.federated_plan_executor import FederatedPlanExecutor
>>> from maref.orchestration.plan_executor import Plan, PlanStep
>>> platform = create_default_federation()
>>> executor = FederatedPlanExecutor(platform=platform)
>>> plan = Plan(plan_id="p1", steps=[
...     PlanStep(task_id="t1", action="federation_dispatch",
...              params={"required_capability": "research",
...                      "consumer_org": "Acme", "provider_org": "BetaLabs",
...                      "token_count": 1000, "complexity_score": 0.5}),
... ])
>>> report = executor.execute(plan)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maref.federation import FederatedPlatform
    from maref.federation.gateway import FederatedAgent, FederationGateway
    from maref.federation.metering import TaskMeteringEngine
    from maref.federation.trust import FederatedTrustEngine
from maref.orchestration.decomposer import SubTask
from maref.orchestration.dispatcher import DispatchResult
from maref.orchestration.plan_executor import (
    ActionHandler,
    GovernanceCheck,
    Plan,
    PlanExecutionReport,
    PlanExecutor,
    RouteResolver,
    StepResult,
)

# Special action name that triggers federation dispatch.
FEDERATION_DISPATCH_ACTION = "federation_dispatch"


@dataclass
class FederationDispatchRecord:
    """Record of a single federation dispatch attempt.

    Attributes:
        task_id: The plan step ID.
        agent_did: The federated agent's DID (if dispatch succeeded).
        agent_aic: The federated agent's AIC.
        provider_org: The provider organization of the chosen agent.
        consumer_org: The consumer organization that requested the task.
        confidence: The dispatcher's confidence score (0.0-1.0).
        duration_ms: Wall-clock time spent on the dispatch path.
        success: Whether the dispatch returned a non-None result.
        remote: True if the agent came from a peer (forwarded via ADP).
        error: Error message (if dispatch failed).
    """

    task_id: str
    provider_org: str
    consumer_org: str
    agent_did: str = ""
    agent_aic: str = ""
    confidence: float = 0.0
    duration_ms: float = 0.0
    success: bool = False
    remote: bool = False
    error: str = ""


@dataclass
class FederatedPlanExecutionReport(PlanExecutionReport):
    """Plan execution report extended with federation metadata.

    Attributes:
        federation_dispatches: Per-step federation dispatch records.
        trust_assessments: Map of agent DID → effective trust score.
        billing_entries_generated: Count of cross-org billing entries
            produced by :class:`FederatedSettlement` during this run.
    """

    federation_dispatches: list[FederationDispatchRecord] = field(default_factory=list)
    trust_assessments: dict[str, float] = field(default_factory=dict)
    billing_entries_generated: int = 0


class FederatedPlanExecutor:
    """Plan executor with cross-organization dispatch.

    Composes a :class:`PlanExecutor` and a :class:`FederatedPlatform`
    so that steps with ``action="federation_dispatch"`` are routed via
    the :class:`FederationGateway`, with automatic task metering and
    trust assessment.

    Args:
        platform: A :class:`FederatedPlatform` (from
            :func:`maref.federation.create_default_federation`).
        governance_check: Optional governance predicate (forwarded to
            the inner :class:`PlanExecutor`).
        action_handlers: Optional action handlers (forwarded to inner).
        route_resolvers: Optional route resolvers (forwarded to inner).
        trust_fallback_threshold: If a local agent's effective trust
            score is below this threshold (0.0-100.0), the executor
            attempts a federated fallback via :class:`FederatedDiscovery`.
            Default 50.0.
    """

    def __init__(
        self,
        platform: FederatedPlatform,
        *,
        governance_check: GovernanceCheck | None = None,
        action_handlers: dict[str, ActionHandler] | None = None,
        route_resolvers: dict[str, RouteResolver] | None = None,
        trust_fallback_threshold: float = 50.0,
        boundary: Any | None = None,
    ) -> None:
        self._platform = platform
        self._gateway: FederationGateway = platform.gateway
        self._metering: TaskMeteringEngine = platform.metering
        self._trust: FederatedTrustEngine = platform.trust_engine
        # v0.47 F3: TrustBoundary gate for federated dispatch — same gate
        # local execution gets via GovernancePipeline (S9).
        self._boundary = boundary
        # Inner executor handles non-federation actions.
        self._executor = PlanExecutor(
            governance_check=governance_check,
            action_handlers=action_handlers,
            route_resolvers=route_resolvers,
        )
        self._trust_fallback_threshold = max(0.0, min(100.0, trust_fallback_threshold))
        # Cache: task_id -> dispatch record produced by the registered
        # handler when the inner PlanExecutor actually executed the step.
        # The post-hoc loop in execute() reads from this cache instead of
        # re-dispatching (which would create duplicate metrics).
        self._last_dispatches: dict[str, FederationDispatchRecord] = {}
        # Federation actions registered on the inner executor.
        self._registered_actions: set[str] = set()

    @property
    def platform(self) -> FederatedPlatform:
        """The underlying federation platform."""
        return self._platform

    @property
    def inner_executor(self) -> PlanExecutor:
        """The wrapped :class:`PlanExecutor` (for non-federation actions)."""
        return self._executor

    @property
    def last_dispatches(self) -> dict[str, FederationDispatchRecord]:
        """Map of step_id → last federation dispatch record from execute()."""
        return dict(self._last_dispatches)

    # ------------------------------------------------------------------ #
    # PlanExecutor API surface (delegated)                                #
    # ------------------------------------------------------------------ #
    def register_handler(self, action: str, handler: ActionHandler) -> None:
        """Register a handler for a non-federation action."""
        self._executor.register_handler(action, handler)

    def register_handlers(self, handlers: dict[str, ActionHandler]) -> None:
        """Register multiple handlers at once."""
        self._executor.register_handlers(handlers)

    def register_route_resolver(self, rule: str, resolver: RouteResolver) -> None:
        """Register a dynamic route resolver."""
        self._executor.register_route_resolver(rule, resolver)

    # ------------------------------------------------------------------ #
    # Federation-specific action registration                            #
    # ------------------------------------------------------------------ #
    def register_federation_capability(self, capability: str) -> None:
        """Register a capability as a federation-dispatchable action.

        After this call, plan steps with ``action == capability`` will be
        routed via :class:`FederationGateway` instead of the local
        :class:`PlanExecutor`.

        Args:
            capability: The capability / action name to register.
        """
        # The actual routing happens in execute(); we just maintain a
        # set of federation-routable actions on the inner executor side
        # so the inner handler check is consistent.
        self._executor.register_handler(capability, self._make_handler(capability))

    def _make_handler(self, capability: str) -> ActionHandler:
        """Build an action handler that forwards to the federation gateway."""

        def _handler(action: str, params: dict[str, Any]) -> FederationDispatchRecord:
            record = self._dispatch_step(action, params)
            # Cache the record (keyed by the step's task_id) so the
            # post-hoc loop in execute() can attach it to the report
            # without re-dispatching.
            task_id = params.get("_task_id", "")
            if task_id:
                record.task_id = task_id
                self._last_dispatches[task_id] = record
            if not record.success:
                # Re-raise so the PlanExecutor marks the step as FAILURE
                # and triggers rollback semantics.
                raise RuntimeError(record.error or "Federation dispatch failed")
            return record

        return _handler

    # ------------------------------------------------------------------ #
    # Execution entry point                                               #
    # ------------------------------------------------------------------ #
    def execute(self, plan: Plan) -> FederatedPlanExecutionReport:
        """Execute a plan, routing federation actions through the gateway.

        Steps whose action is :data:`FEDERATION_DISPATCH_ACTION` (or any
        capability registered via
        :meth:`register_federation_capability`) are dispatched through
        :class:`FederationGateway`. All other actions are delegated to
        the inner :class:`PlanExecutor`.

        Args:
            plan: The :class:`Plan` to execute.

        Returns:
            A :class:`FederatedPlanExecutionReport` with the standard
            step records **plus** federation metadata
            (``federation_dispatches``, ``trust_assessments``,
            ``billing_entries_generated``).
        """
        self._last_dispatches.clear()
        federation_records: list[FederationDispatchRecord] = []
        trust_snapshots: dict[str, float] = {}

        # Register the default federation_dispatch action on first use.
        if (
            any(s.action == FEDERATION_DISPATCH_ACTION for s in plan.steps)
            and FEDERATION_DISPATCH_ACTION not in self._registered_actions
        ):
            self._executor.register_handler(
                FEDERATION_DISPATCH_ACTION,
                self._make_handler(FEDERATION_DISPATCH_ACTION),
            )
            self._registered_actions.add(FEDERATION_DISPATCH_ACTION)

        # Inject _task_id into a **copy** of each federation-routable
        # step's params, so the handler can cache records by task_id
        # without mutating the caller's original dict.
        original_params: dict[str, dict[str, Any]] = {}
        for step in plan.steps:
            if step.action in self._registered_actions:
                original_params[step.task_id] = step.params
                step.params = {**step.params, "_task_id": step.task_id}

        # Delegate to inner executor — it will invoke our registered
        # handler for federation actions, which populates
        # self._last_dispatches.
        try:
            inner_report: PlanExecutionReport = self._executor.execute(plan)
        finally:
            # Restore original params so the caller's PlanStep objects
            # are not permanently mutated.
            for step in plan.steps:
                if step.task_id in original_params:
                    step.params = original_params[step.task_id]

        # Build the federation records list from the handler cache +
        # the inner step records (for success / duration / error).
        # Include all registered federation actions (both the default
        # FEDERATION_DISPATCH_ACTION and custom capabilities registered
        # via register_federation_capability).
        for step in plan.steps:
            if step.action not in self._registered_actions:
                continue
            cached = self._last_dispatches.get(step.task_id)
            if cached is None:
                # The handler may have failed before caching. Build a
                # minimal failure record from the inner step record.
                cached = FederationDispatchRecord(
                    task_id=step.task_id,
                    provider_org=step.params.get("provider_org", ""),
                    consumer_org=step.params.get("consumer_org", ""),
                )
                for rec in inner_report.steps:
                    if rec.task_id == step.task_id:
                        cached.error = rec.error or "Handler not invoked"
                        break
            else:
                # Annotate the cached record with the inner executor's
                # outcome (duration, success/failure).
                for rec in inner_report.steps:
                    if rec.task_id == step.task_id:
                        cached.duration_ms = rec.duration_ms
                        if rec.result == StepResult.SUCCESS:
                            cached.success = True
                        else:
                            cached.success = False
                            if not cached.error:
                                cached.error = rec.error or "Step failed"
                        break
            federation_records.append(cached)

            # Assess trust for the dispatched agent (only if dispatch
            # actually chose an agent).
            if cached.agent_did:
                score = self._trust.assess(cached.agent_did)
                trust_snapshots[cached.agent_did] = round(score.effective_score, 2)

        # Generate billing entries from accumulated metrics.
        billing_entries = self._platform.settlement.generate_billing_from_metering()
        billing_count = len(billing_entries)

        return FederatedPlanExecutionReport(
            plan_id=inner_report.plan_id,
            status=inner_report.status,
            steps=inner_report.steps,
            total_duration_ms=inner_report.total_duration_ms,
            error=inner_report.error,
            federation_dispatches=federation_records,
            trust_assessments=trust_snapshots,
            billing_entries_generated=billing_count,
        )

    # ------------------------------------------------------------------ #
    # Internal: per-step federation dispatch                              #
    # ------------------------------------------------------------------ #
    def _dispatch_step(self, action: str, params: dict[str, Any]) -> FederationDispatchRecord:
        """Perform a single federation dispatch for a plan step.

        Expected params:
            required_capability: str
            consumer_org: str
            provider_org: str  (optional — if missing, any org is allowed)
            token_count: int
            complexity_score: float  (0.0-1.0)
            use_remote: bool  (default False) — also try peer catalogs

        The ``success`` flag is **measured by the executor** from the actual
        dispatch outcome (v0.47 S5) — callers cannot inject it via params to
        fabricate or suppress billable work.
        """
        capability = params.get("required_capability", "")
        consumer_org = params.get("consumer_org", "")
        provider_org = params.get("provider_org", "")
        token_count = int(params.get("token_count", 0))
        complexity_score = float(params.get("complexity_score", 0.5))
        use_remote = bool(params.get("use_remote", False))

        record = FederationDispatchRecord(
            task_id="",
            provider_org=provider_org,
            consumer_org=consumer_org,
        )

        # v0.47 F3: TrustBoundary gate — federated dispatch gets the same
        # boundary check as local execution (GovernancePipeline S9).
        if self._boundary is not None:
            boundary_decision = self._boundary.check_no_raise(
                action=action,
                agent_id=consumer_org or "federated",
                metadata={"capability": capability, "provider_org": provider_org},
            )
            if not boundary_decision.allowed:
                record.error = f"TrustBoundary denied dispatch: {boundary_decision.reason}"
                return record

        if not capability:
            record.error = "Missing 'required_capability' in params"
            return record
        if not consumer_org:
            record.error = "Missing 'consumer_org' in params"
            return record

        start = time.time()
        try:
            # 1. Try local discovery first.
            agent = self._find_local_agent(capability, provider_org)

            # 2. If local search fails or trust is below threshold, try
            #    federated discovery (ADP forwarding to peers).
            remote = False
            if agent is None or self._local_trust_below_threshold(agent.did.did_string):
                if use_remote:
                    agent = self._find_remote_agent(capability, provider_org)
                    remote = agent is not None

            if agent is None:
                record.error = f"No agent found with capability '{capability}'"
                return record

            record.agent_did = agent.did.did_string
            record.agent_aic = agent.aic.aic_string
            record.provider_org = (
                agent.acs.provider.organization if agent.acs.provider else provider_org
            )
            record.remote = remote

            # 3. Build a synthetic SubTask and dispatch through the gateway.
            #    (The gateway's internal dispatcher consults the registered
            #    AgentDispatcher; we don't need to re-route here.)
            subtask = SubTask(
                task_id=record.agent_did,
                description=f"{action}:{capability}",
                estimated_complexity=complexity_score,
                required_capabilities=[capability],
            )
            dispatch_result: DispatchResult | None = self._gateway.dispatch_task(subtask)
            if dispatch_result is None:
                record.error = "Gateway returned no dispatch result"
                return record

            record.confidence = dispatch_result.confidence
            record.success = True

            # 4. Record a TaskMetric so cross-org billing is generated.
            #    success is measured from the dispatch outcome, and the
            #    metric is bound to the consumer as the caller identity
            #    (v0.47 S5).
            duration_ms = (time.time() - start) * 1000
            self._metering.record(
                task_id=record.agent_did,
                agent_did=record.agent_did,
                agent_aic=record.agent_aic,
                provider_org=record.provider_org,
                consumer_org=consumer_org,
                duration_ms=duration_ms,
                token_count=token_count,
                success=record.success,
                complexity_score=complexity_score,
                caller_did=consumer_org,
            )
            record.duration_ms = duration_ms
        except Exception as exc:  # pragma: no cover - defensive
            record.error = f"Dispatch exception: {exc}"

        return record

    def _find_local_agent(self, capability: str, provider_org: str) -> FederatedAgent | None:
        """Find a local federated agent matching the capability and org."""
        agents = self._gateway.discover_by_capability(capability)
        if not agents:
            return None
        if not provider_org:
            return agents[0]
        for agent in agents:
            if agent.acs.provider and agent.acs.provider.organization == provider_org:
                return agent
        return None

    def _find_remote_agent(self, capability: str, provider_org: str) -> FederatedAgent | None:
        """Find a federated agent via ADP discovery across peers.

        Only returns agents from **peer** servers (``hop_count > 0``),
        not local agents re-listed by the discovery layer.
        """
        results = self._platform.discovery.discover(capability=capability, include_remote=True)
        remote_results = [r for r in results if r.hop_count > 0]
        if not remote_results:
            return None
        if not provider_org:
            return remote_results[0].agent
        for r in remote_results:
            if r.agent.acs.provider and r.agent.acs.provider.organization == provider_org:
                return r.agent
        return None

    def _local_trust_below_threshold(self, agent_did: str) -> bool:
        """True if the agent's effective trust is below the fallback threshold."""
        score = self._trust.assess(agent_did)
        return score.effective_score < self._trust_fallback_threshold

    def platform_summary(self) -> dict[str, Any]:
        """Snapshot of the underlying federation platform state."""
        return self._platform.platform_summary()


__all__ = [
    "FEDERATION_DISPATCH_ACTION",
    "FederationDispatchRecord",
    "FederatedPlanExecutionReport",
    "FederatedPlanExecutor",
]
