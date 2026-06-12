"""GaaS FastAPI Router — external-facing REST API for governance services.

Endpoints:
  POST /api/v1/gaas/govern         — Single governance check
  POST /api/v1/gaas/hitl/request   — Request human approval
  POST /api/v1/gaas/hitl/{event_id}/approve
  POST /api/v1/gaas/hitl/{event_id}/deny
  GET  /api/v1/gaas/hitl/pending   — List pending approvals
  GET  /api/v1/gaas/trust/score    — Query trust score
  POST /api/v1/gaas/audit/query    — Query audit logs
  GET  /api/v1/gaas/cb/status      — Circuit breaker status
  GET  /api/v1/gaas/health         — Service health
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status

from maref.gaas.audit_service import AuditLogService
from maref.gaas.cb_pool import CircuitBreakerPool
from maref.gaas.governance_router import GovernanceRouter
from maref.gaas.hitl_service import HITLService
from maref.gaas.models import (
    AuditEntry,
    AuditQueryRequest,
    AuditQueryResponse,
    CBStatusResponse,
    GovernRequest,
    GovernResponse,
    HITLRequest,
    HITLResponse,
    SessionCompleteRequest,
    SessionDeclareRequest,
    SessionDeclareResponse,
    SessionListResponse,
    SessionStatusResponse,
    SessionStepResponse,
    TrustScoreResponse,
)
from maref.gaas.tenant import TenantManager
from maref.gaas.trust_service import TrustScoreService

router = APIRouter(prefix="/api/v1/gaas", tags=["gaas"])

# Global service instances (singleton pattern)
_tenant_manager = TenantManager()
_cb_pool = CircuitBreakerPool()
_hitl_service = HITLService()
_audit_service = AuditLogService()
_trust_service = TrustScoreService()
_governance_router = GovernanceRouter(
    tenant_manager=_tenant_manager,
    cb_pool=_cb_pool,
    hitl_service=_hitl_service,
    audit_service=_audit_service,
    trust_service=_trust_service,
)


def get_tenant_manager() -> TenantManager:
    return _tenant_manager


def get_governance_router() -> GovernanceRouter:
    return _governance_router


def get_hitl_service() -> HITLService:
    return _hitl_service


def get_audit_service() -> AuditLogService:
    return _audit_service


def get_trust_service() -> TrustScoreService:
    return _trust_service


def get_cb_pool() -> CircuitBreakerPool:
    return _cb_pool


async def require_api_key(
    x_api_key: str = Header(..., description="Tenant API Key"),
) -> str:
    """Dependency to validate API key and return tenant_id."""
    tm = get_tenant_manager()
    tenant = tm.get_by_api_key(x_api_key)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return tenant.tenant_id


# ------------------------------------------------------------------
# Governance
# ------------------------------------------------------------------

@router.post("/govern", response_model=GovernResponse)
async def govern(
    req: GovernRequest,
    tenant_id: str = Depends(require_api_key),
) -> GovernResponse:
    """Execute a governance check for an Agent action."""
    # Override tenant_id from auth
    req.tenant_id = tenant_id
    return get_governance_router().govern(req)


# ------------------------------------------------------------------
# HITL
# ------------------------------------------------------------------

@router.post("/hitl/request", response_model=HITLResponse)
async def hitl_request(
    req: HITLRequest,
    tenant_id: str = Depends(require_api_key),
) -> HITLResponse:
    """Request human approval for an Agent action."""
    req.tenant_id = tenant_id
    svc = get_hitl_service()
    event = svc.request(
        tenant_id=req.tenant_id,
        agent_id=req.agent_id,
        action=req.action,
        description=req.description,
        parameters=req.parameters,
        tier=getattr(svc, "_map_tier_str", lambda x: x)(req.tier.value),
        auto_approve_seconds=req.auto_approve_seconds,
    )
    return HITLResponse(
        event_id=event.event_id,
        status=event.status.value,
    )


@router.post("/hitl/{event_id}/approve", response_model=HITLResponse)
async def hitl_approve(
    event_id: str,
    tenant_id: str = Depends(require_api_key),
) -> HITLResponse:
    """Approve a pending HITL event."""
    result = get_hitl_service().approve(tenant_id, event_id)
    return HITLResponse(
        event_id=event_id,
        status=result.value,
        approved=result.value == "approved",
    )


@router.post("/hitl/{event_id}/deny", response_model=HITLResponse)
async def hitl_deny(
    event_id: str,
    tenant_id: str = Depends(require_api_key),
) -> HITLResponse:
    """Deny a pending HITL event."""
    result = get_hitl_service().reject(tenant_id, event_id)
    return HITLResponse(
        event_id=event_id,
        status=result.value,
        approved=False,
    )


@router.get("/hitl/pending")
async def hitl_pending(
    tenant_id: str = Depends(require_api_key),
) -> dict[str, Any]:
    """List pending HITL events for the tenant."""
    events = get_hitl_service().get_pending(tenant_id)
    return {
        "events": [
            {
                "event_id": e.event_id,
                "agent_id": e.agent_id,
                "action": e.action,
                "description": e.description,
                "tier": e.tier.value,
                "created_at": e.created_at,
            }
            for e in events
        ],
        "count": len(events),
    }


# ------------------------------------------------------------------
# Trust Score
# ------------------------------------------------------------------

@router.get("/trust/score")
async def trust_score(
    agent_id: str,
    tenant_id: str = Depends(require_api_key),
) -> TrustScoreResponse:
    """Get trust score for an agent."""
    svc = get_trust_service()
    score = svc.get_score(tenant_id, agent_id)
    report = svc.get_report(tenant_id, agent_id) if score is not None else {}
    return TrustScoreResponse(
        tenant_id=tenant_id,
        agent_id=agent_id,
        trust_score=score,
        trust_tier=report.get("trust_tier", ""),
        history_count=report.get("history_count", 0),
        last_updated=report.get("last_updated"),
    )


# ------------------------------------------------------------------
# Audit Log
# ------------------------------------------------------------------

@router.post("/audit/query", response_model=AuditQueryResponse)
async def audit_query(
    req: AuditQueryRequest,
    tenant_id: str = Depends(require_api_key),
) -> AuditQueryResponse:
    """Query audit logs for the tenant."""
    req.tenant_id = tenant_id
    entries, total = get_audit_service().query(
        tenant_id=req.tenant_id,
        start_time=req.start_time,
        end_time=req.end_time,
        agent_id=req.agent_id,
        action=req.action,
        limit=req.limit,
        offset=req.offset,
    )
    return AuditQueryResponse(
        entries=[
            AuditEntry(
                log_id=e.log_id,
                timestamp=e.timestamp,
                tenant_id=e.tenant_id,
                agent_id=e.agent_id,
                action=e.action,
                verdict=e.verdict,
                hmac_signature=e.hmac_signature,
            )
            for e in entries
        ],
        total=total,
    )


# ------------------------------------------------------------------
# Circuit Breaker
# ------------------------------------------------------------------

@router.get("/cb/status")
async def cb_status(
    agent_id: str,
    action: str,
    tenant_id: str = Depends(require_api_key),
) -> CBStatusResponse:
    """Get circuit breaker status for an action."""
    status_dict = get_cb_pool().get_status(tenant_id, agent_id, action)
    from maref.gaas.models import CircuitBreakerState
    return CBStatusResponse(
        tenant_id=tenant_id,
        agent_id=agent_id,
        action=action,
        state=CircuitBreakerState(status_dict["state"]),
        failure_count=status_dict["failure_count"],
        last_trip_time=status_dict.get("last_trip_time"),
    )


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------

@router.get("/health")
async def health() -> dict[str, str]:
    """Service health check."""
    return {"status": "healthy", "service": "gaas"}


# ------------------------------------------------------------------
# Execution Sessions (for long task chains)
# ------------------------------------------------------------------

from maref.gaas.session_manager import (
    cleanup_stale_sessions,
    complete_session,
    declare_session,
    get_active_sessions,
    get_session,
    is_session_active,
    increment_step,
)

cleanup_stale_sessions()


@router.post("/session/declare", response_model=SessionDeclareResponse)
async def session_declare(
    req: SessionDeclareRequest,
    tenant_id: str = Depends(require_api_key),
) -> SessionDeclareResponse:
    """Declare a new execution session for long-running tasks."""
    try:
        sess = declare_session(
            agent_id=req.agent_id,
            goal=req.goal,
            max_steps=req.max_steps,
            completion_criteria=req.completion_criteria,
            trust_level=req.trust_level,
        )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SessionDeclareResponse(
        session_id=sess.session_id,
        agent_id=sess.agent_id,
        goal=sess.goal,
        max_steps=sess.max_steps,
        steps=sess.steps,
        remaining_steps=sess.max_steps - sess.steps,
        created_at=sess.created_at,
        status="active",
    )


@router.get("/session/active", response_model=SessionListResponse)
async def session_list_active(
    agent_id: str | None = None,
    tenant_id: str = Depends(require_api_key),
) -> SessionListResponse:
    """List active sessions, optionally filtered by agent_id."""
    sessions = get_active_sessions(agent_id)
    return SessionListResponse(
        sessions=[_session_to_status(s) for s in sessions],
        count=len(sessions),
    )


@router.get("/session/{session_id}", response_model=SessionStatusResponse)
async def session_status(
    session_id: str,
    tenant_id: str = Depends(require_api_key),
) -> SessionStatusResponse:
    """Get a specific session's status."""
    sess = get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_to_status(sess)


