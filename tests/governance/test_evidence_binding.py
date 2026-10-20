"""Tests for purpose-bound evidence verification (P0-C)."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import pytest

from maref.governance.commercial_policy import CommercialActionPolicy
from maref.governance.core_pipeline import GovernanceRequest, Verdict
from maref.governance.governed_pipeline import GovernedPipeline
from maref.governance.interaction_evidence import hash_json
from maref.governance.model_route import ModelRouteDecision, ModelRouteRecorder

POLICY_PATH = Path(__file__).resolve().parents[2] / "configs" / "commercial_actions.yaml"
PARAMS = {"sku": "A-1", "price": 100}
PARAMS_HASH = hash_json(PARAMS)


@pytest.fixture
def pipeline(tmp_path):
    return GovernedPipeline(audit_path=tmp_path / "audit.jsonl", hmac_key="test-key")


def _allow(pipeline: GovernedPipeline, **overrides):
    request = GovernanceRequest(
        action="file.read",
        agent_id="agent-1",
        tenant_id="tenant-a",
        trust_score=80,
        parameters=PARAMS,
        **overrides,
    )
    result = pipeline.govern(request)
    assert result.evidence_id
    return result


def test_correct_binding_passes_and_consumes(pipeline):
    result = _allow(pipeline)

    assert pipeline.verify_evidence_for(
        result.evidence_id,
        action="file.read",
        params_hash=PARAMS_HASH,
        tenant_id="tenant-a",
    )
    assert not pipeline.verify_evidence_for(
        result.evidence_id,
        action="file.read",
        params_hash=PARAMS_HASH,
        tenant_id="tenant-a",
    )


def test_non_consuming_binding_can_be_repeated(pipeline):
    result = _allow(pipeline)

    for _ in range(2):
        assert pipeline.verify_evidence_for(
            result.evidence_id,
            action="file.read",
            params_hash=PARAMS_HASH,
            tenant_id="tenant-a",
            consume=False,
        )
    assert pipeline.verify_evidence_for(
        result.evidence_id,
        action="file.read",
        params_hash=PARAMS_HASH,
        tenant_id="tenant-a",
    )


def test_binding_rejects_other_action(pipeline):
    result = _allow(pipeline)

    assert not pipeline.verify_evidence_for(
        result.evidence_id,
        action="file.write",
        params_hash=PARAMS_HASH,
        tenant_id="tenant-a",
        consume=False,
    )


def test_binding_rejects_other_params(pipeline):
    result = _allow(pipeline)

    assert not pipeline.verify_evidence_for(
        result.evidence_id,
        action="file.read",
        params_hash=hash_json({"sku": "B-2", "price": 1}),
        tenant_id="tenant-a",
        consume=False,
    )


def test_binding_rejects_other_tenant(pipeline):
    result = _allow(pipeline)

    assert not pipeline.verify_evidence_for(
        result.evidence_id,
        action="file.read",
        params_hash=PARAMS_HASH,
        tenant_id="tenant-b",
        consume=False,
    )


def test_binding_rejects_other_org(pipeline):
    result = _allow(pipeline)

    assert not pipeline.verify_evidence_for(
        result.evidence_id,
        action="file.read",
        params_hash=PARAMS_HASH,
        tenant_id="tenant-a",
        org_id="org-other",
        consume=False,
    )


def test_binding_rejects_other_route_model_and_detector(pipeline):
    result = _allow(
        pipeline,
        model_route_id="route-x",
        model_version="2026-01",
        detector_set_hash="detector-x",
    )
    base = {
        "action": "file.read",
        "params_hash": PARAMS_HASH,
        "tenant_id": "tenant-a",
        "consume": False,
    }

    assert not pipeline.verify_evidence_for(
        result.evidence_id, **base, route_decision_id="route-y"
    )
    assert not pipeline.verify_evidence_for(
        result.evidence_id, **base, model_version="2025-12"
    )
    assert not pipeline.verify_evidence_for(
        result.evidence_id, **base, detector_set_hash="detector-y"
    )
    assert pipeline.verify_evidence_for(
        result.evidence_id,
        **base,
        route_decision_id="route-x",
        model_version="2026-01",
        detector_set_hash="detector-x",
    )


def test_binding_uses_policy_purpose_not_request_input(tmp_path):
    policy = CommercialActionPolicy.from_path(POLICY_PATH)
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
            parameters={**PARAMS, "purpose_id": "commerce.payment.execute"},
        )
    )
    assert result.evidence_id
    params_with_spoof = {**PARAMS, "purpose_id": "commerce.payment.execute"}
    base = {
        "action": "catalog.read",
        "params_hash": hash_json(params_with_spoof),
        "tenant_id": "tenant-a",
        "consume": False,
    }

    # A caller-supplied purpose_id must not override the policy purpose.
    assert not pipeline.verify_evidence_for(
        result.evidence_id, **base, purpose_id="commerce.payment.execute"
    )
    assert pipeline.verify_evidence_for(
        result.evidence_id, **base, purpose_id="commerce.catalog.read"
    )


def test_binding_survives_pipeline_restart(tmp_path):
    first = GovernedPipeline(audit_path=tmp_path / "audit.jsonl", hmac_key="test-key")
    result = _allow(first)

    second = GovernedPipeline(audit_path=tmp_path / "audit.jsonl", hmac_key="test-key")
    assert second.verify_evidence_for(
        result.evidence_id,
        action="file.read",
        params_hash=PARAMS_HASH,
        tenant_id="tenant-a",
    )


def test_binding_rejects_non_decision_evidence(tmp_path):
    pipeline = GovernedPipeline(audit_path=tmp_path / "audit.jsonl", hmac_key="test-key")
    route = ModelRouteRecorder(pipeline.audit).record(
        ModelRouteDecision(
            trace_id="trace-1",
            tenant_id="tenant-a",
            agent_id="agent-1",
            requested_model="gpt-x",
            selected_model="gpt-y",
            provider="openai",
            model_version="2026-01",
            route_policy_id="route-policy-v1",
            route_policy_hash="policy-hash",
        )
    )

    assert not pipeline.verify_evidence_for(
        route.route_decision_id,
        action="file.read",
        params_hash=PARAMS_HASH,
        tenant_id="tenant-a",
        consume=False,
    )


def test_binding_rejects_tampered_entry(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    pipeline = GovernedPipeline(audit_path=audit_path, hmac_key="test-key")
    result = _allow(pipeline)

    lines = audit_path.read_text(encoding="utf-8").splitlines()
    forged = json.loads(lines[-1])
    forged["details"] = "ALLOW: forged"
    lines[-1] = json.dumps(forged)
    audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    restarted = GovernedPipeline(audit_path=audit_path, hmac_key="test-key")
    assert not restarted.verify_evidence_for(
        result.evidence_id,
        action="file.read",
        params_hash=PARAMS_HASH,
        tenant_id="tenant-a",
        consume=False,
    )
    assert not restarted.verify_evidence(result.evidence_id, consume=False)


def test_new_evidence_records_canonical_hash_version(pipeline):
    result = _allow(pipeline)
    entry = pipeline.audit.find_by_id(result.evidence_id)

    assert entry is not None
    assert entry.metadata["params_hash"] == PARAMS_HASH
    assert entry.metadata["params_hash_version"] == "2"
    assert entry.metadata["params_hash_status"] == "ok"


def test_unhashable_params_denied_for_l2(tmp_path):
    policy = CommercialActionPolicy.from_path(POLICY_PATH)
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
            parameters={"effective_at": dt.datetime.now()},
        )
    )
    entry = pipeline.audit.find_by_id(result.evidence_id)

    assert result.verdict is Verdict.DENY
    assert result.matched_rule == "commercial_params:unhashable"
    assert entry is not None
    assert entry.metadata["params_hash"] == ""
    assert entry.metadata["params_hash_status"] == "unhashable"
    assert entry.metadata["params_hash_version"] == "2"


def test_unhashable_params_allowed_for_l0_but_not_verifiable(tmp_path):
    policy = CommercialActionPolicy.from_path(POLICY_PATH)
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
            parameters={"tags": {"a", "b"}},
        )
    )
    entry = pipeline.audit.find_by_id(result.evidence_id)

    assert result.verdict is Verdict.ALLOW
    assert entry is not None
    assert entry.metadata["params_hash_status"] == "unhashable"
    assert not pipeline.verify_evidence_for(
        result.evidence_id,
        action="catalog.read",
        params_hash="",
        tenant_id="tenant-a",
        consume=False,
    )


def test_legacy_params_hash_requires_explicit_opt_in(pipeline):
    legacy_hash = hashlib.sha256(
        json.dumps(
            PARAMS,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    entry = pipeline.audit.log(
        event_type="governance_decision",
        actor="agent-1",
        action="file.read",
        details="ALLOW: legacy",
        metadata={"tenant_id": "tenant-a", "params_hash": legacy_hash},
        tenant_id="tenant-a",
    )

    assert not pipeline.verify_evidence_for(
        entry.id,
        action="file.read",
        params_hash=legacy_hash,
        tenant_id="tenant-a",
        consume=False,
    )
    assert pipeline.verify_evidence_for(
        entry.id,
        action="file.read",
        params_hash=legacy_hash,
        tenant_id="tenant-a",
        params_hash_version="1",
        allow_legacy=True,
        consume=False,
    )
