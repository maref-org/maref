"""Governance operations API — content, provenance, policy, and evidence.

Exposes the enterprise governance modules through a stable ``/api/v1`` surface
so the GUI, CI jobs, and external orchestrators do not need Python imports.
All mutation endpoints require an explicit scope; the router is mounted by both
``SidecarFastAPI`` and ``create_app``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from maref.governance.ops_service import GovernanceOpsService, get_ops_service
from sidecar.api_auth import require_auth


class ContentReviewRequest(BaseModel):
    platform: str = Field(..., min_length=1)
    text: str = ""
    media_types: list[str] = Field(default_factory=list)
    ai_generated: bool = False
    disclosure: str = ""
    provenance_asset_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProvenanceRequest(BaseModel):
    asset_id: str = Field(..., min_length=1)
    content: str | None = None
    content_hash: str = ""
    license: str = "unknown"
    sources: list[dict[str, Any]] = Field(default_factory=list)
    ai_generated: bool = False
    model: str = ""
    prompt_hash: str = ""
    parent_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PublishableRequest(BaseModel):
    asset_id: str = Field(..., min_length=1)


class OrgCheckRequest(BaseModel):
    org_id: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)


class MarketplacePreflightRequest(BaseModel):
    capability: str = Field(..., min_length=1)
    license: str = "unknown"
    publisher_trust: float = 0.0
    validation: dict[str, Any] | bool | None = None
    asset_id: str = ""
    signed_card: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackRequest(BaseModel):
    evidence_id: str = Field(..., min_length=1)
    outcome: str = Field(..., min_length=1)
    reviewer: str = ""
    score: float | None = None
    notes: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


def create_governance_ops_router(
    service: GovernanceOpsService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/governance/ops", tags=["governance-ops"])

    def svc() -> GovernanceOpsService:
        return service or get_ops_service()

    @router.get("/status")
    @require_auth(scope="governance:read")
    def ops_status() -> dict[str, Any]:
        return svc().status()

    @router.post("/content/review")
    @require_auth(scope="governance:execute")
    def review_content(body: ContentReviewRequest) -> dict[str, Any]:
        return svc().review_content(body.model_dump())

    @router.post("/provenance/assets")
    @require_auth(scope="governance:write")
    def register_asset(body: ProvenanceRequest) -> dict[str, Any]:
        try:
            return svc().register_asset(body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/provenance/assets/{asset_id}")
    @require_auth(scope="governance:read")
    def get_asset(asset_id: str) -> dict[str, Any]:
        asset = svc().get_asset(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="asset not found")
        return asset

    @router.get("/provenance/assets/{asset_id}/lineage")
    @require_auth(scope="governance:read")
    def get_lineage(asset_id: str) -> dict[str, Any]:
        try:
            return svc().lineage(asset_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="asset not found") from exc

    @router.get("/provenance/manifest")
    @require_auth(scope="governance:read")
    def get_manifest(
        asset_ids: str = Query("", description="Comma-separated asset ids"),
    ) -> dict[str, Any]:
        ids = [item.strip() for item in asset_ids.split(",") if item.strip()]
        return svc().manifest(ids or None)

    @router.post("/provenance/publishable")
    @require_auth(scope="governance:read")
    def check_publishable(body: PublishableRequest) -> dict[str, Any]:
        return svc().check_publishable(body.asset_id)

    @router.post("/org/check")
    @require_auth(scope="governance:read")
    def org_check(body: OrgCheckRequest) -> dict[str, Any]:
        try:
            return svc().org_check(body.org_id, body.role, body.action)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/marketplace/preflight")
    @require_auth(scope="governance:read")
    def marketplace_preflight(body: MarketplacePreflightRequest) -> dict[str, Any]:
        return svc().marketplace_preflight(body.model_dump())

    @router.get("/evidence/bundle")
    @require_auth(scope="governance:read")
    def evidence_bundle(
        since: float | None = Query(None, description="Unix timestamp lower bound"),
        limit: int = Query(5000, ge=1, le=50000),
    ) -> dict[str, Any]:
        return svc().evidence_bundle(since=since, limit=limit)

    @router.get("/flywheel/report")
    @require_auth(scope="governance:read")
    def flywheel_report(
        since: float | None = Query(None, description="Unix timestamp lower bound"),
        deny_rate_threshold: float = Query(0.35, ge=0.0, le=1.0),
        evidence_coverage_threshold: float = Query(0.95, ge=0.0, le=1.0),
    ) -> dict[str, Any]:
        return svc().flywheel_report(
            since=since,
            deny_rate_threshold=deny_rate_threshold,
            evidence_coverage_threshold=evidence_coverage_threshold,
        )

    @router.post("/flywheel/feedback")
    @require_auth(scope="governance:write")
    def record_feedback(body: FeedbackRequest) -> dict[str, Any]:
        try:
            return svc().record_feedback(body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router


router = create_governance_ops_router()