@router.post("/session/{session_id}/complete", response_model=SessionStatusResponse)
async def session_complete(
    session_id: str,
    req: SessionCompleteRequest,
    tenant_id: str = Depends(require_api_key),
) -> SessionStatusResponse:
    """Complete a session and adjust trust score."""
    sess = complete_session(session_id, success=req.success, result=req.result)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    # Adjust trust score based on session outcome
    ts = get_trust_service()
    current = ts.get_score(tenant_id, sess.agent_id) or 50.0
    if req.success:
        new_score = min(100.0, current + 3.0)
        reason = f"session_complete:success:{session_id}"
    else:
        new_score = max(0.0, current - 5.0)
        reason = f"session_complete:failure:{session_id}"
    ts.set_score(tenant_id, sess.agent_id, new_score, reason=reason)

    return _session_to_status(sess)


@router.post("/session/{session_id}/step", response_model=SessionStepResponse)
async def session_step(
    session_id: str,
    tenant_id: str = Depends(require_api_key),
) -> SessionStepResponse:
    """Increment step counter for a session."""
    sess = increment_step(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionStepResponse(
        session_id=sess.session_id,
        steps=sess.steps,
        remaining_steps=sess.max_steps - sess.steps,
        is_active=is_session_active(session_id),
    )


def _session_to_status(sess: Any) -> SessionStatusResponse:
    """Convert a Session dataclass to SessionStatusResponse."""
    if is_session_active(sess.session_id):
        status = "active"
    elif sess.success is True:
        status = "completed"
    elif sess.success is False:
        status = "failed"
    else:
        status = "terminated"
    return SessionStatusResponse(
        session_id=sess.session_id,
        agent_id=sess.agent_id,
        goal=sess.goal,
        max_steps=sess.max_steps,
        steps=sess.steps,
        remaining_steps=sess.max_steps - sess.steps,
        completion_criteria=sess.completion_criteria,
        created_at=sess.created_at,
        completed_at=sess.completed_at,
        success=sess.success,
        result=sess.result,
        status=status,
    )
