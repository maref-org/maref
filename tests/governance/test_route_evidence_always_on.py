"""模型闸常开：无商业策略时 L2/L3 风险动作必须携带有效路由证据。"""

from __future__ import annotations

import json
from pathlib import Path

from maref.governance.commercial_policy import CommercialActionPolicy
from maref.governance.core_pipeline import GovernanceRequest, Verdict
from maref.governance.governed_pipeline import GovernedPipeline
from maref.governance.model_route import ModelRouteDecision
from maref.governance.trust_boundary import TrustBoundaryManager

POLICY_PATH = Path(__file__).resolve().parents[2] / "configs" / "commercial_actions.yaml"


def _pipeline(tmp_path, **overrides) -> GovernedPipeline:
    options = {
        "audit_path": tmp_path / "audit.jsonl",
        "hmac_key": "test-key",
        "boundary": TrustBoundaryManager(fail_closed=False),
    }
    options.update(overrides)
    return GovernedPipeline(**options)


def _record_route(pipeline: GovernedPipeline, **overrides):
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
        "route_reason": "risk tier requires reviewable route",
    }
    base.update(overrides)
    return pipeline.route_recorder.record(ModelRouteDecision(**base))


class TestRiskGate:
    def test_high_risk_action_denied_without_route(self, tmp_path):
        pipeline = _pipeline(tmp_path, enable_model_gate=True)
        result = pipeline.govern(
            GovernanceRequest(action="payment:transfer", agent_id="agent-a")
        )
        assert result.verdict is Verdict.DENY
        assert result.matched_rule == "model_gate:missing"

    def test_irreversible_action_denied_without_route(self, tmp_path):
        pipeline = _pipeline(tmp_path, enable_model_gate=True)
        result = pipeline.govern(
            GovernanceRequest(action="delete:account", agent_id="agent-a")
        )
        assert result.verdict is Verdict.DENY
        assert result.matched_rule == "model_gate:missing"

    def test_low_risk_action_not_gated(self, tmp_path):
        pipeline = _pipeline(tmp_path, enable_model_gate=True)
        result = pipeline.govern(
            GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=80)
        )
        assert result.verdict is Verdict.ALLOW

    def test_medium_risk_action_not_gated(self, tmp_path):
        pipeline = _pipeline(tmp_path, enable_model_gate=True)
        result = pipeline.govern(
            GovernanceRequest(action="file.write", agent_id="agent-a", trust_score=80)
        )
        # 角色权限可另行拒绝，但拒绝理由不得来自模型闸（MEDIUM 不在 L2/L3 范围）。
        assert result.matched_rule != "model_gate:missing"

    def test_unhashable_params_denied(self, tmp_path):
        pipeline = _pipeline(tmp_path, enable_model_gate=True)
        result = pipeline.govern(
            GovernanceRequest(
                action="payment:transfer",
                agent_id="agent-a",
                parameters={"tags": {"a", "b"}},
            )
        )
        assert result.verdict is Verdict.DENY
        assert result.matched_rule == "model_gate:unhashable"


class TestRouteBindings:
    def test_missing_model_version_denied(self, tmp_path):
        pipeline = _pipeline(tmp_path, enable_model_gate=True)
        recorded = _record_route(pipeline)

        result = pipeline.govern(
            GovernanceRequest(
                action="payment:transfer",
                agent_id="agent-a",
                tenant_id="tenant-a",
                model_route_id=recorded.route_decision_id,
            )
        )
        assert result.verdict is Verdict.DENY
        assert result.matched_rule == "model_gate:missing_model_version"

    def test_unknown_route_denied(self, tmp_path):
        pipeline = _pipeline(tmp_path, enable_model_gate=True)
        result = pipeline.govern(
            GovernanceRequest(
                action="payment:transfer",
                agent_id="agent-a",
                tenant_id="tenant-a",
                model_route_id="not-a-route",
                model_version="2026-01",
            )
        )
        assert result.verdict is Verdict.DENY
        assert result.matched_rule == "model_gate:invalid"

    def test_route_bound_to_other_agent_denied(self, tmp_path):
        pipeline = _pipeline(tmp_path, enable_model_gate=True)
        recorded = _record_route(pipeline, agent_id="agent-b")

        result = pipeline.govern(
            GovernanceRequest(
                action="payment:transfer",
                agent_id="agent-a",
                tenant_id="tenant-a",
                model_route_id=recorded.route_decision_id,
                model_version="2026-01",
            )
        )
        assert result.verdict is Verdict.DENY
        assert result.matched_rule == "model_gate:invalid"

    def test_valid_route_allows_and_is_auditable(self, tmp_path):
        pipeline = _pipeline(tmp_path, enable_model_gate=True)
        recorded = _record_route(pipeline)

        result = pipeline.govern(
            GovernanceRequest(
                action="payment:transfer",
                agent_id="agent-a",
                tenant_id="tenant-a",
                trust_score=80,
                model_route_id=recorded.route_decision_id,
                model_version="2026-01",
            )
        )
        assert result.verdict is Verdict.ALLOW

        events = [
            json.loads(line)
            for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        metadata = events[-1]["metadata"]
        assert metadata["model_id"] == "selected-model"
        assert metadata["model_version"] == "2026-01"
        assert metadata["route_reason"] == "risk tier requires reviewable route"
        assert metadata["advisory"] is True
        assert metadata["authority"] == "none"


class TestEnablement:
    def test_disabled_by_default(self, tmp_path):
        pipeline = _pipeline(tmp_path)
        assert pipeline.model_gate_enabled is False
        result = pipeline.govern(
            GovernanceRequest(action="payment:transfer", agent_id="agent-a")
        )
        assert result.matched_rule != "model_gate:missing"

    def test_env_enables_gate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAREF_MODEL_GATE", "1")
        pipeline = _pipeline(tmp_path)
        result = pipeline.govern(
            GovernanceRequest(action="payment:transfer", agent_id="agent-a")
        )
        assert pipeline.model_gate_enabled is True
        assert result.matched_rule == "model_gate:missing"

    def test_commercial_policy_path_unchanged(self, tmp_path):
        pipeline = _pipeline(
            tmp_path,
            enable_model_gate=True,
            commercial_action_policy=CommercialActionPolicy.from_path(POLICY_PATH),
        )
        result = pipeline.govern(
            GovernanceRequest(
                action="pricing.update", agent_id="agent-a", tenant_id="tenant-a"
            )
        )
        assert result.verdict is Verdict.DENY
        assert result.matched_rule == "commercial_route:missing"
