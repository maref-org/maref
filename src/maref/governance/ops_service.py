"""Shared operations service for Sidecar API and CLI (P3 productionization).

The service is intentionally framework-free: both the FastAPI router and the
Typer CLI call the same methods, so a decision made through either surface has
identical provenance, audit, HITL, and evidence semantics.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from maref.governance.audit import AuditEntry
from maref.governance.content_provenance import ProvenanceLedger
from maref.governance.marketplace_gate import (
    MarketplaceDecision,
    MarketplaceGovernanceGate,
)
from maref.governance.org_policy import OrganizationPolicy
from maref.governance.regulatory_evidence import EvidenceBundle, RegulatoryEvidenceMapper
from maref.governance.social_content_gate import (
    SocialContentGate,
    SocialContentRequest,
)
from maref.governance.value_flywheel import FlywheelReport, GovernanceFlywheel


def _data_dir() -> Path:
    return Path(os.environ.get("MAREF_GOVERNANCE_DATA_DIR", "data/governance"))


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class GovernanceOpsService:
    """Production facade over content, provenance, policy, and evidence checks."""

    def __init__(
        self,
        *,
        audit_path: str | Path | None = None,
        provenance_path: str | Path | None = None,
        feedback_path: str | Path | None = None,
        org_policy_path: str | Path | None = None,
        hmac_key: str | None = None,
        provenance: ProvenanceLedger | None = None,
        org_policy: OrganizationPolicy | None = None,
        social_gate: SocialContentGate | None = None,
        marketplace_gate: MarketplaceGovernanceGate | None = None,
        flywheel: GovernanceFlywheel | None = None,
        evidence_mapper: RegulatoryEvidenceMapper | None = None,
        pipeline: Any | None = None,
    ) -> None:
        root = _data_dir()
        self.audit_path = Path(audit_path) if audit_path else root / "pipeline_audit.jsonl"
        self.provenance_path = (
            Path(provenance_path) if provenance_path else root / "provenance.jsonl"
        )
        self.feedback_path = Path(feedback_path) if feedback_path else root / "feedback.jsonl"
        env_policy = os.environ.get("MAREF_ORG_POLICY_PATH", "")
        self.org_policy_path: Path | None = (
            Path(org_policy_path)
            if org_policy_path
            else (Path(env_policy) if env_policy else None)
        )
        self.hmac_key = hmac_key or os.environ.get("MAREF_HMAC_SECRET_KEY")
        self.provenance = provenance or ProvenanceLedger(self.provenance_path)
        self.org_policy = org_policy
        if self.org_policy is None and self.org_policy_path is not None:
            if self.org_policy_path.exists():
                self.org_policy = OrganizationPolicy.from_path(self.org_policy_path)
        self.social_gate = social_gate or SocialContentGate(
            provenance=self.provenance,
            require_provenance=_env_bool("MAREF_REQUIRE_CONTENT_PROVENANCE"),
        )
        self.marketplace_gate = marketplace_gate or MarketplaceGovernanceGate(
            require_provenance=_env_bool("MAREF_REQUIRE_MARKETPLACE_PROVENANCE"),
        )
        self.flywheel = flywheel or GovernanceFlywheel(self.feedback_path)
        self.evidence_mapper = evidence_mapper or RegulatoryEvidenceMapper()
        self._pipeline = pipeline
        self._pipeline_lock = threading.RLock()

    @property
    def pipeline(self) -> Any:
        with self._pipeline_lock:
            if self._pipeline is None:
                from maref.governance.governed_pipeline import GovernedPipeline

                self._pipeline = GovernedPipeline(
                    audit_path=self.audit_path,
                    hmac_key=self.hmac_key,
                    org_policy=self.org_policy,
                    social_content_gate=self.social_gate,
                )
            return self._pipeline

    def status(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "audit_path": str(self.audit_path),
            "provenance_path": str(self.provenance_path),
            "feedback_path": str(self.feedback_path),
            "org_policy_loaded": self.org_policy is not None,
            "org_policy_path": str(self.org_policy_path) if self.org_policy_path else "",
            "platforms": sorted(self.social_gate.platforms),
            "provenance_integrity": self.provenance.verify_integrity(),
        }

    def review_content(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = SocialContentRequest(
            platform=str(payload.get("platform", "")),
            text=str(payload.get("text", "")),
            media_types=[str(item) for item in payload.get("media_types", [])],
            ai_generated=bool(payload.get("ai_generated", False)),
            disclosure=str(payload.get("disclosure", "")),
            provenance_asset_id=str(payload.get("provenance_asset_id", "")),
            metadata=dict(payload.get("metadata") or {}),
        )
        return self.pipeline.review_social_content(request).to_dict()

    def register_asset(self, payload: dict[str, Any]) -> dict[str, Any]:
        asset = self.provenance.register(
            str(payload.get("asset_id", "")),
            content=payload.get("content"),
            content_hash=str(payload.get("content_hash", "")),
            license=str(payload.get("license", "")),
            sources=payload.get("sources") or (),
            ai_generated=bool(payload.get("ai_generated", False)),
            model=str(payload.get("model", "")),
            prompt_hash=str(payload.get("prompt_hash", "")),
            parent_ids=[str(item) for item in payload.get("parent_ids", [])],
            metadata=dict(payload.get("metadata") or {}),
        )
        return asset.to_dict()

    def get_asset(self, asset_id: str) -> dict[str, Any] | None:
        asset = self.provenance.get(asset_id)
        return asset.to_dict() if asset is not None else None

    def lineage(self, asset_id: str) -> dict[str, Any]:
        chain = self.provenance.lineage(asset_id)
        return {
            "asset_id": asset_id,
            "lineage": [asset.to_dict() for asset in chain],
            "integrity": self.provenance.verify_integrity(),
        }

    def manifest(self, asset_ids: list[str] | None = None) -> dict[str, Any]:
        return self.provenance.export_manifest(asset_ids)

    def check_publishable(self, asset_id: str) -> dict[str, Any]:
        return self.provenance.check_publishable(asset_id).to_dict()

    def org_check(self, org_id: str, role: str, action: str) -> dict[str, Any]:
        if self.org_policy is None:
            raise ValueError("organization policy is not configured")
        decision = self.org_policy.evaluate(org_id, role, action)
        return {
            "org_id": org_id,
            "role": role,
            "action": action,
            "decision": decision.decision,
            "reason": decision.reason,
            "policy_version": decision.policy_version,
            "policy_epoch": decision.policy_epoch,
            "matched_rule": decision.matched_rule,
        }

    def marketplace_preflight(self, payload: dict[str, Any]) -> dict[str, Any]:
        listing = SimpleNamespace(
            capability=str(payload.get("capability", "")),
            license=str(payload.get("license", "unknown")),
            signed_card=str(payload.get("signed_card", "")),
            metadata=dict(payload.get("metadata") or {}),
        )
        validation_data = payload.get("validation")
        validation = None
        if isinstance(validation_data, dict):
            validation = SimpleNamespace(
                all_passed=bool(validation_data.get("all_passed", False))
            )
        elif isinstance(validation_data, bool):
            validation = SimpleNamespace(all_passed=validation_data)
        decision: MarketplaceDecision = self.marketplace_gate.review_listing(
            listing,
            publisher_trust=float(payload.get("publisher_trust", 0.0)),
            validation=validation,
            provenance=self.provenance,
            asset_id=str(payload.get("asset_id", "")),
        )
        return decision.to_dict()

    def audit_entries(
        self, *, since: float | None = None, limit: int = 1000
    ) -> list[AuditEntry]:
        entries = self.pipeline.audit.read_all(max_entries=limit)
        if since is not None:
            entries = [entry for entry in entries if entry.timestamp >= since]
        return entries

    def evidence_bundle(
        self, *, since: float | None = None, limit: int = 5000
    ) -> dict[str, Any]:
        entries = self.pipeline.audit.read_all(max_entries=limit)
        if since is not None:
            entries = [entry for entry in entries if entry.timestamp >= since]
        bundle: EvidenceBundle = self.evidence_mapper.map_entries(entries)
        return bundle.to_dict()

    def flywheel_report(
        self,
        *,
        since: float | None = None,
        deny_rate_threshold: float = 0.35,
        evidence_coverage_threshold: float = 0.95,
    ) -> dict[str, Any]:
        report: FlywheelReport = self.flywheel.run_cycle(
            self.pipeline.audit.read_all(max_entries=5000),
            since=since,
            deny_rate_threshold=deny_rate_threshold,
            evidence_coverage_threshold=evidence_coverage_threshold,
        )
        return report.to_dict()

    def record_feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.flywheel.record_feedback(
            str(payload.get("evidence_id", "")),
            str(payload.get("outcome", "")),
            reviewer=str(payload.get("reviewer", "")),
            score=payload.get("score"),
            notes=str(payload.get("notes", "")),
            metadata=dict(payload.get("metadata") or {}),
        )


_default_service: GovernanceOpsService | None = None
_default_service_lock = threading.Lock()


def get_ops_service() -> GovernanceOpsService:
    global _default_service
    with _default_service_lock:
        if _default_service is None:
            _default_service = GovernanceOpsService()
        return _default_service


def configure_ops_service(service: GovernanceOpsService | None) -> None:
    global _default_service
    with _default_service_lock:
        _default_service = service


def reset_ops_service() -> None:
    configure_ops_service(None)
