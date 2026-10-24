"""Tests for commercial action policy and model-route evidence (P0-A)."""

from __future__ import annotations

from pathlib import Path

import pytest

from maref.crypto.ed25519_keys import Ed25519KeyPair
from maref.governance.audit import AuditLogger
from maref.governance.commercial_policy import (
    CommercialActionPolicy,
    CommercialRiskLevel,
)
from maref.governance.core_pipeline import GovernanceRequest, Verdict
from maref.governance.governed_pipeline import GovernedPipeline
from maref.governance.model_route import (
    ModelRouteDecision,
    ModelRouteRecorder,
    RouteAttestationError,
    RouteIngestAdapter,
    attest_external_route,
    canonical_bytes,
)

POLICY_PATH = Path(__file__).resolve().parents[2] / "configs" / "commercial_actions.yaml"


@pytest.fixture
def audit(tmp_path):
    return AuditLogger(log_path=tmp_path / "audit.jsonl", hmac_key=b"test-key")


@pytest.fixture
def policy():
    return CommercialActionPolicy.from_path(POLICY_PATH)


def _decision(**overrides) -> ModelRouteDecision:
    base = {
        "trace_id": "trace-1",
        "tenant_id": "tenant-a",
        "agent_id": "agent-1",
        "requested_model": "gpt-x",
        "selected_model": "gpt-y",
        "provider": "openai",
        "model_version": "2026-01",
        "route_policy_id": "route-policy-v1",
        "route_policy_hash": "policy-hash",
    }
    base.update(overrides)
    return ModelRouteDecision(**base)


def test_policy_classifies_action_levels(policy):
    assert policy.classify("catalog.read").level is CommercialRiskLevel.L0
    assert policy.classify("report.generate").level is CommercialRiskLevel.L1
    assert policy.classify("pricing.update").level is CommercialRiskLevel.L2
    assert policy.classify("refund.execute").level is CommercialRiskLevel.L3
    assert policy.classify("unknown.action").level is CommercialRiskLevel.L3
    assert policy.classify("pricing.update").purpose_id == "commerce.pricing.change"


def test_policy_requires_route_for_l2_and_l3(policy):
    assert not policy.requires_route_evidence("catalog.read")
    assert policy.requires_route_evidence("pricing.update")
    assert policy.requires_route_evidence("payment.capture")


def test_policy_rejects_invalid_level():
    with pytest.raises(ValueError):
        CommercialActionPolicy.from_dict(
            {
                "actions": [
                    {"match": "x.*", "level": "L9", "purpose_id": "commerce.x"}
                ]
            }
        )


def test_route_record_and_verify(audit):
    recorder = ModelRouteRecorder(audit)
    recorded = recorder.record(_decision())

    assert recorded.route_decision_id
    assert recorder.verify(
        recorded.route_decision_id,
        tenant_id="tenant-a",
        model_version="2026-01",
    )
    assert not recorder.verify(recorded.route_decision_id, tenant_id="tenant-b")
    assert not recorder.verify(recorded.route_decision_id, model_version="2025-12")
    assert not recorder.verify("missing-route")


def test_route_survives_recorder_restart(audit, tmp_path):
    recorded = ModelRouteRecorder(audit).record(_decision())
    restarted = ModelRouteRecorder(
        AuditLogger(log_path=tmp_path / "audit.jsonl", hmac_key=b"test-key")
    )
    assert restarted.verify(recorded.route_decision_id, tenant_id="tenant-a")


def test_external_attestation_accepted():
    pair = Ed25519KeyPair.generate()
    payload = _decision().to_payload()
    signature = pair.sign(canonical_bytes(payload))

    decision = attest_external_route(payload, signature, pair.public_key_pem)

    assert decision.attestation_hash
    assert decision.selected_model == "gpt-y"


