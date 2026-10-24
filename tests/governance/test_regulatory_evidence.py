"""Tests for EU AI Act evidence mapping (P2-B)."""

from __future__ import annotations

from maref.governance.audit import AuditEntry
from maref.governance.regulatory_evidence import RegulatoryEvidenceMapper


def _entry(
    entry_id: str,
    event_type: str,
    action: str,
    details: str = "",
    *,
    chain_hash: str = "",
) -> AuditEntry:
    return AuditEntry(
        id=entry_id,
        timestamp=1000.0,
        event_type=event_type,
        actor="agent-1",
        action=action,
        details=details,
        hmac_signature="sig",
        chain_hash=chain_hash or f"hash-{entry_id}",
    )


def test_allow_decision_maps_to_record_keeping():
    bundle = RegulatoryEvidenceMapper().map_entries(
        [_entry("e1", "governance_decision", "file.read", "ALLOW: ok")]
    )
    claims = {claim.obligation.obligation_id: claim for claim in bundle.claims}
    assert claims["Art.12"].event_count == 1
    assert claims["Art.12"].evidence_ids == ["e1"]
    assert bundle.evidence_ids == ["e1"]


def test_deny_maps_to_risk_and_robustness():
    bundle = RegulatoryEvidenceMapper().map_entries(
        [_entry("e1", "governance_decision", "shell.exec", "DENY: blocked")]
    )
    covered = {claim.obligation.obligation_id for claim in bundle.claims if claim.event_count}
    assert {"Art.9", "Art.12", "Art.15"}.issubset(covered)


def test_human_oversight_mapping():
    bundle = RegulatoryEvidenceMapper().map_entries(
        [
            _entry("e1", "governance_decision", "file.write", "ASK_USER: review"),
            _entry("e2", "hitl_decision", "file.write", "approved"),
        ]
    )
    claims = {claim.obligation.obligation_id: claim for claim in bundle.claims}
    assert claims["Art.14"].event_count == 2


def test_incident_maps_to_post_market_monitoring():
    bundle = RegulatoryEvidenceMapper().map_entries(
        [_entry("e1", "incident", "model.failure", "incident reported")]
    )
    claims = {claim.obligation.obligation_id: claim for claim in bundle.claims}
    assert claims["Art.72"].event_count == 1


def test_coverage_and_missing_obligations():
    bundle = RegulatoryEvidenceMapper().map_entries(
        [_entry("e1", "governance_decision", "file.read", "ALLOW: ok")]
    )
    assert 0.0 < bundle.coverage < 1.0
    assert "Art.14" in bundle.missing_obligations
    assert "Art.12" not in bundle.missing_obligations


def test_merkle_root_is_deterministic_and_changes_with_evidence():
    entries = [_entry("e1", "governance_decision", "file.read", "ALLOW: ok")]
    first = RegulatoryEvidenceMapper().map_entries(entries).merkle_root
    second = RegulatoryEvidenceMapper().map_entries(entries).merkle_root
    assert first == second
    changed = RegulatoryEvidenceMapper().map_entries(
        [_entry("e2", "governance_decision", "file.read", "ALLOW: ok")]
    ).merkle_root
    assert changed != first


def test_bundle_applies_to_technical_documentation():
    class FakeDocs:
        def __init__(self) -> None:
            self.merkle_root = ""
            self.evidence_ids: list[str] = []

        def set_audit_evidence(self, merkle_root: str, evidence_ids: list[str]) -> None:
            self.merkle_root = merkle_root
            self.evidence_ids = evidence_ids

    bundle = RegulatoryEvidenceMapper().map_entries(
        [_entry("e1", "governance_decision", "file.read", "ALLOW: ok")]
    )
    docs = FakeDocs()
    bundle.apply_to_technical_documentation(docs)
    assert docs.merkle_root == bundle.merkle_root
    assert docs.evidence_ids == ["e1"]


def test_bundle_export_contains_annex_iv_anchor():
    bundle = RegulatoryEvidenceMapper().map_entries(
        [_entry("e1", "governance_decision", "file.read", "ALLOW: ok")]
    )
    data = bundle.to_dict()
    assert data["annex_iv"]["merkle_root"] == bundle.merkle_root
    assert data["annex_iv"]["evidence_ids"] == ["e1"]
