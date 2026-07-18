"""GaaS Governance Router — multi-tenant governance decision routing.

Now delegates core governance logic to GovernancePipeline (core_pipeline.py)
for consistency with MCPGovernance and future governance entry points.

GaaS-specific responsibilities (tenant validation, quota, session mgmt)
remain here; policy evaluation, HITL, and audit go through the unified pipeline.
"""

from __future__ import annotations

import time
from typing import Any

from maref.gaas.audit_service import AuditLogService
from maref.gaas.cb_pool import CircuitBreakerPool
from maref.gaas.models import (
    CircuitBreakerState,
    GovernRequest,
    GovernResponse,
    Verdict,
)
from maref.gaas.models import (
    HITLTier as ModelHITLTier,
)
from maref.gaas.session_manager import increment_step
from maref.gaas.tenant import TenantManager
from maref.gaas.trust_service import TrustScoreService
from maref.governance.core_pipeline import (
    GovernancePipeline,
)
from maref.governance.core_pipeline import (
    GovernanceRequest as CoreRequest,
)
from maref.governance.core_pipeline import (
    GovernanceResult as CoreResult,
)
from maref.integration.hitl import HITLRouter
from maref.integration.hitl import HITLTier as ServiceHITLTier


class GovernanceRouter:
    """Multi-tenant governance decision router.

    Delegates core governance to GovernancePipeline. GaaS-specific
    pre/post-processing (tenant validation, quota, session management)
    stays here.
    """

    def __init__(
        self,
        tenant_manager: TenantManager | None = None,
        cb_pool: CircuitBreakerPool | None = None,
        hitl_service: HITLRouter | None = None,
        audit_service: AuditLogService | None = None,
        trust_service: TrustScoreService | None = None,
    ) -> None:
        self._tenants = tenant_manager or TenantManager()
        self._cb = cb_pool or CircuitBreakerPool()
        self._hitl = hitl_service or HITLRouter()
        self._audit = audit_service or AuditLogService()
        self._trust = trust_service or TrustScoreService()
        self._usage: dict[str, dict[str, int]] = {}

        # Unified governance pipeline — shared with MCPGovernance
        self._pipeline = GovernancePipeline(
            hitl=self._hitl,
            audit_callback=self._on_audit,
            trust_callback=self._on_update_trust,
            cb_check_callback=self._on_cb_check,
            cb_record_callback=self._on_cb_record,
            policy_rules=None,  # use defaults
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def govern(self, req: GovernRequest) -> GovernResponse:
        """Execute full governance pipeline for a request."""
        start = time.time()

        # 1. Tenant validation (GaaS-specific)
        tenant = self._tenants.get_by_id(req.tenant_id)
        if not tenant:
            return self._deny("Unknown tenant", start)

        # 2. Quota check (GaaS-specific)
        usage = self._usage.setdefault(req.tenant_id, {}).get("checks", 0)
        if not self._tenants.check_quota(req.tenant_id, "max_checks_per_month", usage):
            return self._deny("Quota exceeded", start)

        session_id = req.context.session_id

        # 3-8. Delegate to unified pipeline
        core_req = CoreRequest(
            action=req.action,
            agent_id=req.agent_id,
            tenant_id=req.tenant_id,
            parameters=req.parameters,
            recursion_depth=req.context.recursion_depth,
            trust_score=req.context.trust_score,
            session_id=session_id or "",
        )
        core_result = self._pipeline.govern(core_req)

        # Post-processing: session step tracking
        if session_id and core_result.verdict != Verdict.DENY:
            increment_step(session_id, tool_name=req.action, verdict=core_result.verdict.value)

        # Update usage
        self._usage[req.tenant_id]["checks"] = usage + 1

        return self._build_response(req, core_result, start)

    def get_stats(self, tenant_id: str) -> dict[str, Any]:
        return {
            "tenant_id": tenant_id,
            "usage": self._usage.get(tenant_id, {}),
            "audit": self._audit.get_stats(tenant_id),
            "hitl": self._hitl.get_stats(tenant_id),
        }

    # ------------------------------------------------------------------
    # GovernancePipeline callbacks
    # ------------------------------------------------------------------

    def _on_cb_check(self, tenant_id: str, agent_id: str, action: str, depth: int) -> bool:
        allowed, _ = self._cb.check(tenant_id, agent_id, action, depth=depth)
        return allowed

    def _on_cb_record(self, tenant_id: str, agent_id: str, action: str, success: bool) -> None:
        if success:
            self._cb.record_success(tenant_id, agent_id, action)
        else:
            self._cb.record_failure(tenant_id, agent_id, action)

    def _on_update_trust(self, tenant_id: str, agent_id: str, score: float, reason: str) -> None:
        self._trust.set_score(tenant_id, agent_id, score, reason=reason)

    def _on_audit(self, request: CoreRequest, result: CoreResult) -> None:
        audit_context: dict[str, Any] = {
            "recursion_depth": request.recursion_depth,
            "trust_score": request.trust_score,
        }
        if request.session_id:
            audit_context["session_id"] = request.session_id

        entry = self._audit.log(
            tenant_id=request.tenant_id or "default",
            agent_id=request.agent_id,
            action=request.action,
            verdict=result.verdict.value,
            parameters=request.parameters,
            context=audit_context,
        )
        self._last_audit_log_id = entry.log_id if hasattr(entry, 'log_id') else ""

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_response(
        self,
        req: GovernRequest,
        core_result: CoreResult,
        start_time: float,
    ) -> GovernResponse:
        latency_ms = int((time.time() - start_time) * 1000)

        mapped_verdict = Verdict(core_result.verdict.value)

        return GovernResponse(
            verdict=mapped_verdict,
            circuit_breaker_state=CircuitBreakerState.CLOSED,
            audit_log_id=getattr(self, '_last_audit_log_id', ''),
            required_hitl_tier=(
                self._map_tier_for_response(core_result.hitl_tier)
                if core_result.hitl_tier and mapped_verdict == Verdict.ASK_USER
                else None
            ),
            estimated_latency_ms=latency_ms,
            policy_version="v0.36.0-core-pipeline",
            reason=core_result.reason,
        )

    def _map_tier_for_response(self, tier: ServiceHITLTier) -> ModelHITLTier:
        mapping = {
            ServiceHITLTier.P0_RESPONSE: ModelHITLTier.P0,
            ServiceHITLTier.P1_ESCALATE: ModelHITLTier.P1,
            ServiceHITLTier.P2_LOG: ModelHITLTier.P2,
            ServiceHITLTier.P3_OBSERVE: ModelHITLTier.P3,
        }
        return mapping.get(tier, ModelHITLTier.P0)

    def _deny(
        self,
        reason: str,
        start_time: float,
        cb_state: CircuitBreakerState | None = None,
    ) -> GovernResponse:
        latency_ms = int((time.time() - start_time) * 1000)
        return GovernResponse(
            verdict=Verdict.DENY,
            circuit_breaker_state=cb_state or CircuitBreakerState.CLOSED,
            audit_log_id="",
            estimated_latency_ms=latency_ms,
            reason=reason,
        )
