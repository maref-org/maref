"""test_reputation — AgentReputationRegistry 信用分注册表测试

覆盖验收标准:
- 1.3-A5: 初始分 100,每次 CRITICAL -30,HIGH -10,低于 30 触发 quarantine
- 1.3-A6: Agent 信用分变更写入 UnifiedAuditStore,不可篡改
"""

from __future__ import annotations

from typing import Any

import pytest

from maref.sentinel.event import AttackType, ObservationEvent, Severity
from maref.sentinel.reputation import (
    CONSENT_DENIED_PENALTY,
    FORCE_QUARANTINE_THRESHOLD,
    INITIAL_SCORE,
    MAX_SCORE,
    MIN_SCORE,
    AgentReputationRegistry,
    ReputationChangeReason,
    ReputationRecord,
    compute_reputation_hash,
)

pytestmark = pytest.mark.asyncio

HMAC_KEY: bytes = b"test-reputation-hmac-key"


def _make_event(
    severity: Severity = Severity.CRITICAL,
    event_id: str = "evt-001",
    attack_type: AttackType = AttackType.PIXEL_TRACKING,
) -> ObservationEvent:
    """构造测试用 ObservationEvent"""
    return ObservationEvent(
        event_id=event_id,
        source="test_probe",
        severity=severity,
        subject="agent-test",
        attack_type=attack_type,
        evidence={"test": True},
    )


class TestReputationRecord:
    """ReputationRecord 数据类 + HMAC 测试"""

    def test_default_values(self) -> None:
        r = ReputationRecord(agent_id="a1")
        assert r.record_id  # UUID
        assert r.agent_id == "a1"
        assert r.delta == 0
        assert r.reason == ReputationChangeReason.MANUAL_ADJUST
        assert r.hmac_signature == ""

    def test_with_hash_returns_new_instance(self) -> None:
        r = ReputationRecord(agent_id="a1", old_score=100, new_score=70)
        signed = r.with_hash(HMAC_KEY)
        assert signed is not r
        assert signed.agent_id == "a1"
        assert signed.hmac_signature != ""

    def test_verify_valid_signature(self) -> None:
        r = ReputationRecord(
            agent_id="a1", old_score=100, new_score=70, delta=-30,
            reason=ReputationChangeReason.CRITICAL_ALERT,
        ).with_hash(HMAC_KEY)
        assert r.verify(HMAC_KEY) is True

    def test_verify_no_signature_returns_false(self) -> None:
        r = ReputationRecord(agent_id="a1")
        assert r.verify(HMAC_KEY) is False

    def test_verify_tampered_returns_false(self) -> None:
        """1.3-A6: 篡改导致 verify()=False"""
        r = ReputationRecord(
            agent_id="a1", old_score=100, new_score=70,
        ).with_hash(HMAC_KEY)
        from dataclasses import replace

        tampered = replace(r, new_score=100)  # 篡改 new_score
        assert tampered.verify(HMAC_KEY) is False

    def test_verify_tampered_delta_returns_false(self) -> None:
        r = ReputationRecord(
            agent_id="a1", old_score=100, new_score=70, delta=-30,
        ).with_hash(HMAC_KEY)
        from dataclasses import replace

        tampered = replace(r, delta=0)
        assert tampered.verify(HMAC_KEY) is False

    def test_compute_hash_deterministic(self) -> None:
        r1 = ReputationRecord(
            record_id="r-1", agent_id="a1", old_score=100, new_score=70,
            delta=-30, reason=ReputationChangeReason.CRITICAL_ALERT,
            changed_at=1000.0,
        )
        r2 = ReputationRecord(
            record_id="r-1", agent_id="a1", old_score=100, new_score=70,
            delta=-30, reason=ReputationChangeReason.CRITICAL_ALERT,
            changed_at=1000.0,
        )
        assert compute_reputation_hash(r1, HMAC_KEY) == compute_reputation_hash(r2, HMAC_KEY)


