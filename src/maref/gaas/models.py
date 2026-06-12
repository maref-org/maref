"""GaaS Pydantic models — request/response schemas for multi-tenant governance API."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    ASK_USER = "ASK_USER"
    DEFER = "DEFER"


class CircuitBreakerState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class HITLTier(str, Enum):
    P0 = "p0"
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"


class GovernanceContext(BaseModel):
    session_id: str = ""
    recursion_depth: int = 0
    trust_score: float = Field(default=0.0, ge=0.0, le=100.0)
    source_ip: str = ""
    user_agent: str = ""


class GovernRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    context: GovernanceContext = Field(default_factory=GovernanceContext)


class GovernResponse(BaseModel):
    verdict: Verdict
    circuit_breaker_state: CircuitBreakerState
    audit_log_id: str
    required_hitl_tier: HITLTier | None = None
    estimated_latency_ms: int = 0
    policy_version: str = ""
    reason: str = ""


class HITLRequest(BaseModel):
    tenant_id: str
    agent_id: str
    action: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    tier: HITLTier = HITLTier.P0
    auto_approve_seconds: float = Field(default=30.0, ge=0.0)


class HITLResponse(BaseModel):
    event_id: str
    status: str
    approved: bool | None = None
    reason: str = ""


class TrustScoreRequest(BaseModel):
    tenant_id: str
    agent_id: str


class TrustScoreResponse(BaseModel):
    tenant_id: str
    agent_id: str
    trust_score: float | None = None
    trust_tier: str = ""
    history_count: int = 0
    last_updated: float | None = None


class AuditQueryRequest(BaseModel):
    tenant_id: str
    start_time: float | None = None
    end_time: float | None = None
    agent_id: str | None = None
    action: str | None = None
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class AuditEntry(BaseModel):
    log_id: str
    timestamp: float
    tenant_id: str
    agent_id: str
    action: str
    verdict: str
    hmac_signature: str = ""


class AuditQueryResponse(BaseModel):
    entries: list[AuditEntry]
    total: int


class CBStatusRequest(BaseModel):
    tenant_id: str
    agent_id: str
    action: str


class CBStatusResponse(BaseModel):
    tenant_id: str
    agent_id: str
    action: str
    state: CircuitBreakerState
    failure_count: int
    last_trip_time: float | None = None


# ---------------------------------------------------------------------------
# Execution Session models
# ---------------------------------------------------------------------------


class SessionDeclareRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=50)
    goal: str = Field(default="", max_length=200)
    max_steps: int = Field(default=50, ge=1, le=200)
    completion_criteria: str = Field(default="", max_length=200)
    trust_level: str = Field(default="SEMI_TRUSTED")


class SessionDeclareResponse(BaseModel):
    session_id: str
    agent_id: str
    goal: str
    max_steps: int
    steps: int
    remaining_steps: int
    created_at: float
    status: str


class SessionCompleteRequest(BaseModel):
    success: bool
    result: str = Field(default="", max_length=500)


class SessionStatusResponse(BaseModel):
    session_id: str
    agent_id: str
    goal: str
    max_steps: int
    steps: int
    remaining_steps: int
    completion_criteria: str
    created_at: float
    completed_at: float | None = None
    success: bool | None = None
    result: str = ""
    status: str


class SessionListResponse(BaseModel):
    sessions: list[SessionStatusResponse]
    count: int


class SessionStepResponse(BaseModel):
    session_id: str
    steps: int
    remaining_steps: int
    is_active: bool
