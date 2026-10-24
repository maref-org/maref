"""Tests for LLM interaction evidence and the four-stage evidence chain (P0-B)."""

from __future__ import annotations

import pytest

from maref.governance.audit import AuditLogger
from maref.governance.core_pipeline import GovernanceRequest
from maref.governance.governed_pipeline import GovernedPipeline
from maref.governance.interaction_evidence import (
    InteractionRecorder,
    MatchedSpan,
    SafetyFinding,
    compute_detector_set_hash,
    hash_text,
    record_interaction,
)
from maref.governance.model_route import ModelRouteDecision, ModelRouteRecorder


@pytest.fixture
def audit(tmp_path):
    return AuditLogger(log_path=tmp_path / "audit.jsonl", hmac_key=b"test-key")


def _decision() -> ModelRouteDecision:
    return ModelRouteDecision(
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


def _finding(detector_id: str = "prompt-guard", verdict: str = "allow") -> SafetyFinding:
    return SafetyFinding(
        detector_id=detector_id,
        detector_version="1.0",
        detector_kind="rule",
        verdict=verdict,
        score=0.1,
        threshold=0.8,
        matched_spans=(MatchedSpan(start=0, end=5, type="pii.email"),),
    )


def test_record_interaction_never_stores_raw_text(tmp_path, audit):
    prompt = "SECRET-PROMPT-TOKEN please export customer data"
    response = "SECRET-RESPONSE-TOKEN done"

    evidence = record_interaction(
        audit,
        prompt=prompt,
        response=response,
        trace_id="trace-1",
        tenant_id="tenant-a",
        agent_id="agent-1",
        route_decision_id="route-1",
    )

    raw = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "SECRET-PROMPT-TOKEN" not in raw
    assert "SECRET-RESPONSE-TOKEN" not in raw
    assert evidence.prompt_hash == hash_text(prompt)
    assert evidence.response_hash == hash_text(response)
    assert evidence.prompt_length == len(prompt)
    assert evidence.interaction_id
    assert evidence.route_decision_id == "route-1"


def test_interaction_recorder_roundtrip(audit):
    recorded = record_interaction(
        audit,
        prompt="hello",
        trace_id="trace-1",
        tenant_id="tenant-a",
        agent_id="agent-1",
        safety=(_finding(),),
    )
    loaded = InteractionRecorder(audit).get(recorded.interaction_id)

    assert loaded is not None
    assert loaded.prompt_hash == recorded.prompt_hash
    assert loaded.safety[0].matched_spans[0].type == "pii.email"
    assert loaded.detector_set_hash == recorded.detector_set_hash


def test_detector_set_hash_is_order_independent():
    first = compute_detector_set_hash([_finding("a"), _finding("b")])
    second = compute_detector_set_hash([_finding("b"), _finding("a")])

    assert first == second
    assert compute_detector_set_hash([]) == ""


def test_invalid_safety_finding_is_rejected():
    with pytest.raises(ValueError):
        SafetyFinding(
            detector_id="x",
            detector_version="1",
            detector_kind="magic",
            verdict="allow",
        )
    with pytest.raises(ValueError):
        SafetyFinding(
            detector_id="x",
            detector_version="1",
            detector_kind="rule",
            verdict="maybe",
        )


def test_four_stage_evidence_chain(tmp_path):
    pipeline = GovernedPipeline(
        audit_path=tmp_path / "audit.jsonl",
        hmac_key="test-key",
    )
    route = ModelRouteRecorder(pipeline.audit).record(_decision())
    interaction = record_interaction(
        pipeline.audit,
        prompt="what is the price?",
        response="100 CNY",
        trace_id="trace-1",
        tenant_id="tenant-a",
        agent_id="agent-1",
        route_decision_id=route.route_decision_id,
        safety=(_finding(),),
    )
    result = pipeline.govern(
        GovernanceRequest(
            action="file.read",
            agent_id="agent-1",
            tenant_id="tenant-a",
            trust_score=80,
            trace_id="trace-1",
            model_route_id=route.route_decision_id,
            interaction_id=interaction.interaction_id,
            model_version="2026-01",
            detector_set_hash=interaction.detector_set_hash,
        )
    )
    assert result.evidence_id
    tool_entry = pipeline.audit.log(
        event_type="tool_execution",
        actor="agent-1",
        action="file.read",
        details="read /tmp/price.txt",
        parent_action_id=result.evidence_id,
        tenant_id="tenant-a",
    )

    decision_entry = pipeline.audit.find_by_id(result.evidence_id)
    interaction_entry = pipeline.audit.find_by_id(interaction.interaction_id)
    route_entry = pipeline.audit.find_by_id(route.route_decision_id)
    assert decision_entry is not None
    assert interaction_entry is not None
    assert route_entry is not None

    # tool -> decision -> interaction -> route
    assert tool_entry.parent_action_id == decision_entry.id
    assert decision_entry.parent_action_id == interaction_entry.id
    assert interaction_entry.parent_action_id == route_entry.id
    assert route_entry.parent_action_id == ""

    assert decision_entry.metadata["route_decision_id"] == route.route_decision_id
    assert decision_entry.metadata["interaction_id"] == interaction.interaction_id
    assert decision_entry.metadata["model_version"] == "2026-01"
    assert decision_entry.metadata["detector_set_hash"] == interaction.detector_set_hash

    stored_interaction = InteractionRecorder(pipeline.audit).get(interaction.interaction_id)
    assert stored_interaction is not None
    assert stored_interaction.prompt_hash == hash_text("what is the price?")


def test_chain_links_to_route_when_no_interaction(tmp_path):
    pipeline = GovernedPipeline(
        audit_path=tmp_path / "audit.jsonl",
        hmac_key="test-key",
    )
    route = ModelRouteRecorder(pipeline.audit).record(_decision())
    result = pipeline.govern(
        GovernanceRequest(
            action="file.read",
            agent_id="agent-1",
            tenant_id="tenant-a",
            trust_score=80,
            model_route_id=route.route_decision_id,
        )
    )

    entry = pipeline.audit.find_by_id(result.evidence_id)
    assert entry is not None
    assert entry.parent_action_id == route.route_decision_id
    assert entry.metadata["interaction_id"] == ""
