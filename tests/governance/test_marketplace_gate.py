"""Tests for marketplace listing governance (P3-A)."""

from __future__ import annotations

from pathlib import Path

import pytest

from maref.governance.content_provenance import ProvenanceLedger
from maref.governance.marketplace_gate import (
    MarketplaceGovernanceGate,
    MarketplacePolicyError,
)
from maref.marketplace.registry import SkillValidationResult
from maref.recursive.agent_marketplace import AgentMarketplace, CapabilityListing


def _validation(passed: bool = True) -> SkillValidationResult:
    result = SkillValidationResult(skill_id="s1")
    result.static_scan_passed = passed
    result.sandbox_test_passed = passed
    result.manual_review_passed = passed
    return result


def _listing(capability: str = "file.read", license: str = "MIT", signed: bool = True) -> CapabilityListing:
    return CapabilityListing(
        agent_id="agent-1",
        capability=capability,
        license=license,
        signed_card="card" if signed else "",
    )


def test_valid_low_risk_listing_is_allowed():
    decision = MarketplaceGovernanceGate().review_listing(
        _listing(), publisher_trust=0.9, validation=_validation()
    )
    assert decision.allowed is True
    assert decision.risk_level == "low"


def test_low_trust_is_denied():
    decision = MarketplaceGovernanceGate().review_listing(
        _listing(), publisher_trust=0.2, validation=_validation()
    )
    assert decision.allowed is False
    assert "raise_publisher_trust" in decision.required_actions


def test_license_is_enforced():
    decision = MarketplaceGovernanceGate().review_listing(
        _listing(license="GPL-3.0"), publisher_trust=0.9, validation=_validation()
    )
    assert decision.allowed is False
    assert "provide_allowed_license" in decision.required_actions


def test_missing_validation_is_denied():
    decision = MarketplaceGovernanceGate().review_listing(
        _listing(), publisher_trust=0.9, validation=None
    )
    assert decision.allowed is False
    assert "run_static_scan_and_sandbox" in decision.required_actions


def test_failed_validation_is_denied():
    decision = MarketplaceGovernanceGate().review_listing(
        _listing(), publisher_trust=0.9, validation=_validation(passed=False)
    )
    assert decision.allowed is False
    assert "pass_static_scan_sandbox_and_review" in decision.required_actions


def test_high_risk_capability_requires_signed_card_and_trust():
    gate = MarketplaceGovernanceGate()
    denied = gate.review_listing(
        _listing(capability="shell.exec", signed=False),
        publisher_trust=0.9,
        validation=_validation(),
    )
    assert denied.allowed is False
    assert denied.risk_level == "high"
    assert "sign_capability_card" in denied.required_actions

    allowed = gate.review_listing(
        _listing(capability="shell.exec", signed=True),
        publisher_trust=0.9,
        validation=_validation(),
    )
    assert allowed.allowed is True


def test_provenance_license_blocks_listing(tmp_path: Path):
    ledger = ProvenanceLedger(tmp_path / "prov.jsonl")
    ledger.register("asset-1", content="payload", license="unknown")
    decision = MarketplaceGovernanceGate(require_provenance=True).review_listing(
        _listing(),
        publisher_trust=0.9,
        validation=_validation(),
        provenance=ledger,
        asset_id="asset-1",
    )
    assert decision.allowed is False
    assert any("provenance" in reason for reason in decision.reasons)


def test_missing_required_provenance_blocks_listing():
    decision = MarketplaceGovernanceGate(require_provenance=True).review_listing(
        _listing(), publisher_trust=0.9, validation=_validation()
    )
    assert decision.allowed is False
    assert "register_provenance" in decision.required_actions


def test_marketplace_publish_blocks_rejected_listing():
    marketplace = AgentMarketplace(governance_gate=MarketplaceGovernanceGate())
    listing = CapabilityListing(
        agent_id="agent-1",
        capability="file.read",
        license="MIT",
        metadata={"publisher_trust": 0.1, "validation": _validation()},
    )
    with pytest.raises(MarketplacePolicyError):
        marketplace.publish(listing)
    assert marketplace.discover("file.read") == []


def test_empty_allowlist_denies_every_license():
    gate = MarketplaceGovernanceGate(allowed_licenses=[])
    decision = gate.review_listing(
        _listing(), publisher_trust=0.9, validation=_validation()
    )
    assert decision.allowed is False
    assert any("license" in reason for reason in decision.reasons)


def test_dict_validation_evidence_is_honored():
    gate = MarketplaceGovernanceGate()
    passed = gate.review_listing(
        _listing(), publisher_trust=0.9, validation={"all_passed": True}
    )
    assert passed.allowed is True
    failed = gate.review_listing(
        _listing(), publisher_trust=0.9, validation={"all_passed": False}
    )
    assert failed.allowed is False


def test_boolean_validation_evidence_is_honored():
    gate = MarketplaceGovernanceGate()
    assert gate.review_listing(_listing(), publisher_trust=0.9, validation=True).allowed
    assert not gate.review_listing(_listing(), publisher_trust=0.9, validation=False).allowed
