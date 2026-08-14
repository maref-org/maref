"""Organization governance API (v0.49 P7) — sidecar REST surface for the
GovernedPipeline's federated consensus and task preflight.

v0.48 W-track gap: the GovernedPipeline assembled ``consensus`` and
``task_preflight`` but never exposed them over HTTP. This router wires them to
``/api/v1/federation/*`` so external orchestrators (and the GUI) can drive
organization-level governance decisions.

The router reads the assembled :class:`~maref.governance.governed_pipeline.GovernedPipeline`
from ``app.state.governed`` (assembled by ``sidecar/server.py`` W2). If it is
absent, endpoints return 503 (fail-closed).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from sidecar.api_auth import require_auth

router = APIRouter(prefix="/api/v1/federation", tags=["organization-governance"])

_PIPELINE_ATTR = "governed"


def _governed(request: Request) -> Any:
    """Resolve the assembled GovernedPipeline; 503 if not wired (fail-closed)."""
    governed = getattr(request.app.state, _PIPELINE_ATTR, None)
    if governed is None:
        raise HTTPException(
            status_code=503,
            detail="GovernedPipeline not assembled on this sidecar",
        )
    return governed


def _parse_choice(choice: str) -> Any:
    """Parse a vote choice string into a ``VoteChoice`` (400 on invalid)."""
    from maref.governance.federated_consensus import VoteChoice

    try:
        return VoteChoice(choice)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid choice '{choice}': must be 'approve' or 'reject'",
        ) from exc


# ── Consensus ────────────────────────────────────────────────────────────────

@router.get("/consensus/summary")
@require_auth(scope="federation:read")
def consensus_summary(request: Request) -> dict[str, Any]:
    return _governed(request).consensus.summary()


@router.get("/consensus/membership")
@require_auth(scope="federation:read")
def consensus_membership(request: Request) -> dict[str, Any]:
    consensus = _governed(request).consensus
    return {
        "member_count": consensus.member_count,
        "quorum_size": consensus.quorum_size,
        "membership_enforced": consensus.membership_enforced,
        "topology": consensus.topology.value,
    }


@router.get("/consensus/proposals")
@require_auth(scope="federation:read")
def consensus_list_proposals(
    request: Request, state: str | None = None
) -> dict[str, Any]:
    from maref.governance.federated_consensus import ProposalState

    consensus = _governed(request).consensus
    if state is not None:
        try:
            state_enum = ProposalState(state)
        except ValueError as exc:
            valid = ", ".join(sorted({v.value for v in ProposalState}))
            raise HTTPException(
                status_code=400,
                detail=f"Invalid state '{state}': must be one of {valid}",
            ) from exc
        proposals = consensus.list_proposals(state_enum)
    else:
        proposals = consensus.list_proposals()
    return {"proposals": [p.to_dict() for p in proposals]}


@router.post("/consensus/propose")
@require_auth(scope="federation:write")
def consensus_propose(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    proposer_id = body.get("proposer_id")
    topic = body.get("topic")
    if not proposer_id or not topic:
        raise HTTPException(status_code=400, detail="proposer_id and topic are required")
    proposal = _governed(request).consensus.propose(
        proposer_id=proposer_id,
        topic=topic,
        payload=body.get("payload", {}),
        is_critical=body.get("is_critical"),
    )
    return {
        "proposal_id": proposal.proposal_id,
        "status": proposal.state.value,
        "proposal_digest": proposal.proposal_digest(),
    }


@router.post("/consensus/{proposal_id}/vote")
@require_auth(scope="federation:write")
def consensus_vote(
    request: Request, proposal_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    voter_id = body.get("voter_id")
    choice = _parse_choice(body.get("choice", ""))
    if not voter_id:
        raise HTTPException(status_code=400, detail="voter_id is required")
    consensus = _governed(request).consensus
    if consensus.get_proposal(proposal_id) is None:
        raise HTTPException(status_code=404, detail=f"Proposal not found: {proposal_id}")
    accepted = consensus.vote(
        proposal_id=proposal_id,
        voter_id=voter_id,
        choice=choice,
        reason=body.get("reason", ""),
    )
    # v0.53 F3: 投票后自动尝试结算，使提案在达 quorum / 过期时即时进入终态。
    consensus.resolve(proposal_id)
    proposal = consensus.get_proposal(proposal_id)
    return {
        "accepted": accepted,
        "proposal_id": proposal_id,
        "status": proposal.state.value if proposal else "unknown",
        "approve_count": proposal.approve_count if proposal else 0,
        "reject_count": proposal.reject_count if proposal else 0,
    }


@router.post("/consensus/{proposal_id}/resolve")
@require_auth(scope="federation:write")
def consensus_resolve(request: Request, proposal_id: str) -> dict[str, Any]:
    """手动触发提案结算（v0.53 F3）。

    达 quorum → ACCEPTED/REJECTED；过期 → EXPIRED；票数不足/平票 → 保持 OPEN。
    """
    consensus = _governed(request).consensus
    if consensus.get_proposal(proposal_id) is None:
        raise HTTPException(status_code=404, detail=f"Proposal not found: {proposal_id}")
    proposal = consensus.resolve(proposal_id)
    return {
        "proposal_id": proposal_id,
        "status": proposal.state.value if proposal else "unknown",
        "approve_count": proposal.approve_count if proposal else 0,
        "reject_count": proposal.reject_count if proposal else 0,
        "resolution_signature": getattr(proposal, "resolution_signature", "") or "",
    }


@router.get("/consensus/{proposal_id}")
@require_auth(scope="federation:read")
def consensus_get(request: Request, proposal_id: str) -> dict[str, Any]:
    proposal = _governed(request).consensus.get_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"Proposal not found: {proposal_id}")
    return proposal.to_dict()


# ── Task preflight ───────────────────────────────────────────────────────────

@router.get("/preflight/status")
@require_auth(scope="federation:read")
def preflight_status(request: Request) -> dict[str, Any]:
    preflight = _governed(request).task_preflight
    checks = [type(c).__name__ for c in preflight.checks]
    return {"checks": checks, "count": len(checks)}


@router.post("/preflight")
@require_auth(scope="federation:execute")
def preflight_run(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    context = body.get("context", {})
    result = _governed(request).task_preflight.execute(context)
    return result.to_dict()


# ── Unified govern (P0-1 wiring) ───────────────────────────────────────────────

@router.post("/govern")
@require_auth(scope="federation:execute")
def governed_govern(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """Execute the unified governance pipeline (boundary + CB + policy + HITL).

    Closes the S6 loop: every governance decision is audited onto the shared
    audit bus that the behavior probe subscribes to.
    """
    from maref.governance.core_pipeline import GovernanceRequest

    action = body.get("action", "")
    agent_id = body.get("agent_id", "")
    if not action or not agent_id:
        raise HTTPException(status_code=400, detail="action and agent_id are required")

    core_req = GovernanceRequest(
        action=action,
        agent_id=agent_id,
        tenant_id=body.get("tenant_id", "default"),
        parameters=body.get("parameters", {}),
        recursion_depth=int(body.get("recursion_depth", 0)),
        trust_score=float(body.get("trust_score", 50.0)),
        role=body.get("role", "坎"),
        session_id=body.get("session_id", ""),
    )
    result = _governed(request).govern(core_req)
    return {
        "verdict": result.verdict.value,
        "reason": result.reason,
        "matched_rule": result.matched_rule,
        "hitl_tier": result.hitl_tier.name if result.hitl_tier else None,
        "hitl_event_id": result.hitl_event_id,
        "latency_ms": result.latency_ms,
    }


__all__ = ["router"]
