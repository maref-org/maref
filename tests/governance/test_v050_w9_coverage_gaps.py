"""
v0.50 W9-S1 — 治理核心模块覆盖缺口补测

针对覆盖率审计标注的低覆盖分支补测（三大域）：
- TrustBoundary: ``_subjects_match`` 斜杠形式；issuer 公钥表外跳过验签边界；
  ``log`` 接口审计 logger 抛异常不击穿
- TaskPreflight RiskAuthorizationCheck: 无 action 跳过；ENFORCE 辖区 fail-closed；
  RegulatoryPolicyMapper 抛异常降级
- RuntimeBehaviorProbe: 事件适配异常不击穿链路；熔断已 OPEN 时不重复触发
"""

from __future__ import annotations

from typing import Any

import pytest

from maref.governance.trust_boundary import TrustBoundaryManager
from maref.identity.credential import AuthorizationScope
from maref.signing.signing_key import ReportSigningKey


def _scope(subject_did: str, **kwargs: object) -> AuthorizationScope:
    fields: dict[str, object] = {
        "max_risk_level": "HIGH",
        "allowed_actions": ["file.delete"],
    }
    fields.update(kwargs)
    return AuthorizationScope(subject_did=subject_did, **fields)


class TestTrustBoundarySlashSubject:
    def test_slash_separated_subject_matches(self) -> None:
        scope = _scope("did:maref/agent-01")
        boundary = TrustBoundaryManager(scope=scope)
        decision = boundary.check_no_raise("file.delete", agent_id="agent-01")
        assert decision.allowed is True

    def test_slash_separated_other_agent_rejected(self) -> None:
        scope = _scope("did:maref/agent-01")
        boundary = TrustBoundaryManager(scope=scope)
        decision = boundary.check_no_raise("file.delete", agent_id="agent-02")
        assert decision.allowed is False


class TestTrustBoundaryIssuerOutsideKeyTable:
    def test_scope_issuer_not_in_key_table_passes_verification_skip(self) -> None:
        """issuer 不在公钥表内时跳过验签（fail-open 边界）。

        用伪造签名证明确实跳过验签：若实现误走验签分支，会因签名无效
        而拒绝；放行即证明 skip 语义生效。
        """
        forged = ReportSigningKey.generate()
        scope = _scope("agent-A", issuer="did:maref:issuer:alpha")
        scope.sign(forged)
        boundary = TrustBoundaryManager(scope=scope, issuer_public_keys={})
        decision = boundary.check_no_raise("file.delete", agent_id="agent-A")
        assert decision.allowed is True

    def test_forged_issuer_in_key_table_rejected(self) -> None:
        """issuer 在公钥表内但签名伪造 → 拒绝（防伪仍生效）。"""
        real = ReportSigningKey.generate()
        forged = ReportSigningKey.generate()
        scope = _scope("agent-A", issuer="did:maref:issuer:alpha")
        scope.sign(forged)
        boundary = TrustBoundaryManager(
            scope=scope,
            issuer_public_keys={"did:maref:issuer:alpha": real.public_key_pem},
        )
        decision = boundary.check_no_raise("file.delete", agent_id="agent-A")
        assert decision.allowed is False
        assert "签名" in decision.reason


class TestTrustBoundaryAuditLogInterfaceFailure:
    def test_log_interface_exception_does_not_break_check(self) -> None:
        class ExplodingLogAudit:
            # 只有 log 接口（无 append），强制 _record_audit 走 log 分支。
            def log(self, **kwargs: Any) -> None:
                raise RuntimeError("log failed")

        scope = _scope("agent-A")
        boundary = TrustBoundaryManager(scope=scope, audit_logger=ExplodingLogAudit())
        decision = boundary.check_no_raise("file.delete", agent_id="agent-A")
        assert decision.allowed is True


class TestRiskAuthorizationNoAction:
    def test_no_action_passes_skip(self) -> None:
        from maref.governance.task_preflight import RiskAuthorizationCheck

        check = RiskAuthorizationCheck()
        result = check.execute({"agent_id": "a1"})
        assert result.status.value == "PASS"
        assert result.evidence == ""


class TestRiskAuthorizationEnforce:
    def test_enforce_jurisdiction_without_scope_fails(self) -> None:
        from maref.governance.task_preflight import RiskAuthorizationCheck

        check = RiskAuthorizationCheck()
        result = check.execute(
            {
                "agent_id": "a1",
                "action": "data_cross_border_transfer",
                "jurisdiction": "cn",
                "risk_metadata": {"data_type": "pii"},
            }
        )
        assert result.status.value == "FAIL"
        assert result.details.get("action_required") == "HITL"
        assert result.details.get("enforce_blocked") is True

    def test_mapper_exception_degrades_and_check_still_returns(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from maref.compliance.regulatory_policy_mapper import RegulatoryPolicyMapper
        from maref.governance.task_preflight import RiskAuthorizationCheck

        def _boom(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("mapper down")

        monkeypatch.setattr(RegulatoryPolicyMapper, "map_action", _boom)
        check = RiskAuthorizationCheck()
        result = check.execute(
            {
                "agent_id": "a1",
                "action": "file.read",
                "jurisdiction": "cn",
                "risk_metadata": {},
            }
        )
        # mapper 异常降级 enforce_blocked=False（不进入 ENFORCE FAIL 分支），
        # 检查仍返回结果不抛错。
        assert result.status.value in ("PASS", "FAIL")
        assert result.details.get("enforce_blocked") is None


class TestBehaviorProbeResilience:
    def test_event_adapter_exception_does_not_break_stream(self) -> None:
        from maref.agent.behavior_analyzer import RuntimeBehaviorProbe
        from maref.governance.audit_bus import AuditBus
        from maref.governance.circuit_breaker import CircuitBreaker
        from maref.recursive.trust_engine_v2 import TrustEngineV2

        bus = AuditBus()
        probe = RuntimeBehaviorProbe(bus, TrustEngineV2(), CircuitBreaker())
        probe.start()
        entry = bus.log(
            event_type="agent_action.exec",
            actor="agent-1",
            action="decide",
            details="normal",
            metadata={"duration_ms": 5},
        )
        object.__setattr__(entry, "timestamp", "not-a-float")
        probe._on_event(entry)
        good = bus.log(
            event_type="agent_action.exec",
            actor="agent-1",
            action="decide",
            details="normal",
            metadata={"duration_ms": 5},
        )
        probe._on_event(good)
        probe.stop()

    def test_circuit_breaker_already_open_not_reforced(self) -> None:
        from maref.agent.behavior_analyzer import Anomaly, RuntimeBehaviorProbe
        from maref.governance.audit_bus import AuditBus
        from maref.governance.circuit_breaker import BreakerState, CircuitBreaker
        from maref.recursive.trust_engine_v2 import TrustEngineV2

        cb = CircuitBreaker()
        cb.force_open("test")
        baseline_trips = cb.get_stats()["trip_count"]
        probe = RuntimeBehaviorProbe(AuditBus(), TrustEngineV2(), cb)
        probe.start()
        anomaly = Anomaly(
            anomaly_type="acceleration",
            severity="critical",
            agent_id="agent-1",
            description="d",
        )
        for _ in range(7):
            probe._apply_anomaly(anomaly)
        assert cb.state == BreakerState.OPEN
        # 熔断已 OPEN 时 _apply_anomaly 不得重复触发 force_open（trip 不增长）。
        assert cb.get_stats()["trip_count"] == baseline_trips
        probe.stop()
