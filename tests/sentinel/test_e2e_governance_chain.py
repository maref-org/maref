"""test_e2e_governance_chain — M5-A6 全链路端到端延迟测试

验证从攻击输入到治理动作完成的端到端延迟 < 500ms。

链路:
  Attack Input → Probe Detection → ObservationEvent → ThreatAlert
  → ThreatGovernanceBridge → GovernanceStateMachine.force_halt
  → QuarantineProtocol.quarantine

每条链路测量 3 次,取 P95 延迟,断言 < 500ms。
"""

from __future__ import annotations

import time
from datetime import datetime

from maref.codegen.permissions import BashValidator
from maref.governance.state_machine import GovernanceState, GovernanceStateMachine
from maref.governance.threat_bridge import ThreatGovernanceBridge
from maref.monitoring.threat_intelligence import ThreatAlert, ThreatSeverity
from maref.sentinel.event import AttackType
from maref.sentinel.probes.base import ProbeConfig
from maref.sentinel.probes.network_egress_probe import NetworkEgressProbe
from maref.sentinel.quarantine import NoopStrategy, QuarantineProtocol, QuarantineReason

from scripts.redteam.attack_pixel_tracking import PixelTrackingAttack
from scripts.redteam.attack_steganography import SteganographyAttack
from scripts.redteam.attack_privilege_abuse import PrivilegeAbuseAttack

HMAC_KEY: bytes = b"test-e2e-latency-hmac-key-32bytes!!"
LATENCY_THRESHOLD_MS: float = 500.0


def _make_alert(alert_type: str, severity: ThreatSeverity) -> ThreatAlert:
    return ThreatAlert(
        alert_id=f"alert-{alert_type}-latency",
        alert_type=alert_type,
        severity=severity,
        title=f"{alert_type} latency test",
        description="E2E latency measurement",
        detected_at=datetime(2026, 7, 2, 12, 0, 0),
        affected_assets=["test-agent"],
        recommended_actions=[],
    )


async def _measure_pixel_tracking_chain(hmac_key: bytes) -> float:
    """测量攻击 ① 全链路延迟 (Probe → Alert → force_halt → quarantine)"""
    attack = PixelTrackingAttack(pid=30001)

    t0 = time.monotonic()

    # 1. Probe 检测
    probe = NetworkEgressProbe(
        config=ProbeConfig(hmac_key=hmac_key),
        declared_endpoints=("api.anthropic.com",),
    )
    await probe.start()
    await probe.submit_flow(attack.build_flow_record())
    events = await probe.poll()
    await probe.stop()
    assert len(events) >= 1

    # 2. ThreatAlert → Bridge → force_halt
    sm = GovernanceStateMachine()
    sm.transition(GovernanceState.OBSERVE, "latency test")
    bridge = ThreatGovernanceBridge(sm)
    alert = _make_alert("pixel_tracking", ThreatSeverity.CRITICAL)
    bridge.on_threat_alert(alert)
    assert sm.current_state == GovernanceState.HALT

    # 3. Quarantine
    proto = QuarantineProtocol(hmac_key=hmac_key, strategy=NoopStrategy())
    await proto.quarantine(
        pid=attack.pid,
        agent_id=attack.agent_id,
        reason=QuarantineReason.CRITICAL_ATTACK,
    )

    elapsed_ms = (time.monotonic() - t0) * 1000
    return elapsed_ms


async def _measure_steganography_chain(hmac_key: bytes) -> float:
    """测量攻击 ④ 全链路延迟"""
    attack = SteganographyAttack(pid=30002)

    t0 = time.monotonic()

    probe = NetworkEgressProbe(
        config=ProbeConfig(hmac_key=hmac_key),
        declared_endpoints=(attack.exfil_domain,),
    )
    await probe.start()
    await probe.submit_flow(attack.build_flow_record())
    events = await probe.poll()
    await probe.stop()
    assert any(e.attack_type == AttackType.STEGANOGRAPHY for e in events)

    sm = GovernanceStateMachine()
    sm.transition(GovernanceState.OBSERVE, "latency test")
    bridge = ThreatGovernanceBridge(sm)
    alert = _make_alert("steganography", ThreatSeverity.CRITICAL)
    bridge.on_threat_alert(alert)

    proto = QuarantineProtocol(hmac_key=hmac_key, strategy=NoopStrategy())
    await proto.quarantine(
        pid=attack.pid, agent_id=attack.agent_id,
        reason=QuarantineReason.CRITICAL_ATTACK,
    )

    return (time.monotonic() - t0) * 1000


