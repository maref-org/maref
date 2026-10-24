"""Governance gate for knowledge/skill marketplace listings (P3-A).

Marketplace publishing is a supply-chain boundary: a listing must carry an
acceptable license, publisher trust, validation evidence, and (when the
artifact is generated or sensitive) provenance that resolves in a ledger.
The gate is deliberately independent of the marketplace class so it can be
used by the agent marketplace, skill registry, or an HTTP review endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maref.governance.content_provenance import DEFAULT_ALLOWED_LICENSES, ProvenanceLedger

HIGH_RISK_TERMS = frozenset(
    {"shell", "exec", "delete", "drop", "deploy", "payment", "transfer", "publish"}
)


@dataclass(frozen=True)
class MarketplaceDecision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    required_actions: list[str] = field(default_factory=list)
    risk_level: str = "low"

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "required_actions": list(self.required_actions),
            "risk_level": self.risk_level,
        }


class MarketplacePolicyError(PermissionError):
    """Raised when a listing is rejected by marketplace governance."""

    def __init__(self, decision: MarketplaceDecision) -> None:
        super().__init__("; ".join(decision.reasons) or "marketplace listing rejected")
        self.decision = decision


class MarketplaceGovernanceGate:
    """Review marketplace listings before publication."""

    def __init__(
        self,
        *,
        allowed_licenses: set[str] | frozenset[str] | None = None,
        min_publisher_trust: float = 0.6,
        require_provenance: bool = False,
        require_validation: bool = True,
        high_risk_min_trust: float = 0.8,
    ) -> None:
        self.allowed_licenses = (
            frozenset(allowed_licenses)
            if allowed_licenses is not None
            else DEFAULT_ALLOWED_LICENSES
        )
        self.min_publisher_trust = min_publisher_trust
        self.require_provenance = require_provenance
        self.require_validation = require_validation
        self.high_risk_min_trust = high_risk_min_trust

    def review_listing(
        self,
        listing: Any,
        *,
        publisher_trust: float,
        validation: Any | None = None,
        provenance: ProvenanceLedger | None = None,
        asset_id: str = "",
    ) -> MarketplaceDecision:
        capability = str(
            getattr(listing, "capability", "")
            or getattr(listing, "name", "")
            or (listing.get("capability", "") if isinstance(listing, dict) else "")
        )
        listing_metadata = (
            getattr(listing, "metadata", None)
            or (listing.get("metadata", {}) if isinstance(listing, dict) else {})
            or {}
        )
        license_name = str(
            getattr(listing, "license", "")
            or (listing.get("license", "") if isinstance(listing, dict) else "")
            or listing_metadata.get("license", "")
            or "unknown"
        )
        signed_card = str(
            getattr(listing, "signed_card", "")
            or (listing.get("signed_card", "") if isinstance(listing, dict) else "")
        )
        metadata = listing_metadata
        asset_id = asset_id or str(metadata.get("provenance_asset_id", ""))

        reasons: list[str] = []
        required_actions: list[str] = []
        risk_level = self._risk_level(capability)
        required_trust = (
            self.high_risk_min_trust if risk_level != "low" else self.min_publisher_trust
        )

        if publisher_trust < required_trust:
            reasons.append(
                f"publisher trust {publisher_trust:.2f} below required {required_trust:.2f}"
            )
            required_actions.append("raise_publisher_trust")

        if license_name not in self.allowed_licenses:
            reasons.append(f"license '{license_name}' is not allowed")
            required_actions.append("provide_allowed_license")

        if self.require_validation:
            if validation is None:
                reasons.append("validation evidence is missing")
                required_actions.append("run_static_scan_and_sandbox")
            else:
                if isinstance(validation, dict):
                    validation_passed = bool(validation.get("all_passed", False))
                elif isinstance(validation, bool):
                    validation_passed = validation
                else:
                    validation_passed = bool(getattr(validation, "all_passed", False))
                if not validation_passed:
                    reasons.append("validation gates have not all passed")
                    required_actions.append("pass_static_scan_sandbox_and_review")

        if provenance is not None and asset_id:
            license_decision = provenance.check_publishable(
                asset_id, allowed_licenses=self.allowed_licenses
            )
            if not license_decision.allowed:
                reasons.append(f"provenance check failed: {license_decision.reason}")
                required_actions.append("fix_provenance_or_license")
        elif self.require_provenance:
            reasons.append("provenance ledger entry is required")
            required_actions.append("register_provenance")

        if risk_level != "low" and not signed_card:
            reasons.append(f"risk level '{risk_level}' requires a signed capability card")
            required_actions.append("sign_capability_card")

        return MarketplaceDecision(
            allowed=not reasons,
            reasons=reasons,
            required_actions=required_actions,
            risk_level=risk_level,
        )

    @staticmethod
    def _risk_level(capability: str) -> str:
        normalized = capability.lower()
        hits = [term for term in HIGH_RISK_TERMS if term in normalized]
        if hits:
            return "high"
        return "low"
