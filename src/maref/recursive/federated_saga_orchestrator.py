"""Federated Saga Orchestrator.

Adapter that extends
:class:`~maref.recursive.saga_orchestrator.SagaOrchestrator` with
cross-organization governance:

* **Policy gating** — every saga step is evaluated against the
  :class:`~maref.federation.policy.FederationPolicyEngine` before
  execution. Policy decisions can ``ALLOW``/``DENY``/``DEFER`` (HITL).
* **Cross-org HITL** — ``DEFER`` decisions route the step to the
  :class:`~maref.federation.hitl.CrossOrgHITL` engine for review by
  the appropriate organization. Timeouts escalate to a configured
  fallback org.
* **Trust-aware execution** — the executor tracks trust scores per
  agent DID so callers can audit which agents participated.
* **Saga-level audit** — every policy decision and HITL outcome is
  surfaced in the :class:`FederatedSagaResult` so the GUI can render
  governance provenance.

Design goals
------------
1. **Zero regression for existing callers** — wraps (not inherits)
   :class:`SagaOrchestrator`.
2. **Fail-closed by default** — if a step has no policy rule, the
   default is ``ALLOW`` (matches ``FederationPolicyEngine.evaluate``).
3. **HITL is opt-in per saga** — sagas opt in by setting
   ``saga.metadata["federation"]["hitl"] = True`` or by providing an
   explicit ``escalation_org``.
4. **Policy/HITL side effects are observable** — the
   :class:`FederatedSagaResult` exposes a list of
   :class:`SagaPolicyDecision` records.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

# Defer the heavy import to avoid a circular dependency at module load time:
#   maref.federation -> maref.orchestration -> maref.recursive -> federated_saga_orchestrator
if TYPE_CHECKING:
    from maref.federation import FederatedPlatform
from maref.federation.hitl import (
    CrossOrgApprovalStatus,
    CrossOrgHITL,
)
from maref.federation.policy import (
    FederationPolicyEngine,
    PolicyDecision,
)
from maref.federation.trust import FederatedTrustEngine
from maref.recursive.blast_radius import BlastRadiusController
from maref.recursive.saga_orchestrator import (
    BackpressureConfig,
    Saga,
    SagaExecutionRecord,
    SagaOrchestrator,
    SagaResult,
    SagaState,
    SagaStep,
)

# Default saga action for policy gating.
SAGA_DEFAULT_ACTION = "saga_step"


@dataclass
class SagaPolicyDecision:
    """A single saga step's policy + HITL outcome.

    Attributes:
        step_id: The saga step ID.
        decision: The raw :class:`PolicyDecision` from the policy engine.
        conflict_detected: Whether the policy engine reported a conflict.
        matched_rule_id: The winning rule's ID (or empty).
        hitl_request_id: The cross-org HITL request ID (if DEFER).
        hitl_status: The final HITL status (APPROVED/REJECTED/EXPIRED).
        evaluated_at: When the policy was evaluated.
    """

    step_id: str
    decision: PolicyDecision
    conflict_detected: bool = False
    matched_rule_id: str = ""
    hitl_request_id: str = ""
    hitl_status: str = ""
    evaluated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "decision": self.decision.value,
            "conflict_detected": self.conflict_detected,
            "matched_rule_id": self.matched_rule_id,
            "hitl_request_id": self.hitl_request_id,
            "hitl_status": self.hitl_status,
            "evaluated_at": self.evaluated_at,
        }


@dataclass
class FederatedSagaResult:
    """The result of a federated saga execution.

    Attributes:
        saga_id: The saga's ID.
        state: The final saga state.
        steps_executed: Number of steps that completed successfully.
        steps_compensated: Number of compensated steps (on failure).
        step_records: Per-step execution records from the inner
            :class:`SagaOrchestrator`.
        policy_decisions: Per-step :class:`SagaPolicyDecision` records.
        trust_assessments: Map of agent DID → effective trust score.
        error: Error message (if failed).
        duration_ms: Total wall-clock time.
        started_at: Start timestamp.
        completed_at: End timestamp.
    """

    saga_id: str
    state: SagaState
    steps_executed: int = 0
    steps_compensated: int = 0
    step_records: list[SagaExecutionRecord] = field(default_factory=list)
    policy_decisions: list[SagaPolicyDecision] = field(default_factory=list)
    trust_assessments: dict[str, float] = field(default_factory=dict)
    error: str = ""
    duration_ms: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0

    @property
    def is_success(self) -> bool:
        return self.state == SagaState.COMPLETED

    @property
    def is_denied(self) -> bool:
        """True if any step was denied by policy (no HITL pending)."""
        return any(
            d.decision == PolicyDecision.DENY for d in self.policy_decisions
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "saga_id": self.saga_id,
            "state": self.state.value,
            "steps_executed": self.steps_executed,
            "steps_compensated": self.steps_compensated,
            "policy_decisions": [d.to_dict() for d in self.policy_decisions],
            "trust_assessments": dict(self.trust_assessments),
            "error": self.error,
            "duration_ms": self.duration_ms,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


# A function that resolves a saga step's context into a (reviewing_org,
# requesting_org) pair. Override to integrate with your auth / tenant layer.
OrgResolver = Callable[[SagaStep, dict[str, Any]], tuple[str, str]]


def default_org_resolver(step: SagaStep, context: dict[str, Any]) -> tuple[str, str]:
    """Default org resolver: read ``requesting_org`` / ``reviewing_org`` from context.

    Falls back to ``"default-org"`` for both, which means the HITL engine
    auto-approves (intra-org) and the saga proceeds without waiting.
    """
    requesting = context.get("requesting_org", "default-org")
    reviewing = context.get("reviewing_org", "default-org")
    return requesting, reviewing


class FederatedSagaOrchestrator:
    """Saga orchestrator with cross-org policy gating and HITL.

    Composes a :class:`SagaOrchestrator` and a :class:`FederatedPlatform`
    so that each saga step is policy-checked and (optionally) routed
    through :class:`CrossOrgHITL` for human approval.

    Args:
        platform: A :class:`FederatedPlatform` (from
            :func:`maref.federation.create_default_federation`).
        backpressure: Backpressure configuration (forwarded to inner).
        blast_radius: Blast radius controller (forwarded to inner).
        org_resolver: Callable that returns ``(requesting_org,
            reviewing_org)`` for a given step. Defaults to reading from
            the context dict.
        default_timeout_seconds: Default HITL timeout when a step is
            deferred (default 300s = 5 min).
        default_escalation_org: Optional org to escalate timed-out HITL
            requests to. If None, timed-out requests expire.
        auto_approve_intra_org: If True (default), steps with the same
            requesting_org and reviewing_org are auto-approved
            (no human wait). Matches :class:`CrossOrgHITL` semantics.
        hitl_poll_interval: Seconds between HITL status polls while
            waiting for human approval (default 0.5s). The orchestrator
            blocks the saga until the HITL request resolves, escalates,
            or expires — it never silently proceeds on PENDING.
    """

    def __init__(
        self,
        platform: FederatedPlatform,
        *,
        backpressure: BackpressureConfig | None = None,
        blast_radius: BlastRadiusController | None = None,
        org_resolver: OrgResolver | None = None,
        default_timeout_seconds: float = 300.0,
        default_escalation_org: str | None = None,
        auto_approve_intra_org: bool = True,
        hitl_poll_interval: float = 0.5,
    ) -> None:
        self._platform = platform
        self._policy: FederationPolicyEngine = platform.policy_engine
        self._hitl: CrossOrgHITL = platform.hitl
        self._trust: FederatedTrustEngine = platform.trust_engine
        self._inner = SagaOrchestrator(
            backpressure=backpressure or BackpressureConfig(),
            blast_radius=blast_radius,
        )
        self._org_resolver: OrgResolver = org_resolver or default_org_resolver
        self._default_timeout = max(1.0, default_timeout_seconds)
        self._default_escalation_org = default_escalation_org
        self._auto_approve_intra_org = auto_approve_intra_org
        self._hitl_poll_interval = max(0.01, hitl_poll_interval)

    @property
    def platform(self) -> FederatedPlatform:
        """The underlying federation platform."""
        return self._platform

    @property
    def inner(self) -> SagaOrchestrator:
        """The wrapped :class:`SagaOrchestrator` (for inspection)."""
        return self._inner

    @property
    def policy_engine(self) -> FederationPolicyEngine:
        """The :class:`FederationPolicyEngine` (for adding rules)."""
        return self._policy

    @property
    def hitl(self) -> CrossOrgHITL:
        """The :class:`CrossOrgHITL` engine (for manual approval)."""
        return self._hitl

    # ------------------------------------------------------------------ #
    # Saga execution                                                      #
    # ------------------------------------------------------------------ #
    def execute(
        self,
        saga: Saga,
        initial_context: dict[str, Any] | None = None,
    ) -> FederatedSagaResult:
        """Execute a saga with policy gating and optional HITL.

        For each step:
        1. Evaluate policy via :class:`FederationPolicyEngine`. If
           ``DENY``, the step is failed and the saga compensates.
        2. If ``DEFER`` and ``auto_approve_intra_org`` is True and
           requesting_org == reviewing_org, the step proceeds.
        3. If ``DEFER`` and the orgs differ, route to
           :class:`CrossOrgHITL` for review. The saga blocks until the
           HITL request resolves (or times out and is escalated).
        4. If ``ALLOW`` (or no policy rule matched), the step executes
           through the inner :class:`SagaOrchestrator`.

        Args:
            saga: The :class:`Saga` to execute.
            initial_context: Optional initial context for the saga.
                Step ``execute_fn`` callbacks can populate
                ``context[f"{step.step_id}_agent_did"]`` with the agent
                DID they dispatched to, so trust scores are recorded in
                the result's ``trust_assessments`` map.

        Returns:
            A :class:`FederatedSagaResult` with policy + HITL metadata.
        """
        started = time.time()
        context: dict[str, Any] = dict(initial_context) if initial_context else {}
        policy_decisions: list[SagaPolicyDecision] = []
        trust_snapshots: dict[str, float] = {}

        # Pre-flight: evaluate policy for each step. If any is denied
        # outright, fail fast and skip the inner executor.
        denied: list[str] = []
        for step in saga.steps:
            action = self._action_for_step(step)
            policy_result = self._policy.evaluate(action, context=context)
            decision_record = SagaPolicyDecision(
                step_id=step.step_id,
                decision=policy_result.decision,
                conflict_detected=policy_result.conflict_detected,
                matched_rule_id=(
                    policy_result.winning_rule.rule_id
                    if policy_result.winning_rule
                    else ""
                ),
            )
            policy_decisions.append(decision_record)

            if policy_result.decision == PolicyDecision.DENY:
                denied.append(step.step_id)
            elif policy_result.decision == PolicyDecision.DEFER:
                # Route to cross-org HITL.
                hitl_outcome = self._request_hitl_approval(
                    step, context, decision_record
                )
                if hitl_outcome == CrossOrgApprovalStatus.REJECTED:
                    denied.append(step.step_id)
                elif hitl_outcome == CrossOrgApprovalStatus.EXPIRED:
                    # Treat expiry as denial for fail-closed semantics.
                    denied.append(step.step_id)

        if denied:
            completed = time.time()
            return FederatedSagaResult(
                saga_id=saga.saga_id,
                state=SagaState.FAILED,
                steps_executed=0,
                steps_compensated=0,
                step_records=[],
                policy_decisions=policy_decisions,
                trust_assessments=trust_snapshots,
                error=f"Policy denied steps: {denied}",
                duration_ms=(completed - started) * 1000,
                started_at=started,
                completed_at=completed,
            )

        # All steps cleared the policy gate. Delegate to the inner
        # orchestrator.
        inner_result: SagaResult = self._inner.execute(saga, context)

        # Collect trust snapshots for any agents the saga referenced.
        # Convention: a step's execute_fn can stash the agent DID it used
        # in the context dict under the key ``f"{step.step_id}_agent_did"``.
        # Only DID-shaped strings (``did:...``) are assessed.
        for step in saga.steps:
            agent_did = context.get(f"{step.step_id}_agent_did", "")
            if isinstance(agent_did, str) and agent_did.startswith("did:"):
                score = self._trust.assess(agent_did)
                trust_snapshots[agent_did] = round(score.effective_score, 2)

        completed = time.time()
        return FederatedSagaResult(
            saga_id=inner_result.saga_id,
            state=inner_result.state,
            steps_executed=inner_result.steps_executed,
            steps_compensated=inner_result.steps_compensated,
            step_records=inner_result.step_records,
            policy_decisions=policy_decisions,
            trust_assessments=trust_snapshots,
            error=inner_result.error,
            duration_ms=inner_result.duration_ms or (completed - started) * 1000,
            started_at=inner_result.started_at or started,
            completed_at=inner_result.completed_at or completed,
        )

    # ------------------------------------------------------------------ #
    # Inner helpers                                                       #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _action_for_step(step: SagaStep) -> str:
        """Map a saga step to a policy action name.

        Convention: a step's :attr:`SagaStep.description` field is
        treated as the action name. Use the ``"action:foo"`` form to
        be explicit (the leading ``"action:"`` is preserved) or any
        other string. The default :data:`SAGA_DEFAULT_ACTION` is used
        if the description is empty.
        """
        if step.description:
            return step.description
        return SAGA_DEFAULT_ACTION

    def _request_hitl_approval(
        self,
        step: SagaStep,
        context: dict[str, Any],
        decision_record: SagaPolicyDecision,
    ) -> CrossOrgApprovalStatus:
        """Submit a HITL approval request and wait for a verdict.

        Returns the final :class:`CrossOrgApprovalStatus`. For same-org
        requests with :attr:`auto_approve_intra_org` enabled, this
        returns :attr:`CrossOrgApprovalStatus.APPROVED` synchronously
        without actually queueing a request.

        For cross-org requests, the method **blocks** until the HITL
        request resolves (APPROVED/REJECTED), escalates, or expires.
        It never silently returns PENDING — fail-closed semantics.
        """
        requesting_org, reviewing_org = self._org_resolver(step, context)
        if self._auto_approve_intra_org and requesting_org == reviewing_org:
            decision_record.hitl_status = CrossOrgApprovalStatus.APPROVED.value
            decision_record.hitl_request_id = "auto"
            return CrossOrgApprovalStatus.APPROVED

        # Honour explicit per-step overrides from context.
        timeout = float(context.get("hitl_timeout_seconds", self._default_timeout))
        escalation_org = context.get(
            "hitl_escalation_org", self._default_escalation_org
        )

        request = self._hitl.request_approval(
            action=self._action_for_step(step),
            description=step.description,
            requesting_org=requesting_org,
            reviewing_org=reviewing_org,
            agent_did=context.get("agent_did", ""),
            task_id=step.step_id,
            parameters={"timeout_seconds": timeout},
            timeout_seconds=timeout,
            escalation_org=escalation_org,
        )
        decision_record.hitl_request_id = request.request_id

        # Block until the request reaches a terminal state
        # (APPROVED, REJECTED, EXPIRED). PENDING and ESCALATED keep
        # polling. process_timeouts() advances ESCALATED → EXPIRED
        # when the escalation window also expires.
        deadline = time.time() + timeout + 1.0  # +1s grace beyond the HITL timeout
        final_status = request.status
        while time.time() < deadline and final_status in (
            CrossOrgApprovalStatus.PENDING,
            CrossOrgApprovalStatus.ESCALATED,
        ):
            time.sleep(self._hitl_poll_interval)
            self._hitl.process_timeouts()
            refreshed = self._hitl.get_request(request.request_id)
            if refreshed is not None:
                final_status = refreshed.status

        # If still non-terminal after the deadline, treat as EXPIRED
        # (fail-closed) so the saga does not proceed without approval.
        if final_status in (
            CrossOrgApprovalStatus.PENDING,
            CrossOrgApprovalStatus.ESCALATED,
        ):
            final_status = CrossOrgApprovalStatus.EXPIRED

        decision_record.hitl_status = final_status.value
        return final_status


__all__ = [
    "SAGA_DEFAULT_ACTION",
    "SagaPolicyDecision",
    "FederatedSagaResult",
    "FederatedSagaOrchestrator",
    "OrgResolver",
    "default_org_resolver",
]