def test_external_attestation_rejects_tampered_payload():
    pair = Ed25519KeyPair.generate()
    payload = _decision().to_payload()
    signature = pair.sign(canonical_bytes(payload))
    payload["selected_model"] = "attacker-model"

    with pytest.raises(RouteAttestationError):
        attest_external_route(payload, signature, pair.public_key_pem)


def test_external_attestation_rejects_wrong_key():
    signer = Ed25519KeyPair.generate()
    other = Ed25519KeyPair.generate()
    payload = _decision().to_payload()
    signature = signer.sign(canonical_bytes(payload))

    with pytest.raises(RouteAttestationError):
        attest_external_route(payload, signature, other.public_key_pem)


def test_external_attestation_replay_rejected(audit):
    pair = Ed25519KeyPair.generate()
    payload = _decision().to_payload()
    signature = pair.sign(canonical_bytes(payload))
    adapter = RouteIngestAdapter(ModelRouteRecorder(audit), pair.public_key_pem)

    adapter.ingest(payload, signature)
    with pytest.raises(RouteAttestationError):
        adapter.ingest(payload, signature)


def test_pipeline_denies_l2_without_route(tmp_path, policy):
    pipeline = GovernedPipeline(
        audit_path=tmp_path / "audit.jsonl",
        hmac_key="test-key",
        commercial_action_policy=policy,
    )
    result = pipeline.govern(
        GovernanceRequest(
            action="pricing.update",
            agent_id="agent-1",
            tenant_id="tenant-a",
            trust_score=80,
        )
    )

    assert result.verdict is Verdict.DENY
    assert result.matched_rule == "commercial_route:missing"
    assert result.evidence_id


def test_pipeline_denies_unknown_route(tmp_path, policy):
    pipeline = GovernedPipeline(
        audit_path=tmp_path / "audit.jsonl",
        hmac_key="test-key",
        commercial_action_policy=policy,
    )
    result = pipeline.govern(
        GovernanceRequest(
            action="pricing.update",
            agent_id="agent-1",
            tenant_id="tenant-a",
            trust_score=80,
            model_route_id="not-a-route",
            model_version="2026-01",
        )
    )

    assert result.verdict is Verdict.DENY
    assert result.matched_rule == "commercial_route:invalid"


def test_pipeline_allows_l2_with_valid_route(tmp_path, policy):
    pipeline = GovernedPipeline(
        audit_path=tmp_path / "audit.jsonl",
        hmac_key="test-key",
        commercial_action_policy=policy,
    )
    recorded = pipeline.route_recorder.record(_decision(tenant_id="tenant-a"))
    result = pipeline.govern(
        GovernanceRequest(
            action="pricing.update",
            agent_id="agent-1",
            tenant_id="tenant-a",
            trust_score=80,
            model_route_id=recorded.route_decision_id,
            model_version="2026-01",
        )
    )

    assert result.verdict is Verdict.ALLOW


def test_pipeline_skips_route_gate_for_l0(tmp_path, policy):
    pipeline = GovernedPipeline(
        audit_path=tmp_path / "audit.jsonl",
        hmac_key="test-key",
        commercial_action_policy=policy,
    )
    result = pipeline.govern(
        GovernanceRequest(
            action="catalog.read",
            agent_id="agent-1",
            tenant_id="tenant-a",
            trust_score=80,
        )
    )

    assert result.verdict is Verdict.ALLOW


def test_pipeline_denies_route_without_model_version(tmp_path, policy):
    pipeline = GovernedPipeline(
        audit_path=tmp_path / "audit.jsonl",
        hmac_key="test-key",
        commercial_action_policy=policy,
    )
    recorded = pipeline.route_recorder.record(_decision(tenant_id="tenant-a"))
    result = pipeline.govern(
        GovernanceRequest(
            action="pricing.update",
            agent_id="agent-1",
            tenant_id="tenant-a",
            trust_score=80,
            model_route_id=recorded.route_decision_id,
        )
    )

    assert result.verdict is Verdict.DENY
    assert result.matched_rule == "commercial_route:missing_model_version"
