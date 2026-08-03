"""v0.44.0 端到端闭环验收：三个治理维度闭环串联。

验证 v0.44.0-M1/M2/M3 交付的能力点形成可验证闭环：

1. 单 Agent 闭环：TrustBoundary 拦截越界动作 → 审计链事件 →
   RuntimeBehaviorProbe 检测行为异常 → 信任评分下降 → 熔断器降级
2. 身份闭环：AgentIdentityService 签发凭证 → 撤销 DID →
   凭证联动吊销 → AgentDNS 能力目录失效 → 聚合 resolve 反映非 active
3. 联邦闭环：settlement 争议 → VerifierConsensus 加权表决 →
   可溯源 verdict 写审计链 → 恢复结算
"""

from __future__ import annotations

import time
from typing import Any

from maref.federation.metering import TaskMeteringEngine
from maref.federation.settlement import FederatedSettlement, SettlementStatus
from maref.governance.audit_bus import AuditBus
from maref.governance.circuit_breaker import BreakerState, CircuitBreaker
from maref.governance.trust_boundary import TrustBoundaryManager
from maref.governance.verifier_consensus import VerifierConsensus
from maref.governance.verifier_registry import VerifierEntry, VerifierRegistry
from maref.identity.agent_dns import AgentDNS
from maref.identity.agent_identity_service import AgentIdentityService
from maref.identity.did_registry import AgentDID, DIDRegistry
from maref.recursive.trust_engine_v2 import TrustEngineV2


def _verifier_consensus() -> VerifierConsensus:
    reg = VerifierRegistry()
    for i in range(2):
        reg.register(VerifierEntry(name=f"judge-h{i}", model="m", methodology="x", accuracy=0.9))
    reg.register(VerifierEntry(name="judge-l", model="m", methodology="x", accuracy=0.1))
    return VerifierConsensus(reg)


class TestSingleAgentClosure:
    """单 Agent：边界拦截 → 审计 → 行为反馈 → 信任下降 → 降级。"""

    def test_full_closure(self) -> None:
        bus = AuditBus()
        trust = TrustEngineV2()
        cb = CircuitBreaker()
        boundary = TrustBoundaryManager(audit_logger=bus)
        trust.register_agent("agent-1")

        # 1. TrustBoundary 拦截越界动作（HIGH 无 scope）→ 审计事件
        try:
            boundary.check("deploy:app", agent_id="agent-1")
        except Exception as exc:
            assert exc.http_status == 403

        # 2. RuntimeBehaviorProbe 订阅审计，检测行为异常 → 反馈信任 → 降级
        from maref.agent.behavior_analyzer import RuntimeBehaviorProbe

        probe = RuntimeBehaviorProbe(bus, trust, circuit_breaker=cb, window_size=6)
        probe.start()

        # 模拟异常行为：决策加速（前慢后快）
        for d in [1000, 1000, 1000, 100, 100, 100]:
            bus.log(
                event_type="agent_action.exec",
                actor="agent-1",
                action="decide",
                metadata={"duration_ms": d},
            )

        profile = trust._profiles["agent-1"]
        assert profile.behavioral_consistency < 0.7  # 信任被扣减
        assert probe.anomaly_counts().get("agent-1", 0) >= 1
        assert cb.state == BreakerState.OPEN  # critical → 降级
        assert "behavior_anomaly:acceleration" in cb.get_stats()["last_trip"]


class TestIdentityClosure:
    """身份：签发 → 撤销 → 凭证联动吊销 → DNS 失效 → 聚合反映。"""

    def test_full_closure(self) -> None:
        registry = DIDRegistry()
        dns = AgentDNS(did_registry=registry)
        service = AgentIdentityService(did_registry=registry, agent_dns=dns)

        from maref.governance.state_machine import GovernanceStateMachine
        from maref.signing.signing_key import ReportSigningKey

        did = AgentDID.generate()
        registry.register(did, GovernanceStateMachine())
        dns.register(did, name="worker", description="w", endpoints=["https://w/a2a"])
        key = ReportSigningKey.generate()

        # 签发凭证
        cred = service.issue(
            subject_did=did.did_string,
            scope=["state_machine", "audit"],
            signing_key=key,
        )
        assert service.verify(cred)["valid"] is True

        # 撤销 DID → 凭证联动吊销 + DNS 失效
        result = service.revoke(did.did_string, reason="compromised", signer="admin")
        assert result["revoked"] is True
        assert service.verify(cred)["valid"] is False
        assert service.verify(cred)["revoked"] is True
        assert service.resolve_agent_card(did.did_string) is None

        # 聚合 resolve 反映非 active
        agg = service.resolve(did.did_string)
        assert agg is not None
        assert agg["status"] == "revoked"
        assert agg["agent_card"] is None


class TestFederationClosure:
    """联邦：争议 → 加权法官表决 → 可溯源 verdict → 恢复结算。"""

    def test_full_closure(self) -> None:
        class FakeAudit:
            def __init__(self) -> None:
                self.events: list[dict] = []

            def log(self, **kwargs: Any) -> None:
                self.events.append(kwargs)

        audit = FakeAudit()
        settlement = FederatedSettlement(
            metering=TaskMeteringEngine(),
            verifier_consensus=_verifier_consensus(),
            audit_logger=audit,
        )
        engine = settlement._metering
        engine.record(
            task_id="t1", agent_did="did:1", agent_aic="aic:did:1",
            provider_org="OrgA", consumer_org="OrgB",
            duration_ms=1000.0, token_count=100, success=True, complexity_score=0.5,
        )
        settlement.generate_billing_from_metering()
        now = time.time()
        proposal = settlement.generate_proposal("OrgA", "OrgB", now - 60, now + 60)
        assert settlement.dispute_proposal(proposal.proposal_id, reason="overcharged")

        # 仲裁：加权法官表决通过 → 恢复 ACCEPTED
        verdict = settlement.arbitrate_dispute(proposal.proposal_id)
        assert verdict is not None
        assert verdict["passed"] is True
        assert len(verdict["votes"]) == 3
        assert settlement.get_proposal(proposal.proposal_id).status == SettlementStatus.ACCEPTED

        # 可溯源 verdict 写审计链
        assert any(e["event_type"] == "settlement.arbitration" for e in audit.events)

        # 恢复结算
        assert settlement.settle_proposal(proposal.proposal_id) is True
        assert settlement.get_proposal(proposal.proposal_id).status == SettlementStatus.SETTLED