class TestRegistryRegister:
    """register() 注册测试"""

    def test_register_initial_score_100(self) -> None:
        """1.3-A5: 初始分 100"""
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        record = registry.register("agent-1")
        assert record.new_score == 100
        assert record.old_score == 0
        assert record.delta == 100
        assert record.reason == ReputationChangeReason.INITIAL_REGISTER
        assert registry.score("agent-1") == 100

    def test_register_custom_initial_score(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        record = registry.register("agent-1", initial_score=80)
        assert record.new_score == 80
        assert registry.score("agent-1") == 80

    def test_register_duplicate_raises(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")
        with pytest.raises(ValueError, match="already registered"):
            registry.register("agent-1")

    def test_register_records_history(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")
        history = registry.history("agent-1")
        assert len(history) == 1
        assert history[0].reason == ReputationChangeReason.INITIAL_REGISTER

    def test_register_initial_score_clamped(self) -> None:
        """初始分 clamp 到 [0, 100]"""
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        r1 = registry.register("agent-high", initial_score=200)
        assert r1.new_score == MAX_SCORE  # 100
        r2 = registry.register("agent-low", initial_score=-50)
        assert r2.new_score == MIN_SCORE  # 0

    def test_register_emits_audit(self) -> None:
        audits: list[Any] = []

        def audit_cb(r: Any) -> None:
            audits.append(r)

        registry = AgentReputationRegistry(
            hmac_key=HMAC_KEY, audit_callback=audit_cb
        )
        registry.register("agent-1")
        assert len(audits) == 1
        assert audits[0].reason == ReputationChangeReason.INITIAL_REGISTER


class TestRegistryApplyEvent:
    """apply_event() 扣分测试 — 覆盖 1.3-A5"""

    async def test_critical_alert_minus_30(self) -> None:
        """1.3-A5: CRITICAL 告警 -30"""
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")
        event = _make_event(severity=Severity.CRITICAL)
        record = await registry.apply_event(event, agent_id="agent-1")
        assert record.old_score == 100
        assert record.new_score == 70
        assert record.delta == -30
        assert record.reason == ReputationChangeReason.CRITICAL_ALERT
        assert registry.score("agent-1") == 70

    async def test_high_alert_minus_10(self) -> None:
        """1.3-A5: HIGH 告警 -10"""
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")
        event = _make_event(severity=Severity.HIGH)
        record = await registry.apply_event(event, agent_id="agent-1")
        assert record.new_score == 90
        assert record.delta == -10
        assert record.reason == ReputationChangeReason.HIGH_ALERT

    async def test_medium_alert_minus_5(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")
        event = _make_event(severity=Severity.MEDIUM)
        record = await registry.apply_event(event, agent_id="agent-1")
        assert record.new_score == 95
        assert record.delta == -5
        assert record.reason == ReputationChangeReason.MEDIUM_ALERT

    async def test_low_alert_minus_1(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")
        event = _make_event(severity=Severity.LOW)
        record = await registry.apply_event(event, agent_id="agent-1")
        assert record.new_score == 99
        assert record.delta == -1
        assert record.reason == ReputationChangeReason.LOW_ALERT

    async def test_apply_event_unknown_agent_raises(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        event = _make_event()
        with pytest.raises(KeyError, match="not registered"):
            await registry.apply_event(event, agent_id="ghost")

    async def test_score_clamped_at_min(self) -> None:
        """分数不会低于 0"""
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")
        # 4 次 CRITICAL = -120, 但 clamp 到 0
        for i in range(4):
            event = _make_event(
                severity=Severity.CRITICAL, event_id=f"evt-{i}"
            )
            await registry.apply_event(event, agent_id="agent-1")
        assert registry.score("agent-1") == MIN_SCORE

    async def test_apply_event_records_trigger_event_id(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")
        event = _make_event(severity=Severity.HIGH, event_id="evt-xyz")
        record = await registry.apply_event(event, agent_id="agent-1")
        assert record.trigger_event_id == "evt-xyz"

    async def test_apply_event_emits_audit(self) -> None:
        """1.3-A6: 信用分变更写入审计"""
        audits: list[Any] = []

        async def audit_cb(r: Any) -> None:
            audits.append(r)

        registry = AgentReputationRegistry(
            hmac_key=HMAC_KEY, audit_callback=audit_cb
        )
        registry.register("agent-1")
        event = _make_event(severity=Severity.CRITICAL)
        await registry.apply_event(event, agent_id="agent-1")
        # register (sync, fire-and-forget) + apply_event
        # 注意: register 的 audit 是 fire-and-forget,可能尚未执行
        # apply_event 的 audit 是 await
        assert any(r.reason == ReputationChangeReason.CRITICAL_ALERT for r in audits)


class TestRegistryQuarantineTrigger:
    """1.3-A5: 信用分 < 30 触发 quarantine"""

    async def test_critical_below_threshold_triggers_quarantine(self) -> None:
        """1.3-A5: 低于 30 触发 quarantine_callback"""
        quarantine_calls: list[tuple[str, str]] = []

        async def q_cb(agent_id: str, reason: str) -> None:
            quarantine_calls.append((agent_id, reason))

        registry = AgentReputationRegistry(
            hmac_key=HMAC_KEY, quarantine_callback=q_cb
        )
        registry.register("agent-1")  # 100 分
        # 3 次 CRITICAL = -90 → 100-90=10 < 30,触发 quarantine
        for i in range(3):
            event = _make_event(severity=Severity.CRITICAL, event_id=f"evt-{i}")
            await registry.apply_event(event, agent_id="agent-1")

        assert registry.score("agent-1") == 10
        assert registry.is_quarantined("agent-1") is True
        assert len(quarantine_calls) >= 1
        assert quarantine_calls[0][0] == "agent-1"

    async def test_high_only_does_not_trigger_until_below_threshold(self) -> None:
        """HIGH -10 需 7 次才低于 30 (100-70=30 不触发,100-80=20 触发)"""
        quarantine_calls: list[tuple[str, str]] = []

        def q_cb(agent_id: str, reason: str) -> None:
            quarantine_calls.append((agent_id, reason))

        registry = AgentReputationRegistry(
            hmac_key=HMAC_KEY, quarantine_callback=q_cb
        )
        registry.register("agent-1")
        # 7 次 HIGH = -70 → 30 (不触发, 30 不 < 30)
        for i in range(7):
            event = _make_event(severity=Severity.HIGH, event_id=f"evt-{i}")
            await registry.apply_event(event, agent_id="agent-1")
        assert registry.score("agent-1") == 30
        assert len(quarantine_calls) == 0
        # 第 8 次 → 20 < 30,触发
        event = _make_event(severity=Severity.HIGH, event_id="evt-8")
        await registry.apply_event(event, agent_id="agent-1")
        assert registry.score("agent-1") == 20
        assert len(quarantine_calls) == 1

    async def test_quarantine_callback_failure_does_not_block_scoring(self) -> None:
        """quarantine_callback 抛异常不影响信用分变更"""

        async def q_cb(agent_id: str, reason: str) -> None:
            raise RuntimeError("quarantine failed")

        registry = AgentReputationRegistry(
            hmac_key=HMAC_KEY, quarantine_callback=q_cb
        )
        registry.register("agent-1")
        for i in range(3):
            event = _make_event(severity=Severity.CRITICAL, event_id=f"evt-{i}")
            await registry.apply_event(event, agent_id="agent-1")
        # 即使 quarantine 失败,分数仍然扣了
        assert registry.score("agent-1") == 10

    async def test_no_quarantine_callback_still_works(self) -> None:
        """无 quarantine_callback 时分数仍正常扣减"""
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")
        for i in range(3):
            event = _make_event(severity=Severity.CRITICAL, event_id=f"evt-{i}")
            await registry.apply_event(event, agent_id="agent-1")
        assert registry.score("agent-1") == 10
        assert registry.is_quarantined("agent-1") is True


class TestRegistryConsentDenial:
    """apply_consent_denial() 测试"""

    async def test_consent_denial_minus_20(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")
        record = await registry.apply_consent_denial(
            agent_id="agent-1", operation="sentinel.mitmproxy.ca_install"
        )
        assert record.old_score == 100
        assert record.new_score == 80
        assert record.delta == CONSENT_DENIED_PENALTY  # -20
        assert record.reason == ReputationChangeReason.CONSENT_DENIED
        assert "sentinel.mitmproxy.ca_install" in record.trigger_event_id

    async def test_consent_denial_unknown_agent_raises(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        with pytest.raises(KeyError, match="not registered"):
            await registry.apply_consent_denial(
                agent_id="ghost", operation="op"
            )

    async def test_consent_denial_triggers_quarantine_when_below_threshold(self) -> None:
        """连续 consent 拒绝导致低于阈值"""
        quarantine_calls: list[str] = []

        def q_cb(agent_id: str, reason: str) -> None:
            quarantine_calls.append(agent_id)

        registry = AgentReputationRegistry(
            hmac_key=HMAC_KEY, quarantine_callback=q_cb
        )
        registry.register("agent-1")
        # 4 次 consent 拒绝 = -80 → 20 < 30,触发
        for i in range(4):
            await registry.apply_consent_denial("agent-1", f"op-{i}")
        assert registry.score("agent-1") == 20
        assert len(quarantine_calls) >= 1


class TestRegistryRecoveryBonus:
    """apply_recovery_bonus() 测试"""

    async def test_recovery_bonus_default_plus_5(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")
        # 先扣到 70
        event = _make_event(severity=Severity.CRITICAL)
        await registry.apply_event(event, agent_id="agent-1")
        assert registry.score("agent-1") == 70
        # 恢复 +5
        record = await registry.apply_recovery_bonus("agent-1")
        assert record.old_score == 70
        assert record.new_score == 75
        assert record.delta == 5
        assert record.reason == ReputationChangeReason.RECOVERY_BONUS

    async def test_recovery_bonus_clamped_at_max(self) -> None:
        """恢复不超过 100"""
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")  # 100
        record = await registry.apply_recovery_bonus("agent-1", bonus=50)
        assert record.new_score == MAX_SCORE  # 100, 不超

    async def test_recovery_bonus_custom_amount(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")
        event = _make_event(severity=Severity.CRITICAL)
        await registry.apply_event(event, agent_id="agent-1")  # 70
        record = await registry.apply_recovery_bonus("agent-1", bonus=15)
        assert record.new_score == 85


class TestRegistryManualAdjust:
    """manual_adjust() 测试"""

    async def test_manual_adjust_negative(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")
        record = await registry.manual_adjust("agent-1", delta=-25, note="investigation")
        assert record.old_score == 100
        assert record.new_score == 75
        assert record.delta == -25
        assert "manual:investigation" in record.trigger_event_id

    async def test_manual_adjust_positive(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1", initial_score=50)
        record = await registry.manual_adjust("agent-1", delta=30)
        assert record.new_score == 80


class TestRegistryReset:
    """reset() 测试"""

    async def test_reset_restores_initial_score(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")
        event = _make_event(severity=Severity.CRITICAL)
        await registry.apply_event(event, agent_id="agent-1")
        assert registry.score("agent-1") == 70
        record = await registry.reset("agent-1")
        assert record.new_score == INITIAL_SCORE  # 100
        assert record.reason == ReputationChangeReason.RESET
        assert registry.score("agent-1") == 100

    async def test_reset_clears_violation_stats(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")
        for i in range(3):
            event = _make_event(severity=Severity.HIGH, event_id=f"e-{i}")
            await registry.apply_event(event, agent_id="agent-1")
        snap = registry.snapshot()
        assert snap["agents"]["agent-1"]["total_violations"] == 3
        await registry.reset("agent-1")
        snap = registry.snapshot()
        assert snap["agents"]["agent-1"]["total_violations"] == 0


class TestRegistryHistory:
    """history() 测试"""

    async def test_history_records_all_changes(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")  # 1 条 (INITIAL)
        event = _make_event(severity=Severity.HIGH)
        await registry.apply_event(event, agent_id="agent-1")  # 2 条
        await registry.apply_recovery_bonus("agent-1")  # 3 条

        history = registry.history("agent-1")
        assert len(history) == 3
        assert history[0].reason == ReputationChangeReason.INITIAL_REGISTER
        assert history[1].reason == ReputationChangeReason.HIGH_ALERT
        assert history[2].reason == ReputationChangeReason.RECOVERY_BONUS

    async def test_history_unknown_agent_returns_empty(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        assert registry.history("ghost") == []

    async def test_history_records_hmac_signed(self) -> None:
        """1.3-A6: 历史记录不可篡改"""
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")
        event = _make_event(severity=Severity.CRITICAL)
        await registry.apply_event(event, agent_id="agent-1")
        for record in registry.history("agent-1"):
            assert record.verify(HMAC_KEY) is True


class TestRegistrySnapshot:
    """snapshot() 测试"""

    async def test_snapshot_structure(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")
        snap = registry.snapshot()
        assert snap["agent_count"] == 1
        assert snap["force_quarantine_threshold"] == FORCE_QUARANTINE_THRESHOLD
        assert snap["initial_score"] == INITIAL_SCORE
        assert "agent-1" in snap["agents"]
        assert snap["agents"]["agent-1"]["score"] == 100
        assert snap["agents"]["agent-1"]["is_quarantined"] is False

    async def test_snapshot_reflects_violations(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")
        for i in range(3):
            event = _make_event(severity=Severity.CRITICAL, event_id=f"e-{i}")
            await registry.apply_event(event, agent_id="agent-1")
        snap = registry.snapshot()
        assert snap["agents"]["agent-1"]["score"] == 10
        assert snap["agents"]["agent-1"]["is_quarantined"] is True
        assert snap["agents"]["agent-1"]["total_violations"] == 3


class TestRegistryThresholdChecks:
    """is_quarantined / is_warning 阈值测试"""

    async def test_is_quarantined_below_threshold(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1", initial_score=29)
        assert registry.is_quarantined("agent-1") is True

    async def test_is_quarantined_at_threshold(self) -> None:
        """分数 == 阈值 (30) 不算隔离 (需要 < 30)"""
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1", initial_score=30)
        assert registry.is_quarantined("agent-1") is False

    async def test_is_warning_between_thresholds(self) -> None:
        """分数在 [30, 60) 之间为告警区"""
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1", initial_score=45)
        assert registry.is_warning("agent-1") is True
        assert registry.is_quarantined("agent-1") is False

    async def test_is_warning_false_above_threshold(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1", initial_score=70)
        assert registry.is_warning("agent-1") is False

    async def test_is_quarantined_unknown_agent(self) -> None:
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        # 未注册 Agent score=0 < 30,所以 is_quarantined=True
        assert registry.is_quarantined("ghost") is True

    async def test_list_agents(self) -> None:
        """list_agents 返回所有已注册 Agent (sync 调用,async 测试以保持模块一致性)"""
        registry = AgentReputationRegistry(hmac_key=HMAC_KEY)
        registry.register("agent-1")
        registry.register("agent-2")
        agents = registry.list_agents()
        assert set(agents) == {"agent-1", "agent-2"}


class TestRegistryCustomThresholds:
    """自定义阈值测试"""

    async def test_custom_force_quarantine_threshold(self) -> None:
        registry = AgentReputationRegistry(
            hmac_key=HMAC_KEY, force_quarantine_threshold=50
        )
        registry.register("agent-1", initial_score=55)
        assert registry.is_quarantined("agent-1") is False
        # 扣 10 → 45 < 50,触发
        event = _make_event(severity=Severity.HIGH)
        await registry.apply_event(event, agent_id="agent-1")
        assert registry.is_quarantined("agent-1") is True

    async def test_custom_warning_threshold(self) -> None:
        registry = AgentReputationRegistry(
            hmac_key=HMAC_KEY, warning_threshold=80
        )
        registry.register("agent-1", initial_score=75)
        assert registry.is_warning("agent-1") is True


class TestRegistryAuditFailure:
    """audit_callback 失败不影响信用分变更"""

    async def test_audit_failure_does_not_block_scoring(self) -> None:
        async def audit_cb(r: Any) -> None:
            raise RuntimeError("audit log broken")

        registry = AgentReputationRegistry(
            hmac_key=HMAC_KEY, audit_callback=audit_cb
        )
        registry.register("agent-1")
        event = _make_event(severity=Severity.CRITICAL)
        record = await registry.apply_event(event, agent_id="agent-1")
        # 即使审计失败,分数仍然扣了
        assert record.new_score == 70
        assert registry.score("agent-1") == 70
