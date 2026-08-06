"""v0.52 P0-1 治理接线收口 — TrustBoundary 注入真实执行链路。

审计缺口 S1/S6（25-MAREF-治理三维度缺口审计报告-20260805）：
- GaaS GovernanceRouter 构造 GovernancePipeline 未传 boundary → 步骤 0 边界校验被跳过
- MCP 网关三层（SecurityGate→PolicyEngine→CircuitBreaker）无 TrustBoundary
- org_governance_router 未暴露 GovernedPipeline.govern() → 行为探针无事件源

本测试断言三条生产链路在默认装配下均执行边界门禁。
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from maref.federation.settlement import BillingEntry
from maref.gaas.governance_router import GovernanceRouter
from maref.gaas.models import GovernanceContext, GovernRequest
from maref.gaas.tenant import Tenant, TenantManager
from maref.governance.trust_boundary import TrustBoundaryManager
from maref.governance.verifier_registry import VerifierEntry, VerifierRegistry
from sidecar.mcp_gateway import MCPGateway


def _make_govern_request(action: str) -> GovernRequest:
    return GovernRequest(
        tenant_id="tenant-001",
        agent_id="agent-01",
        action=action,
        context=GovernanceContext(trust_score=50.0),
    )


def _make_router() -> GovernanceRouter:
    tm = TenantManager()
    tm.register(Tenant(tenant_id="tenant-001", name="Test Tenant"))
    return GovernanceRouter(tenant_manager=tm)


class TestGaaSGovernanceRouterBoundary:
    """GaaS 生产链路默认装配 TrustBoundaryManager，HIGH/IRREVERSIBLE fail-closed。"""

    def test_pipeline_has_boundary_by_default(self) -> None:
        router = _make_router()
        assert router._pipeline._boundary is not None

    def test_irreversible_action_denied(self) -> None:
        result = _make_router().govern(_make_govern_request("payment:transfer"))
        assert result.verdict.value == "DENY"
        assert "trust_boundary" in result.reason or "越界" in result.reason

    def test_high_risk_action_denied_without_scope(self) -> None:
        result = _make_router().govern(_make_govern_request("file.delete"))
        assert result.verdict.value == "DENY"

    def test_low_risk_action_allowed(self) -> None:
        result = _make_router().govern(_make_govern_request("file.read"))
        assert result.verdict.value == "ALLOW"

    def test_custom_boundary_propagated_to_pipeline(self) -> None:
        # P0-1 核心装配断言：传入 GovernanceRouter 的 boundary 必须
        # 原样注入 pipeline（同一实例），而非绕道替换私有字段。
        boundary = TrustBoundaryManager(fail_closed=False)
        router = GovernanceRouter(
            tenant_manager=_make_router()._tenants,
            boundary=boundary,
        )
        assert router._pipeline._boundary is boundary

    def test_high_risk_passes_when_boundary_injected(self) -> None:
        # 通过构造注入（非替换私有字段）的 fail_closed=False boundary，
        # HIGH 动作在无 scope 时放行 → 证明注入真实生效。
        boundary = TrustBoundaryManager(fail_closed=False)
        router = GovernanceRouter(
            tenant_manager=_make_router()._tenants,
            boundary=boundary,
        )
        result = router.govern(_make_govern_request("payment:transfer"))
        assert result.verdict.value != "DENY"


class TestMCPGatewayBoundary:
    """MCP 网关注入 TrustBoundary 后越界工具调用被阻断。"""

    def _gateway(self, boundary: TrustBoundaryManager | None = None) -> MCPGateway:
        gw = MCPGateway(boundary=boundary, secret_key=b"test-secret")
        captured: dict[str, Any] = {}

        def handler(name: str, args: dict[str, Any]) -> dict[str, Any]:
            captured["called"] = name
            return {"content": [{"type": "text", "text": "ok"}]}

        gw.register_backend(
            "file.",
            transport_type="in-process",
            handler=handler,
            tools=[{"name": "file.read"}],
        )
        gw.register_backend(
            "payment",
            transport_type="in-process",
            handler=handler,
            tools=[{"name": "payment:transfer"}],
        )
        gw._captured = captured
        return gw

    def test_boundary_defaults_to_enforced(self) -> None:
        gw = self._gateway()
        result = gw.route_tool_call("payment:transfer")
        assert result["isError"] is True
        assert "denied" in result["content"][0]["text"].lower() or "阻断" in result["content"][0]["text"]

    def test_low_risk_tool_passes_boundary(self) -> None:
        gw = self._gateway()
        result = gw.route_tool_call("file.read")
        assert result.get("isError", False) is False
        assert gw._captured["called"] == "file.read"

    def test_explicit_boundary_injected(self) -> None:
        boundary = TrustBoundaryManager(fail_closed=False)
        gw = self._gateway(boundary=boundary)
        # fail_closed=False 无 scope → 放行到 handler
        result = gw.route_tool_call("payment:transfer")
        assert result.get("isError", False) is False
        assert gw._captured["called"] == "payment:transfer"


class TestOrgGovernanceGovernEndpoint:
    """org_governance_router 暴露 govern 端点，激活行为探针事件源。"""

    @pytest.fixture()
    def client(self) -> Any:
        from sidecar.collector import MockAgentAdapter, ObservationCollector
        from sidecar.monitor import CompositeMonitor
        from sidecar.server import create_app

        app = create_app(
            collector=ObservationCollector(MockAgentAdapter()),
            monitor=CompositeMonitor(),
            allow_unauthenticated=True,
        )
        return TestClient(app)

    def test_govern_high_risk_denied(self, client: Any) -> None:
        resp = client.post(
            "/api/v1/federation/govern",
            json={"action": "payment:transfer", "agent_id": "agent-01"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["verdict"] == "DENY"

    def test_govern_low_risk_allowed(self, client: Any) -> None:
        resp = client.post(
            "/api/v1/federation/govern",
            json={"action": "file.read", "agent_id": "agent-01"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["verdict"] == "ALLOW"


class TestIrreversibleConsensusRequired:
    """P0-2: IRREVERSIBLE 动作授权放行后仍需人工确认/共识（非字符串标记）。"""

    def _boundary(self, max_risk: str, actions: list[str]) -> TrustBoundaryManager:
        from maref.identity.credential import AuthorizationScope

        scope = AuthorizationScope.issue(
            subject_did="agent-01",
            max_risk_level=max_risk,
            allowed_actions=actions,
        )
        return TrustBoundaryManager(scope=scope)

    def test_irreversible_allowed_marks_consensus_required(self) -> None:
        decision = self._boundary("IRREVERSIBLE", ["payment:transfer"]).check_no_raise(
            "payment:transfer", agent_id="agent-01"
        )
        assert decision.allowed is True
        assert decision.consensus_required is True

    def test_non_irreversible_no_consensus_required(self) -> None:
        decision = self._boundary("HIGH", ["file.write"]).check_no_raise(
            "file.write", agent_id="agent-01"
        )
        assert decision.allowed is True
        assert decision.consensus_required is False

    def test_pipeline_upgrades_irreversible_to_hitl(self) -> None:
        from maref.governance.core_pipeline import (
            GovernancePipeline,
            GovernanceRequest,
        )

        pipeline = GovernancePipeline(
            boundary=self._boundary("IRREVERSIBLE", ["payment:transfer"])
        )
        result = pipeline.govern(
            GovernanceRequest(action="payment:transfer", agent_id="agent-01")
        )
        assert result.verdict.value == "ASK_USER"
        assert result.matched_rule == "irreversible_hitl"
        assert result.hitl_event_id != ""
        assert "IRREVERSIBLE" in result.reason

    def test_non_irreversible_passes_pipeline(self) -> None:
        from maref.governance.core_pipeline import (
            GovernancePipeline,
            GovernanceRequest,
        )

        pipeline = GovernancePipeline(
            boundary=self._boundary("HIGH", ["file.read"])
        )
        result = pipeline.govern(
            GovernanceRequest(action="file.read", agent_id="agent-01")
        )
        assert result.verdict.value in ("ALLOW", "ASK_USER")
        assert result.matched_rule != "irreversible_hitl"


class TestFederationFactoryConsensusWiring:
    """P0-3 (F1/F2)：联邦工厂默认注入 VerifierConsensus + RuleJudge。

    审计前 create_default_federation 的 FederatedSettlement 未注入
    verifier_consensus → arbitrate_dispute 恒返回 None，联邦争议无真实仲裁。
    """

    def test_factory_wires_consensus_engine(self) -> None:
        from maref.federation import create_default_federation

        platform = create_default_federation(server_id="test-factory-01")
        assert platform.settlement._verifier_consensus is not None

    def test_factory_wires_default_judge(self) -> None:
        from maref.federation import create_default_federation

        platform = create_default_federation(server_id="test-factory-02")
        assert platform.settlement._verifier_consensus.has_judges is True

    def test_arbitrate_dispute_now_returns_verdict(self) -> None:
        from maref.federation import create_default_federation

        platform = create_default_federation(server_id="test-factory-03")
        settlement = platform.settlement
        proposal = settlement.generate_proposal(
            provider_org="org-a",
            consumer_org="org-b",
            period_start=0.0,
            period_end=1.0,
        )
        assert settlement.accept_proposal(proposal.proposal_id)
        assert settlement.dispute_proposal(
            proposal.proposal_id, reason="billing_discrepancy"
        )
        verdict = settlement.arbitrate_dispute(proposal.proposal_id)
        assert verdict is not None
        assert verdict["arbitrated"] is True
        assert "rule-judge" in {
            e["verifier"] for e in verdict.get("judge_evidence", [])
        }

    def test_arbitrate_dispute_uses_real_judge_path(self) -> None:
        from maref.federation import create_default_federation

        platform = create_default_federation(server_id="test-factory-04")
        settlement = platform.settlement
        # 争议轨迹含越权模式 → 规则法官应 BLOCK/FLAG（非空 evidence）。
        proposal = settlement.generate_proposal(
            provider_org="org-a",
            consumer_org="org-b",
            period_start=0.0,
            period_end=1.0,
        )
        proposal.entries.append(
            BillingEntry(
                entry_id="b1",
                provider_org="org-a",
                consumer_org="org-b",
                task_id="t1",
                agent_did="did:agent:org-a:001",
                amount=1.0,
                metric_id="escalation_privilege",
                timestamp=0.5,
            )
        )
        proposal.total_amount = 1.0
        assert settlement.accept_proposal(proposal.proposal_id)
        assert settlement.dispute_proposal(
            proposal.proposal_id, reason="privilege_escalation"
        )
        verdict = settlement.arbitrate_dispute(proposal.proposal_id)
        assert verdict is not None
        assert verdict["arbitrated"] is True
        assert verdict.get("judge_evidence")


class _PassProvider:
    """测试用 LLM 法官提供方：一律 PASS。"""

    def arbitrate(self, trace: Any, verdict_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"decision": "pass", "reasoning": "test pass", "confidence": 1.0}


class TestJudgeRecusal:
    """P0-4 (F2)：法官与被审 agent 同源时 recusal 回避，杜绝自审。"""

    def _consensus(self, affiliations: dict[str, str | None]) -> tuple[Any, VerifierRegistry]:
        from maref.governance.judge import ProviderJudge
        from maref.governance.verifier_consensus import VerifierConsensus

        registry = VerifierRegistry()
        judges: dict[str, Any] = {}
        for name, aff in affiliations.items():
            entry = VerifierEntry(
                name=name,
                model="test",
                methodology="test",
                accuracy=0.9,
            )
            registry.register(entry)
            judges[name] = ProviderJudge(
                _PassProvider(), name=f"judge-{name}", affiliation=aff
            )
        return VerifierConsensus(registry=registry, judges=judges), registry

    def _trace(self, agent_id: str = "agent-1") -> Any:
        from maref.governance.trace import Trace, TraceStep

        trace = Trace(trace_id="t1", agent_id=agent_id)
        trace.add_step(TraceStep(agent_id=agent_id, action="file.read", decision="allow"))
        return trace

    def test_same_source_org_equal(self) -> None:
        from maref.governance.verifier_consensus import _same_source

        assert _same_source("org:acme", "org:acme") is True
        assert _same_source("org:acme", "org:acme:agent-1") is True
        assert _same_source("org:acme", "org:other") is False

    def test_same_org_judge_recused(self) -> None:
        consensus, registry = self._consensus({"j1": "org:acme"})
        result = consensus.evaluate(
            self._trace("org:acme:agent-1"),
            subject_affiliation="org:acme:agent-1",
        )
        assert result.passed is False
        assert result.votes[0]["verdict"]["recused"] is True

    def test_different_org_judge_participates(self) -> None:
        consensus, registry = self._consensus({"j1": "org:other"})
        result = consensus.evaluate(
            self._trace("org:acme:agent-1"),
            subject_affiliation="org:acme:agent-1",
        )
        assert result.passed is True
        assert "recused" not in result.votes[0]["verdict"]

    def test_all_recused_fails_closed(self) -> None:
        consensus, registry = self._consensus({"j1": "org:acme", "j2": "org:acme"})
        result = consensus.evaluate(
            self._trace("org:acme:agent-1"),
            subject_affiliation="org:acme:agent-1",
        )
        assert result.passed is False
        assert len(result.votes) == 2
        assert all(v["verdict"]["recused"] for v in result.votes)

    def test_partial_recusal_does_not_skew_weight(self) -> None:
        consensus, registry = self._consensus(
            {"j1": "org:acme", "j2": "org:other"}
        )
        result = consensus.evaluate(
            self._trace("org:acme:agent-1"),
            subject_affiliation="org:acme:agent-1",
        )
        # 只有 j2 参与表决，j1 回避不计权。
        assert result.passed is True
        participating = [v for v in result.votes if "recused" not in v.get("verdict", {})]
        assert len(participating) == 1
        assert participating[0]["verifier"] == "j2"


class TestCrossOrgAccountabilityChain:
    """P0-5 (I1)：跨组织责任链三要素随请求携带。"""

    def test_a2a_client_uses_real_caller_did(self) -> None:
        from maref.integration.a2a_client import AGENT_ID, A2AClient

        default_client = A2AClient()
        assert default_client._headers()["X-A2A-Agent-Id"] == AGENT_ID
        did_client = A2AClient(agent_id="did:agent:org-b:001")
        assert did_client._headers()["X-A2A-Agent-Id"] == "did:agent:org-b:001"

    def test_a2a_bridge_sends_caller_did_and_scope(self) -> None:
        from maref.governance.audit import AuditLogger
        from maref.governance.state_machine import GovernanceStateMachine
        from maref.governance.types import GovernanceState
        from maref.identity.credential import AuthorizationScope
        from maref.integration.a2a_bridge import A2ABridge
        from maref.integration.a2a_types import A2ATaskContext, A2ATaskState

        scope = AuthorizationScope(
            subject_did="did:agent:org-b:001",
            max_risk_level="HIGH",
            allowed_actions=["file:read", "file:write"],
            jurisdiction="org-b",
            issuer="did:org:b:issuer",
        )
        sm = GovernanceStateMachine()
        audit = AuditLogger()
        bridge = A2ABridge(
            state_machine=sm,
            audit_logger=audit,
            agent_name="org-b-agent",
            agent_did="did:agent:org-b:001",
            authorization_scope=scope,
        )
        task = A2ATaskContext(
            task_id="t-1",
            description="delegate me",
            a2a_state=A2ATaskState.SUBMITTED,
            maref_state=GovernanceState.ACT,
            context={"skills": ["maref-delegate"]},
            created_at=0.0,
            updated_at=0.0,
        )
        # 直接调用真实实现 _delegation_metadata，断言 scope 序列化。
        metadata = bridge._delegation_metadata(task.context)
        assert metadata["authorization_scope"]["subject_did"] == (
            "did:agent:org-b:001"
        )
        assert metadata["authorization_scope"]["max_risk_level"] == "HIGH"
        assert metadata["authorization_scope"]["allowed_actions"] == [
            "file:read",
            "file:write",
        ]
        assert metadata["skills"] == ["maref-delegate"]

    def test_delegate_task_carries_real_did_and_scope(self) -> None:
        import asyncio
        from unittest import mock

        from maref.governance.audit import AuditLogger
        from maref.governance.state_machine import GovernanceStateMachine
        from maref.governance.types import GovernanceState
        from maref.identity.credential import AuthorizationScope
        from maref.integration import a2a_bridge as a2a_bridge_mod
        from maref.integration.a2a_bridge import A2ABridge
        from maref.integration.a2a_types import A2ATaskContext, A2ATaskState

        scope = AuthorizationScope(
            subject_did="did:agent:org-b:001",
            max_risk_level="HIGH",
            allowed_actions=["file:read"],
            jurisdiction="org-b",
            issuer="did:org:b:issuer",
        )
        sm = GovernanceStateMachine()
        audit = AuditLogger()
        bridge = A2ABridge(
            state_machine=sm,
            audit_logger=audit,
            agent_name="org-b-agent",
            agent_did="did:agent:org-b:001",
            authorization_scope=scope,
        )
        task = A2ATaskContext(
            task_id="t-1",
            description="delegate me",
            a2a_state=A2ATaskState.SUBMITTED,
            maref_state=GovernanceState.ACT,
            context={"skills": ["maref-delegate"]},
            created_at=0.0,
            updated_at=0.0,
        )
        bridge._tasks["t-1"] = task
        bridge._last_action_ids["t-1"] = ""

        captured: dict[str, Any] = {}

        class _FakeClient:
            def __init__(self, signing_key: Any = None, agent_id: str | None = None) -> None:
                captured["agent_id"] = agent_id

            async def send_task(self, **kwargs: Any) -> None:
                captured["send_kwargs"] = kwargs

        class _FakeLoop:
            def is_running(self) -> bool:
                return True

            def create_task(self, coro: Any) -> None:
                asyncio.run(coro)

        with mock.patch.object(
            a2a_bridge_mod, "A2AClient", _FakeClient
        ), mock.patch.object(
            a2a_bridge_mod.asyncio, "get_event_loop", return_value=_FakeLoop()
        ):
            assert bridge.delegate_task("t-1", "https://peer.example.com") is True

        # 责任链三要素：header 用真实 caller DID + scope 序列化进 metadata。
        assert captured["agent_id"] == "did:agent:org-b:001"
        send_kwargs = captured["send_kwargs"]
        assert send_kwargs["agent_url"] == "https://peer.example.com"
        assert send_kwargs["metadata"]["authorization_scope"]["subject_did"] == (
            "did:agent:org-b:001"
        )
        assert send_kwargs["metadata"]["authorization_scope"]["max_risk_level"] == "HIGH"

    def test_envelope_carries_chain_id(self) -> None:
        from maref.integration.mcp_envelope import (
            make_envelope,
            validate_envelope,
        )

        env = make_envelope(source_agent="agent-a", chain_id="chain-1")
        assert env["chain_id"] == "chain-1"
        ok, _ = validate_envelope(env)
        assert ok

    def test_envelope_inject_keeps_chain_id(self) -> None:
        from maref.integration.mcp_envelope import inject_envelope

        injected = inject_envelope(
            {"trace_id": "missing-chain"},
            source_agent="agent-a",
            chain_id="chain-9",
        )
        assert injected["chain_id"] == "chain-9"

    def test_envelope_chain_id_missing_degraded_not_rejected(self) -> None:
        from maref.integration.mcp_envelope import make_envelope, validate_envelope

        env = make_envelope(source_agent="agent-a")
        env.pop("chain_id", None)
        ok, msg = validate_envelope(env)
        assert ok is True
        assert "chain_id" in msg