async def _measure_privilege_abuse_chain(hmac_key: bytes) -> float:
    """测量攻击 ⑤ 全链路延迟"""
    attack = PrivilegeAbuseAttack(pid=30003)

    t0 = time.monotonic()

    validator = BashValidator()
    is_valid, _, _ = validator.validate(attack.build_bash_command())
    assert not is_valid

    sm = GovernanceStateMachine()
    sm.transition(GovernanceState.OBSERVE, "latency test")
    bridge = ThreatGovernanceBridge(sm)
    alert = _make_alert("privilege_abuse", ThreatSeverity.CRITICAL)
    bridge.on_threat_alert(alert)

    proto = QuarantineProtocol(hmac_key=hmac_key, strategy=NoopStrategy())
    await proto.quarantine(
        pid=attack.pid, agent_id=attack.agent_id,
        reason=QuarantineReason.CRITICAL_ATTACK,
    )

    return (time.monotonic() - t0) * 1000


class TestE2ELatency:
    """M5-A6: 全链路端到端延迟 < 500ms"""

    async def test_pixel_tracking_chain_latency(self) -> None:
        """攻击 ① 全链路延迟 < 500ms (3 次测量取最大值)"""
        latencies = []
        for _ in range(3):
            ms = await _measure_pixel_tracking_chain(HMAC_KEY)
            latencies.append(ms)
        # 3 样本不足以计算 P95,取 max 作为最严格约束
        worst = max(latencies)
        assert worst < LATENCY_THRESHOLD_MS, (
            f"攻击 ① 最大延迟 {worst:.1f}ms ≥ {LATENCY_THRESHOLD_MS}ms "
            f"(all: {[f'{m:.1f}' for m in latencies]})"
        )

    async def test_steganography_chain_latency(self) -> None:
        """攻击 ④ 全链路延迟 < 500ms (3 次测量取最大值)"""
        latencies = []
        for _ in range(3):
            ms = await _measure_steganography_chain(HMAC_KEY)
            latencies.append(ms)
        worst = max(latencies)
        assert worst < LATENCY_THRESHOLD_MS, (
            f"攻击 ④ 最大延迟 {worst:.1f}ms ≥ {LATENCY_THRESHOLD_MS}ms"
        )

    async def test_privilege_abuse_chain_latency(self) -> None:
        """攻击 ⑤ 全链路延迟 < 500ms (3 次测量取最大值)"""
        latencies = []
        for _ in range(3):
            ms = await _measure_privilege_abuse_chain(HMAC_KEY)
            latencies.append(ms)
        worst = max(latencies)
        assert worst < LATENCY_THRESHOLD_MS, (
            f"攻击 ⑤ 最大延迟 {worst:.1f}ms ≥ {LATENCY_THRESHOLD_MS}ms"
        )

    async def test_all_chains_under_threshold(self) -> None:
        """所有攻击链路平均延迟 < 500ms"""
        all_latencies: list[float] = []
        for _ in range(2):
            all_latencies.append(await _measure_pixel_tracking_chain(HMAC_KEY))
            all_latencies.append(await _measure_steganography_chain(HMAC_KEY))
            all_latencies.append(await _measure_privilege_abuse_chain(HMAC_KEY))

        avg = sum(all_latencies) / len(all_latencies)
        max_ms = max(all_latencies)
        assert max_ms < LATENCY_THRESHOLD_MS, (
            f"最大延迟 {max_ms:.1f}ms ≥ {LATENCY_THRESHOLD_MS}ms "
            f"(avg={avg:.1f}ms, all={[f'{m:.1f}' for m in all_latencies]})"
        )
