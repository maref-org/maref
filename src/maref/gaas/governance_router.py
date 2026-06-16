"""GaaS Governance Router — core orchestration of multi-tenant governance decisions.

Routes every governance request through:
  1. Tenant validation + quota check
  2. CircuitBreaker check
  3. Policy evaluation (ALLOW | DENY | ASK_USER)
  4. HITL routing (if ASK_USER)
  5. Audit logging
  6. Trust score update
"""

from __future__ import annotations

import time
from typing import Any

from maref.gaas.audit_service import AuditLogService
from maref.gaas.cb_pool import CircuitBreakerPool
from maref.gaas.hitl_service import HITLService
from maref.gaas.hitl_service import HITLTier as ServiceHITLTier
from maref.gaas.models import (
    CircuitBreakerState,
    GovernRequest,
    GovernResponse,
    HITLTier,
    Verdict,
)
from maref.gaas.session_manager import is_session_active
from maref.gaas.tenant import TenantManager
from maref.gaas.trust_service import TrustScoreService


class GovernanceRouter:
    """Multi-tenant governance decision router."""

    def __init__(
        self,
        tenant_manager: TenantManager | None = None,
        cb_pool: CircuitBreakerPool | None = None,
        hitl_service: HITLService | None = None,
        audit_service: AuditLogService | None = None,
        trust_service: TrustScoreService | None = None,
    ) -> None:
        self._tenants = tenant_manager or TenantManager()
        self._cb = cb_pool or CircuitBreakerPool()
        self._hitl = hitl_service or HITLService()
        self._audit = audit_service or AuditLogService()
        self._trust = trust_service or TrustScoreService()
        self._usage: dict[str, dict[str, int]] = {}

    def govern(self, req: GovernRequest) -> GovernResponse:
        """Execute full governance pipeline for a request."""
        start = time.time()

        # 1. Tenant validation
        tenant = self._tenants.get_by_id(req.tenant_id)
        if not tenant:
            return self._deny("Unknown tenant", start)

        # 2. Quota check
        usage = self._usage.setdefault(req.tenant_id, {}).get("checks", 0)
        if not self._tenants.check_quota(req.tenant_id, "max_checks_per_month", usage):
            return self._deny("Quota exceeded", start)

        # 3. CircuitBreaker check (session-aware depth)
        session_id = req.context.session_id
        allowed, cb_state = self._cb.check(
            req.tenant_id,
            req.agent_id,
            req.action,
            depth=req.context.recursion_depth,
        )
        if not allowed:
            return self._deny("Circuit breaker OPEN", start, cb_state)

        # 4. Simple policy evaluation (placeholder for full policy engine)
        verdict, hitl_tier, reason = self._evaluate_policy(req)

        # 5. HITL routing
        if verdict == Verdict.ASK_USER:
            if not tenant.quota.get("hitl_enabled", False):
                verdict = Verdict.DENY
                reason = "HITL not enabled for tier"
            else:
                self._hitl.request(
                    tenant_id=req.tenant_id,
                    agent_id=req.agent_id,
                    action=req.action,
                    description=f"Approval required for {req.action}",
                    parameters=req.parameters,
                    tier=self._map_hitl_tier(hitl_tier),
                )
                # For synchronous API, auto-approve if timeout is 0
                if hitl_tier == HITLTier.P3:
                    verdict = Verdict.ALLOW
                    reason = "Auto-approved (p3 observe tier)"

        # 6. Audit logging (with session context)
        audit_context = {
            "recursion_depth": req.context.recursion_depth,
            "trust_score": req.context.trust_score,
            "cb_state": cb_state.value,
        }
        if session_id:
            audit_context["session_id"] = session_id
            from maref.gaas.session_manager import increment_step

            increment_step(session_id, tool_name=req.action, verdict=verdict.value)

        audit_entry = self._audit.log(
            tenant_id=req.tenant_id,
            agent_id=req.agent_id,
            action=req.action,
            verdict=verdict.value,
            parameters=req.parameters,
            context=audit_context,
        )

        # 7. Update usage
        self._usage[req.tenant_id]["checks"] = usage + 1

        # 8. Update trust score based on verdict
        self._update_trust(req, verdict)

        latency_ms = int((time.time() - start) * 1000)

        return GovernResponse(
            verdict=verdict,
            circuit_breaker_state=cb_state,
            audit_log_id=audit_entry.log_id,
            required_hitl_tier=hitl_tier if verdict == Verdict.ASK_USER else None,
            estimated_latency_ms=latency_ms,
            policy_version="v0.28.0-default",
            reason=reason,
        )

    def _evaluate_policy(
        self,
        req: GovernRequest,
    ) -> tuple[Verdict, HITLTier, str]:
        """Evaluate governance policy. Returns (verdict, hitl_tier, reason)."""
        # P0: Block dangerous actions
        dangerous_actions = {"file.delete", "shell.exec", "system.shutdown", "registry.modify"}
        if req.action in dangerous_actions:
            if req.context.trust_score < 70:
                return Verdict.ASK_USER, HITLTier.P0, "Dangerous action requires approval"
            return Verdict.ALLOW, HITLTier.P0, "Dangerous action allowed for trusted agent"

        # P1: High recursion depth (relaxed during active sessions)
        if req.context.recursion_depth > 2:
            session_id = req.context.session_id
            if session_id and is_session_active(session_id):
                if req.context.recursion_depth > 200:
                    return Verdict.ASK_USER, HITLTier.P1, "Session recursion depth exceeded"
            else:
                return Verdict.ASK_USER, HITLTier.P1, "High recursion depth"

        # P2: Low trust score
        if req.context.trust_score < 30:
            return Verdict.DENY, HITLTier.P2, "Trust score too low"

        # P3: Default observe
        return Verdict.ALLOW, HITLTier.P3, "Default allow"

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

    def _map_hitl_tier(self, tier: HITLTier) -> ServiceHITLTier:
        mapping = {
            HITLTier.P0: ServiceHITLTier.P0,
            HITLTier.P1: ServiceHITLTier.P1,
            HITLTier.P2: ServiceHITLTier.P2,
            HITLTier.P3: ServiceHITLTier.P3,
        }
        return mapping.get(tier, ServiceHITLTier.P0)

    def _update_trust(self, req: GovernRequest, verdict: Verdict) -> None:
        current = self._trust.get_score(req.tenant_id, req.agent_id)
        if current is None:
            current = 50.0

        if verdict == Verdict.ALLOW:
            new_score = min(100.0, current + 0.5)
        elif verdict == Verdict.DENY:
            new_score = max(0.0, current - 1.0)
        else:
            new_score = current

        self._trust.set_score(
            req.tenant_id, req.agent_id, new_score, reason=f"govern:{verdict.value}"
        )

    def get_stats(self, tenant_id: str) -> dict[str, Any]:
        return {
            "tenant_id": tenant_id,
            "usage": self._usage.get(tenant_id, {}),
            "audit": self._audit.get_stats(tenant_id),
            "hitl": self._hitl.get_stats(tenant_id),
        }
