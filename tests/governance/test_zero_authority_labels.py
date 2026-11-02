"""零权威标注：模型路由、法官裁决与多模型共识都只是建议。"""

from __future__ import annotations

import pytest

from maref.crypto.ed25519_keys import Ed25519KeyPair
from maref.governance.audit import AuditLogger
from maref.governance.core_pipeline import GovernanceRequest, Verdict
from maref.governance.governed_pipeline import GovernedPipeline
from maref.governance.judge import RuleJudge
from maref.governance.model_route import (
    ModelRouteDecision,
    ModelRouteRecorder,
    attest_external_route,
    canonical_bytes,
)
from maref.governance.trace import Trace, TraceStep
from maref.governance.trust_boundary import TrustBoundaryManager
from maref.governance.verifier_consensus import (
    ConsensusStrategy,
    VerifierConsensus,
)
from maref.governance.verifier_registry import VerifierEntry, VerifierRegistry


def _decision(**overrides) -> ModelRouteDecision:
    base = {
        "trace_id": "trace-1",
        "tenant_id": "tenant-a",
        "agent_id": "agent-a",
        "requested_model": "requested-model",
        "selected_model": "selected-model",
        "provider": "provider-a",
        "model_version": "2026-01",
        "route_policy_id": "route-policy-v1",
        "route_policy_hash": "policy-hash",
        "route_reason": "cost band",
    }
    base.update(overrides)
    return ModelRouteDecision(**base)


def _trace() -> Trace:
    return Trace(
        trace_id="trace-1",
        agent_id="agent-a",
        steps=[TraceStep(agent_id="agent-a", action="file.read", decision="allowed")],
    )


class TestRouteLabels:
    def test_payload_marks_route_as_advisory(self):
        payload = _decision().to_payload()
        assert payload["advisory"] is True
        assert payload["authority"] == "none"
        assert payload["model_id"] == "selected-model"
        assert payload["model_version"] == "2026-01"
        assert payload["route_reason"] == "cost band"

    def test_external_router_cannot_claim_authority(self):
        pair = Ed25519KeyPair.generate()
        payload = _decision().to_payload()
        payload["advisory"] = False
        payload["authority"] = "policy"
        signature = pair.sign(canonical_bytes(payload))

        decision = attest_external_route(payload, signature, pair.public_key_pem)

        assert decision.advisory is True
        assert decision.authority == "none"

    def test_recorded_route_is_marked_advisory(self, tmp_path):
        audit = AuditLogger(log_path=tmp_path / "audit.jsonl", hmac_key=b"test-key")
        recorded = ModelRouteRecorder(audit).record(_decision())

        entry = audit.find_by_id(recorded.route_decision_id)
        assert entry is not None
        assert entry.metadata["advisory"] is True
        assert entry.metadata["authority"] == "none"


class TestJudgeLabels:
    def test_judge_verdict_is_advisory(self):
        verdict = RuleJudge().arbitrate(_trace())

        assert verdict.advisory is True
        assert verdict.authority == "none"
        assert verdict.to_dict()["advisory"] is True
        assert verdict.to_dict()["authority"] == "none"

    def test_judge_authority_cannot_be_reassigned(self):
        verdict = RuleJudge().arbitrate(_trace())
        with pytest.raises(AttributeError):
            verdict.authority = "policy"


class TestConsensusLabels:
    def _consensus(self) -> VerifierConsensus:
        registry = VerifierRegistry()
        registry.register(
            VerifierEntry(name="judge", model="rule-based", methodology="pattern-match")
        )
        return VerifierConsensus(registry, judges={"judge": RuleJudge()})

    def test_consensus_record_is_compressor_consensus(self):
        result = self._consensus().evaluate(_trace(), strategy=ConsensusStrategy.UNANIMITY)

        assert result.passed is True
        payload = result.to_dict()
        assert payload["consensus_type"] == "compressor_consensus"
        assert payload["is_safety_signal"] is False
        assert payload["advisory"] is True
        assert payload["authority"] == "none"

    def test_unanimous_consensus_cannot_authorize_pipeline(self, tmp_path):
        class _Tripwire:
            def __getattr__(self, name):
                raise AssertionError(f"consensus must not be consulted: {name}")

        pipeline = GovernedPipeline(
            audit_path=tmp_path / "audit.jsonl",
            hmac_key="test-key",
            boundary=TrustBoundaryManager(fail_closed=False),
            enable_model_gate=True,
            consensus=_Tripwire(),
        )
        result = pipeline.govern(
            GovernanceRequest(
                action="payment:transfer",
                agent_id="agent-a",
                tenant_id="tenant-a",
                trust_score=80,
            )
        )

        assert result.verdict is Verdict.DENY
        assert result.matched_rule == "model_gate:missing"
